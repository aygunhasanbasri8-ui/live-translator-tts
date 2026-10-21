"""Canlı sistem sesi çevirmeni: WASAPI loopback -> STT -> çeviri -> altyazı/dublaj."""

import importlib
import sys

# (import adı, pip paketi)
_REQUIRED = (
    ("numpy", "numpy"),
    ("PyQt6.QtWidgets", "PyQt6"),
    ("pyaudiowpatch", "PyAudioWPatch"),
    ("speech_recognition", "SpeechRecognition"),
    ("deep_translator", "deep-translator"),
    ("edge_tts", "edge-tts"),
)


def _check_dependencies() -> None:
    # Alt modüller bunları doğrudan import ediyor; eksik olanı traceback
    # yerine tek bir anlaşılır mesajla söylemek için önce burada deniyoruz.
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


_check_dependencies()

from .app import main  # noqa: E402
from .audio_math import AudioMath  # noqa: E402
from .audio_player import create_audio_player  # noqa: E402
from .capture import AudioSegment, LoopbackAudioCapturer  # noqa: E402
from .config import LANGUAGES, AppConfig, LanguageProfile  # noqa: E402
from .main_window import MainWindow  # noqa: E402
from .overlay import SubtitleOverlay  # noqa: E402
from .pipeline import PipelineWorker  # noqa: E402
from .speech import SpeechToTextService, TranslatorService  # noqa: E402
from .tts import TTSRequest, TTSService  # noqa: E402

__all__ = [
    "AppConfig",
    "AudioMath",
    "AudioSegment",
    "LANGUAGES",
    "LanguageProfile",
    "LoopbackAudioCapturer",
    "MainWindow",
    "PipelineWorker",
    "SpeechToTextService",
    "SubtitleOverlay",
    "TTSRequest",
    "TTSService",
    "TranslatorService",
    "create_audio_player",
    "main",
]
