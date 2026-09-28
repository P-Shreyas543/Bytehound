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
    DecodedPacket,
    FaultSoCTelemetry,
    decode_stream,
    encode_command_packet,
)
from .protocol_defs import DEFAULT_BAUD_RATE, DEFAULT_TIMEOUT_S

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

    def disconnect_serial(self) -> None:
        """Disconnect and stop worker thread."""
        self._is_running = False
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

        try:
            self.connection_changed.emit(TransceiverState.CONNECTING.value, f"Opening {self.port}...")
            self._serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                timeout=DEFAULT_TIMEOUT_S,
                write_timeout=0.2,
            )
            self.connection_changed.emit(TransceiverState.CONNECTED.value, f"Connected to {self.port} @ {self.baud_rate}")
        except Exception as exc:
            self._is_running = False
            self._err_count += 1
            self.connection_changed.emit(TransceiverState.ERROR.value, f"Failed to open {self.port}: {exc}")
            self.error_occurred.emit(str(exc))
            return

        rx_buffer = bytearray()
        last_stats_time = time.time()

        while self._is_running:
            # 1. Process outbound priority TX queue
            while not self._tx_queue.empty():
                try:
                    prio, ts, frame_id, payload_byte, wire_bytes = self._tx_queue.get_nowait()
                    if self._serial_conn and self._serial_conn.is_open:
                        self._serial_conn.write(wire_bytes)
                        self._serial_conn.flush()
                        time.sleep(0.015)  # Enforce 15ms inter-frame delay per protocol spec

                    self._tx_count += 1
                    self.command_transmitted.emit(frame_id, payload_byte, wire_bytes)
                except Exception as exc:
                    self._err_count += 1
                    self.error_occurred.emit(f"TX Error: {exc}")

            # 2. Read inbound RX bytes from physical serial
            if self._serial_conn and self._serial_conn.is_open:
                try:
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
                except Exception as exc:
                    self._err_count += 1
                    self.error_occurred.emit(f"RX Error: {exc}")
                    time.sleep(0.05)

            # 3. Emit stats periodically (every 500ms)
            now = time.time()
            if now - last_stats_time >= 0.5:
                self.stats_updated.emit(self._rx_count, self._tx_count, self._err_count)
                last_stats_time = now

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
