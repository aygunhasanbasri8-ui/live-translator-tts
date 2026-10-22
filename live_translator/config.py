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
}


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
    whisper_model: str = "base"

    target_sample_rate: int = 16000      # STT'ye giden örnekleme hızı
    silence_threshold: float = 0.010     # RMS eşiği (0.0 - 1.0)
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
    show_original: bool = True

    mute_capture_while_dubbing: bool = True
    dubbing_tail_sec: float = 0.45       # dublaj bittikten sonra da bir süre dinleme

    def profile(self, code: str) -> LanguageProfile:
        return LANGUAGES.get(code, LANGUAGES["en"])
