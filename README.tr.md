# Live Translator

[English](README.md) | Türkçe

Bilgisayarda çalan sesi (YouTube, Zoom, oyun...) dinleyip ekranın altında
çevrilmiş altyazı olarak gösteren masaüstü uygulaması. İstenirse çeviriyi
Edge-TTS ile seslendirip dublaj da yapıyor. Mikrofonu değil sistem sesini
yakaladığı için yalnızca Windows'ta çalışıyor (WASAPI loopback).

## Özellikler

- Sistem sesini WASAPI loopback ile yakalar, konuşmayı sessizliklere göre cümlelere böler.
- Google Web Speech ile konuşmayı metne, deep-translator ile hedef dile çevirir; 19 dil tanımlı (`config.py` içindeki `LANGUAGES`).
- Çevrilmiş altyazıyı ekranın altında, her şeyin üstünde, fareyi engellemeyen saydam bir şeritte gösterir.
- "Akıcı mod": altyazı konuşma sürerken yaklaşık saniyede bir güncellenir.
- İsteğe bağlı dublaj: çeviri Edge-TTS ile seslendirilir; dublaj sırasında yakalama kısa süre susturulur, böylece uygulama kendi sesini dinlemez.
- Global kısayollar (`keyboard`, olmazsa `pynput`).
- Sessizlik eşiği, cümle sonu bekleme süresi, yazı boyutu, genişlik ve yükseklik gibi ayarlar çalışırken değiştirilebilir.

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

## Proje yapısı

```
live_translator/
├── app.py            giriş noktası (QApplication, günlükleme)
├── capture.py        WASAPI loopback yakalama, cümlelere bölme
├── speech.py         Google Web Speech (STT) ve deep-translator (çeviri)
├── pipeline.py       paralel işleme, sonuçları sırayla yayınlama
├── tts.py            Edge-TTS ile dublaj
├── audio_player.py   pygame ya da Windows MCI ile çalma
├── audio_math.py     mono'ya indirme, yeniden örnekleme
├── overlay.py        altyazı şeridi
├── main_window.py    ana pencere
├── hotkeys.py        global kısayollar
├── config.py         AppConfig ve LANGUAGES tablosu
└── queues.py         kuyruk yardımcıları
tests/                donanım ve ağ gerektirmeyen testler
selftest.py           gerçek cihaz ve servislerle uçtan uca sınama
pyinstaller_ortak.py  PyInstaller spec'lerinin ortak ayarları
```

## Test

Donanım ve ağ gerektirmeyen testler:

```powershell
python -m pytest
```

Gerçek cihaz, STT, çeviri ve TTS zincirini sınamak için:

```powershell
python selftest.py
```

Şu an repoda CI iş akışı yok.

## Exe almak

```powershell
python -m PyInstaller --noconfirm live_translator.spec          # tek dosya
python -m PyInstaller --noconfirm live_translator_klasor.spec   # klasör hâlinde, daha hızlı açılır
python -m PyInstaller --noconfirm selftest.spec                 # konsol testi
```

Üç spec'in ortak ayarları `pyinstaller_ortak.py`'de. `selftest` dağıtılan
uygulamanın parçası değil; exe içinde ses yakalama, TTS ve çeviri zincirini
sınayıp sonucu konsola yazıyor.

Çıktılar: `dist\CanliCevirmen.exe` (tek dosya), `dist\CanliCevirmen_klasor\CanliCevirmen.exe`
(klasör) ve `dist\selftest.exe`.

## Gizlilik

Yakalanan konuşma parçaları metne çevrilmek üzere Google'ın ücretsiz konuşma tanıma ucuna,
metinler çeviri için Google Translate'e gönderiliyor. Dublaj açıksa çevrilen metin Edge-TTS
üzerinden Microsoft'un çevrimiçi ses servisine gidiyor. Hassas içerik oynatırken bunu göz önünde
bulundurun.

## Lisans

MIT. Ayrıntılar için [`LICENSE`](LICENSE).
