# -*- coding: utf-8 -*-
"""Üç .spec dosyasının ortak PyInstaller ayarları."""
import os

import speech_recognition
from PyInstaller.utils.hooks import collect_dynamic_libs

# recognize_google sesi FLAC'a çevirmek için paketle gelen flac-win32.exe'yi
# çalıştırıyor. Bu dosya kopyalanmazsa exe "flac conversion utility not
# available" deyip hiçbir şeyi tanıyamıyor.
_SR_DIR = os.path.dirname(speech_recognition.__file__)

datas = [
    (os.path.join(_SR_DIR, "flac-win32.exe"), "speech_recognition"),
    (os.path.join(_SR_DIR, "version.txt"), "speech_recognition"),
]

# PortAudio uzantısı site-packages kökünde duruyor, kendiliğinden bulunmayabiliyor.
binaries = collect_dynamic_libs("pyaudiowpatch")

hiddenimports = [
    "_portaudiowpatch",     # PyAudioWPatch'in C uzantısı
    "pyaudiowpatch",
    "edge_tts",
    "deep_translator",
    "speech_recognition",
]

# Kullanılmayan ağır paketler: boyut ve derleme süresi için dışarıda.
excludes = [
    "tkinter", "matplotlib", "scipy", "pandas", "PIL", "pytest",
    "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtQuick",
    "PyQt6.QtQml", "PyQt6.Qt3DCore", "PyQt6.QtMultimedia", "PyQt6.QtBluetooth",
    "PyQt6.QtDesigner", "PyQt6.QtHelp", "PyQt6.QtTest", "PyQt6.QtSql",
    "PyQt6.QtCharts", "PyQt6.QtDataVisualization", "PyQt6.QtPdf",
]


def analysis_options() -> dict:
    return dict(
        pathex=[],
        binaries=binaries,
        datas=datas,
        hiddenimports=hiddenimports,
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=excludes,
        noarchive=False,
        optimize=0,
    )


def without_pocketsphinx(toc):
    """pocketsphinx verisi 37 MB ve hiç kullanılmıyor (Google Web Speech kullanıyoruz)."""
    return [d for d in toc if "pocketsphinx" not in d[0].lower()]
