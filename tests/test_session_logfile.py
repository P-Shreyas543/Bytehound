"""Each logging session writes the application log of that recording to
``<session>/log.txt`` (owner request 2026-10-22), and Activity Log lines
reach the log files too, so a zipped session folder explains itself."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.decoder.config_loader import load_config
from app.protocol.packet_builder import build_packet
from app.serial_io.serial_worker import SerialSettings
from app.serial_logging.session import SessionSettings
from tests.test_session_gui import Device, _pump

TEMPLATE = Path(__file__).resolve().parents[1] / "app" / "resources" / "config_template"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _window(tmp_path, monkeypatch):
    import app.ui.main_window as mw

    ini = str(tmp_path / "settings.ini")

    class IsolatedSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(ini, QSettings.Format.IniFormat)

    monkeypatch.setattr(mw, "QSettings", IsolatedSettings)
    monkeypatch.setattr(mw.MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    monkeypatch.setattr(mw.MainWindow, "_popup_warning", lambda self, *a, **k: None)
    monkeypatch.setattr(mw.MainWindow, "_popup_critical", lambda self, *a, **k: None)
    return mw.MainWindow()


def test_each_session_gets_its_own_log_txt(qapp, tmp_path, monkeypatch):
    config = load_config(TEMPLATE)
    frames = [build_packet(config.protocol, fid, bytes(f.payload_length)) for fid, f in config.frames.items()]
    dev = Device(frames)
    win = _window(tmp_path, monkeypatch)
    root_handlers_before = list(logging.getLogger().handlers)
    try:
        win._load_config_from_path(TEMPLATE, suppress_popups=True)
        monkeypatch.setattr(win, "_session_settings_from_qsettings",
                            lambda: SessionSettings(segment_seconds=3600))
        settings = SerialSettings(port="127.0.0.1", connection_type="tcp", host="127.0.0.1",
                                  port_num=dev.port, auto_reconnect=False)
        assert win._attempt_connect(settings)
        folders = []
        for name in ("session_a", "session_b"):
            folder = tmp_path / name
            assert win._start_logging_file(folder)
            assert _pump(qapp, 10, until=lambda: win._packet_count > 50)
            win._log_activity(f"[TEST] marker for {name}")
            session = win._session_log
            win._stop_logging()
            assert session.await_finished(60)
            assert _pump(qapp, 5, until=lambda: getattr(win, "_session_log_handler", None) is None)
            folders.append(folder)
    finally:
        win._disconnect(reason="test done")
        win.close()
        dev.close()
        _pump(qapp, 0.3)

    a, b = ((f / "log.txt").read_text(encoding="utf-8") for f in folders)
    for text, name in ((a, "session_a"), (b, "session_b")):
        assert "session log ====" in text and f"Session folder: {tmp_path / name}" in text
        assert "Configuration:" in text and "Connection: tcp" in text
        assert "Logging started" in text                         # Activity Log lines are in it
        assert f"[TEST] marker for {name}" in text
        assert "==== session log closed ====" in text
    assert "[TEST] marker for session_b" not in a                # a new file per session
    assert "[TEST] marker for session_a" not in b
    assert logging.getLogger().handlers == root_handlers_before   # nothing left attached


def test_activity_log_lines_reach_the_log_files(qapp, tmp_path, monkeypatch, caplog):
    win = _window(tmp_path, monkeypatch)
    try:
        with caplog.at_level(logging.INFO, logger="bytehound.activity"):
            win._log_activity("Connected to COM7 @ 115200")
        assert ("bytehound.activity", logging.INFO, "Connected to COM7 @ 115200") in caplog.record_tuples
    finally:
        win.close()
