"""Simulated BMS device for system tests.

Speaks the framed protocol of ``tests/fixtures/canonical_config`` over a
real transport (TCP socket or a POSIX pseudo-terminal) so the complete app
can be driven end to end. Frames are encoded here independently of
``app.protocol`` — header, big-endian frame id, 1-byte payload length,
payload, CRC16/Modbus little-endian over header..payload — so a system test
checks the on-wire format, not the app agreeing with itself.
"""

from __future__ import annotations

import os
import socket
import struct
import threading
import time
from typing import Optional

HEADER = b"\xAA\x55"
FRAME_CELLS = 0x0010      # Cell Voltage 1/2, uint16 big-endian, 1 mV/bit
FRAME_STATE = 0x0030      # BMS State u8, FET Status u8, Fault Status u16


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def encode_frame(frame_id: int, payload: bytes) -> bytes:
    body = HEADER + struct.pack(">HB", frame_id, len(payload)) + payload
    return body + struct.pack("<H", crc16_modbus(body))


class SimulatedBms:
    """Streams telemetry frames every ``period`` seconds and records every
    byte the app sends. Transport-agnostic: subclasses provide the I/O."""

    def __init__(self, period: float = 0.02, stream: bool = True) -> None:
        self.period = period
        self.stream = stream          # False: silent request/response device
        self.cell_mv = [3300, 3310]
        self.bms_state = 2            # enum label "Charge"
        self.fet_status = 0b01        # bit 0 "Main FET Status" on
        self.fault_status = 0
        self.frames_sent = 0
        self._received = bytearray()
        self._inject: list[bytes] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---- test-facing API -------------------------------------------------
    def received(self) -> bytes:
        with self._lock:
            return bytes(self._received)

    def inject(self, raw: bytes) -> None:
        """Queue raw bytes (e.g. garbage or a corrupted frame) for the wire."""
        with self._lock:
            self._inject.append(raw)

    def start(self) -> "SimulatedBms":
        self._thread = threading.Thread(target=self._run, name=type(self).__name__, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)

    # ---- frame generation -------------------------------------------------
    def telemetry(self) -> bytes:
        with self._lock:
            extra = b"".join(self._inject)
            self._inject.clear()
            cells = struct.pack(">HH", *self.cell_mv)
            state = struct.pack(">BBH", self.bms_state, self.fet_status, self.fault_status)
        return extra + encode_frame(FRAME_CELLS, cells) + encode_frame(FRAME_STATE, state)

    def _record(self, data: bytes) -> None:
        with self._lock:
            self._received.extend(data)

    def _run(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


class TcpBms(SimulatedBms):
    """TCP server on 127.0.0.1; accepts a new client after each drop, so
    auto-reconnect can be exercised."""

    def __init__(self, period: float = 0.02, stream: bool = True) -> None:
        super().__init__(period, stream)
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", 0))
        self._server.listen(1)
        self._server.settimeout(0.1)
        self.port = self._server.getsockname()[1]
        self.connections = 0
        self._drop = threading.Event()
        self._refuse_until = 0.0

    def drop_connection(self, refuse_for: float = 0.0) -> None:
        """Close the current client, like a USB cable being pulled, and
        refuse new clients for ``refuse_for`` seconds."""
        self._refuse_until = time.monotonic() + refuse_for
        self._drop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                client, _ = self._server.accept()
            except socket.timeout:
                continue
            if time.monotonic() < self._refuse_until:
                client.close()
                continue
            self.connections += 1
            self._drop.clear()
            client.settimeout(0.005)
            try:
                self._serve(client)
            finally:
                client.close()
        self._server.close()

    def _serve(self, client: socket.socket) -> None:
        next_tx = time.monotonic()
        while not self._stop.is_set() and not self._drop.is_set():
            try:
                data = client.recv(4096)
                if not data:
                    return
                self._record(data)
            except socket.timeout:
                pass
            except OSError:
                return
            if self.stream and time.monotonic() >= next_tx:
                try:
                    client.sendall(self.telemetry())
                except OSError:
                    return
                self.frames_sent += 2
                next_tx += self.period


class PtyBms(SimulatedBms):
    """Device on the master side of a POSIX pseudo-terminal; the app opens
    ``self.port`` (e.g. /dev/pts/3) as an ordinary serial port."""

    def __init__(self, period: float = 0.02) -> None:
        super().__init__(period)
        import tty

        self._master, slave = os.openpty()
        tty.setraw(slave)
        self.port = os.ttyname(slave)
        self._slave = slave   # keep open so the pty survives app close/reopen
        os.set_blocking(self._master, False)

    def _run(self) -> None:
        next_tx = time.monotonic()
        try:
            while not self._stop.is_set():
                try:
                    data = os.read(self._master, 4096)
                    if data:
                        self._record(data)
                except (BlockingIOError, OSError):
                    pass
                if time.monotonic() >= next_tx:
                    try:
                        os.write(self._master, self.telemetry())
                        self.frames_sent += 2
                    except OSError:
                        pass
                    next_tx += self.period
                time.sleep(0.002)
        finally:
            os.close(self._master)
            os.close(self._slave)
