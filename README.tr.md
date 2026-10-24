# Live Translator

[English](README.md) | Türkçe

[![CI](https://github.com/aygunhasanbasri8-ui/live-translator-tts/actions/workflows/ci.yml/badge.svg)](https://github.com/aygunhasanbasri8-ui/live-translator-tts/actions/workflows/ci.yml)

Bilgisayarda çalan sesi (YouTube, Zoom, oyun...) dinleyip ekranın altında
çevrilmiş altyazı olarak gösteren masaüstü uygulaması. İstenirse çeviriyi
Edge-TTS ile seslendirip dublaj da yapıyor. Mikrofonu değil sistem sesini
yakaladığı için yalnızca Windows'ta çalışıyor (WASAPI loopback).

## Özellikler

- Sistem sesini WASAPI loopback ile yakalar, konuşmayı sessizliklere göre cümlelere böler.
- Konuşmayı Google Web Speech ile ya da (kuruluysa) yerel Whisper ile metne çevirir; 37 dil tanımlı (`config.py` içindeki `LANGUAGES`).
- Çeviri için sırayla üç servis dener (Google, Google web, MyMemory); biri sınırlayınca geri çekilip sıradakine geçer.
- Çevrilmiş altyazıyı ekranın altında, her şeyin üstünde, fareyi engellemeyen saydam bir şeritte gösterir; renk, boyut, genişlik, yükseklik ve opaklık ayarlanır, çoklu monitörde ekran seçilebilir.
- "Akıcı mod": altyazı konuşma sürerken yaklaşık saniyede bir güncellenir.
- İsteğe bağlı dublaj: çeviri Edge-TTS ile seslendirilir; geride kalınca konuşma hızlanır, bozuk ses yedeğine geçilir.
- Tepsi simgesi, global kısayollar, ses çıkışı değişince yakalamanın kendini yeniden kurması.
- Altyazı dökümünü SRT ya da düz metin olarak kaydetme.
- Ayarlar oturumlar arasında saklanır.

## Kurulum

Python 3.10 veya üzeri gerekiyor:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,shortcuts]"
```

`pygame` isteğe bağlı (`.[audio]`); yoksa dublaj Windows MCI ile çalınıyor.
Kısayollar önce `keyboard`, o kurulamazsa `pynput` ile bağlanıyor.

Tanıma ve çeviri varsayılan olarak Google'ın ücretsiz uçlarını kullanıyor,
internet şart. Çok sık istekte Google geçici olarak "too many requests"
dönebiliyor; o zaman uygulama o servise bir süre (2 sn'den başlayıp en fazla
1 dk) hiç gitmiyor ve yedeğe geçiyor:

- Çeviri önce Google Translate web sayfasının kullandığı uçtan, o sınırlarsa
  deep-translator'ın kullandığı mobil sayfadan geliyor; ikisi ayrı
  sınırlanıyor. İkisi de sınırladığında yedek MyMemory. Onun anahtarsız
  günlük kotası dar olduğu için yalnızca kesinleşmiş cümlelerde
  kullanılıyor, kısmi sonuçlarda değil.
- Tanıma için yedek yerel Whisper, kuruluysa:

  ```powershell
  python -m pip install -e ".[whisper]"
  ```

  Whisper arayüzden doğrudan da seçilebiliyor; o zaman internet olmadan
  çalışıyor. Kuruluyken kaynak dil listesinin başında "Otomatik algıla"
  da çıkıyor: dili her cümlede Whisper buluyor, karışık dilli içerikte
  kaynak dili değiştirmeye gerek kalmıyor. Model (tiny/base/small) ilk kullanımda bir kez indiriliyor,
  CPU'da int8 çalışıyor. Exe'ye girmiyor, yalnızca kaynaktan çalıştırınca var.
  Kuruluyken birlikte gelen Silero VAD da kullanılıyor: içinde konuşma
  olmayan parçalar (müzik, gürültü) hiç tanımaya gönderilmiyor, böylece
  Google'a giden istek ve sınırlanma ihtimali azalıyor.

Hangi servisin kullanıldığı ve bekleyenler çalışırken durum çubuğunun
sağında görünüyor (ör. `Çeviri: Google web (Google 16 sn ara)`).

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

Dublajda çeviri çoğu zaman orijinalden uzun sürüyor. Sırada bekleyen cümle
oldukça konuşma hızı cümle başına %10 artıyor (en fazla +%50); yine de
12 sn'den fazla geride kalan cümle okunmadan atlanıyor, altyazısı zaten
görülmüş oluyor. Seçilen ses Edge tarafında ses üretmiyorsa aynı dilin
diğer sesine geçiliyor.

Birden fazla monitörde altyazının hangi ekranda çıkacağı "Altyazı görünümü"
sekmesinden seçiliyor; o ekran çıkarılırsa birincil ekrana dönülüyor. Aynı
sekmede "Önceki cümleyi de göster" açılırsa bir önceki cümlenin çevirisi
üstte soluk olarak duruyor, hızlı konuşmada okumaya yetişmek kolaylaşıyor.

Pencere küçültülünce tepsiye iniyor; tepsi menüsünden başlat/durdur,
altyazıyı gizle ve çıkış yapılabiliyor. Ses çıkışı değişince (kulaklık
takmak, varsayılan cihazı değiştirmek) ya da cihaz çıkarılınca dinleme
birkaç saniye içinde yeni cihaza kendiliğinden geçiyor.

Kesinleşen cümleler bir dökümde birikiyor; "Altyazıları kaydet..." ile
çeviri, orijinal ya da iki dilli SRT veya düz metin olarak kaydedilebiliyor.
Zamanlar ilk cümleye göre, yani videoyu baştan izlerken kabaca hizalı.

Ayarlar (diller, mod, ses, hassasiyet, altyazı boyutu/rengi/konumu/opaklığı,
pencere konumu) kapanışta ve her Başlat'ta kaydediliyor, bir sonraki
açılışta aynen geliyor. Windows'ta kayıt defterinde
`HKCU\Software\LiveTranslator` altında duruyor; silinirse varsayılanlara
dönülüyor.

Günlük `%LOCALAPPDATA%\LiveTranslator\live_translator.log` dosyasına da
yazılıyor (pencereli exe'de konsol olmadığı için sorun ararken bakılacak yer).
Beklenmeyen bir hata uygulamayı kapatmıyor, bu dosyaya düşüyor.

## Nasıl çalışıyor

1. `capture.py` sistem sesini WASAPI loopback ile alıyor, konuşmayı
   sessizliklere göre cümlelere bölüyor. Duraksamadan 6 sn'yi geçen konuşma
   kelime ortasından değil, son 1.5 sn'nin en sessiz anından bölünüyor.
2. `speech.py` her parçayı Google Web Speech (ya da `whisper_stt.py`) ile
   metne, Google/MyMemory ile hedef dile çeviriyor. Hangi sağlayıcının ne
   zaman atlanacağı `providers.py`'de.
3. `pipeline.py` parçaları paralel işliyor ama sonuçları geliş sırasıyla
   yayınlıyor, altyazılar karışık sırada gelmiyor. Arkasından daha yenisi
   gelmiş kısmi sonuçlar atlanıyor, bir işçi hep kesin cümleye ayrılıyor;
   ağ yavaşken bile cümle sonu altyazısı beklemiyor.
4. `overlay.py` altyazıyı ekranın altında, her şeyin üstünde gösteriyor.
   Dublaj açıksa `tts.py` çeviriyi seslendiriyor.

Arayüz `main_window.py`'de. Desteklenen diller ve sesler `config.py` içindeki
`LANGUAGES` tablosunda; yeni dil eklemek için oraya bir satır yeterli.

## Proje yapısı

```
live_translator/
├── app.py            giriş noktası (QApplication, günlükleme)
├── capture.py        WASAPI loopback yakalama, cümlelere bölme, cihaz değişimi
├── speech.py         Google Web Speech (STT) ve çeviri servisleri
├── whisper_stt.py    isteğe bağlı yerel tanıma (faster-whisper, Silero VAD)
├── providers.py      sağlayıcı sırası ve geri çekilme (cooldown)
├── pipeline.py       paralel işleme, sonuçları sırayla yayınlama
├── tts.py            Edge-TTS ile dublaj
├── audio_player.py   pygame ya da Windows MCI ile çalma
├── audio_math.py     mono'ya indirme, yeniden örnekleme
├── overlay.py        altyazı şeridi
├── main_window.py    ana pencere
├── tray.py           tepsi simgesi
├── settings.py       ayarların kalıcı saklanması
├── transcript.py     altyazı dökümü, SRT/metin dışa aktarma
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
pip install -e ".[dev]"
python -m pytest
ruff check .
```

Testler Windows dışında da çalışıyor: PyAudioWPatch yalnızca Windows tekerleği yayımladığı
için kurulu değilse `tests/conftest.py` yerine küçük bir taklit modül koyuyor, `windows_audio`
işaretli testler orada atlanıyor. Paketi import etmek artık eksik bağımlılıkta süreci
kapatmıyor; kontrol uygulama başlarken yapılıyor.

Gerçek cihaz, STT, çeviri ve TTS zincirini sınamak için:

```powershell
python selftest.py            # --no-wait: sonda Enter beklemesin
```

`python -m live_translator --smoke` (ya da `CanliCevirmen.exe --smoke`) ana pencereyi kurar,
bir saniye sonra kapatır ve 0 ile çıkar; bir derlemenin gerçekten açıldığını hızlıca görmek için.

GitHub Actions `main`'e her push'ta ve her pull request'te ruff'ı ve testleri Ubuntu ve Windows'ta
(Python 3.11 ve 3.12) çalıştırıyor; ardından Windows'ta klasör exe'sini derleyip `--smoke` ile açıyor ve
260 MB'ı geçerse kırmızıya düşüyor. `_version.py` ile aynı `vX.Y.Z` etiketi push'lanınca iki exe derlenip
`LiveTranslator-vX.Y.Z-win64.zip`, `LiveTranslator-vX.Y.Z-portable.exe` ve `SHA256SUMS.txt` ile GitHub
Release yayımlanıyor.

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
(klasör) ve `dist\selftest.exe`. Yerel Whisper boyut nedeniyle exe'ye dahil edilmiyor.
Sürüm `live_translator/_version.py`'de tutuluyor ve pencere başlığında görünüyor.

## Gizlilik

Varsayılan ayarlarda yakalanan konuşma parçaları metne çevrilmek üzere Google'ın ücretsiz konuşma
tanıma ucuna, metinler çeviri için Google'ın çeviri uçlarına (Google sınırlarsa MyMemory'ye)
gönderiliyor. Dublaj açıksa çevrilen metin Edge-TTS üzerinden Microsoft'un çevrimiçi ses servisine
gidiyor. Yerel Whisper seçilirse ses cihazdan çıkmıyor, yalnızca metin çeviri servislerine gidiyor.
Hassas içerik oynatırken bunu göz önünde bulundurun.

## Lisans

MIT. Ayrıntılar için [`LICENSE`](LICENSE).
