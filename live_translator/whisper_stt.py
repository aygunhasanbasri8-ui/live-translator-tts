"""İsteğe bağlı yerel tanıma (faster-whisper). Kurulu değilse uygulama
Google ile eskisi gibi çalışıyor. Exe'ye girmiyor (pyinstaller_ortak.py)."""
from __future__ import annotations

import importlib.util
import threading

import numpy as np

from .log import LOGGER

WHISPER_MODELS = ("tiny", "base", "small")


class WhisperLoadError(RuntimeError):
    """Model indirilemedi/açılamadı; ağ düzelince yeniden denenebilir."""


def whisper_available() -> bool:
    try:
        return importlib.util.find_spec("faster_whisper") is not None
    except (ImportError, ValueError):
        return False


class WhisperRecognizer:
    def __init__(self, model_size: str = "base") -> None:
        self._model_size = model_size
        self._model = None
        self._loaded_size = ""
        self._lock = threading.Lock()

    def set_model_size(self, model_size: str) -> None:
        # Kilit alınmıyor: süren bir çözümleme arayüzü bekletmesin, yeni
        # boyut bir sonraki çağrıda yüklenir.
        self._model_size = model_size

    def is_loaded(self) -> bool:
        return self._model is not None and self._loaded_size == self._model_size

    def preload(self) -> None:
        with self._lock:
            self._ensure_model()

    def transcribe(self, pcm16: bytes, language: str, is_final: bool) -> str:
        # CPU'da aynı anda iki çözümleme ikisini de yavaşlatıyor. Kısmi sonuç
        # sırada beklemeye değmez, kesin olan zaten arkasından geliyor.
        if not self._lock.acquire(blocking=is_final):
            return ""
        try:
            model = self._ensure_model()
            audio = np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0
            segments, _info = model.transcribe(
                audio,
                language=language.split("-")[0].lower(),
                beam_size=5 if is_final else 1,
                # Her parça bağımsız; önceki metne koşullamak sessizlikte
                # "izlediğiniz için teşekkürler" gibi uydurmaları artırıyor.
                condition_on_previous_text=False,
                # Sessizlik ve müzikte Whisper "You", "Thank you" uyduruyor;
                # dahili VAD bunları kesiyor, konuşmada doğruluğu değiştirmedi.
                vad_filter=True,
            )
            return " ".join(s.text.strip() for s in segments).strip()
        finally:
            self._lock.release()

    def _ensure_model(self):
        size = self._model_size
        if self._model is not None and self._loaded_size == size:
            return self._model
        LOGGER.info("Whisper '%s' modeli yükleniyor (ilk seferde indirilir)...", size)
        try:
            from faster_whisper import WhisperModel
            # GPU sürücüsü/CUDA kütüphanesi eksik makinelerde "auto" ilk
            # çözümlemede çöküyor; CPU int8 her yerde çalışıyor ve yeterince hızlı.
            self._model = WhisperModel(size, device="cpu", compute_type="int8")
        except Exception as exc:
            raise WhisperLoadError(f"Whisper modeli yüklenemedi: {exc}") from exc
        self._loaded_size = size
        LOGGER.info("Whisper modeli hazır.")
        return self._model
