"""End to end through MainWindow: a logging session survives a device
disconnect + auto-reconnect as a recorded gap and a new segment, and every
file the manifest names exists (Plane.md Part A / F11)."""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.decoder.config_loader import load_config
from app.protocol.packet_builder import build_packet
from app.serial_io.serial_worker import SerialSettings
from app.serial_logging.session import SessionSettings, read_manifest

TEMPLATE = Path(__file__).resolve().parents[1] / "app" / "resources" / "config_template"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class Device:
    """TCP device that streams frames to each connection; drop() simulates an unplug."""

    def __init__(self, frames: list[bytes]) -> None:
        self.frames = frames
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(2)
        self.port = self.srv.getsockname()[1]
        self.sent = 0
        self._conn = None
        self._stop = threading.Event()
        self.connections = 0
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self.srv.accept()
            except OSError:
                return
            self.connections += 1
            self._conn = conn
            try:
                while not self._stop.is_set() and self._conn is conn:
                    conn.sendall(self.frames[self.sent % len(self.frames)])
                    self.sent += 1
                    time.sleep(0.01)
            except OSError:
                pass

    def drop(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            conn.close()

    def close(self) -> None:
        self._stop.set()
        self.drop()
        self.srv.close()


def _pump(app, seconds: float, until=None) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if until is not None and until():
            return True
        time.sleep(0.01)
    return until is None


def test_session_survives_disconnect_and_auto_reconnect(qapp, tmp_path, monkeypatch):
    import app.ui.main_window as mw

    ini = str(tmp_path / "settings.ini")

    class IsolatedSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(ini, QSettings.Format.IniFormat)

    monkeypatch.setattr(mw, "QSettings", IsolatedSettings)
    monkeypatch.setattr(mw.MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    monkeypatch.setattr(mw.MainWindow, "_popup_warning", lambda self, *a, **k: None)
    monkeypatch.setattr(mw.MainWindow, "_popup_critical", lambda self, *a, **k: None)

    config = load_config(TEMPLATE)
    frames = [build_packet(config.protocol, fid, bytes(f.payload_length)) for fid, f in config.frames.items()]
    dev = Device(frames)
    win = mw.MainWindow()
    try:
        win._load_config_from_path(TEMPLATE, suppress_popups=True)
        _pump(qapp, 0.5)
        monkeypatch.setattr(
            win, "_session_settings_from_qsettings",
            lambda: SessionSettings(segment_seconds=3600, fixed_step_s=0.5),
        )
        settings = SerialSettings(
            port="127.0.0.1", connection_type="tcp", host="127.0.0.1",
            port_num=dev.port, auto_reconnect=True,
        )
        assert win._attempt_connect(settings)
        folder = tmp_path / "session_a"
        assert win._start_logging_file(folder)
        assert _pump(qapp, 10, until=lambda: win._packet_count > 100)

        dev.drop()                                     # unplug
        assert _pump(qapp, 10, until=lambda: win._session_log is not None
                     and win._session_log.segment_index is None)
        assert win._logging                            # still recording
        assert win._logging_action.isEnabled()         # Stop Logging usable in the gap
        assert _pump(qapp, 15, until=lambda: dev.connections >= 2
                     and win._session_log.segment_index == 2)
        count_before = win._packet_count
        assert _pump(qapp, 10, until=lambda: win._packet_count > count_before + 100)

        session = win._session_log
        win._stop_logging()
        assert session.await_finished(60)
    finally:
        win._disconnect(reason="test done")
        win.close()
        dev.close()
        _pump(qapp, 0.3)

    m = read_manifest(folder)
    assert m["status"] == "closed"
    assert len(m["segments"]) == 2
    assert m["segments"][0]["close_reason"].startswith("connection lost")
    assert len(m["gaps"]) == 1 and m["gaps"][0]["end_utc"]
    for seg in m["segments"]:
        assert seg["status"] == "closed", seg.get("errors")
        assert seg["rows"]["event"] > 0 and seg["rows"]["fixed"] > 0
        for name in seg["files"].values():
            assert (folder / name).exists(), name
        assert (folder / seg["files"]["raw"]).stat().st_size > 0
    assert (folder / "config" / "frames.csv").exists()


def test_auto_reconnect_restores_the_exact_polling_setup():
    """A reconnect creates a new worker; without this, a polled device stayed
    silent after a USB glitch (polling off, target choices and pipelining lost)."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.decoder.types import PollingScheduleSpec
    from app.ui.polling_session import PollingSessionMixin

    scheds = [PollingScheduleSpec(0x10, 100, 50), PollingScheduleSpec(0x20, 100, 50),
              PollingScheduleSpec(0x30, 100, 50)]
    host = SimpleNamespace(
        _resume_polling=True,
        _polling_setup=({0x10, 0x30}, (True, 3, 40)),
        _serial=MagicMock(),
        _config=SimpleNamespace(polling_schedules=scheds),
        _polling_action=MagicMock(),
        _style_action_btn=lambda *a: None,
        _session_log=MagicMock(),
        _log_activity=lambda *a: None,
    )
    PollingSessionMixin._restore_polling_after_reconnect(host)

    toggles = {c.args[0]: c.args[1] for c in host._serial.toggle_schedule.call_args_list}
    assert toggles == {0x10: True, 0x20: False, 0x30: True}
    host._serial.set_pipelining.assert_called_once_with(True, 3, gap_ms=40)
    host._serial.set_polling_global.assert_called_once_with(True)
    host._polling_action.setChecked.assert_called_once_with(True)
    host._session_log.set_polling_mode.assert_called_once_with(True)
    assert host._resume_polling is False
