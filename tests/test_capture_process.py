"""CaptureClient: PollingWorker running in a child process.

Covers the contract MainWindow relies on: batches arrive as
``(packet, decoded, rx_perf)`` on the GUI thread, commands reach the device,
port errors raise ``SerialException`` like the in-thread worker, the child is
reused across connections, and a dead child looks like an unplugged device.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest
import serial
from PySide6.QtWidgets import QApplication

from app.decoder.config_loader import load_config
from app.protocol.packet_builder import build_packet
from app.serial_io import capture_process
from app.serial_io.capture_process import CaptureClient
from app.serial_io.serial_worker import SerialSettings
from app.serial_logging.raw_capture import RX, TX, iter_raw_capture

TEMPLATE = Path(__file__).resolve().parents[1] / "app" / "resources" / "config_template"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    capture_process.shutdown_pool()


@pytest.fixture(scope="module")
def config():
    return load_config(TEMPLATE)


def _frames(config) -> list[bytes]:
    return [
        build_packet(config.protocol, fid, bytes((i + fid) & 0xFF for i in range(f.payload_length)))
        for fid, f in config.frames.items()
    ]


class Device:
    """TCP 'device': streams frames on demand and records what it receives."""

    def __init__(self) -> None:
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        self.conn = None
        self.received = bytearray()
        self._accepted = threading.Event()
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        self.conn, _ = self.srv.accept()
        self._accepted.set()
        self.conn.settimeout(0.05)
        while True:
            try:
                data = self.conn.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            if not data:
                return
            self.received += data

    def send(self, blob: bytes) -> None:
        assert self._accepted.wait(5)
        self.conn.sendall(blob)

    def close(self) -> None:
        for s in (self.conn, self.srv):
            try:
                if s is not None:
                    s.close()
            except OSError:
                pass


def _settings(port: int) -> SerialSettings:
    return SerialSettings(port="127.0.0.1", connection_type="tcp", host="127.0.0.1", port_num=port)


def _pump_until(app, cond, timeout=10.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_streams_decoded_batches_and_sends_tx(qapp, config):
    dev = Device()
    client = CaptureClient(_settings(dev.port), config.protocol, [], decode_config=config)
    got = []
    client.packets_received.connect(lambda batch: got.extend(batch))
    client.open()
    try:
        assert client.is_open
        assert client.child_pid is not None
        frames = _frames(config)
        dev.send(b"".join(frames[i % 3] for i in range(300)))
        assert _pump_until(qapp, lambda: len(got) >= 300)
        packet, decoded, rx_perf = got[0]
        assert packet.ok and decoded is not None and isinstance(rx_perf, float)
        assert {p.frame_id for p, _, _ in got} == set(config.frames)

        client.enqueue_priority_tx(b"\x01\x02\x03PING")
        assert _pump_until(qapp, lambda: b"PING" in dev.received)
        # Fire-and-forget commands must not raise.
        client.set_polling_global(False)
        client.set_pipelining(False)
        client.reset_metrics()
        client.set_backpressure(False)
    finally:
        client.close()
        dev.close()
    assert not client.is_open


def test_raw_capture_runs_in_child(qapp, config, tmp_path):
    dev = Device()
    client = CaptureClient(_settings(dev.port), config.protocol, [], decode_config=config)
    got = []
    client.packets_received.connect(lambda batch: got.extend(batch))
    raw = tmp_path / "c.bhraw"
    client.open()
    try:
        client.start_raw_capture(raw, {"log_started_perf": time.perf_counter()})
        frames = _frames(config)
        blob = b"".join(frames[i % 3] for i in range(90))
        dev.send(blob)
        assert _pump_until(qapp, lambda: len(got) >= 90)
        client.enqueue_priority_tx(b"TXDATA")
        assert _pump_until(qapp, lambda: b"TXDATA" in dev.received)
        assert client.stop_raw_capture() is None
    finally:
        client.close()
        dev.close()
    recs = list(iter_raw_capture(raw))
    assert b"".join(d for k, _, d in recs if k == RX) == blob
    assert [d for k, _, d in recs if k == TX] == [b"TXDATA"]


def test_port_error_raises_serial_exception_and_child_is_reused(qapp, config):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    dead_port = s.getsockname()[1]
    s.close()  # nothing listens here

    capture_process.shutdown_pool()
    capture_process.prewarm()
    warm_pid = capture_process._idle[0].pid

    client = CaptureClient(_settings(dead_port), config.protocol, [], decode_config=config)
    with pytest.raises(serial.SerialException):
        client.open()
    assert not client.is_open

    # The failed open handed the same warm child back; every later
    # connection reuses it instead of spawning a new process.
    for _ in range(2):
        dev = Device()
        c = CaptureClient(_settings(dev.port), config.protocol, [], decode_config=config)
        c.open()
        try:
            assert c.is_open
            assert c.child_pid == warm_pid
        finally:
            c.close()
            dev.close()
    assert [ch.pid for ch in capture_process._idle] == [warm_pid]


def test_dead_child_emits_connection_lost(qapp, config):
    dev = Device()
    client = CaptureClient(_settings(dev.port), config.protocol, [], decode_config=config)
    lost = []
    client.connection_lost.connect(lambda: lost.append(True))
    client.open()
    try:
        client._child.proc.kill()
        assert _pump_until(qapp, lambda: bool(lost))
        assert not client.is_open
    finally:
        client.close()  # must not hang or raise on a dead child
        dev.close()


def test_device_disconnect_is_forwarded(qapp, config):
    dev = Device()
    client = CaptureClient(_settings(dev.port), config.protocol, [], decode_config=config)
    lost = []
    client.connection_lost.connect(lambda: lost.append(True))
    client.open()
    try:
        dev.send(_frames(config)[0])
        dev.close()  # remote end goes away
        assert _pump_until(qapp, lambda: bool(lost), timeout=15)
    finally:
        client.close()
