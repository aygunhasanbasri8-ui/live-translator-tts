"""Global kısayollar: önce 'keyboard', olmazsa 'pynput'. Callback'ler başka
thread'den geliyor; sinyal üzerinden gittiği için Qt ana thread'e taşıyor."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from .log import LOGGER

try:
    import keyboard as kb_lib  # type: ignore
except Exception:  # pragma: no cover - opsiyonel
    kb_lib = None

try:
    from pynput import keyboard as pynput_keyboard  # type: ignore
except Exception:  # pragma: no cover - opsiyonel
    pynput_keyboard = None


class HotkeyManager(QObject):
    start_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    toggle_overlay_requested = pyqtSignal()
    status_message = pyqtSignal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._backend: Optional[str] = None
        self._pynput_listener = None
        self._handles: list = []

    def _bindings(self):
        """Ctrl+Shift+<tuş> -> sinyal."""
        return (
            ("r", self.start_requested.emit),
            ("s", self.stop_requested.emit),
            ("h", self.toggle_overlay_requested.emit),
        )

    def install(self) -> None:
        if self._try_keyboard() or self._try_pynput():
            return
        self.status_message.emit(
            "⚠ Global kısayollar etkinleştirilemedi (keyboard/pynput yok ya da yetki gerekiyor). "
            "Butonları kullanabilirsiniz."
        )

    def _try_keyboard(self) -> bool:
        if kb_lib is None:
            return False
        try:
            for key, callback in self._bindings():
                self._handles.append(kb_lib.add_hotkey(f"ctrl+shift+{key}", callback))
            self._backend = "keyboard"
            self.status_message.emit("Kısayollar aktif (keyboard): Ctrl+Shift+R / S / H")
            return True
        except Exception as exc:
            LOGGER.warning("keyboard kütüphanesi kısayol kuramadı: %s", exc)
            self._handles.clear()
            return False

    def _try_pynput(self) -> bool:
        if pynput_keyboard is None:
            return False
        try:
            mapping = {f"<ctrl>+<shift>+{key}": callback for key, callback in self._bindings()}
            self._pynput_listener = pynput_keyboard.GlobalHotKeys(mapping)
            self._pynput_listener.daemon = True
            self._pynput_listener.start()
            self._backend = "pynput"
            self.status_message.emit("Kısayollar aktif (pynput): Ctrl+Shift+R / S / H")
            return True
        except Exception as exc:
            LOGGER.warning("pynput kısayol kuramadı: %s", exc)
            return False

    def uninstall(self) -> None:
        try:
            if self._backend == "keyboard" and kb_lib is not None:
                for handle in self._handles:
                    try:
                        kb_lib.remove_hotkey(handle)
                    except Exception:
                        pass
                self._handles.clear()
            elif self._backend == "pynput" and self._pynput_listener is not None:
                self._pynput_listener.stop()
        except Exception as exc:
            LOGGER.debug("Kısayol kaldırma hatası: %s", exc)
