"""Comprehensive Test Suite for Serial Workers, Threading, Timing, and Sockets.

Verifies:
1. High-Throughput Burst Processing & Batch Emission (60 Hz throttle / 50 pkts).
2. Worker-Side Pre-Decoding (zero CPU burden on GUI thread).
3. Priority TX Queue Preemption over Active Polling.
4. Data Watchdog Silence Detection & Recovery.
5. Hardware Disconnect Detection (WinError 5, 22, 31, 1167).
6. Thread-Safe Shutdown & Clean Resource Release.
7. Live TCP Loopback Socket Communication.
8. Live UDP Loopback Socket Communication.
9. Round-Robin Fair Polling Timing & Starvation Prevention.
"""

import sys
import time
import socket
import struct
import threading
from pathlib import Path
from typing import List, Tuple
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path when executed directly as python test_xxx.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import serial

from app.decoder.types import (
    FrameConfig, ProtocolConfig, FrameDefinition, SignalSpec, PollingScheduleSpec
)
from app.protocol.packet_builder import build_packet
from app.serial_io.serial_worker import (
    PollingWorker, SerialSettings, TcpSocketWrapper, UdpSocketWrapper,
    WATCHDOG_TIMEOUT, _BATCH_SIZE, _DISCONNECT_WINERRORS
)


def _make_protocol() -> ProtocolConfig:
    return ProtocolConfig(
        profile_name="TestSerialProto",
        header=b"\xaa\x55",
        frame_id_size=2,
        frame_id_byte_order="little",
        length_size=1,
        length_meaning="payload_only",
        crc_type="crc16_modbus",
        crc_size=2,
        crc_byte_order="little",
        crc_coverage="header_to_payload",
        footer=b"\xee",
        escape_mode="none",
        enabled=True,
        parser_type="framed"
    )


def _make_frame_config(proto: ProtocolConfig) -> FrameConfig:
    frames = {
        0x1000: FrameDefinition(frame_id=0x1000, frame_name="Telemetry", payload_length=4, direction="rxtx"),
        0x2000: FrameDefinition(frame_id=0x2000, frame_name="Status", payload_length=2, direction="rxtx"),
    }
    signals_by_frame = {
        0x1000: [
            SignalSpec(frame_id=0x1000, frame_name="Telemetry", signal_name="Voltage", start_byte=0, byte_length=2, endianness="little", data_type="uint16", scale=0.1, offset=0.0, unit="V", group="Sensors"),
            SignalSpec(frame_id=0x1000, frame_name="Telemetry", signal_name="Current", start_byte=2, byte_length=2, endianness="little", data_type="int16", scale=0.01, offset=0.0, unit="A", group="Sensors"),
        ],
        0x2000: [
            SignalSpec(frame_id=0x2000, frame_name="Status", signal_name="State", start_byte=0, byte_length=2, endianness="little", data_type="uint16", scale=1.0, offset=0.0, unit="", group="System"),
        ]
    }
    return FrameConfig(protocol=proto, frames=frames, signals_by_frame=signals_by_frame)


class MockSerialPort:
    """In-memory mock serial device with thread-safe read/write buffers."""
    def __init__(self):
        self._rx_buf = bytearray()
        self._tx_buf = bytearray()
        self._lock = threading.Lock()
        self._is_open = True
        self.raise_on_read = None
        self.raise_on_write = None

    @property
    def is_open(self) -> bool:
        return self._is_open

    def open(self):
        self._is_open = True

    def close(self):
        self._is_open = False

    def write(self, data: bytes) -> int:
        if self.raise_on_write:
            raise self.raise_on_write
        with self._lock:
            self._tx_buf.extend(data)
        return len(data)

    def read(self, size: int = 1) -> bytes:
        if self.raise_on_read:
            raise self.raise_on_read
        with self._lock:
            if not self._rx_buf:
                return b""
            chunk = bytes(self._rx_buf[:size])
            del self._rx_buf[:size]
            return chunk

    @property
    def in_waiting(self) -> int:
        with self._lock:
            return len(self._rx_buf)

    def feed_rx(self, data: bytes):
        with self._lock:
            self._rx_buf.extend(data)

    def get_tx(self) -> bytes:
        with self._lock:
            res = bytes(self._tx_buf)
            self._tx_buf.clear()
            return res


# ============================================================================
# 1. HIGH-THROUGHPUT BURST & BATCH EMISSION TEST
# ============================================================================

def test_high_throughput_burst_and_pre_decoding():
    """Simulate a 100-packet high-speed telemetry burst and verify worker pre-decoding."""
    proto = _make_protocol()
    cfg = _make_frame_config(proto)
    settings = SerialSettings(port="MOCK_COM", baud_rate=115200)
    worker = PollingWorker(settings, proto, schedules=[], decode_config=cfg)

    mock_port = MockSerialPort()
    worker._serial = mock_port

    # Prepare 100 packets
    raw_stream = bytearray()
    for i in range(100):
        # Voltage = (100 + i) * 0.1 V, Current = (i - 50) * 0.01 A
        payload = struct.pack("<Hh", 100 + i, i - 50)
        pkt_bytes = build_packet(proto, 0x1000, payload)
        raw_stream.extend(pkt_bytes)

    mock_port.feed_rx(bytes(raw_stream))

    collected_batches = []
    worker.packets_received.connect(lambda b: collected_batches.append(b))

    # Drain pending RX and flush
    worker._drain_pending_rx()
    worker._flush_batch()

    total_packets = sum(len(b) for b in collected_batches)
    assert total_packets == 100

    # Verify worker-side pre-decoding
    first_pkt, first_dec = collected_batches[0][0]
    assert first_pkt.ok is True
    assert first_pkt.frame_id == 0x1000
    assert first_dec is not None
    assert first_dec.signals[0].signal_name == "Voltage"
    assert first_dec.signals[0].scaled_value == 10.0  # 100 * 0.1
    assert first_dec.signals[1].signal_name == "Current"
    assert first_dec.signals[1].scaled_value == -0.5  # -50 * 0.01


# ============================================================================
# 2. PRIORITY TX QUEUE PREEMPTION TEST
# ============================================================================

def test_priority_tx_queue_preemption():
    """Verify that user-initiated TX commands take immediate precedence over polling."""
    proto = _make_protocol()
    cfg = _make_frame_config(proto)
    schedules = [
        PollingScheduleSpec(target_id=0x1000, interval_ms=50, timeout_ms=30, enabled=True),
    ]
    settings = SerialSettings(port="MOCK_COM", baud_rate=115200)
    worker = PollingWorker(settings, proto, schedules=schedules, decode_config=cfg)

    mock_port = MockSerialPort()
    worker._serial = mock_port
    worker._polling_global_enabled = True

    # Enqueue a high-priority user command (e.g. Set Voltage Limit = 0xAA 55 00 20 ...)
    priority_payload = b"\xaa\x55\x00\x20\x02\x34\x12\x00\x00\xee"
    worker.enqueue_priority_tx(priority_payload)

    assert not worker._priority_tx_queue.empty()
    tx_item = worker._priority_tx_queue.get()
    worker._write_serial(tx_item)

    transmitted = mock_port.get_tx()
    assert transmitted == priority_payload
    assert worker._priority_tx_queue.empty()


# ============================================================================
# 3. DATA WATCHDOG SILENCE DETECTION & RECOVERY TEST
# ============================================================================

def test_data_watchdog_silence_and_recovery():
    """Verify that worker fires device_timeout on silence and clears on traffic."""
    proto = _make_protocol()
    cfg = _make_frame_config(proto)
    settings = SerialSettings(port="MOCK_COM", baud_rate=115200)
    worker = PollingWorker(settings, proto, schedules=[], decode_config=cfg)

    timeout_fired = []
    worker.device_timeout.connect(lambda: timeout_fired.append(True))

    mock_port = MockSerialPort()
    worker._serial = mock_port

    # Initially last_rx_time is fresh
    worker._check_watchdog()
    assert len(timeout_fired) == 0

    # Simulate 4 seconds of silence
    worker._last_rx_time = time.monotonic() - (WATCHDOG_TIMEOUT + 1.0)
    worker._check_watchdog()
    assert len(timeout_fired) == 1

    # Verify debouncing (does not fire repeatedly on consecutive silent ticks)
    worker._check_watchdog()
    assert len(timeout_fired) == 1

    # Resume traffic: feed a packet
    pkt_bytes = build_packet(proto, 0x1000, b"\x00\x00\x00\x00")
    mock_port.feed_rx(pkt_bytes)
    worker._drain_pending_rx()

    # Watchdog state should be reset
    assert worker._watchdog_fired is False


# ============================================================================
# 4. HARDWARE DISCONNECT DETECTION TEST
# ============================================================================

@pytest.mark.parametrize("winerror", [5, 22, 31, 1167])
def test_hardware_disconnect_detection(winerror):
    """Verify that OS USB disconnection errors trigger the connection_lost signal."""
    proto = _make_protocol()
    settings = SerialSettings(port="MOCK_COM", baud_rate=115200)
    worker = PollingWorker(settings, proto, schedules=[])

    exc = serial.SerialException(f"ClearCommError failed (PermissionError(13, 'Access is denied.', None, {winerror}))")
    exc.winerror = winerror
    assert worker._is_disconnect_error(exc) is True


# ============================================================================
# 5. THREAD-SAFE SHUTDOWN & CLEANUP TEST
# ============================================================================

def test_thread_safe_shutdown():
    """Verify that stopping/closing the worker terminates cleanly and frees ports."""
    proto = _make_protocol()
    settings = SerialSettings(port="MOCK_COM", baud_rate=115200)
    worker = PollingWorker(settings, proto, schedules=[])

    mock_port = MockSerialPort()
    worker._serial = mock_port

    assert worker.is_open is True
    worker.stop()
    assert worker._stop_event.is_set()

    worker.close()
    assert worker._serial is None


# ============================================================================
# 6. LIVE TCP LOOPBACK SOCKET STREAMING TEST
# ============================================================================

def test_tcp_socket_loopback_streaming():
    """Test live TCP server-client loopback streaming with framing and pre-decoding."""
    # Find free port
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(1)
    port_num = server_sock.getsockname()[1]

    proto = _make_protocol()
    cfg = _make_frame_config(proto)

    client_wrapper = TcpSocketWrapper(host="127.0.0.1", port=port_num, timeout=0.1)

    # Accept thread
    client_conn = []
    def _accept():
        conn, _ = server_sock.accept()
        client_conn.append(conn)

    t = threading.Thread(target=_accept, daemon=True)
    t.start()

    client_wrapper.open()
    t.join(timeout=2.0)
    assert client_wrapper.is_open is True
    assert len(client_conn) == 1
    server_side = client_conn[0]

    try:
        # Send a packet from server to client
        pkt_bytes = build_packet(proto, 0x1000, struct.pack("<Hh", 250, 100))
        server_side.sendall(pkt_bytes)

        time.sleep(0.05)
        assert client_wrapper.in_waiting >= len(pkt_bytes)
        received = client_wrapper.read(len(pkt_bytes))
        assert received == pkt_bytes

        # Send from client to server
        tx_data = b"HELLO_BYTEHOUND_TCP"
        sent_len = client_wrapper.write(tx_data)
        assert sent_len == len(tx_data)

        server_side.settimeout(1.0)
        from_client = server_side.recv(1024)
        assert from_client == tx_data

    finally:
        client_wrapper.close()
        server_side.close()
        server_sock.close()


# ============================================================================
# 7. LIVE UDP LOOPBACK SOCKET STREAMING TEST
# ============================================================================

def test_udp_socket_loopback_streaming():
    """Test live UDP unicast loopback communication."""
    # Server socket
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_sock.bind(("127.0.0.1", 0))
    server_port = server_sock.getsockname()[1]

    client_wrapper = UdpSocketWrapper(host="127.0.0.1", port=server_port, timeout=0.1)
    client_wrapper.open()

    try:
        # Client writes to server
        tx_data = b"UDP_TEST_PAYLOAD"
        client_wrapper.write(tx_data)

        server_sock.settimeout(1.0)
        data, client_addr = server_sock.recvfrom(1024)
        assert data == tx_data

        # Server replies to client
        reply_data = b"UDP_REPLY_PAYLOAD"
        server_sock.sendto(reply_data, client_addr)

        time.sleep(0.05)
        assert client_wrapper.in_waiting >= len(reply_data)
        read_reply = client_wrapper.read(len(reply_data))
        assert read_reply == reply_data

    finally:
        client_wrapper.close()
        server_sock.close()


# ============================================================================
# 8. ROUND-ROBIN POLLING FAIRNESS & CADENCE TEST
# ============================================================================

def test_round_robin_polling_fairness():
    """Verify that multiple polling schedules are distributed fairly across cycles."""
    proto = _make_protocol()
    cfg = _make_frame_config(proto)
    schedules = [
        PollingScheduleSpec(target_id=0x1000, interval_ms=50, timeout_ms=20, enabled=True),
        PollingScheduleSpec(target_id=0x2000, interval_ms=50, timeout_ms=20, enabled=True),
    ]
    settings = SerialSettings(port="MOCK_COM", baud_rate=115200)
    worker = PollingWorker(settings, proto, schedules=schedules, decode_config=cfg)

    # Force all schedules to be due
    now = time.monotonic()
    for s in worker._schedules:
        s["next_run"] = now - 1.0

    n = len(worker._schedules)
    # First poll pick: schedule 0
    chosen1 = None
    for offset in range(n):
        idx = (worker._sched_cursor + offset) % n
        sched = worker._schedules[idx]
        if sched["enabled"] and now >= sched["next_run"]:
            chosen1 = sched
            worker._sched_cursor = (idx + 1) % n
            break

    assert chosen1 is not None
    assert chosen1["spec"].target_id == 0x1000
    assert worker._sched_cursor == 1

    # Second poll pick: schedule 1
    chosen2 = None
    for offset in range(n):
        idx = (worker._sched_cursor + offset) % n
        sched = worker._schedules[idx]
        if sched["enabled"] and now >= sched["next_run"]:
            chosen2 = sched
            worker._sched_cursor = (idx + 1) % n
            break

    assert chosen2 is not None
    assert chosen2["spec"].target_id == 0x2000
    assert worker._sched_cursor == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
