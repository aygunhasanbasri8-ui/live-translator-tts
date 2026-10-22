"""Ekranın altında duran, çerçevesiz, yarı saydam ve tıklamaları alttaki
pencereye geçiren altyazı şeridi."""
from __future__ import annotations

import ctypes
import sys
from typing import Optional

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import Qt, QTimer, pyqtSlot

from .config import AppConfig
from .log import LOGGER


class SubtitleOverlay(QtWidgets.QWidget):
    # Win32 extended window style sabitleri
    _GWL_EXSTYLE = -20
    _WS_EX_TRANSPARENT = 0x00000020
    _WS_EX_LAYERED = 0x00080000
    _WS_EX_NOACTIVATE = 0x08000000
    _WS_EX_TOOLWINDOW = 0x00000080

    _PAD_H_MAIN, _PAD_V_MAIN, _BORDER_MAIN = 22, 10, 1
    _PAD_H_SUB, _PAD_V_SUB = 16, 4
    _SPACING = 6

    def __init__(self, config: AppConfig) -> None:
        super().__init__(None)
        self._config = config

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self._SPACING)

        self._previous_label = self._make_label(is_primary=False)
        self._original_label = self._make_label(is_primary=False)
        self._translated_label = self._make_label(is_primary=True)
        for label in self._labels():
            layout.addWidget(label, 0, Qt.AlignmentFlag.AlignHCenter)
        self._last_final = ""

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._clear_text)

        self.apply_style()
        self.reposition()

    def _labels(self) -> tuple[QtWidgets.QLabel, ...]:
        return (self._previous_label, self._original_label, self._translated_label)

    def _make_label(self, is_primary: bool) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel("", self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        label.setProperty("primary", is_primary)
        label.setVisible(False)
        return label

    def apply_style(self) -> None:
        size = self._config.subtitle_font_size

        main_font = QtGui.QFont("Segoe UI")
        main_font.setPixelSize(size)
        main_font.setWeight(QtGui.QFont.Weight.DemiBold)
        self._translated_label.setFont(main_font)

        sub_font = QtGui.QFont("Segoe UI")
        sub_font.setPixelSize(max(12, int(size * 0.58)))
        sub_font.setItalic(True)
        self._original_label.setFont(sub_font)

        previous_font = QtGui.QFont("Segoe UI")
        previous_font.setPixelSize(max(12, int(size * 0.75)))
        self._previous_label.setFont(previous_font)

        # Orijinal satırın zemini ana satırınkinin 0.6'sı; eskiden 120/200'dü
        opacity = max(0, min(100, self._config.subtitle_opacity)) / 100
        alpha = int(255 * opacity)
        self._translated_label.setStyleSheet(
            f"""
            QLabel {{
                color: #FFFFFF;
                background-color: rgba(0, 0, 0, {alpha});
                border: {self._BORDER_MAIN}px solid rgba(255, 255, 255, {int(45 * opacity)});
                border-radius: 14px;
                padding: {self._PAD_V_MAIN}px {self._PAD_H_MAIN}px;
            }}
            """
        )
        self._original_label.setStyleSheet(
            f"""
            QLabel {{
                color: #B9C4D0;
                background-color: rgba(0, 0, 0, {int(alpha * 0.6)});
                border-radius: 10px;
                padding: {self._PAD_V_SUB}px {self._PAD_H_SUB}px;
            }}
            """
        )
        self._previous_label.setStyleSheet(
            f"""
            QLabel {{
                color: #C8C8C8;
                background-color: rgba(0, 0, 0, {int(alpha * 0.6)});
                border-radius: 10px;
                padding: {self._PAD_V_SUB}px {self._PAD_H_SUB}px;
            }}
            """
        )
        # Zemin silikleşince beyaz yazı açık renkli sahnede kayboluyor;
        # yazının etrafına koyu bir hale ekliyoruz.
        for label in self._labels():
            label.setGraphicsEffect(self._text_halo() if opacity < 0.5 else None)
        self.reposition()

    @staticmethod
    def _text_halo() -> QtWidgets.QGraphicsDropShadowEffect:
        effect = QtWidgets.QGraphicsDropShadowEffect()
        effect.setBlurRadius(8)
        effect.setOffset(0, 0)
        effect.setColor(QtGui.QColor(0, 0, 0, 255))
        return effect

    def enable_click_through(self) -> None:
        """Qt bayrağı her durumda yetmiyor, Win32 tarafında da ayarlıyoruz."""
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            style = get_long(hwnd, self._GWL_EXSTYLE)
            style |= (self._WS_EX_TRANSPARENT | self._WS_EX_LAYERED
                      | self._WS_EX_NOACTIVATE | self._WS_EX_TOOLWINDOW)
            set_long(hwnd, self._GWL_EXSTYLE, style)
        except Exception as exc:
            LOGGER.warning("Click-through ayarlanamadı: %s", exc)

    def reposition(self) -> None:
        """Genişlik ayardan, yükseklik içerikten geliyor. Sabit yükseklikte
        3-4 satırlık uzun çeviriler kırpılıp altyazı gelmemiş gibi görünüyordu."""
        screen = self._target_screen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        pct = max(20, min(100, self._config.subtitle_width_pct))
        max_width = min(geo.width(), max(200, int(geo.width() * pct / 100.0)))

        content_width = 0
        height = 0
        shown = 0
        for label in self._labels():
            # isVisible() pencere gizliyken hep False; gizliyken gelen ilk
            # altyazı (ve ayar önizlemesi) yanlış ölçülüp alttan kırpılıyordu
            if not label.isVisibleTo(self):
                continue
            label.setWordWrap(False)
            natural = label.sizeHint().width()
            label.setWordWrap(True)
            label_width = max(1, min(max_width, natural))
            label.setFixedWidth(label_width)

            needed = label.heightForWidth(label_width)
            if needed <= 0:
                needed = label.sizeHint().height()
            height += needed
            content_width = max(content_width, label_width)
            shown += 1

        if shown == 0:
            content_width = max_width
            height = int(self._config.subtitle_font_size * 1.8)
        else:
            height += self._SPACING * (shown - 1)

        layout = self.layout()
        if layout is not None:
            layout.activate()

        width = min(max_width, max(1, content_width))
        height = min(height, geo.height())

        x = geo.x() + (geo.width() - width) // 2
        y = geo.y() + geo.height() - height - self._config.subtitle_bottom_margin
        self.setGeometry(x, max(geo.y(), y), width, height)

    def _target_screen(self) -> Optional[QtGui.QScreen]:
        # Video çoğu zaman ikinci ekranda oynuyor; seçilen ekran çıkarıldıysa birincile dön
        name = self._config.subtitle_screen
        if name:
            for screen in QtWidgets.QApplication.screens():
                if screen.name() == name:
                    return screen
        return QtWidgets.QApplication.primaryScreen()

    @pyqtSlot(str, str)
    def show_subtitle(self, original: str, translated: str) -> None:
        # Slot içinden kaçan istisna PyQt6'da uygulamayı düşürüyor
        try:
            if self._config.show_original and original:
                self._original_label.setText(original)
                self._original_label.setVisible(True)
            else:
                self._original_label.setVisible(False)

            current = translated or original
            self._translated_label.setText(current)
            self._translated_label.setVisible(bool(current))

            # Hızlı konuşmada bir önceki cümle okunmadan kayboluyordu
            previous = self._last_final if self._config.subtitle_show_previous else ""
            self._previous_label.setText(previous)
            self._previous_label.setVisible(bool(previous) and previous != current)

            self.reposition()

            if not self.isVisible():
                self.show()
                self.enable_click_through()
            self._hide_timer.start(int(self._config.subtitle_hold_sec * 1000))
        except Exception as exc:
            LOGGER.warning("Altyazı gösterilemedi: %s", exc)

    def prime(self) -> None:
        """Katmanlı pencerenin ilk gösterim maliyetini açılışta öder, ilk
        altyazı takılmadan gelsin diye."""
        try:
            self._translated_label.setText(" ")
            self._translated_label.setVisible(True)
            self.reposition()
            self.show()
            QtWidgets.QApplication.processEvents()
        except Exception as exc:
            LOGGER.debug("Overlay ön ısıtma başarısız (önemsiz): %s", exc)
        finally:
            self._hide_timer.stop()
            self._clear_text()
            self.hide()

    def remember_final(self, translated: str) -> None:
        self._last_final = translated

    def _clear_text(self) -> None:
        # Uzun sessizlikten sonra eski cümle "önceki" diye geri gelmesin
        self._last_final = ""
        for label in self._labels():
            label.setVisible(False)

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # noqa: N802 (Qt API)
        super().showEvent(event)
        self.enable_click_through()
