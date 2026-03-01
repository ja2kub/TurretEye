# -*- coding: utf-8 -*-
import os
import sys

from PyQt6.QtCore import qInstallMessageHandler
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from .app import TurretEyeApp

APP_USER_MODEL_ID = "TurretEye.App"


def _qt_message_handler(mode, context, message):
    if message.startswith("QPainter::"):
        return
    sys.stderr.write(f"{message}\n")


def _resolve_app_icon_path() -> str | None:
    candidate_roots = []
    if hasattr(sys, "_MEIPASS"):
        candidate_roots.append(sys._MEIPASS)
    if getattr(sys, "frozen", False):
        candidate_roots.append(os.path.dirname(sys.executable))
    candidate_roots.append(os.path.dirname(os.path.dirname(__file__)))

    for root in candidate_roots:
        icon_path = os.path.join(root, "TurretEye.ico")
        if os.path.exists(icon_path):
            return icon_path
    return None


def _set_windows_app_user_model_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        # If this fails, app still works; only taskbar icon/grouping may be affected.
        pass


def main() -> int:
    qInstallMessageHandler(_qt_message_handler)
    _set_windows_app_user_model_id()
    app = QApplication(sys.argv)
    icon_path = _resolve_app_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))
    window = TurretEyeApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
