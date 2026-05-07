"""Serial worker thread with background polling and priority TX queue."""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass
from typing import Iterable, List, Optional

import serial
from serial.tools import list_ports
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker

from ..protocol.packet_parser import ParsedPacket, ParserProtocol, create_parser
from ..decoder.types import PollingScheduleSpec, ProtocolConfig


@dataclass(frozen=True)
class SerialSettings:
    port: str
    baud_rate: int = 115200
    data_bits: int = 8
    stop_bits: float = 1
    parity: str = "N"
    timeout_ms: int = 50


class PollingWorker(QThread):
    packet_received = Signal(ParsedPacket, float) # packet, delta_t_ms
    metrics_updated = Signal(int, int, int) # timeouts, crc_errors, rx_bytes
    error_occurred = Signal(str)
    tx_recorded = Signal(bytes)

    def __init__(
        self, 
        settings: SerialSettings, 
        protocol: ProtocolConfig, 
        schedules: List[PollingScheduleSpec]
    ) -> None:
        super().__init__()
        self.settings = settings
        self.protocol = protocol
        
        # Make a mutable copy of schedules so we can toggle them
        self._schedules = [
            {"spec": s, "next_run": time.time(), "enabled": s.enabled} 
            for s in schedules
        ]
        self._parser = create_parser(protocol)
        
        self._serial: serial.Serial | None = None
        self._running = False
        self._polling_global_enabled = True
        
        self._priority_tx_queue: queue.Queue[bytes] = queue.Queue()
        self._mutex = QMutex()
        
        self._timeouts = 0
        self._crc_errors = 0
        self._rx_bytes = 0

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def open(self) -> None:
        if self.is_open:
            return
        self._serial = serial.Serial(
            port=self.settings.port,
            baudrate=self.settings.baud_rate,
            bytesize=self.settings.data_bits,
            stopbits=self.settings.stop_bits,
            parity=self.settings.parity,
            timeout=self.settings.timeout_ms / 1000.0,
            write_timeout=self.settings.timeout_ms / 1000.0,
        )
        self._running = True
        self.start()

    def close(self) -> None:
        self._running = False
        self.wait()
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def enqueue_priority_tx(self, data: bytes) -> None:
        self._priority_tx_queue.put(data)

    def set_polling_global(self, enabled: bool) -> None:
        with QMutexLocker(self._mutex):
            self._polling_global_enabled = enabled

    def toggle_schedule(self, target_id: int, enabled: bool) -> None:
        with QMutexLocker(self._mutex):
            for s in self._schedules:
                if s["spec"].target_id == target_id:
                    s["enabled"] = enabled

    def run(self) -> None:
        while self._running:
            try:
                # 1. Handle Priority TX (Parameter editing / manual commands)
                if not self._priority_tx_queue.empty():
                    tx_data = self._priority_tx_queue.get()
                    if self._serial:
                        self._serial.write(tx_data)
                        self.tx_recorded.emit(tx_data)
                        # Wait for response if it's Modbus, to avoid collisions.
                        # For simplicity, we just wait a bit or let the read loop catch it.
                        if self.protocol.parser_type == "modbus_rtu":
                            self._await_modbus_response(tx_data, target_id=None)
                        else:
                            time.sleep(0.01) # Give device time to process
                    continue

                # 2. Handle Polling Engine
                with QMutexLocker(self._mutex):
                    polling_enabled = self._polling_global_enabled
                
                polled = False
                if polling_enabled:
                    now = time.time()
                    for sched in self._schedules:
                        if sched["enabled"] and now >= sched["next_run"]:
                            self._do_poll(sched)
                            sched["next_run"] = time.time() + (sched["spec"].interval_ms / 1000.0)
                            polled = True
                            break # Only do one poll per loop to interleave Priority TX
                
                # 3. Drain incoming data (for continuous framed protocols or unexpected data)
                if not polled and self._serial:
                    w = self._serial.in_waiting
                    if w > 0:
                        data = self._serial.read(w)
                        print(f"[DEBUG] serial read {len(data)} bytes: {data.hex()}")
                        self._rx_bytes += len(data)
                        self._parser.feed(data)
                        for p in self._parser.extract_all():
                            if not p.ok:
                                self._crc_errors += 1
                            self.packet_received.emit(p, 0.0)
                        self.metrics_updated.emit(self._timeouts, self._crc_errors, self._rx_bytes)
                
                time.sleep(0.01)

            except Exception as e:
                self.error_occurred.emit(str(e))
                self._running = False

    def _do_poll(self, sched: dict) -> None:
        target_id = sched["spec"].target_id
        timeout_ms = sched["spec"].timeout_ms
        
        if self.protocol.parser_type == "modbus_rtu":
            from ..protocol.packet_builder import build_modbus_packet
            req = build_modbus_packet(self.protocol, target_id, b"")
            self._serial.write(req)
            self.tx_recorded.emit(req)
            self._await_modbus_response(req, target_id, timeout_ms)
        else:
            # Framed protocol polling
            from ..protocol.packet_builder import build_packet
            try:
                req = build_packet(self.protocol, target_id, b"")
                self._serial.write(req)
                self.tx_recorded.emit(req)
                self._await_response(timeout_ms, target_id)
            except ValueError:
                # If we cannot build a packet with empty payload, ignore
                pass

    def _await_modbus_response(self, req: bytes, target_id: Optional[int], timeout_ms: int = 100) -> None:
        self._await_response(timeout_ms, target_id)

    def _await_response(self, timeout_ms: int, target_id: Optional[int]) -> None:
        tx_time = time.time()
        end_time = tx_time + (timeout_ms / 1000.0)
        packet_found = False
        
        while time.time() < end_time and self._running:
            w = self._serial.in_waiting
            if w > 0:
                data = self._serial.read(w)
                self._rx_bytes += len(data)
                self._parser.feed(data)
                for p in self._parser.extract_all():
                    if not p.ok:
                        self._crc_errors += 1
                    else:
                        if target_id is not None and p.frame_id == 1:
                            # If it's Modbus RTU, the parser returns Slave ID (1)
                            # We overwrite it with target_id (register address) for the decoder
                            if self.protocol.parser_type == "modbus_rtu":
                                p.frame_id = target_id
                    
                    rx_time = time.time()
                    delta_t = (rx_time - tx_time) * 1000.0
                    self.packet_received.emit(p, delta_t)
                    packet_found = True
            if packet_found:
                break
            time.sleep(0.005)
            
        if not packet_found:
            self._timeouts += 1
        self.metrics_updated.emit(self._timeouts, self._crc_errors, self._rx_bytes)


def available_ports() -> Iterable[str]:
    return [port.device for port in list_ports.comports()]
