"""Application entry point for Single-Cell BMS Cycler."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure repo root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from single_cell_cycler.ui.main_window import MainWindow

def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Enable High-DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    app.setApplicationName("Bytehound Single-Cell Cycler")
    app.setOrganizationName("Bytehound")

    window = MainWindow()
    app.aboutToQuit.connect(window.close)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
