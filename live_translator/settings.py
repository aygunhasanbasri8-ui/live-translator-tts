"""Kullanıcı ayarlarını oturumlar arasında saklar (Windows'ta kayıt defteri)."""
from __future__ import annotations

from PyQt6.QtCore import QSettings

from .config import AppConfig
from .log import LOGGER

# Yalnızca arayüzden değiştirilebilenler; iç ayarlar (örnekleme hızı vb.)
# saklanırsa kod tarafındaki düzeltmeler eski kurulumlara hiç ulaşmaz.
PERSISTED_FIELDS = (
    "source_lang", "target_lang", "dubbing_enabled", "voice", "tts_rate",
    "stt_engine", "whisper_model", "streaming_enabled", "show_original",
    "translation_engine", "llm_model",
    "silence_threshold", "silence_duration", "gate_mode",
    "subtitle_font_size", "subtitle_width_pct", "subtitle_bottom_margin", "subtitle_opacity",
    "subtitle_screen", "subtitle_show_previous", "subtitle_color",
)


def open_settings() -> QSettings:
    return QSettings("LiveTranslator", "LiveTranslator")


def load_config(config: AppConfig, settings: QSettings) -> None:
    for name in PERSISTED_FIELDS:
        if not settings.contains(name):
            continue
        default = getattr(config, name)
        try:
            # type= olmadan kayıt defterinden bool/int de str olarak dönüyor
            setattr(config, name, settings.value(name, default, type=type(default)))
        except (TypeError, ValueError) as exc:
            LOGGER.warning("Ayar okunamadı (%s), varsayılan kullanılıyor: %s", name, exc)


def save_config(config: AppConfig, settings: QSettings) -> None:
    for name in PERSISTED_FIELDS:
        settings.setValue(name, getattr(config, name))
    settings.sync()
