# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller yapılandırması — KLASÖR sürümü (onedir).

Tek dosyalık sürümden farkı: her açılışta 54 MB'ı geçici klasöre açmadığı
için çok daha hızlı başlar. Karşılığında tek .exe yerine bir klasör çıkar;
paylaşırken klasörün TAMAMI zip'lenmelidir.

Derlemek için:
    .venv\\Scripts\\python.exe -m PyInstaller --noconfirm live_translator_klasor.spec

Çıktı:  dist\\CanliCevirmen_klasor\\CanliCevirmen.exe
"""

import os
from PyInstaller.utils.hooks import collect_dynamic_libs

import speech_recognition
SR_DIR = os.path.dirname(speech_recognition.__file__)

datas = [
    (os.path.join(SR_DIR, "flac-win32.exe"), "speech_recognition"),
    (os.path.join(SR_DIR, "version.txt"), "speech_recognition"),
]

binaries = collect_dynamic_libs("pyaudiowpatch")

hiddenimports = [
    "_portaudiowpatch",
    "pyaudiowpatch",
    "edge_tts",
    "deep_translator",
    "speech_recognition",
]

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

a.datas = [d for d in a.datas if "pocketsphinx" not in d[0].lower()]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,      # onedir: ikililer COLLECT'e gider
    name="CanliCevirmen",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CanliCevirmen_klasor",
)
