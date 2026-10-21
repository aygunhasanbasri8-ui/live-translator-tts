"""Konuşmayı metne (Google Web Speech) ve metni hedef dile (deep-translator) çevirir."""
from __future__ import annotations

import threading

import speech_recognition as sr
from deep_translator import GoogleTranslator

from .capture import AudioSegment


class SpeechToTextService:
    def __init__(self) -> None:
        self._recognizer = sr.Recognizer()
        self._recognizer.operation_timeout = 12  # ağ takılırsa sonsuza kadar beklemesin
        # SpeechRecognition sürümleri arasında metodun adı değişmiş
        self._call = getattr(self._recognizer, "recognize_google", None) \
            or getattr(self._recognizer, "recognize_legacy", None)
        if self._call is None:  # pragma: no cover
            raise RuntimeError("SpeechRecognition sürümünde Google tanıyıcı bulunamadı.")

    def transcribe(self, segment: AudioSegment, language: str) -> str:
        """Anlaşılamayan ses için boş string döner; ağ ve servis hataları yukarı çıkar."""
        audio = sr.AudioData(segment.pcm16, segment.sample_rate, 2)
        try:
            text = self._call(audio, language=language)
        except sr.UnknownValueError:
            return ""
        return (text or "").strip()


class TranslatorService:
    """Aynı cümleler (kısmi sonuçlar, tekrarlar) sık geldiği için küçük bir önbellekle."""

    _CACHE_LIMIT = 256

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str, str], str] = {}
        self._lock = threading.Lock()

    def translate(self, text: str, source: str, target: str) -> str:
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

        translated = GoogleTranslator(source=source, target=target).translate(text)
        translated = (translated or "").strip() or text

        with self._lock:
            if len(self._cache) >= self._CACHE_LIMIT:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = translated
        return translated
