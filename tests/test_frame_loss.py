"""Zero-frame-loss guarantees for the network transports (Plane.md Part F).

Each test here would have failed before its fix: it pins one place where
received data or transmitted commands used to be lost silently.
"""

from __future__ import annotations

import socket
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
        _integrity={}, _integrity_baseline=None, _warning_badge=badge,
        _log_activity=activity.append, _refresh_counts_label=lambda: None,
    )
    host._lost_bytes = MainWindow._lost_bytes
    handler = MainWindow._on_integrity_updated.__get__(host)

    handler({"frames_ok": 0, "discarded_bytes": 7})
    handler({"frames_ok": 3, "discarded_bytes": 7})     # baseline: 7 bytes at connect
    handler({"frames_ok": 9, "discarded_bytes": 7})
    assert not badge.visible and not activity
    handler({"frames_ok": 12, "discarded_bytes": 12})   # 5 bytes lost mid-stream
    assert badge.visible and "5 B since the first valid frame" in badge.tip
    assert len(activity) == 1
