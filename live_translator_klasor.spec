# -*- mode: python ; coding: utf-8 -*-
"""
Klasör (onedir) sürümü.

Tek dosyalıdan farkı her açılışta 54 MB'ı geçici klasöre açmaması, bu yüzden
çok daha hızlı başlıyor. Karşılığında tek .exe yerine klasör çıkıyor;
paylaşırken klasörün tamamı zip'lenmeli.

Derlemek için:
    .venv\\Scripts\\python.exe -m PyInstaller --noconfirm live_translator_klasor.spec

Çıktı:  dist\\CanliCevirmen_klasor\\CanliCevirmen.exe
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
    [],
    exclude_binaries=True,      # onedir: ikililer COLLECT'e gidiyor
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
