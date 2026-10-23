"""Asynchronous QThread Serial Transceiver with priority TX queue."""

from __future__ import annotations

import logging
import queue
import time
from enum import Enum
from typing import Any, List, Optional

import serial
from PySide6.QtCore import QObject, QThread, Signal

from .packet_codec import (
    BoardParamsTelemetry,
    CellDataTelemetry,
    CommandEchoTelemetry,
    DecodedPacket,
    FaultSoCTelemetry,
    decode_stream,
    encode_command_packet,
)
from .protocol_defs import ALL_CONTROL_FRAMES, DEFAULT_BAUD_RATE, DEFAULT_TIMEOUT_S

logger = logging.getLogger("SingleCellCycler.Transceiver")


class TransceiverState(Enum):
    DISCONNECTED = "Disconnected"
    CONNECTING = "Connecting"
    CONNECTED = "Connected"
    ERROR = "Error"


class SerialTransceiver(QThread):
    """Worker thread managing physical serial communication."""

    # Qt Signals
    connection_changed = Signal(str, str)             # state_value, message
    cell_data_received = Signal(object)               # CellDataTelemetry
    board_params_received = Signal(object)           # BoardParamsTelemetry
    fault_soc_received = Signal(object)              # FaultSoCTelemetry
    command_echo_received = Signal(object)           # CommandEchoTelemetry (0x6000-0x6004 readbacks)
    raw_packet_received = Signal(object)             # DecodedPacket
    command_transmitted = Signal(int, int, bytes)    # frame_id, payload_byte, full_wire_bytes
    error_occurred = Signal(str)                     # error message
    stats_updated = Signal(int, int, int)            # rx_packets, tx_packets, errors

    def __init__(
        self,
        port: str = "",
        baud_rate: int = DEFAULT_BAUD_RATE,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.port = port
        self.baud_rate = baud_rate

        self._is_running = False
        self._tx_queue: queue.PriorityQueue = queue.PriorityQueue()
        self._serial_conn: Optional[serial.Serial] = None

        # Stats
        self._rx_count = 0
        self._tx_count = 0
        self._err_count = 0

    def connect_serial(self, port: str, baud_rate: int = DEFAULT_BAUD_RATE) -> None:
        """Initiate physical serial connection."""
        self.port = port
        self.baud_rate = baud_rate
        if not self.isRunning():
            self.start()

    def send_safe_zero_commands(self, priority: int = 0) -> None:
        """Enqueue priority commands to safely reset all 5 control registers (0x6000 - 0x6004) to zero."""
        for frame_id in ALL_CONTROL_FRAMES:
            self.send_command(frame_id, 0x00, priority)

    def disconnect_serial(self, send_safe_zero: bool = True, timeout_s: float = 1.5) -> None:
        """Disconnect and stop worker thread, ensuring all control registers are zeroed and flushed.
        
        Parameters
        ----------
        send_safe_zero: bool
            If True and connection is active, dispatches 0x00 to all 5 control registers (0x6000-0x6004).
        timeout_s: float
            Maximum seconds to wait for outgoing queue to drain before closing physical port.
        """
        if self._serial_conn and self._serial_conn.is_open:
            if send_safe_zero and self._tx_queue.empty():
                logger.info("Transceiver disconnect: resetting all hardware controls (0x6000 - 0x6004) to 0...")
                self.send_safe_zero_commands(priority=0)

            # Wait for TX queue to be completely written out by background thread
            start = time.time()
            while not self._tx_queue.empty() and (time.time() - start) < timeout_s:
                time.sleep(0.02)
            # Give short settling time for final frame to clear hardware UART FIFO
            time.sleep(0.06)

        self._is_running = False
        if self.isRunning():
            self.wait(1000)

        if self._serial_conn and self._serial_conn.is_open:
            try:
                self._serial_conn.close()
            except Exception:
                pass
        self._serial_conn = None
        self.connection_changed.emit(TransceiverState.DISCONNECTED.value, "Disconnected")

    def send_command(self, frame_id: int, payload_byte: int, priority: int = 1) -> None:
        """Enqueue high-priority command for transmission.
        
        Priority: 0 = Emergency (Highest), 1 = Normal Control, 2 = Low.
        """
        wire_packet = encode_command_packet(frame_id, payload_byte)
        self._tx_queue.put((priority, time.time(), frame_id, payload_byte, wire_packet))

    def run(self) -> None:
        """Background thread execution loop for physical serial I/O."""
        self._is_running = True
        rx_buffer = bytearray()
        last_stats_time = time.time()

        while self._is_running:
            # Reopen the port after startup or I/O failures without requiring a restart.
            if not self._serial_conn or not self._serial_conn.is_open:
                try:
                    self.connection_changed.emit(TransceiverState.CONNECTING.value, f"Opening {self.port}...")
                    self._serial_conn = serial.Serial(
                        port=self.port,
                        baudrate=self.baud_rate,
                        timeout=DEFAULT_TIMEOUT_S,
                        write_timeout=0.2,
                    )
                    rx_buffer.clear()
                    self.connection_changed.emit(
                        TransceiverState.CONNECTED.value,
                        f"Connected to {self.port} @ {self.baud_rate}",
                    )
                except Exception as exc:
                    self._err_count += 1
                    self.connection_changed.emit(TransceiverState.ERROR.value, f"Serial unavailable; retrying: {exc}")
                    self.error_occurred.emit(str(exc))
                    self._serial_conn = None
                    for _ in range(50):
                        if not self._is_running:
                            break
                        time.sleep(0.1)
                    continue

            try:
                # 1. Process outbound priority TX queue
                while not self._tx_queue.empty():
                    prio, ts, frame_id, payload_byte, wire_bytes = self._tx_queue.get_nowait()
                    self._serial_conn.write(wire_bytes)
                    self._serial_conn.flush()
                    time.sleep(0.050)  # Enforce 50ms inter-frame delay to prevent MCU UART drops
                    self._tx_count += 1
                    self.command_transmitted.emit(frame_id, payload_byte, wire_bytes)

                # 2. Read inbound RX bytes from physical serial
                bytes_waiting = self._serial_conn.in_waiting
                if bytes_waiting > 0:
                    chunk = self._serial_conn.read(min(bytes_waiting, 1024))
                    if chunk:
                        rx_buffer.extend(chunk)
                        packets, rx_buffer = decode_stream(rx_buffer)
                        for pkt in packets:
                            self._rx_count += 1
                            self._dispatch_packet(pkt)
                else:
                    time.sleep(0.005)

                # 3. Emit stats periodically (every 500ms)
                now = time.time()
                if now - last_stats_time >= 0.5:
                    self.stats_updated.emit(self._rx_count, self._tx_count, self._err_count)
                    last_stats_time = now
            except Exception as exc:
                self._err_count += 1
                self.error_occurred.emit(f"Serial I/O error; reconnecting: {exc}")
                try:
                    if self._serial_conn and self._serial_conn.is_open:
                        self._serial_conn.close()
                except Exception:
                    pass
                self._serial_conn = None
                time.sleep(0.5)

        # Cleanup
        if self._serial_conn and self._serial_conn.is_open:
            try:
                self._serial_conn.close()
            except Exception:
                pass
        self._serial_conn = None

    def _dispatch_packet(self, packet: DecodedPacket) -> None:
        """Route decoded packet to appropriate Qt signal."""
        self.raw_packet_received.emit(packet)
        if isinstance(packet, CellDataTelemetry):
            self.cell_data_received.emit(packet)
        elif isinstance(packet, BoardParamsTelemetry):
            self.board_params_received.emit(packet)
        elif isinstance(packet, FaultSoCTelemetry):
            self.fault_soc_received.emit(packet)
        elif isinstance(packet, CommandEchoTelemetry):
            self.command_echo_received.emit(packet)
