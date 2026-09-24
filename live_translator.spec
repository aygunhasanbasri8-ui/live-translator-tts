# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller yapılandırması — tek dosyalık .exe üretir.

Derlemek için:
    .venv\\Scripts\\python.exe -m PyInstaller --noconfirm live_translator.spec

Çıktı:  dist\\CanliCevirmen.exe
"""

import os
from PyInstaller.utils.hooks import collect_dynamic_libs

# --- SpeechRecognition'ın yardımcı ikilileri --------------------------------
# recognize_google, sesi FLAC'a çevirmek için paketle gelen flac-win32.exe'yi
# çalıştırır. Bu dosya kopyalanmazsa exe "flac conversion utility not
# available" diyerek HİÇBİR şeyi tanıyamaz.
import speech_recognition
SR_DIR = os.path.dirname(speech_recognition.__file__)

datas = [
    (os.path.join(SR_DIR, "flac-win32.exe"), "speech_recognition"),
    (os.path.join(SR_DIR, "version.txt"), "speech_recognition"),
]

# PortAudio uzantısı site-packages kökünde duruyor; otomatik bulunmayabiliyor.
binaries = collect_dynamic_libs("pyaudiowpatch")

hiddenimports = [
    "_portaudiowpatch",     # PyAudioWPatch'in C uzantısı
    "pyaudiowpatch",
    "edge_tts",
    "deep_translator",
    "speech_recognition",
]

# Kullanılmayan ağır bağımlılıkları dışarıda bırak (boyut ve derleme süresi).
excludes = [
    "tkinter", "matplotlib", "scipy", "pandas", "PIL", "pytest",
    "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtQuick",
    "PyQt6.QtQml", "PyQt6.Qt3DCore", "PyQt6.QtMultimedia", "PyQt6.QtBluetooth",
    "PyQt6.QtDesigner", "PyQt6.QtHelp", "PyQt6.QtTest", "PyQt6.QtSql",
    "PyQt6.QtCharts", "PyQt6.QtDataVisualization", "PyQt6.QtPdf",
]

a = Analysis(
    ["live_translator\\__main__.py"],
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

# pocketsphinx verisi 37 MB ve hiç kullanılmıyor (biz Google Web Speech
# kullanıyoruz); toplanmışsa at.
a.datas = [d for d in a.datas if "pocketsphinx" not in d[0].lower()]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CanliCevirmen",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # UPX sıkıştırması antivirüs yanlış alarmını artırır
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # konsol penceresi açılmasın
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
