"""Local compatibility shim to satisfy `import qdarktheme` when running
`python app/main.py` (script-context sys.path points at `app/`).

See project-root `qdarktheme.py` for implementation and rationale.
"""
from __future__ import annotations

from typing import Any

try:
    from PySide6.QtGui import QPalette, QColor
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover - defensive
    QPalette = None  # type: ignore
    QColor = None  # type: ignore
    QApplication = None  # type: ignore


def setup_theme(name: str | None = "dark", **kwargs: Any) -> None:
    if not name:
        return
    if QPalette is None or QApplication is None:
        return
    try:
        if str(name).lower().startswith("dark"):
            p = QPalette()
            p.setColor(QPalette.ColorRole.Window, QColor(50, 50, 50))
            p.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
            p.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
            p.setColor(QPalette.ColorRole.AlternateBase, QColor(50, 50, 50))
            p.setColor(QPalette.ColorRole.ToolTipBase, QColor(100, 100, 100))
            p.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
            p.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
            p.setColor(QPalette.ColorRole.Button, QColor(50, 50, 50))
            p.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
            p.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
            p.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
            p.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
            p.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))

            app = QApplication.instance()
            if app is not None:
                app.setPalette(p)
    except Exception:
        return
