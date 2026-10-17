"""Session logging on the capture worker's thread (task.md Phase 1).

Per-frame logging used to run on the GUI thread and cost it most of its
time at high frame rates. The worker now writes frames to the session while
the GUI thread keeps the housekeeping (tick, rotation, stop). These tests
pin the risks of that move: exactly-once logging while segments rotate
concurrently, no double logging by the GUI, callbacks on the GUI thread.
"""

from __future__ import annotations

import socket
import struct
import threading
import time

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from app.decoder.config_loader import load_config
from app.protocol.packet_builder import build_packet
from app.serial_io.serial_worker import PollingWorker, SerialSettings
from app.serial_logging.session import SessionLog, SessionSettings, read_manifest
from tools.hil import nucleo as hw


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def seq_config(tmp_path):
    folder = hw.hil_config_dir(tmp_path / "config")
    return folder, load_config(folder)


def test_worker_logs_every_frame_exactly_once_while_segments_rotate(qapp, seq_config, tmp_path):
    cfg_dir, config = seq_config
    n = 6000
    frames = [build_packet(config.protocol, 0x4000, struct.pack("<II", i, i)) for i in range(n)]

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    go = threading.Event()

    def device():
        conn, _ = srv.accept()
        go.wait(5)
        for i in range(0, n, 20):                    # ~2,000 frames/s for ~3 s
            conn.sendall(b"".join(frames[i:i + 20]))
            time.sleep(0.01)
        time.sleep(1.0)
        conn.close()

    threading.Thread(target=device, daemon=True).start()
    worker = PollingWorker(
        SerialSettings(port="x", connection_type="tcp", host="127.0.0.1", port_num=srv.getsockname()[1]),
        config.protocol, [], decode_config=config,
    )
    session = SessionLog(tmp_path / "session", config, SessionSettings(segment_seconds=0.4, fixed_step_s=0.1),
                         config_source=cfg_dir)
    session.start()
    worker.set_session_sink(session)
    worker.open()
    go.set()
    try:
        end = time.monotonic() + 6.0
        while time.monotonic() < end:                # this thread plays the GUI: rotation runs here
            session.tick()
            qapp.processEvents()
            time.sleep(0.05)
            if worker.integrity_snapshot()["frames_ok"] >= n:
                break
        assert worker.integrity_snapshot()["frames_ok"] == n
        worker.set_session_sink(None)
        session.stop()
        assert session.await_finished(120)
    finally:
        worker.close()
        srv.close()

    snap = worker.integrity_snapshot()
    assert snap["session_log_errors"] == 0 and snap["parse_errors"] == 0
    segs = read_manifest(tmp_path / "session")["segments"]
    assert len(segs) >= 4, "the test must rotate segments while the worker logs"
    seqs = []
    for s in segs:
        ev = pd.read_csv(tmp_path / "session" / s["files"]["event_csv"])
        col = next(c for c in ev.columns if c.endswith("HIL Seq"))
        seqs += ev[col].dropna().astype("int64").tolist()
    assert seqs == list(range(n))                    # every frame once, in order, across rotations


def test_gui_does_not_log_batches_the_worker_logs():
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.protocol.packet_parser import ParsedPacket
    from app.ui.telemetry_pipeline import TelemetryPipelineMixin

    class Window(TelemetryPipelineMixin):
        pass

    win = Window()
    win._session_log = MagicMock()
    win._config = SimpleNamespace()
    item = (ParsedPacket(raw=b"x", frame_id=1, payload=b"", ok=True), object(), 0.0)
    win._serial = SimpleNamespace(logs_sessions=True)
    assert win._log_batch([item]) == [item]
    win._session_log.log_frame.assert_not_called()
    win._serial = SimpleNamespace()                  # e.g. the capture-process client
    win._log_batch([item])
    win._session_log.log_frame.assert_called_once()


def test_session_callbacks_run_on_the_gui_thread():
    from app.ui.logging_session import _GuiCallbackRelay

    app = QApplication.instance() or QApplication([])
    relay = _GuiCallbackRelay()
    seen = []
    deliver = relay.wrap(lambda msg: seen.append((msg, threading.get_ident())))
    t = threading.Thread(target=deliver, args=("from worker",))
    t.start()
    t.join()
    assert seen == []                                # queued, not run on the worker thread
    end = time.monotonic() + 2
    while not seen and time.monotonic() < end:
        app.processEvents()
    assert seen == [("from worker", threading.get_ident())]
    deliver("from gui")                              # same thread: direct
    assert seen[-1] == ("from gui", threading.get_ident())
