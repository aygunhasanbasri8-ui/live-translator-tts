"""Kontrol paneli; servisleri kurup birbirine bağlayan yer burası."""
from __future__ import annotations

import queue
import threading
from typing import Optional

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSlot

from .audio_player import create_audio_player
from .capture import AudioSegment, LoopbackAudioCapturer
from .config import LANGUAGES, AppConfig
from .hotkeys import HotkeyManager
from .log import LOGGER
from .overlay import SubtitleOverlay
from .pipeline import PipelineWorker
from .queues import drain
from .settings import load_config, open_settings, save_config
from .speech import SpeechToTextService, TranslatorService
from .tts import TTSService
from .whisper_stt import WHISPER_MODELS

TTS_RATES = ("+0%", "+10%", "+15%", "+25%", "+40%")
BUTTON_STYLE = "QPushButton { padding: 10px; font-weight: bold; }"


def _select(combo: QtWidgets.QComboBox, value) -> None:
    """Kayıtlı değer artık listede yoksa (eski sürümden kalma) varsayılan seçim kalır."""
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config = AppConfig()
        self._settings = open_settings()
        load_config(self.config, self._settings)

        self._audio_queue: "queue.Queue[AudioSegment]" = queue.Queue(maxsize=12)
        self._speaking_flag = threading.Event()
        self._stt = SpeechToTextService()
        self._translator = TranslatorService()
        self._tts = TTSService(create_audio_player(), self._speaking_flag,
                               on_error=self._append_warning)
        self._tts.start()

        self._capturer: Optional[LoopbackAudioCapturer] = None
        self._pipeline: Optional[PipelineWorker] = None
        self._running = False

        self.overlay = SubtitleOverlay(self.config)
        self.hotkeys = HotkeyManager(self)

        self._build_ui()
        self._connect_hotkeys()
        self._sync_config_from_ui()
        geometry = self._settings.value("window_geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        QTimer.singleShot(60, self.overlay.prime)

    def _build_ui(self) -> None:
        self.setWindowTitle("Canlı Sistem Sesi Çevirmeni — Altyazı + Dublaj")
        self.setMinimumSize(560, 620)

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

        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Hazır.")

        self._connect_ui_signals()
        self._refresh_voices()

    def _build_language_box(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Diller")
        layout = QtWidgets.QGridLayout(box)

        self.source_combo = QtWidgets.QComboBox()
        self.target_combo = QtWidgets.QComboBox()
        for code, profile in LANGUAGES.items():
            self.source_combo.addItem(profile.label, code)
            self.target_combo.addItem(profile.label, code)
        _select(self.source_combo, self.config.source_lang)
        _select(self.target_combo, self.config.target_lang)

        layout.addWidget(QtWidgets.QLabel("Kaynak dil (videonun dili):"), 0, 0)
        layout.addWidget(self.source_combo, 0, 1)
        layout.addWidget(QtWidgets.QLabel("Hedef dil (çeviri):"), 1, 0)
        layout.addWidget(self.target_combo, 1, 1)

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
        layout.addLayout(engine_row, 2, 1)
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

    def _build_tuning_box(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Hassasiyet ve Görünüm")
        layout = QtWidgets.QGridLayout(box)

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

        layout.addWidget(QtWidgets.QLabel("Sessizlik eşiği:"), 0, 0)
        layout.addWidget(self.threshold_slider, 0, 1)
        layout.addWidget(self.threshold_value, 0, 2)
        layout.addWidget(QtWidgets.QLabel("Cümle sonu bekleme:"), 1, 0)
        layout.addWidget(self.silence_spin, 1, 1, 1, 2)
        layout.addWidget(QtWidgets.QLabel("Altyazı yazı boyutu:"), 2, 0)
        layout.addWidget(self.font_spin, 2, 1, 1, 2)
        layout.addWidget(QtWidgets.QLabel("Altyazı genişliği:"), 3, 0)
        layout.addWidget(self.width_slider, 3, 1)
        layout.addWidget(self.width_value, 3, 2)
        layout.addWidget(QtWidgets.QLabel("Yükseklik (alttan):"), 4, 0)
        layout.addWidget(self.margin_spin, 4, 1, 1, 2)
        layout.addWidget(QtWidgets.QLabel("Zemin opaklığı:"), 5, 0)
        layout.addWidget(self.opacity_slider, 5, 1)
        layout.addWidget(self.opacity_value, 5, 2)

        self.level_bar = QtWidgets.QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setTextVisible(False)
        self.level_bar.setFixedHeight(10)
        layout.addWidget(QtWidgets.QLabel("Sistem ses seviyesi:"), 6, 0)
        layout.addWidget(self.level_bar, 6, 1, 1, 2)
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

    def _connect_ui_signals(self) -> None:
        self.start_button.clicked.connect(self.start_translation)
        self.stop_button.clicked.connect(self.stop_translation)
        self.source_combo.currentIndexChanged.connect(self._sync_config_from_ui)
        self.engine_combo.currentIndexChanged.connect(self._sync_config_from_ui)
        self.whisper_model_combo.currentIndexChanged.connect(self._sync_config_from_ui)
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
        if self._stt.whisper is not None:
            self._stt.whisper.set_model_size(self.config.whisper_model)

    @pyqtSlot()
    def start_translation(self) -> None:
        if self._running:
            return
        if self.config.source_lang == self.config.target_lang:
            self._append_warning("Kaynak ve hedef dil aynı; çeviri yapılmayacak.")

        self._sync_config_from_ui()
        save_config(self.config, self._settings)
        drain(self._audio_queue)
        self._warm_up_services()

        self._pipeline = PipelineWorker(self.config, self._audio_queue, self._stt,
                                        self._translator, self._tts, parent=self)
        self._pipeline.subtitle_ready.connect(self.overlay.show_subtitle)
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
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.overlay.show()
        self.overlay.show_subtitle("", "🎧 Dinleniyor...")
        self._append_log("▶ Başlatıldı.")

    @pyqtSlot()
    def stop_translation(self) -> None:
        if not self._running:
            return
        self._running = False

        self._stop_worker(self._capturer, 4000, "Yakalayıcı")
        self._capturer = None
        self._stop_worker(self._pipeline, 6000, "Pipeline")
        self._pipeline = None

        self._tts.clear()
        drain(self._audio_queue)

        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.level_bar.setValue(0)
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

    @pyqtSlot(float)
    def _on_level(self, level: float) -> None:
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
            save_config(self.config, self._settings)
            self._settings.setValue("window_geometry", self.saveGeometry())
            self.hotkeys.uninstall()
            self._tts.shutdown()
            self.overlay.close()
        except Exception as exc:
            LOGGER.warning("Kapanış sırasında hata: %s", exc)
        super().closeEvent(event)
