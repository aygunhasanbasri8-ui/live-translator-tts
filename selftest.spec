# -*- mode: python ; coding: utf-8 -*-
"""
Donmuş ortam testi (selftest.py) için konsollu tek dosyalık .exe.

Derlemek için:
    .venv\\Scripts\\python.exe -m PyInstaller --noconfirm selftest.spec

Çıktı:  dist\\selftest.exe
"""
import sys

sys.path.insert(0, SPECPATH)
from pyinstaller_ortak import analysis_options, without_pocketsphinx

a = Analysis(["selftest.py"], **analysis_options())
a.datas = without_pocketsphinx(a.datas)

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
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,            # sonuçlar konsolda okunuyor
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
