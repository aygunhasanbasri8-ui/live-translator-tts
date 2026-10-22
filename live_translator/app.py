import logging
import logging.handlers
import os
import sys

from PyQt6 import QtWidgets

from .log import LOGGER
from .main_window import MainWindow


def log_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "LiveTranslator")


def _configure_logging() -> None:
    LOGGER.setLevel(logging.INFO)
    if LOGGER.handlers:
        return
    formatter = logging.Formatter("[%(asctime)s] %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    # Pencereli exe'de konsol yok (sys.stdout None); sorun bildiriminde
    # bakılacak tek yer bu dosya.
    if sys.stdout is not None:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        LOGGER.addHandler(handler)
    try:
        os.makedirs(log_dir(), exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir(), "live_translator.log"),
            maxBytes=1_000_000, backupCount=1, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)-7s %(threadName)s: %(message)s"))
        LOGGER.addHandler(file_handler)
    except OSError as exc:
        LOGGER.warning("Günlük dosyası açılamadı: %s", exc)


def _log_unhandled(exc_type, exc, tb) -> None:
    # Varsayılan kancayla PyQt6 slot içinden kaçan istisnada uygulamayı
    # kapatıyor; kendi kancamız varken yalnızca bunu çağırıp devam ediyor.
    LOGGER.error("Beklenmeyen hata", exc_info=(exc_type, exc, tb))


def main() -> int:
    _configure_logging()
    sys.excepthook = _log_unhandled

    if sys.platform != "win32":
        print("UYARI: WASAPI loopback yakalama yalnızca Windows'ta desteklenir.", file=sys.stderr)

    QtWidgets.QApplication.setApplicationName("Live System Audio Translator")
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    window = MainWindow()
    window.show()

    code = app.exec()
    # Ağda takılı bir tanıma/çeviri isteği varsa yorumlayıcı kapanışta onu
    # bekliyor, süreç pencere kapandıktan sonra da (zaman aşımına kadar) açık
    # kalıyordu. Ayarlar ve geçici dosyalar closeEvent'te zaten toplandı.
    logging.shutdown()
    os._exit(code)


if __name__ == "__main__":
    sys.exit(main())
