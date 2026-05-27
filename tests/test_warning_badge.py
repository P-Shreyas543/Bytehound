"""Tests for the QStatusBar WarningBadge queue saturation indicator."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QMouseEvent

from app.ui.main_window import MainWindow
from app.ui.ui_builders import WarningBadge


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_warning_badge_mouse_press_event(qapp):
    badge = WarningBadge("Test Warning")
    badge.setVisible(True)
    assert badge.isVisible()

    # Simulate click event
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        badge.rect().center(),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    badge.mousePressEvent(event)
    assert not badge.isVisible()


def test_warning_badge_visibility_on_activity_log(qapp, monkeypatch):
    # Mock QSettings to use clean key/value mappings
    class MockSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__("BytehoundTestOrg", "BytehoundTestApp")
            self.clear()

    monkeypatch.setattr("app.ui.main_window.QSettings", MockSettings)

    # Mock connection dialog to prevent GUI block
    monkeypatch.setattr("app.ui.main_window.ConnectionDialog", lambda *args, **kwargs: None)
    
    # Construct a real MainWindow
    win = MainWindow()
    
    assert win._warning_badge is not None
    assert win._warning_badge.isHidden()

    # Trigger logger queue saturation warning
    win._log_activity("Raw log queue full - dropped 1 row(s).")
    assert not win._warning_badge.isHidden()

    # Clear badge on disconnect
    win._disconnect(reason="Test disconnect")
    assert win._warning_badge.isHidden()

    # Trigger queue saturation again
    win._log_activity("TX queue full - command dropped.")
    assert not win._warning_badge.isHidden()

    # Clear badge manually
    win._warning_badge.setVisible(False)
    assert win._warning_badge.isHidden()
    
    win.close()
