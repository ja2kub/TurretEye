# -*- coding: utf-8 -*-
import sys

from PyQt6.QtCore import qInstallMessageHandler
from PyQt6.QtWidgets import QApplication

from .app import TurretEyeApp


def _qt_message_handler(mode, context, message):
    if message.startswith("QPainter::"):
        return
    sys.stderr.write(f"{message}\n")


def main() -> int:
    qInstallMessageHandler(_qt_message_handler)
    app = QApplication(sys.argv)
    window = TurretEyeApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
