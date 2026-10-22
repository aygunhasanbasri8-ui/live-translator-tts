"""Konuşmayı metne, metni hedef dile çevirir.

Tanıma: Google Web Speech; faster-whisper kuruluysa yerel Whisper da seçilebiliyor
ve Google sınırladığında yedek oluyor. Çeviri: Google'ın iki ayrı ücretsiz ucu,
ikisi de sınırladığında MyMemory."""
from __future__ import annotations

import html
import json
import threading
from typing import Optional

import deep_translator.google
import requests
import speech_recognition as sr
from deep_translator import GoogleTranslator
from deep_translator import exceptions as dt_errors

from .capture import AudioSegment
from .providers import Provider, call_first_available, describe
from .whisper_stt import WhisperLoadError, WhisperRecognizer, has_speech, whisper_available


def _is_transient_stt(exc: Exception) -> bool:
    return isinstance(exc, (requests.RequestException, OSError, WhisperLoadError))


def parse_google_stt(body: str) -> str:
    """Yanıt satır satır JSON. continuous modunda her ifade ayrı bir final
    sonuç olarak geliyor, hepsini birleştiriyoruz."""
    finals, last_interim = [], ""
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        for result in json.loads(line).get("result", []):
            alternatives = result.get("alternative") or []
            if not alternatives:
                continue
            text = (alternatives[0].get("transcript") or "").strip()
            if result.get("final"):
                finals.append(text)
            else:
                last_interim = text
    return " ".join(t for t in finals if t) or last_interim


class SpeechToTextService:
    # Chromium'un herkese açık Web Speech anahtarı; SpeechRecognition da bunu kullanıyor.
    _GOOGLE_URL = "https://www.google.com/speech-api/v2/recognize"
    _GOOGLE_KEY = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"
    _GOOGLE_TIMEOUT_SEC = 12    # ağ takılırsa sonsuza kadar beklemesin

    def __init__(self, whisper: Optional[WhisperRecognizer] = None) -> None:
        # Bağlantıyı açık tutmak her segmentte TLS el sıkışmasını atlatıyor
        self._session = requests.Session()

        if whisper is None and whisper_available():
            whisper = WhisperRecognizer()
        self.whisper = whisper
        self._google = Provider("Google", self._google_transcribe)
        self._local = Provider("Whisper", self._whisper_transcribe) if whisper else None

    def transcribe(self, segment: AudioSegment, language: str, engine: str = "google") -> str:
        """Anlaşılamayan ses için boş string döner. Hiçbir motor sonuç
        veremezse ServiceUnavailable fırlatır."""
        if self.whisper is not None and not has_speech(segment.pcm16):
            return ""
        return call_first_available(self._providers_for(engine), (segment, language),
                                    segment.is_final, _is_transient_stt)

    def status(self, engine: str = "google") -> str:
        return describe(self._providers_for(engine))

    def _providers_for(self, engine: str) -> list[Provider]:
        if engine == "whisper" and self._local is not None:
            return [self._local]
        return [self._google] + ([self._local] if self._local is not None else [])

    def _google_transcribe(self, segment: AudioSegment, language: str) -> str:
        # recognize_google yerine kendimiz çağırıyoruz: o "continuous" olmadan
        # istiyor ve Google ses içinde ifade sınırı görürse yalnızca son
        # ifadeyi döndürüyor. Ölçümde 5 sn'lik cümlelerin kabaca beşte birinde
        # baştaki yarım cümle kayboluyordu; continuous ile hepsi tam geldi.
        flac = sr.AudioData(segment.pcm16, segment.sample_rate, 2).get_flac_data(convert_width=2)
        response = self._session.post(
            self._GOOGLE_URL,
            params={"client": "chromium", "lang": language, "key": self._GOOGLE_KEY,
                    "pFilter": 0, "continuous": ""},
            data=flac,
            headers={"Content-Type": f"audio/x-flac; rate={segment.sample_rate}"},
            timeout=self._GOOGLE_TIMEOUT_SEC,
        )
        response.raise_for_status()
        return parse_google_stt(response.text)

    def _whisper_transcribe(self, segment: AudioSegment, language: str) -> str:
        return self.whisper.transcribe(segment.pcm16, language, segment.is_final)


class _QuotaExceeded(RuntimeError):
    pass


class _PooledRequests:
    """deep-translator her çeviride requests.get'i yeni bağlantıyla ve zaman
    aşımı olmadan çağırıyor. Modülün kendi 'requests' adını bununla
    değiştirince bağlantı açık kalıyor (ölçümde istek başına ~0.35 sn) ve ağ
    takılırsa işçi thread sonsuza kadar beklemiyor. Bilmediğimiz her şey
    gerçek requests'e gidiyor, kütüphane başka çağrı yaparsa da bozulmasın."""

    def __init__(self, session: requests.Session, timeout: float) -> None:
        self._session = session
        self._timeout = timeout

    def get(self, *args, **kwargs):
        kwargs.setdefault("timeout", self._timeout)
        return self._session.get(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(requests, name)


def _is_transient_translation(exc: Exception) -> bool:
    return isinstance(exc, (dt_errors.TooManyRequests, dt_errors.RequestError,
                            requests.RequestException, OSError, _QuotaExceeded))


class TranslatorService:
    """Aynı cümleler (kısmi sonuçlar, tekrarlar) sık geldiği için küçük bir önbellekle."""

    _CACHE_LIMIT = 256
    _MYMEMORY_URL = "https://api.mymemory.translated.net/get"
    # Google Translate web sayfasının kendi kullandığı uç ve sayfaya gömülü
    # herkese açık anahtar. deep-translator'ın kazıdığı mobil sayfadan ayrı
    # sınırlanıyor (bu makinede o 429 verirken bu çalıştı) ve JSON döndüğü
    # için hızlı: ölçümde medyan 0.22 sn.
    _GOOGLE_API_URL = "https://translate-pa.googleapis.com/v1/translate"
    _GOOGLE_API_KEY = "AIzaSyDLEeFI5OtFBwYBIoK_jj5m32rZK5CkCXA"

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str, str], str] = {}
        self._lock = threading.Lock()
        self._session = requests.Session()
        deep_translator.google.requests = _PooledRequests(self._session, timeout=6)
        self._providers = (
            Provider("Google", self._google_api),
            Provider("Google web", self._google),
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

    def status(self) -> str:
        return describe(self._providers)

    def _google_api(self, text: str, source: str, target: str) -> str:
        response = self._session.get(
            self._GOOGLE_API_URL,
            params={"params.client": "gtx", "query.source_language": source,
                    "query.target_language": target, "query.display_language": "en-US",
                    "query.text": text, "key": self._GOOGLE_API_KEY, "data_types": "TRANSLATION"},
            timeout=6)
        response.raise_for_status()
        return response.json()["translation"]

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
