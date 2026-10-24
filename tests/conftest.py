"""Windows dışında (CI'daki Linux, geliştirici makinesi) testlerin açılabilmesi için.

PyAudioWPatch yalnızca Windows tekerleği yayımlıyor. Kurulu değilse capture.py'nin
import edebileceği kadarını taklit eden küçük bir modül koyuyoruz; gerçek cihaz
gerektiren testler `windows_audio` işaretiyle ayrılıyor.
"""

import os
import sys
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import pyaudiowpatch  # noqa: F401
except ImportError:
    fake = types.ModuleType("pyaudiowpatch")
    fake.paInt16 = 8
    fake.paFloat32 = 1
    fake.paWASAPI = 13

    class PyAudio:
        def __init__(self) -> None:
            raise OSError("pyaudiowpatch yok: gerçek ses cihazı yalnızca Windows'ta")

    fake.PyAudio = PyAudio
    sys.modules["pyaudiowpatch"] = fake


def pytest_collection_modifyitems(config, items):
    if sys.platform == "win32":
        return
    skip = pytest.mark.skip(reason="gerçek WASAPI cihazı gerekiyor")
    for item in items:
        if "windows_audio" in item.keywords:
            item.add_marker(skip)
