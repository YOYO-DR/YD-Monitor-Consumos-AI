"""Punto de entrada: `python -m monitor_consumos`."""

from __future__ import annotations

import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from . import config
from .ui.tray import TrayApp


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv

    config.ensure_dirs()

    app = QApplication(argv)
    app.setApplicationName(config.APP_NAME)
    # El widget vive en la bandeja: cerrar el panel no debe terminar el proceso.
    app.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None,
            "Monitor de consumos",
            "Este escritorio no expone bandeja del sistema, así que el widget "
            "no tiene dónde vivir.\n\nEn GNOME suele bastar con la extensión "
            "AppIndicator support.",
        )
        return 1

    tray = TrayApp()
    tray.quit_requested.connect(app.quit)
    app.aboutToQuit.connect(tray.shutdown)
    tray.start()

    # Sin esto, Ctrl+C en la terminal no llega mientras Qt tiene el control.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    keepalive = QTimer()
    keepalive.start(500)
    keepalive.timeout.connect(lambda: None)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
