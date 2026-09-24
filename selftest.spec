# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller yapÄ±landÄ±rmasÄ± â€” tek dosyalÄ±k .exe Ã¼retir.

Derlemek iÃ§in:
    .venv\\Scripts\\python.exe -m PyInstaller --noconfirm live_translator.spec

Ã‡Ä±ktÄ±:  dist\\CanliCevirmen.exe
"""

import os
from PyInstaller.utils.hooks import collect_dynamic_libs

# --- SpeechRecognition'Ä±n yardÄ±mcÄ± ikilileri --------------------------------
# recognize_google, sesi FLAC'a Ã§evirmek iÃ§in paketle gelen flac-win32.exe'yi
# Ã§alÄ±ÅŸtÄ±rÄ±r. Bu dosya kopyalanmazsa exe "flac conversion utility not
# available" diyerek HÄ°Ã‡BÄ°R ÅŸeyi tanÄ±yamaz.
import speech_recognition
SR_DIR = os.path.dirname(speech_recognition.__file__)

datas = [
    (os.path.join(SR_DIR, "flac-win32.exe"), "speech_recognition"),
    (os.path.join(SR_DIR, "version.txt"), "speech_recognition"),
]

# PortAudio uzantÄ±sÄ± site-packages kÃ¶kÃ¼nde duruyor; otomatik bulunmayabiliyor.
binaries = collect_dynamic_libs("pyaudiowpatch")

hiddenimports = [
    "_portaudiowpatch",     # PyAudioWPatch'in C uzantÄ±sÄ±
    "pyaudiowpatch",
    "edge_tts",
    "deep_translator",
    "speech_recognition",
]

# KullanÄ±lmayan aÄŸÄ±r baÄŸÄ±mlÄ±lÄ±klarÄ± dÄ±ÅŸarÄ±da bÄ±rak (boyut ve derleme sÃ¼resi).
excludes = [
    "tkinter", "matplotlib", "scipy", "pandas", "PIL", "pytest",
    "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtQuick",
    "PyQt6.QtQml", "PyQt6.Qt3DCore", "PyQt6.QtMultimedia", "PyQt6.QtBluetooth",
    "PyQt6.QtDesigner", "PyQt6.QtHelp", "PyQt6.QtTest", "PyQt6.QtSql",
    "PyQt6.QtCharts", "PyQt6.QtDataVisualization", "PyQt6.QtPdf",
]

a = Analysis(
    ["selftest.py"],
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

# pocketsphinx verisi 37 MB ve hiÃ§ kullanÄ±lmÄ±yor (biz Google Web Speech
# kullanÄ±yoruz); toplanmÄ±ÅŸsa at.
a.datas = [d for d in a.datas if "pocketsphinx" not in d[0].lower()]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="selftest",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # UPX sÄ±kÄ±ÅŸtÄ±rmasÄ± antivirÃ¼s yanlÄ±ÅŸ alarmÄ±nÄ± artÄ±rÄ±r
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,           # konsol penceresi aÃ§Ä±lmasÄ±n
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

