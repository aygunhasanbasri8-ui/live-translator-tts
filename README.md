# Live Translator

Bilgisayarda çalan sesi (YouTube, Zoom, oyun...) dinleyip ekranın altında
çevrilmiş altyazı olarak gösteren masaüstü uygulaması. İstenirse çeviriyi
Edge-TTS ile seslendirip dublaj da yapıyor. Mikrofonu değil sistem sesini
yakaladığı için yalnızca Windows'ta çalışıyor (WASAPI loopback).

## Kurulum

Python 3.10 veya üzeri gerekiyor:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,shortcuts]"
```

`pygame` isteğe bağlı (`.[audio]`); yoksa dublaj Windows MCI ile çalınıyor.
Kısayollar önce `keyboard`, o kurulamazsa `pynput` ile bağlanıyor.

Tanıma ve çeviri Google'ın ücretsiz uçlarını kullandığı için internet şart.
Çok sık istekte Google geçici olarak "too many requests" dönebiliyor.

## Kullanım

```powershell
python -m live_translator
```

| Kısayol      |                        |
|--------------|------------------------|
| Ctrl+Shift+R | Başlat                 |
| Ctrl+Shift+S | Durdur                 |
| Ctrl+Shift+H | Altyazıyı gizle/göster |

Pencerede kaynak/hedef dil, mod (sadece altyazı ya da altyazı + dublaj), ses
ve konuşma hızı seçiliyor. "Akıcı mod" açıkken altyazı konuşma sürerken
yaklaşık saniyede bir güncelleniyor; kapalıyken sadece cümle bitince geliyor,
daha az istek atıyor.

## Nasıl çalışıyor

1. `capture.py` sistem sesini WASAPI loopback ile alıyor, konuşmayı
   sessizliklere göre cümlelere bölüyor.
2. `speech.py` her parçayı Google Web Speech ile metne, deep-translator ile
   hedef dile çeviriyor.
3. `pipeline.py` parçaları paralel işliyor ama sonuçları geliş sırasıyla
   yayınlıyor, altyazılar karışık sırada gelmiyor.
4. `overlay.py` altyazıyı ekranın altında, her şeyin üstünde gösteriyor.
   Dublaj açıksa `tts.py` çeviriyi seslendiriyor.

Arayüz `main_window.py`'de. Desteklenen diller ve sesler `config.py` içindeki
`LANGUAGES` tablosunda; yeni dil eklemek için oraya bir satır yeterli.

## Test

Donanım ve ağ gerektirmeyen testler:

```powershell
python -m pytest
```

Gerçek cihaz, STT, çeviri ve TTS zincirini sınamak için:

```powershell
python selftest.py
```

## Exe almak

```powershell
python -m PyInstaller --noconfirm live_translator.spec          # tek dosya
python -m PyInstaller --noconfirm live_translator_klasor.spec   # klasör hâlinde, daha hızlı açılır
python -m PyInstaller --noconfirm selftest.spec                 # konsol testi
```

Üç spec'in ortak ayarları `pyinstaller_ortak.py`'de. `selftest` dağıtılan
uygulamanın parçası değil; exe içinde ses yakalama, TTS ve çeviri zincirini
sınayıp sonucu konsola yazıyor.

## Lisans

MIT
