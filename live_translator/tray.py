"""Tepsi simgesi. Altyazı açıkken kontrol penceresi çoğu zaman ayak altında;
küçültünce tepsiye iniyor, başlat/durdur oradan da yapılabiliyor."""
from __future__ import annotations

from typing import Optional

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import QObject, pyqtSignal

_TITLE = "Canlı Çevirmen"


class AppTray(QtWidgets.QSystemTrayIcon):
    toggle_running_requested = pyqtSignal()
    toggle_overlay_requested = pyqtSignal()
    restore_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    @classmethod
    def create(cls, icon: QtGui.QIcon, parent: QObject) -> Optional["AppTray"]:
        if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = cls(icon, parent)
        tray.show()
        return tray

    def __init__(self, icon: QtGui.QIcon, parent: QObject) -> None:
        super().__init__(icon, parent)
        self.setToolTip(_TITLE)
        # Menünün sahibi bir widget olmalı; QSystemTrayIcon widget değil
        self._menu = QtWidgets.QMenu()
        self._run_action = self._menu.addAction("Başlat", self.toggle_running_requested.emit)
        self._menu.addAction("Altyazıyı gizle/göster", self.toggle_overlay_requested.emit)
        self._menu.addAction("Pencereyi göster", self.restore_requested.emit)
        self._menu.addSeparator()
        self._menu.addAction("Çıkış", self.quit_requested.emit)
        self.setContextMenu(self._menu)
        self.activated.connect(self._on_activated)
        self._hint_shown = False

    def set_running(self, running: bool) -> None:
        self._run_action.setText("Durdur" if running else "Başlat")
        self.setToolTip(f"{_TITLE} — " + ("dinliyor" if running else "durdu"))

    def show_minimized_hint(self) -> None:
        if self._hint_shown:
            return
        self._hint_shown = True
        self.showMessage(_TITLE, "Tepside çalışmaya devam ediyor.",
                         QtWidgets.QSystemTrayIcon.MessageIcon.Information, 2500)

    def _on_activated(self, reason: QtWidgets.QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QtWidgets.QSystemTrayIcon.ActivationReason.Trigger,
                      QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick):
            self.restore_requested.emit()
