"""Canlı sistem sesi çevirmeni: WASAPI loopback -> STT -> çeviri -> altyazı/dublaj."""

import importlib
import sys

from ._version import __version__

# (import adı, pip paketi)
_REQUIRED = (
    ("numpy", "numpy"),
    ("PyQt6.QtWidgets", "PyQt6"),
    ("pyaudiowpatch", "PyAudioWPatch"),
    ("speech_recognition", "SpeechRecognition"),
    ("deep_translator", "deep-translator"),
    ("edge_tts", "edge-tts"),
)


def check_dependencies() -> None:
    # Alt modüller bunları doğrudan import ediyor; eksik olanı traceback
    # yerine tek bir anlaşılır mesajla söylemek için önce burada deniyoruz.
    # Paket import'unda değil başlatırken çalışıyor: testler ve araçlar
    # (sahte pyaudiowpatch ile) paketi Windows dışında da açabilsin.
    missing = []
    for module, package in _REQUIRED:
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(package)
    if missing:
        print(
            "Eksik kütüphaneler tespit edildi: %s\n\n"
            "Kurmak için:\n    pip install %s\n" % (", ".join(missing), " ".join(missing)),
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> int:
    check_dependencies()
    from .app import main as run

    return run()


# Eski "from live_translator import MainWindow" kullanımları çalışmaya devam
# etsin; modüller ancak istendiğinde yükleniyor.
_EXPORTS = {
    "AppConfig": "config",
    "AudioMath": "audio_math",
    "AudioSegment": "capture",
    "LANGUAGES": "config",
    "LanguageProfile": "config",
    "LoopbackAudioCapturer": "capture",
    "MainWindow": "main_window",
    "PipelineWorker": "pipeline",
    "SpeechToTextService": "speech",
    "SubtitleOverlay": "overlay",
    "TTSRequest": "tts",
    "TTSService": "tts",
    "TranslatorService": "speech",
    "create_audio_player": "audio_player",
}


def __getattr__(name: str):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(f".{module}", __name__), name)
    globals()[name] = value
    return value


__all__ = ["__version__", "check_dependencies", "main", *_EXPORTS]
