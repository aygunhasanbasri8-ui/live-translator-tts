from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LanguageProfile:
    label: str               # arayüzde görünen ad
    stt_code: str            # Google Web Speech kodu (en-US)
    translate_code: str      # deep-translator kodu (en)
    voices: tuple[str, ...]  # edge-tts sesleri


LANGUAGES: dict[str, LanguageProfile] = {
    "tr": LanguageProfile("Türkçe",        "tr-TR", "tr", ("tr-TR-EmelNeural", "tr-TR-AhmetNeural")),
    "en": LanguageProfile("İngilizce",     "en-US", "en", ("en-US-AriaNeural", "en-US-GuyNeural", "en-GB-SoniaNeural")),
    "de": LanguageProfile("Almanca",       "de-DE", "de", ("de-DE-KatjaNeural", "de-DE-ConradNeural")),
    "fr": LanguageProfile("Fransızca",     "fr-FR", "fr", ("fr-FR-DeniseNeural", "fr-FR-HenriNeural")),
    "es": LanguageProfile("İspanyolca",    "es-ES", "es", ("es-ES-ElviraNeural", "es-ES-AlvaroNeural")),
    "it": LanguageProfile("İtalyanca",     "it-IT", "it", ("it-IT-ElsaNeural", "it-IT-DiegoNeural")),
    "pt": LanguageProfile("Portekizce",    "pt-BR", "pt", ("pt-BR-FranciscaNeural", "pt-BR-AntonioNeural")),
    "ru": LanguageProfile("Rusça",         "ru-RU", "ru", ("ru-RU-SvetlanaNeural", "ru-RU-DmitryNeural")),
    "ar": LanguageProfile("Arapça",        "ar-SA", "ar", ("ar-SA-ZariyahNeural", "ar-SA-HamedNeural")),
    "ja": LanguageProfile("Japonca",       "ja-JP", "ja", ("ja-JP-NanamiNeural", "ja-JP-KeitaNeural")),
    "ko": LanguageProfile("Korece",        "ko-KR", "ko", ("ko-KR-SunHiNeural", "ko-KR-InJoonNeural")),
    "zh-CN": LanguageProfile("Çince (Basit.)", "zh-CN", "zh-CN", ("zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural")),
    "hi": LanguageProfile("Hintçe",        "hi-IN", "hi", ("hi-IN-SwaraNeural", "hi-IN-MadhurNeural")),
    "nl": LanguageProfile("Felemenkçe",    "nl-NL", "nl", ("nl-NL-ColetteNeural", "nl-NL-MaartenNeural")),
    "pl": LanguageProfile("Lehçe",         "pl-PL", "pl", ("pl-PL-ZofiaNeural", "pl-PL-MarekNeural")),
    "sv": LanguageProfile("İsveççe",       "sv-SE", "sv", ("sv-SE-SofieNeural", "sv-SE-MattiasNeural")),
    "uk": LanguageProfile("Ukraynaca",     "uk-UA", "uk", ("uk-UA-PolinaNeural", "uk-UA-OstapNeural")),
    "fa": LanguageProfile("Farsça",        "fa-IR", "fa", ("fa-IR-DilaraNeural", "fa-IR-FaridNeural")),
    "az": LanguageProfile("Azerice",       "az-AZ", "az", ("az-AZ-BanuNeural", "az-AZ-BabekNeural")),
    "id": LanguageProfile("Endonezce",     "id-ID", "id", ("id-ID-GadisNeural", "id-ID-ArdiNeural")),
    "vi": LanguageProfile("Vietnamca",     "vi-VN", "vi", ("vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural")),
    "th": LanguageProfile("Tayca",         "th-TH", "th", ("th-TH-PremwadeeNeural", "th-TH-NiwatNeural")),
    "el": LanguageProfile("Yunanca",       "el-GR", "el", ("el-GR-AthinaNeural", "el-GR-NestorasNeural")),
    "cs": LanguageProfile("Çekçe",         "cs-CZ", "cs", ("cs-CZ-VlastaNeural", "cs-CZ-AntoninNeural")),
    "ro": LanguageProfile("Rumence",       "ro-RO", "ro", ("ro-RO-AlinaNeural", "ro-RO-EmilNeural")),
    "hu": LanguageProfile("Macarca",       "hu-HU", "hu", ("hu-HU-NoemiNeural", "hu-HU-TamasNeural")),
    "da": LanguageProfile("Danca",         "da-DK", "da", ("da-DK-ChristelNeural", "da-DK-JeppeNeural")),
    "fi": LanguageProfile("Fince",         "fi-FI", "fi", ("fi-FI-NooraNeural", "fi-FI-HarriNeural")),
    "bg": LanguageProfile("Bulgarca",      "bg-BG", "bg", ("bg-BG-KalinaNeural", "bg-BG-BorislavNeural")),
    "hr": LanguageProfile("Hırvatça",      "hr-HR", "hr", ("hr-HR-GabrijelaNeural", "hr-HR-SreckoNeural")),
    "sk": LanguageProfile("Slovakça",      "sk-SK", "sk", ("sk-SK-ViktoriaNeural", "sk-SK-LukasNeural")),
    "ms": LanguageProfile("Malayca",       "ms-MY", "ms", ("ms-MY-YasminNeural", "ms-MY-OsmanNeural")),
    "bn": LanguageProfile("Bengalce",      "bn-IN", "bn", ("bn-IN-TanishaaNeural", "bn-IN-BashkarNeural")),
    "ur": LanguageProfile("Urduca",        "ur-PK", "ur", ("ur-PK-UzmaNeural", "ur-PK-AsadNeural")),
    "ta": LanguageProfile("Tamilce",       "ta-IN", "ta", ("ta-IN-PallaviNeural", "ta-IN-ValluvarNeural")),
    "ka": LanguageProfile("Gürcüce",       "ka-GE", "ka", ("ka-GE-EkaNeural", "ka-GE-GiorgiNeural")),
    "kk": LanguageProfile("Kazakça",       "kk-KZ", "kk", ("kk-KZ-AigulNeural", "kk-KZ-DauletNeural")),
}


# Kaynak dil olarak seçilince dili Whisper buluyor (Google tanıma dil kodu istiyor)
AUTO_LANGUAGE = "auto"


@dataclass
class AppConfig:
    """Çalışma anı ayarları. Yakalama ve pipeline thread'leri her turda
    buradan okuduğu için arayüzdeki değişiklik anında etki eder."""
    source_lang: str = "en"
    target_lang: str = "tr"
    dubbing_enabled: bool = False
    voice: str = "tr-TR-EmelNeural"
    tts_rate: str = "+15%"

    stt_engine: str = "google"           # "google" ya da "whisper" (faster-whisper kuruluysa)
    translation_engine: str = "classic"  # "classic" (Google/MyMemory) ya da "claude" (bağlamlı, anahtar ister)
    llm_model: str = "claude-haiku-5-5"
    whisper_model: str = "base"

    target_sample_rate: int = 16000      # STT'ye giden örnekleme hızı
    silence_threshold: float = 0.010     # RMS eşiği (0.0 - 1.0)
    gate_mode: str = "rms"               # "rms": sabit eşik, "auto": gürültü tabanına göre (müzik altında konuşma)
    silence_duration: float = 0.35       # cümle bitti sayılacak sessizlik (sn)
    min_segment_sec: float = 0.40        # bundan kısa segmentler atılır
    max_segment_sec: float = 6.0         # bu süreye ulaşınca zorla gönderilir
    pre_roll_sec: float = 0.30           # kelime başı kesilmesin diye konuşma öncesi tampon

    streaming_enabled: bool = True       # konuşma sürerken kısmi altyazı akıt
    partial_interval_sec: float = 0.9
    partial_min_sec: float = 0.7         # bundan kısa konuşmada kısmi gönderme

    subtitle_font_size: int = 30
    subtitle_width_pct: int = 80         # ekran genişliğine oran
    subtitle_bottom_margin: int = 90     # ekranın altından yükseklik (px)
    subtitle_hold_sec: float = 6.0
    subtitle_opacity: int = 78           # arka plan opaklığı (%), 78 ≈ eski sabit 200/255
    subtitle_screen: str = ""            # ekran adı; boşsa birincil ekran
    subtitle_show_previous: bool = False  # önceki cümlenin çevirisi üstte soluk dursun
    subtitle_color: str = "#FFFFFF"
    show_original: bool = True

    web_output_enabled: bool = False     # OBS Browser Source / tarayıcı için yerel çıktı
    web_output_port: int = 8765
    web_output_token: str = ""           # ilk açılışta üretilip saklanıyor

    mute_capture_while_dubbing: bool = True
    dubbing_tail_sec: float = 0.45       # dublaj bittikten sonra da bir süre dinleme

    def profile(self, code: str) -> LanguageProfile:
        return LANGUAGES.get(code, LANGUAGES["en"])
