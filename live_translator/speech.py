"""Konuşmayı metne, metni hedef dile çevirir.

Tanıma: Google Web Speech; faster-whisper kuruluysa yerel Whisper da seçilebiliyor
ve Google sınırladığında yedek oluyor. Çeviri: Google (deep-translator), o
sınırladığında MyMemory."""
from __future__ import annotations

import html
import threading
from typing import Optional

import requests
import speech_recognition as sr
from deep_translator import GoogleTranslator
from deep_translator import exceptions as dt_errors

from .capture import AudioSegment
from .providers import Provider, call_first_available
from .whisper_stt import WhisperLoadError, WhisperRecognizer, whisper_available


def _is_transient_stt(exc: Exception) -> bool:
    return isinstance(exc, (sr.RequestError, OSError, WhisperLoadError))


class SpeechToTextService:
    def __init__(self, whisper: Optional[WhisperRecognizer] = None) -> None:
        self._recognizer = sr.Recognizer()
        self._recognizer.operation_timeout = 12  # ağ takılırsa sonsuza kadar beklemesin
        # SpeechRecognition sürümleri arasında metodun adı değişmiş
        self._call = getattr(self._recognizer, "recognize_google", None) \
            or getattr(self._recognizer, "recognize_legacy", None)
        if self._call is None:  # pragma: no cover
            raise RuntimeError("SpeechRecognition sürümünde Google tanıyıcı bulunamadı.")

        if whisper is None and whisper_available():
            whisper = WhisperRecognizer()
        self.whisper = whisper
        self._google = Provider("Google", self._google_transcribe)
        self._local = Provider("Whisper", self._whisper_transcribe) if whisper else None

    def transcribe(self, segment: AudioSegment, language: str, engine: str = "google") -> str:
        """Anlaşılamayan ses için boş string döner. Hiçbir motor sonuç
        veremezse ServiceUnavailable fırlatır."""
        if engine == "whisper" and self._local is not None:
            providers = [self._local]
        else:
            providers = [self._google] + ([self._local] if self._local is not None else [])
        return call_first_available(providers, (segment, language), segment.is_final, _is_transient_stt)

    def _google_transcribe(self, segment: AudioSegment, language: str) -> str:
        audio = sr.AudioData(segment.pcm16, segment.sample_rate, 2)
        try:
            text = self._call(audio, language=language)
        except sr.UnknownValueError:
            return ""
        return (text or "").strip()

    def _whisper_transcribe(self, segment: AudioSegment, language: str) -> str:
        return self.whisper.transcribe(segment.pcm16, language, segment.is_final)


class _QuotaExceeded(RuntimeError):
    pass


def _is_transient_translation(exc: Exception) -> bool:
    return isinstance(exc, (dt_errors.TooManyRequests, dt_errors.RequestError,
                            requests.RequestException, OSError, _QuotaExceeded))


class TranslatorService:
    """Aynı cümleler (kısmi sonuçlar, tekrarlar) sık geldiği için küçük bir önbellekle."""

    _CACHE_LIMIT = 256
    _MYMEMORY_URL = "https://api.mymemory.translated.net/get"

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str, str], str] = {}
        self._lock = threading.Lock()
        self._session = requests.Session()
        self._providers = (
            Provider("Google", self._google),
            # Anahtarsız kullanımda günlük kota dar, kısmi sonuçlara harcanmıyor.
            Provider("MyMemory", self._mymemory, finals_only=True),
        )

    def translate(self, text: str, source: str, target: str, is_final: bool = True) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        if source == target:
            return text

        key = (text, source, target)
        with self._lock:
            cached = self._cache.get(key)
        if cached is not None:
            return cached

        translated = call_first_available(self._providers, (text, source, target), is_final,
                                          _is_transient_translation)
        translated = (translated or "").strip() or text

        with self._lock:
            if len(self._cache) >= self._CACHE_LIMIT:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = translated
        return translated

    @staticmethod
    def _google(text: str, source: str, target: str) -> str:
        return GoogleTranslator(source=source, target=target).translate(text)

    def _mymemory(self, text: str, source: str, target: str) -> str:
        response = self._session.get(
            self._MYMEMORY_URL, params={"q": text, "langpair": f"{source}|{target}"}, timeout=6)
        if response.status_code == 429:
            raise _QuotaExceeded("günlük ücretsiz kota doldu")
        response.raise_for_status()
        data = response.json()
        # Kota bitince de 200 dönüp çeviri yerine uyarı metni koyabiliyor
        status = str(data.get("responseStatus", "200"))
        if status == "429" or data.get("quotaFinished"):
            raise _QuotaExceeded("günlük ücretsiz kota doldu")
        if status != "200":
            raise RuntimeError(data.get("responseDetails") or f"durum {status}")
        return html.unescape(data["responseData"]["translatedText"] or "")
