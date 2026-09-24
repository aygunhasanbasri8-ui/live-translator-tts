# Live Translator

Windows'ta sistem sesini WASAPI loopback ile yakalar, konuşmayı metne çevirir, hedef dile çevirir ve ekranda altyazı olarak gösterir. İsteğe bağlı Edge-TTS dublajı desteklenir.

## Kurulum

Python 3.10 veya üzeri gerekir. Windows'ta sanal ortam oluşturup bağımlılıkları kurun:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,shortcuts]"
```

`pygame` kurulamazsa uygulama Windows MCI oynatıcısına düşer.

## Çalıştırma

```powershell
python -m live_translator
```

Kısayollar:

- `Ctrl+Shift+R`: dinlemeyi başlatır
- `Ctrl+Shift+S`: dinlemeyi durdurur
- `Ctrl+Shift+H`: altyazı katmanını gösterir veya gizler

## Test

Donanım ve ağ gerektirmeyen testler:

```powershell
python -m pytest
```

Gerçek cihaz, STT, çeviri ve TTS zincirini sınamak için:

```powershell
python selftest.py
```

## Paketleme

PyInstaller tanımları kökte tutulur. Klasör çıktısı için:

```powershell
python -m PyInstaller --noconfirm live_translator_klasor.spec
```

## Yapı

- `live_translator/app.py`: uygulama mantığı ve Qt arayüzü
- `live_translator/__main__.py`: modül çalıştırma girişi
- `tests/`: hızlı birim testleri
- `selftest.py`: gerçek Windows ses ve çevrim içi servis testi
