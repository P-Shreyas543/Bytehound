"""Nothing may be drawn over the menu bar.

Widgets created with the main window as parent but never placed in a layout
are shown at the window's top-left corner. A combo box, a list and several
labels kept as hidden state holders were drawn there for this reason — a box
users could not move or close (reported from the field).
"""

from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QPoint, QSettings
from PySide6.QtWidgets import QApplication, QWidget


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_no_stray_widget_over_the_menu_bar(qapp, tmp_path, monkeypatch):
    import app.ui.main_window as mw

    ini = str(tmp_path / "settings.ini")

    class IsolatedSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(ini, QSettings.Format.IniFormat)

    monkeypatch.setattr(mw, "QSettings", IsolatedSettings)
    monkeypatch.setattr(mw.MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    win = mw.MainWindow()
    win.resize(1280, 780)
    win.show()
    end = time.monotonic() + 1.5
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)
    try:
        menu_rect = win.menuBar().geometry()
        strays = []
        for child in win.findChildren(QWidget):
            if not child.isVisible() or child.isWindow() or child is win.menuBar():
                continue
            if win.menuBar().isAncestorOf(child):
                continue
            top_left = child.mapTo(win, QPoint(0, 0))
            rect = child.rect().translated(top_left)
            if rect.intersects(menu_rect):
                strays.append((type(child).__name__, rect.x(), rect.y(), rect.width(), rect.height()))
        assert strays == [], f"widgets drawn over the menu bar: {strays}"
        # The logging status is visible in the status bar.
        assert win.statusBar().isAncestorOf(win._logging_label)
        assert win._logging_label.isVisible()
    finally:
        win.close()
