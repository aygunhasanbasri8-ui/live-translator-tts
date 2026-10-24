"""Kontrol paneli; servisleri kurup birbirine bağlayan yer burası."""
from __future__ import annotations

import os
import queue
import threading
from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal, pyqtSlot

from ._version import __version__
from .audio_player import create_audio_player
from .capture import AudioSegment, LoopbackAudioCapturer
from .config import AUTO_LANGUAGE, LANGUAGES, AppConfig
from .hotkeys import HotkeyManager
from .llm_translate import (MODELS as LLM_MODELS, ClaudeTranslator, ConversationContext, Glossary,
                            anthropic_available, load_api_key, mask_key, save_api_key)
from .log import LOGGER
from .overlay import SubtitleOverlay
from .pipeline import PipelineWorker
from .queues import drain
from .settings import load_config, open_settings, save_config
from .speech import SpeechToTextService, TranslatorService
from .transcript import Transcript
from .tray import AppTray
from .tts import TTSService
from .whisper_stt import WHISPER_MODELS

TTS_RATES = ("+0%", "+10%", "+15%", "+25%", "+40%")
SUBTITLE_COLORS = (("Beyaz", "#FFFFFF"), ("Sarı", "#FFE14D"), ("Açık yeşil", "#B5F5A8"),
                   ("Açık mavi", "#A8D8FF"))
BUTTON_STYLE = "QPushButton { padding: 10px; font-weight: bold; }"
LLM_PRIVACY_TEXT = (
    "Claude çevirisi açıkken konuşmanın METNİ (ses değil), önceki birkaç cümle ve\n"
    "sözlükten ilgili terimler Anthropic API'sine gönderilir. İstekler sizin\n"
    "anahtarınızla faturalanır (Haiku ile saatlik konuşma yaklaşık birkaç sent).\n\n"
    "Devam edilsin mi?"
)


def _config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "LiveTranslator")


def _select(combo: QtWidgets.QComboBox, value, fallback=None) -> None:
    """Kayıtlı değer artık listede yoksa (eski sürümden ya da Whisper kurulu
    başka makineden kalma) fallback, o da yoksa mevcut seçim kalır."""
    for candidate in (value, fallback):
        index = combo.findData(candidate)
        if candidate is not None and index >= 0:
            combo.setCurrentIndex(index)
            return


class MainWindow(QtWidgets.QMainWindow):
    # TTS ve model yükleme kendi thread'lerinden haber veriyor; widget'a oradan
    # dokunmak Qt'yi çökertebildiği için sinyalle ana thread'e taşıyoruz.
    _thread_warning = pyqtSignal(str)
    _thread_log = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.config = AppConfig()
        self._settings = open_settings()
        load_config(self.config, self._settings)

        self._audio_queue: "queue.Queue[AudioSegment]" = queue.Queue(maxsize=12)
        self._speaking_flag = threading.Event()
        self._stt = SpeechToTextService()
        self._translator = TranslatorService()
        self._llm_context = ConversationContext()
        self._glossary = Glossary(os.path.join(_config_dir(), "glossary.json"))
        self._tts = TTSService(create_audio_player(), self._speaking_flag,
                               on_error=self._thread_warning.emit)
        self._thread_warning.connect(self._append_warning)
        self._thread_log.connect(self._append_log)
        self._whisper_loading = False
        self._tts.start()

        self._capturer: Optional[LoopbackAudioCapturer] = None
        self._pipeline: Optional[PipelineWorker] = None
        self._running = False
        self.transcript = Transcript()

        self.overlay = SubtitleOverlay(self.config)
        self.hotkeys = HotkeyManager(self)

        self._build_ui()
        self._connect_hotkeys()
        self._build_tray()
        self._sync_config_from_ui()
        geometry = self._settings.value("window_geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        QTimer.singleShot(60, self.overlay.prime)

    def _build_ui(self) -> None:
        self.setWindowTitle(f"Canlı Sistem Sesi Çevirmeni — Altyazı + Dublaj  v{__version__}")
        self.setMinimumWidth(560)

        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        root.addWidget(self._build_language_box())
        root.addWidget(self._build_mode_box())
        root.addWidget(self._build_tuning_box())
        root.addLayout(self._build_buttons())

        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(400)
        self.log_view.setPlaceholderText("Tanınan ve çevrilen metinler burada görünür...")
        root.addWidget(self.log_view, 1)
        root.addLayout(self._build_transcript_row())

        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Hazır.")
        # Google sınırladığında altyazının neden yavaşladığı/yedekten geldiği görünsün
        self.service_label = QtWidgets.QLabel()
        self.status_bar.addPermanentWidget(self.service_label)
        self._service_timer = QTimer(self)
        self._service_timer.setInterval(1000)
        self._service_timer.timeout.connect(self._refresh_service_status)

        self._connect_ui_signals()
        self._refresh_voices()

    def _build_language_box(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Diller")
        layout = QtWidgets.QGridLayout(box)

        self.source_combo = QtWidgets.QComboBox()
        self.target_combo = QtWidgets.QComboBox()
        if self._stt.whisper is not None:
            self.source_combo.addItem("Otomatik algıla (Whisper)", AUTO_LANGUAGE)
            self.source_combo.setItemData(
                0, "Dili Whisper buluyor; tanıma motoru seçiminden bağımsız olarak\n"
                   "Whisper kullanılır. Karışık dilli içerik için.",
                Qt.ItemDataRole.ToolTipRole)
        for code, profile in LANGUAGES.items():
            self.source_combo.addItem(profile.label, code)
            self.target_combo.addItem(profile.label, code)
        defaults = AppConfig()
        _select(self.source_combo, self.config.source_lang, defaults.source_lang)
        _select(self.target_combo, self.config.target_lang, defaults.target_lang)

        layout.addWidget(QtWidgets.QLabel("Kaynak dil (videonun dili):"), 0, 0)
        layout.addWidget(self.source_combo, 0, 1)
        layout.addWidget(QtWidgets.QLabel("Hedef dil (çeviri):"), 1, 0)
        layout.addWidget(self.target_combo, 1, 1)

        # Görüntülü görüşmede karşı taraf değişince iki combo'yu tek tek
        # çevirmek zahmetli
        self.swap_button = QtWidgets.QToolButton()
        self.swap_button.setText("⇅")
        self.swap_button.setToolTip("Kaynak ve hedef dili yer değiştir")
        layout.addWidget(self.swap_button, 0, 2, 2, 1)

        self.engine_combo = QtWidgets.QComboBox()
        self.engine_combo.addItem("Google (çevrimiçi)", "google")
        self.engine_combo.addItem("Whisper (yerel, çevrimdışı)", "whisper")
        self.whisper_model_combo = QtWidgets.QComboBox()
        for size in WHISPER_MODELS:
            self.whisper_model_combo.addItem(size, size)
        _select(self.whisper_model_combo, self.config.whisper_model)
        self.whisper_model_combo.setToolTip(
            "tiny: en hızlı, base: dengeli, small: en doğru ama CPU'yu zorlar.\n"
            "Model ilk kullanımda bir kez indirilir.")

        if self._stt.whisper is None:
            self.engine_combo.model().item(1).setEnabled(False)
            self.engine_combo.setToolTip(
                "Yerel tanıma için: pip install \".[whisper]\"\n"
                "Kuruluysa Google sınırladığında otomatik yedek olarak da kullanılır.")
            self.whisper_model_combo.setEnabled(False)
        else:
            self.engine_combo.setToolTip(
                "Google seçiliyken Google sınırlarsa Whisper otomatik devreye girer.")
            _select(self.engine_combo, self.config.stt_engine)

        engine_row = QtWidgets.QHBoxLayout()
        engine_row.addWidget(self.engine_combo, 1)
        engine_row.addWidget(QtWidgets.QLabel("Model:"))
        engine_row.addWidget(self.whisper_model_combo)
        layout.addWidget(QtWidgets.QLabel("Tanıma motoru:"), 2, 0)
        layout.addLayout(engine_row, 2, 1, 1, 2)

        self.translation_combo = QtWidgets.QComboBox()
        self.translation_combo.addItem("Klasik (Google, ücretsiz)", "classic")
        for model, label in LLM_MODELS:
            self.translation_combo.addItem(f"{label}: bağlamlı", f"claude:{model}")
        self.translation_combo.setToolTip(
            "Claude önceki cümleleri ve sözlüğünüzü de dikkate alarak çevirir (yalnız kesin\n"
            "cümlelerde; kısmi altyazılar yine Google'la akar). Kendi Anthropic anahtarınız gerekir.\n"
            "Hata ya da gecikmede cümle Google'la çevrilir.")
        current = ("classic" if self.config.translation_engine != "claude"
                   else f"claude:{self.config.llm_model}")
        _select(self.translation_combo, current, "classic")
        self.llm_key_button = QtWidgets.QToolButton()
        self.llm_key_button.setText("Anahtar…")
        self.llm_key_button.setToolTip("Anthropic API anahtarı (Windows Kimlik Bilgisi Yöneticisi'nde saklanır)")
        self.glossary_button = QtWidgets.QToolButton()
        self.glossary_button.setText("Sözlük…")
        self.glossary_button.setToolTip("Oyun terimleri, karakter adları gibi sabit çeviriler (JSON dosyası)")
        if not anthropic_available():
            for i in range(1, self.translation_combo.count()):
                self.translation_combo.model().item(i).setEnabled(False)
            self.translation_combo.setToolTip("Claude çevirisi için: pip install \".[llm]\"")
            self.llm_key_button.setEnabled(False)

        translation_row = QtWidgets.QHBoxLayout()
        translation_row.addWidget(self.translation_combo, 1)
        translation_row.addWidget(self.llm_key_button)
        translation_row.addWidget(self.glossary_button)
        layout.addWidget(QtWidgets.QLabel("Çeviri motoru:"), 3, 0)
        layout.addLayout(translation_row, 3, 1, 1, 2)
        return box

    def _build_mode_box(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Mod")
        layout = QtWidgets.QVBoxLayout(box)
        self.radio_subtitle = QtWidgets.QRadioButton("Sadece Altyazı")
        self.radio_dubbing = QtWidgets.QRadioButton("Altyazı + Dublaj (Edge-TTS)")
        self.radio_subtitle.setChecked(not self.config.dubbing_enabled)
        self.radio_dubbing.setChecked(self.config.dubbing_enabled)
        layout.addWidget(self.radio_subtitle)
        layout.addWidget(self.radio_dubbing)

        voice_row = QtWidgets.QHBoxLayout()
        self.voice_combo = QtWidgets.QComboBox()
        self.rate_combo = QtWidgets.QComboBox()
        for rate in TTS_RATES:
            self.rate_combo.addItem(rate, rate)
        _select(self.rate_combo, self.config.tts_rate)
        voice_row.addWidget(QtWidgets.QLabel("Ses:"))
        voice_row.addWidget(self.voice_combo, 1)
        voice_row.addWidget(QtWidgets.QLabel("Hız:"))
        voice_row.addWidget(self.rate_combo)
        self.preview_voice_button = QtWidgets.QToolButton()
        self.preview_voice_button.setText("▶")
        self.preview_voice_button.setToolTip("Seçili sesi ve hızı dinle")
        voice_row.addWidget(self.preview_voice_button)
        layout.addLayout(voice_row)

        self.check_show_original = QtWidgets.QCheckBox("Altyazıda orijinal metni de göster")
        self.check_show_original.setChecked(self.config.show_original)
        layout.addWidget(self.check_show_original)

        self.check_streaming = QtWidgets.QCheckBox(
            "Akıcı mod: cümle bitmeden altyazıyı canlı akıt")
        self.check_streaming.setChecked(self.config.streaming_enabled)
        self.check_streaming.setToolTip(
            "Açık: konuşma sürerken altyazı ~1 sn'de bir güncellenir (akıcı).\n"
            "Kapalı: yalnızca cümle bitince tek seferde görünür (daha az veri)."
        )
        layout.addWidget(self.check_streaming)
        return box

    def _build_tuning_box(self) -> QtWidgets.QWidget:
        box = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)

        self.threshold_slider = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        # /10000 ile 0.0001 - 0.0500 arası. Varsayılan 0.0100 aralığın alt
        # beşte birinde; gürültülü içerikte eşik yükseltilebilsin diye.
        self.threshold_slider.setRange(1, 500)
        self.threshold_slider.setValue(int(self.config.silence_threshold * 10000))
        self.threshold_slider.setToolTip(
            "Sola: daha hassas (kısık sesleri de yakalar).\n"
            "Sağa: daha seçici (arka plan gürültüsünü eler)."
        )
        self.threshold_value = QtWidgets.QLabel(f"{self.config.silence_threshold:.4f}")

        # Gecikmenin doğrudan bileşeni: küçük değer altyazıyı hızlandırır
        # ama cümleler ortadan bölünebilir.
        self.silence_spin = QtWidgets.QDoubleSpinBox()
        self.silence_spin.setRange(0.15, 1.50)
        self.silence_spin.setSingleStep(0.05)
        self.silence_spin.setDecimals(2)
        self.silence_spin.setSuffix(" sn")
        self.silence_spin.setValue(self.config.silence_duration)
        self.silence_spin.setToolTip(
            "Cümlenin bittiğine karar vermeden önce beklenen sessizlik.\n"
            "Düşürmek altyazıyı hızlandırır; çok düşük olursa cümleler bölünür."
        )

        self.font_spin = QtWidgets.QSpinBox()
        self.font_spin.setRange(14, 96)
        self.font_spin.setValue(self.config.subtitle_font_size)

        self.width_slider = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        self.width_slider.setRange(20, 100)
        self.width_slider.setValue(self.config.subtitle_width_pct)
        self.width_slider.setToolTip("Altyazı şeridinin ekran genişliğine oranı (kenarlara doğru).")
        self.width_value = QtWidgets.QLabel(f"%{self.config.subtitle_width_pct}")

        self.margin_spin = QtWidgets.QSpinBox()
        self.margin_spin.setRange(0, 2000)      # ekranın en altından en üstüne
        self.margin_spin.setSingleStep(10)
        self.margin_spin.setSuffix(" px")
        self.margin_spin.setValue(self.config.subtitle_bottom_margin)
        self.margin_spin.setToolTip("Ekranın altından yükseklik. Büyüt = altyazı yukarı çıkar.")

        self.opacity_slider = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(self.config.subtitle_opacity)
        self.opacity_slider.setToolTip("Altyazı zemininin koyuluğu. 0: yalnızca yazı.")
        self.opacity_value = QtWidgets.QLabel(f"%{self.config.subtitle_opacity}")

        self.screen_combo = QtWidgets.QComboBox()
        self.screen_combo.addItem("Birincil ekran", "")
        for screen in QtWidgets.QApplication.screens():
            if not screen.name():
                continue
            geo = screen.geometry()
            self.screen_combo.addItem(f"{screen.name()} ({geo.width()}x{geo.height()})", screen.name())
        _select(self.screen_combo, self.config.subtitle_screen)

        # Hepsi alt alta tek kutudayken pencere 800 px'i aşıyor, küçük
        # ekranlarda satırlar üst üste biniyordu; iki sekmeye bölündü.
        sensitivity = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(sensitivity)
        grid.addWidget(QtWidgets.QLabel("Sessizlik eşiği:"), 0, 0)
        grid.addWidget(self.threshold_slider, 0, 1)
        grid.addWidget(self.threshold_value, 0, 2)
        grid.addWidget(QtWidgets.QLabel("Cümle sonu bekleme:"), 1, 0)
        grid.addWidget(self.silence_spin, 1, 1, 1, 2)
        grid.setRowStretch(2, 1)

        self.color_combo = QtWidgets.QComboBox()
        for name, color in SUBTITLE_COLORS:
            self.color_combo.addItem(name, color)
        _select(self.color_combo, self.config.subtitle_color)
        self.check_show_previous = QtWidgets.QCheckBox("Önceki cümleyi de göster")
        self.check_show_previous.setChecked(self.config.subtitle_show_previous)
        self.check_show_previous.setToolTip("Bir önceki cümlenin çevirisi üstte soluk olarak durur.")

        appearance = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(appearance)
        grid.addWidget(QtWidgets.QLabel("Yazı boyutu:"), 0, 0)
        grid.addWidget(self.font_spin, 0, 1)
        grid.addWidget(QtWidgets.QLabel("Renk:"), 0, 2)
        grid.addWidget(self.color_combo, 0, 3, 1, 2)
        grid.addWidget(QtWidgets.QLabel("Genişlik:"), 1, 0)
        grid.addWidget(self.width_slider, 1, 1, 1, 3)
        grid.addWidget(self.width_value, 1, 4)
        grid.addWidget(QtWidgets.QLabel("Zemin opaklığı:"), 2, 0)
        grid.addWidget(self.opacity_slider, 2, 1, 1, 3)
        grid.addWidget(self.opacity_value, 2, 4)
        grid.addWidget(QtWidgets.QLabel("Yükseklik (alttan):"), 3, 0)
        grid.addWidget(self.margin_spin, 3, 1)
        grid.addWidget(QtWidgets.QLabel("Ekran:"), 3, 2)
        grid.addWidget(self.screen_combo, 3, 3, 1, 2)
        grid.addWidget(self.check_show_previous, 4, 0, 1, 5)

        tabs = QtWidgets.QTabWidget()
        tabs.addTab(sensitivity, "Hassasiyet")
        tabs.addTab(appearance, "Altyazı görünümü")

        self.level_bar = QtWidgets.QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setTextVisible(False)
        self.level_bar.setFixedHeight(10)
        level_row = QtWidgets.QHBoxLayout()
        level_row.addWidget(QtWidgets.QLabel("Sistem ses seviyesi:"))
        level_row.addWidget(self.level_bar, 1)

        layout.addWidget(tabs)
        layout.addLayout(level_row)
        return box

    def _build_buttons(self) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        self.start_button = QtWidgets.QPushButton("▶  Başlat  (Ctrl+Shift+R)")
        self.stop_button = QtWidgets.QPushButton("■  Durdur  (Ctrl+Shift+S)")
        self.stop_button.setEnabled(False)
        for button in (self.start_button, self.stop_button):
            button.setStyleSheet(BUTTON_STYLE)
            row.addWidget(button)
        return row

    def _build_transcript_row(self) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        self.transcript_label = QtWidgets.QLabel()
        self.export_button = QtWidgets.QPushButton("Altyazıları kaydet...")
        self.export_button.setToolTip("Kesinleşmiş cümleleri SRT ya da metin olarak kaydeder.")
        self.clear_transcript_button = QtWidgets.QPushButton("Temizle")
        row.addWidget(self.transcript_label, 1)
        row.addWidget(self.export_button)
        row.addWidget(self.clear_transcript_button)
        self._update_transcript_label()
        return row

    def _connect_ui_signals(self) -> None:
        self.start_button.clicked.connect(self.start_translation)
        self.stop_button.clicked.connect(self.stop_translation)
        self.export_button.clicked.connect(self._export_transcript)
        self.clear_transcript_button.clicked.connect(self._clear_transcript)
        self.source_combo.currentIndexChanged.connect(self._sync_config_from_ui)
        self.swap_button.clicked.connect(self._swap_languages)
        self.preview_voice_button.clicked.connect(self._preview_voice)
        self.engine_combo.currentIndexChanged.connect(self._sync_config_from_ui)
        self.whisper_model_combo.currentIndexChanged.connect(self._sync_config_from_ui)
        self.translation_combo.activated.connect(self._on_translation_engine_chosen)
        self.translation_combo.currentIndexChanged.connect(self._sync_config_from_ui)
        self.llm_key_button.clicked.connect(self._ask_llm_key)
        self.glossary_button.clicked.connect(self._open_glossary)
        self.target_combo.currentIndexChanged.connect(self._on_target_changed)
        self.radio_subtitle.toggled.connect(self._sync_config_from_ui)
        self.radio_dubbing.toggled.connect(self._sync_config_from_ui)
        self.voice_combo.currentIndexChanged.connect(self._sync_config_from_ui)
        self.rate_combo.currentIndexChanged.connect(self._sync_config_from_ui)
        self.check_show_original.toggled.connect(self._sync_config_from_ui)
        self.check_streaming.toggled.connect(self._sync_config_from_ui)
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        self.silence_spin.valueChanged.connect(self._on_silence_changed)
        self.font_spin.valueChanged.connect(self._on_appearance_changed)
        self.width_slider.valueChanged.connect(self._on_appearance_changed)
        self.margin_spin.valueChanged.connect(self._on_appearance_changed)
        self.opacity_slider.valueChanged.connect(self._on_appearance_changed)
        self.screen_combo.currentIndexChanged.connect(self._on_appearance_changed)
        self.check_show_previous.toggled.connect(self._on_appearance_changed)
        self.color_combo.currentIndexChanged.connect(self._on_appearance_changed)

    def _build_tray(self) -> None:
        icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaVolume)
        self.setWindowIcon(icon)
        self.tray = AppTray.create(icon, self)
        if self.tray is None:
            return
        self.tray.toggle_running_requested.connect(self._toggle_running)
        self.tray.toggle_overlay_requested.connect(self._toggle_overlay)
        self.tray.restore_requested.connect(self._restore_from_tray)
        self.tray.quit_requested.connect(self._quit)

    def _quit(self) -> None:
        # Pencere tepsideyken (gizli) close() son görünür pencere kapanmış
        # sayılmıyor ve uygulama arkada açık kalıyordu.
        self.close()
        QtWidgets.QApplication.quit()

    def _toggle_running(self) -> None:
        if self._running:
            self.stop_translation()
        else:
            self.start_translation()

    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def changeEvent(self, event: QtCore.QEvent) -> None:  # noqa: N802 (Qt API)
        super().changeEvent(event)
        # Pencere kurulurken de çağrılıyor, tepsi o sırada henüz yok
        if (getattr(self, "tray", None) is not None
                and event.type() == QtCore.QEvent.Type.WindowStateChange
                and self.isMinimized()):
            # Doğrudan hide() olay işlenirken pencereyi yarım bırakabiliyor
            QTimer.singleShot(0, self.hide)
            self.tray.show_minimized_hint()

    def _update_run_state(self) -> None:
        self.start_button.setEnabled(not self._running)
        self.stop_button.setEnabled(self._running)
        if self.tray is not None:
            self.tray.set_running(self._running)

    def _connect_hotkeys(self) -> None:
        self.hotkeys.start_requested.connect(self.start_translation)
        self.hotkeys.stop_requested.connect(self.stop_translation)
        self.hotkeys.toggle_overlay_requested.connect(self._toggle_overlay)
        self.hotkeys.status_message.connect(self._append_log)
        self.hotkeys.install()

    def _refresh_voices(self) -> None:
        target = self.target_combo.currentData() or "tr"
        profile = LANGUAGES.get(target, LANGUAGES["tr"])
        self.voice_combo.blockSignals(True)
        self.voice_combo.clear()
        for voice in profile.voices:
            self.voice_combo.addItem(voice, voice)
        _select(self.voice_combo, self.config.voice)
        self.voice_combo.blockSignals(False)

    def _preview_voice(self) -> None:
        if self._running:
            return      # dublajın arasına girmesin
        self._sync_config_from_ui()
        voice, rate = self.config.voice, self.config.tts_rate
        target = self.config.profile(self.config.target_lang).translate_code
        sample = "Hello! This is how the dubbing will sound."

        def speak() -> None:
            try:
                text = self._translator.translate(sample, "en", target)
            except Exception as exc:
                LOGGER.debug("Örnek cümle çevrilemedi: %s", exc)
                text = sample
            self._tts.speak(text, voice, rate)

        threading.Thread(target=speak, name="VoicePreview", daemon=True).start()

    def _swap_languages(self) -> None:
        # İndeksle değil kodla: kaynak listesinin başında "Otomatik" de var
        source, target = self.source_combo.currentData(), self.target_combo.currentData()
        if source == AUTO_LANGUAGE:
            return
        _select(self.source_combo, target)
        _select(self.target_combo, source)

    def _on_target_changed(self) -> None:
        self._refresh_voices()
        self._sync_config_from_ui()

    def _on_threshold_changed(self, value: int) -> None:
        self.config.silence_threshold = value / 10000.0
        self.threshold_value.setText(f"{self.config.silence_threshold:.4f}")

    def _on_silence_changed(self, value: float) -> None:
        self.config.silence_duration = float(value)

    def _on_appearance_changed(self) -> None:
        self.config.subtitle_font_size = self.font_spin.value()
        self.config.subtitle_width_pct = self.width_slider.value()
        self.config.subtitle_bottom_margin = self.margin_spin.value()
        self.config.subtitle_opacity = self.opacity_slider.value()
        self.config.subtitle_screen = self.screen_combo.currentData() or ""
        self.config.subtitle_show_previous = self.check_show_previous.isChecked()
        self.config.subtitle_color = self.color_combo.currentData() or "#FFFFFF"
        self.width_value.setText(f"%{self.config.subtitle_width_pct}")
        self.opacity_value.setText(f"%{self.config.subtitle_opacity}")
        self.overlay.apply_style()
        if not self._running:
            # ayarın etkisi hemen görülsün diye örnek altyazı
            self.overlay.show_subtitle(
                "Preview — original line",
                "Örnek altyazı: konum, genişlik ve boyut böyle görünür.",
            )

    def _sync_config_from_ui(self) -> None:
        self.config.source_lang = self.source_combo.currentData() or "en"
        self.config.target_lang = self.target_combo.currentData() or "tr"
        self.config.dubbing_enabled = self.radio_dubbing.isChecked()
        self.config.voice = self.voice_combo.currentData() or "tr-TR-EmelNeural"
        self.config.tts_rate = self.rate_combo.currentData() or "+15%"
        self.config.show_original = self.check_show_original.isChecked()
        self.config.streaming_enabled = self.check_streaming.isChecked()
        self.config.stt_engine = self.engine_combo.currentData() or "google"
        self.config.whisper_model = self.whisper_model_combo.currentData() or "base"
        engine = self.translation_combo.currentData() or "classic"
        if engine.startswith("claude:"):
            self.config.translation_engine, self.config.llm_model = "claude", engine.split(":", 1)[1]
        else:
            self.config.translation_engine = "classic"
        if self._stt.whisper is not None:
            self._stt.whisper.set_model_size(self.config.whisper_model)
            self._preload_whisper()

    def _preload_whisper(self) -> None:
        """Model ilk segmentte yüklenirse (hele indirilecekse) ilk cümleler
        zaman aşımına uğrayıp kayboluyor; seçildiği anda arkada hazırlıyoruz."""
        whisper = self._stt.whisper
        if (self._effective_engine() != "whisper" or whisper.is_loaded()
                or self._whisper_loading):
            return
        self._whisper_loading = True
        self._append_log(f"Whisper '{self.config.whisper_model}' modeli hazırlanıyor "
                         "(ilk seferde indirilir)...")

        def load() -> None:
            try:
                # Yüklenirken model boyutu değiştirildiyse yenisini de hazırla
                while not whisper.is_loaded():
                    whisper.preload()
                self._thread_log.emit("Whisper modeli hazır.")
            except Exception as exc:
                self._thread_warning.emit(str(exc))
            finally:
                self._whisper_loading = False

        threading.Thread(target=load, name="WhisperLoad", daemon=True).start()

    def _on_translation_engine_chosen(self, index: int) -> None:
        """Claude seçilince bir kez gizlilik onayı; reddedilirse klasiğe döner."""
        data = self.translation_combo.itemData(index) or "classic"
        if not data.startswith("claude:") or self._settings.value("llm_privacy_ok", False, type=bool):
            return
        answer = QtWidgets.QMessageBox.question(self, "Claude çevirisi", LLM_PRIVACY_TEXT)
        if answer == QtWidgets.QMessageBox.StandardButton.Yes:
            self._settings.setValue("llm_privacy_ok", True)
            if not load_api_key():
                self._ask_llm_key()
        else:
            _select(self.translation_combo, "classic")

    def _ask_llm_key(self) -> None:
        key, ok = QtWidgets.QInputDialog.getText(
            self, "Anthropic API anahtarı",
            "Anahtar (sk-ant-...). Boş bırakıp Tamam'a basarsanız kayıtlı anahtar silinir:",
            QtWidgets.QLineEdit.EchoMode.Password)
        if not ok:
            return
        try:
            save_api_key(key.strip())
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self, "Anahtar kaydedilemedi",
                f"{mask_key(str(exc))}\n\nkeyring kurulu değilse ANTHROPIC_API_KEY ortam değişkenini kullanın.")
            return
        self._append_log("Claude anahtarı kaydedildi." if key.strip() else "Claude anahtarı silindi.")

    def _open_glossary(self) -> None:
        try:
            self._glossary.write_template()
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Sözlük açılamadı", str(exc))
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(self._glossary.path))
        self._append_log(f"Sözlük: {self._glossary.path} (kaydedince bir sonraki cümlede geçerli olur)")

    def _configure_translation_engine(self) -> None:
        if self.config.translation_engine != "claude":
            self._translator.set_llm(None)
            return
        if not anthropic_available() or not load_api_key():
            self._append_warning("Claude çevirisi seçili ama anahtar ya da paket yok; klasik çeviri kullanılıyor.")
            self._translator.set_llm(None)
            return
        self._translator.set_llm(ClaudeTranslator(self.config.llm_model, self._glossary, self._llm_context,
                                                  on_disabled=self._thread_warning.emit))
        self._append_log(f"Çeviri: {self.config.llm_model} (bağlamlı), yedek Google.")

    @pyqtSlot()
    def start_translation(self) -> None:
        if self._running:
            return
        if self.config.source_lang == self.config.target_lang:
            self._append_warning("Kaynak ve hedef dil aynı; çeviri yapılmayacak.")

        self._sync_config_from_ui()
        save_config(self.config, self._settings)
        drain(self._audio_queue)
        self._configure_translation_engine()
        self._warm_up_services()

        self._pipeline = PipelineWorker(self.config, self._audio_queue, self._stt,
                                        self._translator, self._tts, parent=self)
        self._pipeline.subtitle_ready.connect(self.overlay.show_subtitle)
        self._pipeline.line_finalized.connect(self._on_line_finalized)
        self._pipeline.log_message.connect(self._append_log)
        self._pipeline.error_occurred.connect(self._append_warning)
        self._pipeline.start()

        self._capturer = LoopbackAudioCapturer(self.config, self._audio_queue,
                                               self._speaking_flag, parent=self)
        self._capturer.status_message.connect(self._append_log)
        self._capturer.error_occurred.connect(self._on_capture_error)
        self._capturer.level_changed.connect(self._on_level)
        self._capturer.device_resolved.connect(lambda name: self.status_bar.showMessage(f"Kaynak: {name}"))
        self._capturer.start()

        self._running = True
        self._refresh_service_status()
        self._service_timer.start()
        self._update_run_state()
        self.overlay.show()
        self.overlay.show_subtitle("", "🎧 Dinleniyor...")
        self._append_log("▶ Başlatıldı.")

    @pyqtSlot()
    def stop_translation(self) -> None:
        if not self._running:
            return
        self._running = False
        self._service_timer.stop()
        self.service_label.clear()

        self._stop_worker(self._capturer, 4000, "Yakalayıcı")
        self._capturer = None
        self._stop_worker(self._pipeline, 6000, "Pipeline")
        self._pipeline = None

        self._tts.clear()
        drain(self._audio_queue)
        # Bir sonraki oturumun ilk cümlesi bu oturumun bağlamıyla çevrilmesin
        self._llm_context.clear()

        self._update_run_state()
        self.level_bar.setValue(0)
        self.overlay.clear()
        self.overlay.hide()
        self._append_log("■ Durduruldu.")
        self.status_bar.showMessage("Hazır.")

    @staticmethod
    def _stop_worker(worker: Optional[QThread], timeout_ms: int, name: str) -> None:
        if worker is None:
            return
        worker.stop()
        if not worker.wait(timeout_ms):
            LOGGER.warning("%s thread zamanında kapanmadı.", name)
        else:
            worker.deleteLater()   # tekrar tekrar başlat/durdur yapınca birikmesin

    def _warm_up_services(self) -> None:
        """İlk cümlede bağlantı kurma gecikmesi yaşanmasın diye çeviri
        servisine önden kısa bir istek atıyoruz."""
        target = self.config.profile(self.config.target_lang).translate_code
        source = self.config.profile(self.config.source_lang).translate_code

        def warm() -> None:
            try:
                self._translator.translate("hello", source, target)
            except Exception as exc:
                LOGGER.debug("Isıtma isteği başarısız (önemsiz): %s", exc)

        threading.Thread(target=warm, name="WarmUp", daemon=True).start()

    @pyqtSlot(float, float, str, str)
    def _on_line_finalized(self, start: float, end: float, original: str, translated: str) -> None:
        self.transcript.add(start, end, original, translated)
        self.overlay.remember_final(translated)
        self._update_transcript_label()

    def _update_transcript_label(self) -> None:
        count = len(self.transcript)
        self.transcript_label.setText(f"Dökümde {count} cümle" if count else "Döküm boş")
        self.export_button.setEnabled(count > 0)
        self.clear_transcript_button.setEnabled(count > 0)

    def _clear_transcript(self) -> None:
        self.transcript.clear()
        self._update_transcript_label()

    def _export_transcript(self) -> None:
        formats = {
            "Çeviri altyazısı (*.srt)": lambda: self.transcript.to_srt("translated"),
            "İki dilli altyazı (*.srt)": lambda: self.transcript.to_srt("both"),
            "Orijinal altyazı (*.srt)": lambda: self.transcript.to_srt("original"),
            "Metin dökümü (*.txt)": self.transcript.to_text,
        }
        path, chosen = QtWidgets.QFileDialog.getSaveFileName(
            self, "Altyazıları kaydet", "altyazi.srt", ";;".join(formats))
        if not path:
            return
        render = formats.get(chosen, formats["Çeviri altyazısı (*.srt)"])
        # Varsayılan ad .srt; metin dökümü seçilince uzantı da ona uysun
        wanted = ".txt" if chosen.endswith("(*.txt)") else ".srt"
        root, ext = os.path.splitext(path)
        if ext.lower() in (".srt", ".txt", "") and ext.lower() != wanted:
            path = root + wanted
        try:
            # BOM'lu UTF-8: Windows'taki bazı oynatıcılar BOM'suz dosyada Türkçe karakterleri bozuyor
            with open(path, "w", encoding="utf-8-sig", newline="\n") as f:
                f.write(render())
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Kaydedilemedi", str(exc))
            return
        self._append_log(f"💾 Kaydedildi: {path}")

    def _effective_engine(self) -> str:
        return "whisper" if self.config.source_lang == AUTO_LANGUAGE else self.config.stt_engine

    def _refresh_service_status(self) -> None:
        stt = self._stt.status(self._effective_engine())
        translation = ("—" if self.config.source_lang == self.config.target_lang
                       else self._translator.status())
        self.service_label.setText(f"Tanıma: {stt}  ·  Çeviri: {translation}")

    @pyqtSlot(float)
    def _on_level(self, level: float) -> None:
        # Durdur'dan sonra kuyrukta kalan seviye sinyalleri çubuğu dolu bırakıyordu
        if not self._running:
            return
        self.level_bar.setValue(int(max(0.0, min(level, 1.0)) * 100))

    @pyqtSlot(str)
    def _on_capture_error(self, message: str) -> None:
        self._append_warning(f"Ses yakalama hatası: {message}")
        QtWidgets.QMessageBox.critical(self, "Ses Yakalama Hatası", message)
        self.stop_translation()

    @pyqtSlot(str)
    def _append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def _append_warning(self, message: str) -> None:
        self._append_log(f"⚠ {message}")

    def _toggle_overlay(self) -> None:
        self.overlay.setVisible(not self.overlay.isVisible())

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802 (Qt API)
        try:
            self.stop_translation()
            # save_config sync ediyor; geometri ondan önce yazılmalı, kapanışta
            # os._exit QSettings'in kendi flush'ını beklemiyor
            self._settings.setValue("window_geometry", self.saveGeometry())
            save_config(self.config, self._settings)
            self.hotkeys.uninstall()
            self._tts.shutdown()
            self.overlay.close()
            if self.tray is not None:
                self.tray.hide()
        except Exception as exc:
            LOGGER.warning("Kapanış sırasında hata: %s", exc)
        super().closeEvent(event)
