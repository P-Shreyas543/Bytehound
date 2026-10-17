"""Zero-frame-loss guarantees for the network transports (Plane.md Part F).

Each test here would have failed before its fix: it pins one place where
received data or transmitted commands used to be lost silently.
"""

from __future__ import annotations

import socket
from pathlib import Path
import sys
import threading
import time

import pytest

from app.serial_io.serial_worker import (
    SOCKET_RCVBUF_BYTES,
    TcpSocketWrapper,
    UdpSocketWrapper,
)


def _udp_pair():
    """A bound 'device' UDP socket and a wrapper connected to it."""
    dev = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dev.bind(("127.0.0.1", 0))
    wrapper = UdpSocketWrapper(host="127.0.0.1", port=dev.getsockname()[1])
    wrapper.open()
    return dev, wrapper


def _wait_for(wrapper, n: int, timeout: float = 3.0) -> None:
    end = time.monotonic() + timeout
    while wrapper.in_waiting < n and time.monotonic() < end:
        time.sleep(0.005)


def test_udp_large_datagram_is_received_whole():
    """F4: datagrams larger than 4096 bytes used to error/truncate."""
    dev, w = _udp_pair()
    try:
        payload = bytes(range(256)) * 36  # 9216 bytes
        dev.sendto(payload, ("127.0.0.1", w._socket.getsockname()[1]))
        _wait_for(w, len(payload))
        assert w.read(len(payload)) == payload
    finally:
        w.close()
        dev.close()


def test_sockets_get_a_large_receive_buffer():
    """F5: the OS default receive buffer drops UDP bursts silently."""
    dev, w = _udp_pair()
    try:
        assert w.rcvbuf_bytes >= SOCKET_RCVBUF_BYTES // 2
    finally:
        w.close()
        dev.close()


def test_udp_burst_is_not_dropped():
    """F5: a burst arriving while the worker is busy must all be kept."""
    dev, w = _udp_pair()
    try:
        target = ("127.0.0.1", w._socket.getsockname()[1])
        datagram = b"\xAA" * 1400
        count = 1500  # ~2.1 MB, far beyond a 64 KiB default buffer
        for _ in range(count):  # sent while nobody reads
            dev.sendto(datagram, target)
        _wait_for(w, count * len(datagram))
        assert w.in_waiting == count * len(datagram)
    finally:
        w.close()
        dev.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific ICMP behaviour")
def test_udp_unreachable_port_does_not_end_the_session():
    """A device rebooting (port briefly closed) produces an ICMP reset that
    Windows reports as WSAECONNRESET; it must not read as an unplug."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()  # nothing listens on `port` now
    w = UdpSocketWrapper(host="127.0.0.1", port=port)
    w.open()
    try:
        w.write(b"poll")
        time.sleep(0.1)
        assert w.in_waiting == 0  # no exception
    finally:
        w.close()


def test_tcp_write_sends_every_byte():
    """send() may write only part of a buffer; the rest was lost silently."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Small buffers on both ends, like a slow embedded TCP stack, so the
    # client's send() can only take part of the payload at a time.
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    received = bytearray()
    payload = bytes(range(256)) * 40_000  # 10 MB: larger than socket buffers
    done = threading.Event()

    def device() -> None:
        conn, _ = srv.accept()
        time.sleep(0.3)  # slow reader: forces partial sends on the client
        while len(received) < len(payload):
            chunk = conn.recv(1 << 16)
            if not chunk:
                break
            received.extend(chunk)
        conn.close()
        done.set()

    threading.Thread(target=device, daemon=True).start()
    w = TcpSocketWrapper(host="127.0.0.1", port=srv.getsockname()[1])
    w.open()
    w._socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
    try:
        assert w.write(payload) == len(payload)
        assert done.wait(10)
        assert bytes(received) == payload
    finally:
        w.close()
        srv.close()


class _PartialSendSocket:
    """Socket double that, like a busy TCP stack, accepts at most 1000 bytes
    per send() and sometimes none (BlockingIOError)."""

    def __init__(self) -> None:
        self.sent = bytearray()
        self.calls = 0

    def send(self, data) -> int:
        self.calls += 1
        if self.calls % 3 == 0:
            raise BlockingIOError
        chunk = bytes(data[:1000])
        self.sent += chunk
        return len(chunk)

    def fileno(self) -> int:  # select() is patched out below
        return -1


def test_tcp_write_completes_after_partial_sends(monkeypatch):
    """socket.send() returning fewer bytes than given used to lose the rest
    of a TX command; the wrapper must keep sending until all bytes are out."""
    import app.serial_io.serial_worker as sw

    monkeypatch.setattr(sw.select, "select", lambda r, w, x, t=None: (r, w, x))
    w = TcpSocketWrapper(host="127.0.0.1", port=1)
    w._socket = _PartialSendSocket()
    w._is_open = True
    payload = bytes(range(256)) * 20  # 5120 bytes
    assert w.write(payload) == len(payload)
    assert bytes(w._socket.sent) == payload


# ---------------------------------------------------------------------------
# F3 — every received byte is accounted for
# ---------------------------------------------------------------------------

import random  # noqa: E402

from app.protocol.packet_builder import build_packet  # noqa: E402
from app.protocol.packet_parser import create_parser  # noqa: E402
from tests.conftest import dummy_protocol_config  # noqa: E402


def _assert_accounted(parser) -> None:
    st = parser.stats
    assert st.bytes_in == (
        st.frame_bytes_ok + st.frame_bytes_rejected + st.discarded_bytes
        + st.overflow_bytes + parser.buffered_bytes
    ), vars(st)


def _feed_in_random_chunks(parser, blob: bytes, seed: int = 1) -> list:
    rng = random.Random(seed)
    out, i = [], 0
    while i < len(blob):
        n = rng.randint(1, 37)
        parser.feed(blob[i:i + n])
        out += parser.extract_all()
        i += n
    return out


def test_framed_parser_accounts_for_noise_split_concatenated_and_bad_crc():
    pc = dummy_protocol_config(header=b"\xAA\x55")
    good = [build_packet(pc, 0x100 + i, bytes([i]) * (i % 9)) for i in range(200)]
    bad = bytearray(build_packet(pc, 0x7, b"\x01\x02\x03"))
    bad[-1] ^= 0xFF  # corrupt the CRC
    noise = bytes([0x13, 0xAA, 0x00, 0x55, 0xFE])  # includes a false 0xAA
    blob = noise + b"".join(good[:100]) + bytes(bad) + noise + b"".join(good[100:]) + b"\xAA"
    parser = create_parser(pc)
    pkts = _feed_in_random_chunks(parser, blob)

    assert [p.frame_id for p in pkts if p.ok] == [0x100 + i for i in range(200)]
    assert sum(not p.ok for p in pkts) == 1
    st = parser.stats
    assert st.frames_ok == 200 and st.frames_rejected == 1
    assert st.frame_bytes_rejected == len(bad)
    assert st.discarded_bytes >= 2 * len(noise) - 2  # noise skipped, and counted
    _assert_accounted(parser)
    assert parser.buffered_bytes == 1  # the trailing lone 0xAA waits


def test_framed_parser_counts_overflow_drops():
    import app.protocol.packet_parser as pp

    pc = dummy_protocol_config(header=b"\xAA\x55")
    parser = create_parser(pc)
    garbage = b"\x00" * (pp._MAX_BUFFER_BYTES + 5000)  # never contains a header
    parser.feed(garbage)
    parser.extract_all()
    parser.feed(garbage)
    parser.extract_all()
    _assert_accounted(parser)
    assert parser.stats.discarded_bytes + parser.stats.overflow_bytes > 0


def test_waveshare_variable_parser_accounts_for_every_byte():
    pc = dummy_protocol_config(parser_type="waveshare_can", header=b"", crc_type="none", crc_size=0)
    frames = [build_packet(pc, 0x100 + i, bytes([i]) * (i % 9)) for i in range(150)]
    blob = b"\x00\xAA\x01" + b"".join(frames) + b"\x55\x55"
    parser = create_parser(pc)
    pkts = _feed_in_random_chunks(parser, blob, seed=7)
    assert [p.frame_id for p in pkts if p.ok] == [0x100 + i for i in range(150)]
    _assert_accounted(parser)


def test_cobs_unframer_counts_undecodable_blocks():
    pc = dummy_protocol_config(header=b"\xAA\x55", escape_mode="cobs")
    parser = create_parser(pc)
    good = build_packet(pc, 0x10, b"\x01\x02")
    # A COBS block whose code byte points past its end cannot be decoded.
    parser.feed(b"\x09\x01\x02\x00" + good)
    pkts = parser.extract_all()
    assert [p.frame_id for p in pkts if p.ok] == [0x10]
    assert parser.stats.unframer_dropped_frames == 1
    assert parser.stats.unframer_dropped_bytes == 3


def test_slip_unframer_counts_invalid_escape():
    pc = dummy_protocol_config(header=b"\xAA\x55", escape_mode="slip")
    parser = create_parser(pc)
    good = build_packet(pc, 0x11, b"\x05")
    parser.feed(b"\x01\x02\xDB\x00\xC0" + good)  # ESC followed by an invalid byte
    pkts = parser.extract_all()
    assert [p.frame_id for p in pkts if p.ok] == [0x11]
    assert parser.stats.unframer_dropped_frames == 1


def test_worker_integrity_snapshot_accounts_for_a_noisy_stream():
    """End to end through a real PollingWorker over TCP: the published
    snapshot accounts for every byte the device sent."""
    from PySide6.QtCore import Qt

    from app.serial_io.serial_worker import PollingWorker, SerialSettings

    pc = dummy_protocol_config(header=b"\xAA\x55")
    frames = [build_packet(pc, 0x200 + (i % 5), bytes([i % 256]) * 4) for i in range(400)]
    noise = b"\x01\xAA\x02\x03"
    blob = noise + b"".join(f + (noise if i % 50 == 0 else b"") for i, f in enumerate(frames))

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def device() -> None:
        conn, _ = srv.accept()
        for i in range(0, len(blob), 53):
            conn.sendall(blob[i:i + 53])
        time.sleep(1.0)
        conn.close()

    threading.Thread(target=device, daemon=True).start()
    worker = PollingWorker(
        SerialSettings(port="x", connection_type="tcp", host="127.0.0.1", port_num=srv.getsockname()[1]),
        pc, [],
    )
    snaps: list = []
    worker.integrity_updated.connect(snaps.append, Qt.ConnectionType.DirectConnection)
    worker.open()
    deadline = time.monotonic() + 5
    while (not snaps or snaps[-1]["frames_ok"] < 400) and time.monotonic() < deadline:
        time.sleep(0.05)
        worker._emit_metrics_throttled(force=True)
    worker.close()
    srv.close()

    s = snaps[-1]
    assert s["frames_ok"] == 400
    assert s["parser_bytes_in"] == len(blob)
    assert s["parser_bytes_in"] == (
        s["frame_bytes_ok"] + s["frame_bytes_rejected"] + s["discarded_bytes"]
        + s["overflow_bytes"] + s["buffered_bytes"]
    )
    assert s["discarded_bytes"] == len(noise) * (1 + 8)  # every noise block counted


def test_ui_flags_discards_only_after_the_first_valid_frame():
    """Bytes skipped before the first frame (connected mid-frame) are normal;
    anything discarded later raises the warning badge."""
    from types import SimpleNamespace

    from app.ui.main_window import MainWindow

    activity: list = []
    badge = SimpleNamespace(visible=False, tip="")
    badge.setVisible = lambda v: setattr(badge, "visible", v)
    badge.setToolTip = lambda t: setattr(badge, "tip", t)
    host = SimpleNamespace(
        _integrity={}, _integrity_baseline=None, _warning_badge=badge, _session_log=None,
        _log_activity=activity.append, _refresh_counts_label=lambda: None,
    )
    host._lost_bytes = MainWindow._lost_bytes
    host._driver_error_total = MainWindow._driver_error_total
    handler = MainWindow._on_integrity_updated.__get__(host)

    handler({"frames_ok": 0, "discarded_bytes": 7})
    handler({"frames_ok": 3, "discarded_bytes": 7})     # baseline: 7 bytes at connect
    handler({"frames_ok": 9, "discarded_bytes": 7})
    assert not badge.visible and not activity
    handler({"frames_ok": 12, "discarded_bytes": 12})   # 5 bytes lost mid-stream
    assert badge.visible and "5 B since the first valid frame" in badge.tip
    assert len(activity) == 1


# ---------------------------------------------------------------------------
# F6 / F7 / F8 — connect purge, driver errors, thread priority
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="ClearCommError is Windows-only")
def test_driver_error_flags_are_counted_not_discarded(monkeypatch):
    """F7: pyserial calls ClearCommError and throws the flags away, so UART
    overruns were invisible. The tracking port records them."""
    import app.serial_io.serial_worker as sw

    reports = iter([0x0002 | 0x0008, 0x0000, 0x0001])

    def fake_clear(handle, flags_ref, comstat_ref):
        flags_ref._obj.value = next(reports)
        comstat_ref._obj.cbInQue = 7
        return True

    monkeypatch.setattr(sw._win32, "ClearCommError", fake_clear)
    port = sw.ErrorTrackingSerial.__new__(sw.ErrorTrackingSerial)
    port.comm_errors = sw._empty_comm_errors()
    port._port_handle = 1
    port.is_open = True

    assert port.in_waiting == 7
    assert port.in_waiting == 7
    assert port.in_waiting == 7
    assert port.comm_errors["hardware_overrun"] == 1
    assert port.comm_errors["framing_error"] == 1
    assert port.comm_errors["rx_buffer_overflow"] == 1
    assert port.comm_errors["parity_error"] == 0


def test_open_records_purge_and_raises_thread_priority(monkeypatch):
    """F6: bytes dropped at connect are counted; F8: the capture thread
    starts at high priority."""
    from unittest.mock import MagicMock

    from PySide6.QtCore import QThread

    import app.serial_io.serial_worker as sw

    class FakePort:
        def __init__(self, **kwargs):
            self.is_open = True
            self.in_waiting = 5

        def set_buffer_size(self, **kwargs):
            pass

        def reset_input_buffer(self):
            self.in_waiting = 0

        def close(self):
            self.is_open = False

    monkeypatch.setattr(sw, "ErrorTrackingSerial", FakePort)
    worker = sw.PollingWorker(sw.SerialSettings(port="COM_TEST"), dummy_protocol_config(), [])
    worker.start = MagicMock()
    worker.open()
    worker.start.assert_called_once_with(QThread.Priority.HighestPriority)
    assert worker.integrity_snapshot()["purged_at_connect"] == 5
    worker._serial = None


# ---------------------------------------------------------------------------
# Stress: maximum rate, noise, split / concatenated / corrupted frames
# ---------------------------------------------------------------------------

def _stress_stream(config, n_frames: int, seed: int = 11):
    """(blob, valid frames by id, corrupted count) for a hostile stream."""
    from collections import Counter

    rng = random.Random(seed)
    pc = config.protocol
    ids = list(config.frames)
    parts, valid, corrupt = [], Counter(), 0
    for i in range(n_frames):
        fid = ids[i % len(ids)]
        length = config.frames[fid].payload_length
        pkt = bytearray(build_packet(pc, fid, bytes(rng.randrange(256) for _ in range(length))))
        if i % 97 == 13:                      # corrupt the CRC
            pkt[-2] ^= 0x5A
            corrupt += 1
        else:
            valid[fid] += 1
        parts.append(bytes(pkt))
        if i % 41 == 7:                       # line noise, incl. a false header byte
            parts.append(bytes([0x00, 0xAA, 0x13, 0x77]))
    return b"".join(parts), valid, corrupt


@pytest.mark.parametrize("transport", ["tcp", "udp"])
def test_stress_every_byte_and_frame_accounted(tmp_path, transport):
    """30,000 frames sent as fast as possible with noise, random splits and
    corrupted CRCs, through a real worker into a logging session: every byte
    in the raw capture and accounted for, every valid frame in the decoded
    log exactly once, every corrupted one in the rejected file, and a
    rebuild from the raw capture finds the same frames (Plane.md Part F)."""
    from collections import Counter

    import pandas as pd
    from PySide6.QtCore import Qt

    from app.decoder.config_loader import load_config
    from app.serial_io.serial_worker import PollingWorker, SerialSettings
    from app.serial_logging.raw_capture import RX, iter_raw_capture, rebuild_decoded_log
    from app.serial_logging.session import SessionLog, SessionSettings, read_manifest

    config = load_config(Path(__file__).resolve().parents[1] / "app" / "resources" / "config_template")
    blob, valid, corrupt = _stress_stream(config, 30_000)

    if transport == "tcp":
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        endpoint = srv
        settings = SerialSettings(port="x", connection_type="tcp", host="127.0.0.1",
                                  port_num=srv.getsockname()[1])
    else:
        dev = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dev.bind(("127.0.0.1", 0))
        endpoint = dev
        settings = SerialSettings(port="x", connection_type="udp", host="127.0.0.1",
                                  port_num=dev.getsockname()[1])

    worker = PollingWorker(settings, config.protocol, [], decode_config=config)

    class Hooks:
        def start(self, path, meta):
            worker.start_raw_capture(path, meta)

        def stop(self):
            return worker.stop_raw_capture()

    session = SessionLog(tmp_path / "s", config, SessionSettings(), raw_capture=Hooks(),
                         disk_free=lambda p: 1 << 40)
    counted = {"n": 0}

    def on_batch(batch):
        for packet, decoded, rx_perf in batch:
            if packet.ok and decoded is not None:
                session.log_frame(decoded, rx_perf)
            elif not packet.ok:
                session.log_rejected(packet.raw, packet.frame_id, packet.error or "", rx_perf)
        counted["n"] += len(batch)            # only after the batch is logged

    worker.packets_received.connect(on_batch, Qt.ConnectionType.DirectConnection)
    session.start()

    def device():
        rng = random.Random(5)
        if transport == "tcp":
            conn, _ = srv.accept()
            i = 0
            while i < len(blob):              # random split points, as fast as possible
                n = rng.randint(1, 900)
                conn.sendall(blob[i:i + n])
                i += n
            time.sleep(1.5)
            conn.close()
        else:
            time.sleep(0.3)                   # let the worker bind
            target = ("127.0.0.1", worker._serial._socket.getsockname()[1])
            i = 0
            while i < len(blob):
                n = rng.randint(200, 1400)
                dev.sendto(blob[i:i + n], target)
                i += n

    threading.Thread(target=device, daemon=True).start()
    worker.open()
    # SessionLog is single-threaded (the GUI thread in the app): wait until
    # the worker has delivered every frame, stop the worker thread, and only
    # then touch the session or read counters from this thread.
    want = sum(valid.values()) + corrupt
    deadline = time.monotonic() + 30
    while counted["n"] < want and time.monotonic() < deadline:
        time.sleep(0.05)
    worker.close()
    snap = worker.integrity_snapshot()
    session.stop()
    assert session.await_finished(120)
    endpoint.close()

    # 1. Every byte arrived, is in the raw capture, and is accounted for.
    raw_path = tmp_path / "s" / "seg_0001.bhraw"
    captured = b"".join(d for k, _, d in iter_raw_capture(raw_path) if k == RX)
    assert captured == blob
    assert snap["parser_bytes_in"] == len(blob)
    assert snap["parser_bytes_in"] == (snap["frame_bytes_ok"] + snap["frame_bytes_rejected"]
                                       + snap["discarded_bytes"] + snap["overflow_bytes"]
                                       + snap["buffered_bytes"])
    # 2. Every valid frame decoded, every corrupted one rejected.
    assert snap["frames_ok"] == sum(valid.values())
    assert snap["frames_rejected"] == corrupt
    # 3. Every valid frame logged exactly once (frame_id cells per block).
    df = pd.read_csv(tmp_path / "s" / "seg_0001_event.csv", low_memory=False)
    logged = Counter()
    for col in [c for c in df.columns if c.endswith(".frame_id")]:
        for v in df[col].dropna():
            logged[int(str(v), 16)] += 1
    assert logged == valid
    m = read_manifest(tmp_path / "s")
    assert m["segments"][0]["rejected_frames"] == corrupt
    assert m["segments"][0]["decoded_dropped"] == 0
    # 4. A rebuild from the raw capture finds exactly the same frames.
    assert rebuild_decoded_log(raw_path, config, tmp_path / "rebuilt.xlsx") == sum(valid.values())


def test_tcp_data_received_before_peer_close_is_delivered():
    """F15: when the device sends its last bytes and closes, those bytes must
    still be delivered. The wrapper used to raise "closed by remote peer"
    while already-received bytes sat in its buffer — losing the last frames
    whenever the worker lagged (e.g. a busy PC)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    payload = bytes(range(256)) * 200
    w = TcpSocketWrapper(host="127.0.0.1", port=srv.getsockname()[1])
    w.open()
    conn, _ = srv.accept()
    conn.sendall(payload)
    conn.close()                      # data and FIN both in flight
    time.sleep(0.3)                   # worker lagging: both have arrived
    got = bytearray()
    try:
        while True:
            n = w.in_waiting
            if n == 0:
                break
            got += w.read(n)
    except Exception:
        pass                          # the close may be reported once drained
    assert bytes(got) == payload
    import serial as _serial
    with pytest.raises(_serial.SerialException):   # ...and then the close is reported
        _ = w.in_waiting
    w.close()
    srv.close()


# ---------------------------------------------------------------------------
# Found on the NUCLEO-G474RE HIL rig (tools/hil/run_hil.py)
# ---------------------------------------------------------------------------

class _BufferedPort:
    """Port whose driver buffer holds ``data``; reads drain it."""

    def __init__(self, data: bytes = b"") -> None:
        self.buf = bytearray(data)
        self.is_open = True
        self.buffer_requests: list = []
        self.written = bytearray()

    @property
    def in_waiting(self) -> int:
        return len(self.buf)

    def read(self, n: int = 1) -> bytes:
        out = bytes(self.buf[:n])
        del self.buf[:n]
        return out

    def write(self, data: bytes) -> int:
        self.written += data
        return len(data)

    def set_buffer_size(self, rx_size: int, tx_size: int) -> None:
        self.buffer_requests.append(rx_size)

    def reset_input_buffer(self) -> None:
        self.buf.clear()

    def close(self) -> None:
        self.is_open = False


def test_open_requests_a_large_driver_buffer(monkeypatch):
    """F16: at 2 Mbaud a 64 KiB driver buffer overflowed during a 200 ms read
    stall and the ST-LINK bridge dropped the excess with no error flag."""
    from unittest.mock import MagicMock

    import app.serial_io.serial_worker as sw

    port = _BufferedPort()
    monkeypatch.setattr(sw, "ErrorTrackingSerial", lambda **kw: port)
    worker = sw.PollingWorker(sw.SerialSettings(port="COM_TEST"), dummy_protocol_config(), [])
    worker.start = MagicMock()
    worker.open()
    assert port.buffer_requests[0] == sw.RX_DRIVER_BUFFER >= 4 * 1024 * 1024
    worker._serial = None


def test_tx_gap_wait_keeps_reading():
    """F17: waiting out the TX gap used to sleep with reads blocked (100 ms
    per command, 20 kB at 2 Mbaud)."""
    from app.serial_io.serial_worker import PollingWorker, SerialSettings

    pc = dummy_protocol_config(header=b"\xAA\x55")
    data = b"".join(build_packet(pc, 0x200, bytes([i]) * 4) for i in range(20))
    worker = PollingWorker(SerialSettings(port="x"), pc, [])
    worker._serial = _BufferedPort(data)
    worker._last_tx_time = time.monotonic()
    worker._write_serial(b"\x01", min_gap_ms=100)
    snap = worker.integrity_snapshot()
    assert snap["parser_bytes_in"] == len(data)
    assert snap["frames_ok"] == 20
    assert "rx_service_gap_max_ms" in snap
    worker._serial = None


def test_poll_response_read_during_gap_wait_ends_the_wait():
    from app.serial_io.serial_worker import PollingWorker, SerialSettings

    pc = dummy_protocol_config(header=b"\xAA\x55")
    worker = PollingWorker(SerialSettings(port="x"), pc, [])
    worker._serial = _BufferedPort(build_packet(pc, 0x300, b"\x01\x02"))
    worker._await_target, worker._await_hit = 0x300, False
    worker._drain_pending_rx()
    assert worker._await_hit
    worker._serial = None


def test_schedule_faster_than_tx_gap_warns():
    """The template schedule (100/200/500 ms) needs 17 polls/s; the default
    100 ms gap allows 10, so every interval silently ran ~1.7x long."""
    from PySide6.QtCore import Qt

    from app.decoder.types import PollingScheduleSpec
    from app.serial_io.serial_worker import PollingWorker, SerialSettings

    specs = [PollingScheduleSpec(0x100, 100, 50), PollingScheduleSpec(0x200, 200, 50),
             PollingScheduleSpec(0x300, 500, 50)]
    worker = PollingWorker(SerialSettings(port="x"), dummy_protocol_config(), specs)
    warnings: list = []
    worker.warning_occurred.connect(warnings.append, Qt.ConnectionType.DirectConnection)
    worker.set_polling_global(True)
    assert len(warnings) == 1 and "17.0 polls/s" in warnings[0]

    worker.set_polling_global(False)
    worker.set_pipelining(False, gap_ms=20)
    worker.set_polling_global(True)
    assert len(warnings) == 1


def test_poll_schedule_is_fixed_rate_not_completion_relative():
    """F20: next poll = previous due time + interval. Measuring from the end
    of the poll made a 100 ms schedule run 10-25 % slow on the HIL rig."""
    from app.decoder.types import PollingScheduleSpec
    from app.serial_io.serial_worker import PollingWorker

    sched = {"spec": PollingScheduleSpec(0x100, 100, 50), "next_run": 10.0}
    PollingWorker._advance_next_run(sched, now=10.045)    # poll took 45 ms
    assert sched["next_run"] == pytest.approx(10.1)       # not 10.145
    PollingWorker._advance_next_run(sched, now=10.13)
    assert sched["next_run"] == pytest.approx(10.2)
    PollingWorker._advance_next_run(sched, now=10.75)     # stalled 550 ms
    assert sched["next_run"] == pytest.approx(10.75)      # realign, no catch-up burst
    PollingWorker._advance_next_run(sched, now=10.76)
    assert sched["next_run"] == pytest.approx(10.85)
