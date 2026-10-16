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
