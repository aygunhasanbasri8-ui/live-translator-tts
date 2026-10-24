# -*- mode: python ; coding: utf-8 -*-
"""
Tek dosyalık .exe.

Derlemek için:
    .venv\\Scripts\\python.exe -m PyInstaller --noconfirm live_translator.spec

Çıktı:  dist\\CanliCevirmen.exe
"""
import os
import sys

sys.path.insert(0, SPECPATH)
from pyinstaller_ortak import analysis_options, without_pocketsphinx

a = Analysis([os.path.join("live_translator", "__main__.py")], **analysis_options())
a.datas = without_pocketsphinx(a.datas)

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
    upx=False,               # UPX antivirüs yanlış alarmını artırıyor
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
