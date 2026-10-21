import logging
import sys

from PyQt6 import QtWidgets

from .log import LOGGER
from .main_window import MainWindow


def _configure_logging() -> None:
    LOGGER.setLevel(logging.INFO)
    if LOGGER.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"))
    LOGGER.addHandler(handler)


def main() -> int:
    _configure_logging()

    if sys.platform != "win32":
        print("UYARI: WASAPI loopback yakalama yalnızca Windows'ta desteklenir.", file=sys.stderr)

    QtWidgets.QApplication.setApplicationName("Live System Audio Translator")
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
