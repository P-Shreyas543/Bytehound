"""Tests for connection dialog auto-reconnect checkbox and MainWindow auto-reconnect logic."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings

from app.ui.dialogs import ConnectionDialog
from app.ui.main_window import MainWindow
from app.serial_io.serial_worker import SerialSettings


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_connection_dialog_auto_reconnect(qapp):
    settings = QSettings("BytehoundTest", "TestReconnectDialog")
    settings.clear()

    # Instantiate dialog
    dlg = ConnectionDialog(settings)
    assert not dlg._auto_reconnect_chk.isChecked()

    # Toggle it
    dlg._auto_reconnect_chk.setChecked(True)
    dlg._on_accept()

    # Verify value persisted
    assert settings.value("conn/auto_reconnect") == "true"

    serial_settings = dlg.get_settings()
    assert serial_settings.auto_reconnect is True

    settings.clear()


def test_mainwindow_auto_reconnect_backoff_logic(qapp, monkeypatch):
    # Mock QSettings to prevent disk pollution
    class MockSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__("BytehoundTestOrg", "BytehoundTestApp")
            self.clear()
    monkeypatch.setattr("app.ui.main_window.QSettings", MockSettings)
    monkeypatch.setattr("app.ui.main_window.ConnectionDialog", lambda *args, **kwargs: None)

    win = MainWindow()

    # Simulate connection established with auto_reconnect=True
    settings = SerialSettings(port="COM999", auto_reconnect=True)
    win._saved_settings = settings

    # Mock _attempt_connect to simulate connection failures
    attempts = []
    def mock_attempt_connect(settings_obj, is_retry=False):
        attempts.append(settings_obj)
        return False # simulate connection failure
    monkeypatch.setattr(win, "_attempt_connect", mock_attempt_connect)

    # Trigger connection lost
    win._on_connection_lost()

    # Timer should be active and scheduled for 1000ms
    assert win._reconnect_timer.isActive()
    assert win._reconnect_timer.interval() == 1000

    # Run the reconnect timeout method to simulate timer firing
    win._on_reconnect_timeout()

    # Check that _attempt_connect was called
    assert len(attempts) == 1
    assert attempts[0] == settings

    # Reconnect failed, so next backoff should be 2000ms (attempts = 1 -> 2**1 * 1000 = 2000)
    assert win._reconnect_timer.isActive()
    assert win._reconnect_timer.interval() == 2000

    # Run reconnect timeout again
    win._on_reconnect_timeout()
    assert len(attempts) == 2
    assert win._reconnect_timer.interval() == 4000

    # Run a few more times to test cap at 16000ms
    for _ in range(5):
        win._on_reconnect_timeout()

    assert win._reconnect_timer.interval() == 16000

    # If connection succeeds, timer stops and attempts resets
    def mock_attempt_connect_success(settings_obj, is_retry=False):
        win._reconnect_attempts = 0
        win._reconnect_timer.stop()
        return True
    monkeypatch.setattr(win, "_attempt_connect", mock_attempt_connect_success)

    win._on_reconnect_timeout()
    assert not win._reconnect_timer.isActive()
    assert win._reconnect_attempts == 0

    win.close()
