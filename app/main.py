"""Entry point for the Serial-Monitor desktop app.

Run either way:
    python -m app.main          # from the project root (preferred)
    python app/main.py          # direct file run (e.g. VS Code "Code Runner")

The sys.path bootstrap at the top makes the direct-file form work too,
so editor "run file" buttons don't break.
"""

from __future__ import annotations

import multiprocessing
import os
import sys
from pathlib import Path
import qdarktheme

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow, APP_ORG, APP_NAME, TitleBarThemeFilter, _find_logo


def main() -> int:
    app = QApplication(sys.argv)

    icon_path = _find_logo("logo_sq.ico") or _find_logo("logo_sq.png")
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))

    settings = QSettings(APP_ORG, APP_NAME)
    saved_theme = str(settings.value("ui/theme", "dark"))
    qdarktheme.setup_theme(saved_theme, corner_shape="rounded")

    font = QFont("PT Sans", 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)

    titlebar_filter = TitleBarThemeFilter(settings)
    app.installEventFilter(titlebar_filter)
    app._titlebar_filter = titlebar_filter  # keep reference alive

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    # Prevent fork-bomb when the frozen EXE spawns child processes (PyInstaller).
    multiprocessing.freeze_support()
    # Enable crisp rendering on 4K / HiDPI monitors before QApplication starts.
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    sys.exit(main())
