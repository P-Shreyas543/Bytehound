"""Compatibility shim for projects importing `qdarktheme`.

Provides a minimal `setup_theme(name, **kwargs)` that applies a dark
QPalette when requested. This keeps the app runnable when the
distribution-provided dark theme package exposes a different module name.
"""
from __future__ import annotations

from typing import Any

try:
    from PySide6.QtGui import QPalette, QColor
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover - defensive: if PySide6 missing, make shim no-op
    QPalette = None  # type: ignore
    QColor = None  # type: ignore
    QApplication = None  # type: ignore


def setup_theme(name: str | None = "dark", **kwargs: Any) -> None:
    """Apply a minimal dark theme when `name` is truthy and contains 'dark'.

    This intentionally keeps behaviour simple: if PySide6 is available and
    a QApplication exists, a dark QPalette is applied. Otherwise this is a
    harmless no-op so imports succeed in environments where the original
    `qdarktheme` package isn't installed.
    """
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
        # Don't raise from a theme setup failure — it's non-fatal.
        return
