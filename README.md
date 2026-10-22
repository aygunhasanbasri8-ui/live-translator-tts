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

Tanıma ve çeviri varsayılan olarak Google'ın ücretsiz uçlarını kullanıyor,
internet şart. Çok sık istekte Google geçici olarak "too many requests"
dönebiliyor; o zaman uygulama o servise bir süre (4 sn'den başlayıp en fazla
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
  çalışıyor. Model (tiny/base/small) ilk kullanımda bir kez indiriliyor,
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
