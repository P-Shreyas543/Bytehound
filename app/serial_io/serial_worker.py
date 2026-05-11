"""Serial worker thread with background polling, priority TX queue,
hardware-disconnect detection, data watchdog, and graceful shutdown.

Architecture changes vs the prototype
--------------------------------------
* ``packets_received(list)`` – emits *batched* packets (up to 50 at once, or
  every 16 ms) instead of one signal per packet. Prevents Qt event-loop
  flooding at high baud rates (≥ 115200).

* ``connection_lost`` – emitted when a ``serial.SerialException`` whose OS
  error code indicates a physical unplug (WinError 5, 22, or the generic
  "device disconnected" pattern) is caught inside the run loop.

* ``device_timeout`` – emitted when the device is connected but has sent no
  data for ``WATCHDOG_TIMEOUT`` seconds. Fires repeatedly (once per loop
  iteration while starved) so the UI can debounce it.

* ``stop()`` / ``threading.Event`` – thread-safe shutdown that avoids the
  boolean-flag race present in the prototype. ``close()`` calls ``stop()``
  then ``wait(2000)`` so the COM port is released before the caller returns.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Iterable, List, Optional

import serial
from serial.tools import list_ports
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker

from ..protocol.packet_parser import ParsedPacket, ParserProtocol, create_parser
from ..decoder.types import PollingScheduleSpec, ProtocolConfig

# ------------------------------------------------------------------
# Tuning constants
# ------------------------------------------------------------------
_BATCH_SIZE = 50          # emit after accumulating this many packets …
_BATCH_INTERVAL = 0.016  # … or after this many seconds (≈ 60 Hz), whichever is first
WATCHDOG_TIMEOUT = 3.0   # seconds of silence before emitting device_timeout
# Hold off polling for this long after open() if the device has not yet sent
# anything. Cover Arduino bootloader (~1.5 s) plus a margin. Once the first
# byte arrives the gate opens immediately, so request/response-only devices
# still see polling start as soon as the user enables it AND the timeout
# elapses (whichever comes second).
POLLING_BOOT_GRACE = 2.5

# OS error codes that indicate a physical disconnect on Windows.
_DISCONNECT_WINERRORS = {5, 22, 31, 1167}


@dataclass(frozen=True)
class SerialSettings:
    port: str
    baud_rate: int = 115200
    data_bits: int = 8
    stop_bits: float = 1
    parity: str = "N"
    timeout_ms: int = 50


class PollingWorker(QThread):
    # Batch of parsed packets (may include bad CRC frames)
    packets_received = Signal(list)
    metrics_updated = Signal(int, int, int)   # timeouts, crc_errors, rx_bytes
    error_occurred = Signal(str)
    tx_recorded = Signal(bytes)

    # Hardware-safety signals
    connection_lost = Signal()   # USB physically unplugged
    device_timeout = Signal()    # connected but no data for WATCHDOG_TIMEOUT s

    def __init__(
        self,
        settings: SerialSettings,
        protocol: ProtocolConfig,
        schedules: List[PollingScheduleSpec],
    ) -> None:
        super().__init__()
        self.settings = settings
        self.protocol = protocol

        self._schedules = [
            {"spec": s, "next_run": time.time(), "enabled": s.enabled}
            for s in schedules
        ]
        # Round-robin cursor into _schedules. The polling loop scans starting
        # here instead of from index 0 every time, so a schedule near the top
        # of the list can't starve schedules further down (which happened when
        # a dummy frame's timeout blocked the loop long enough for earlier
        # schedules to become due again before the cursor reached the tail).
        self._sched_cursor: int = 0
        self._parser = create_parser(protocol)

        self._serial: serial.Serial | None = None
        self._stop_event = threading.Event()          # thread-safe shutdown flag
        self._polling_global_enabled = False

        # Bounded queue so a buggy UI loop pushing TX commands faster than
        # the worker can drain them cannot grow without limit and OOM.
        # 256 is a generous cap — far above any human-driven rate.
        self._priority_tx_queue: queue.Queue[bytes] = queue.Queue(maxsize=256)
        self._mutex = QMutex()

        self._timeouts = 0
        self._crc_errors = 0
        self._rx_bytes = 0

        # Batch-emission state
        self._batch: List[ParsedPacket] = []
        self._last_emit_time: float = 0.0

        # Watchdog state
        self._last_rx_time: float = time.time()
        self._watchdog_fired = False  # debounce: only emit once per silence window
        # Set in open() — used by the polling-boot-grace gate in _run_loop.
        self._open_time: float = time.time()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
            # Fix (review comment 3): explicitly bound read() to timeout_ms
            # (default 50 ms). This guarantees the run loop checks _stop_event
            # at least every 50 ms so closeEvent's wait(2000) can never hang
            # beyond one read-timeout cycle after stop() is called.
            timeout=self.settings.timeout_ms / 1000.0,
            write_timeout=self.settings.timeout_ms / 1000.0,
        )
        self._stop_event.clear()
        self._last_rx_time = time.time()
        self._last_emit_time = time.time()
        # Used by the polling gate in _run_loop — see POLLING_BOOT_GRACE.
        self._open_time = time.time()
        self.start()


    def stop(self) -> None:
        """Signal the run loop to exit.  Thread-safe; may be called from any thread."""
        self._stop_event.set()

    def close(self) -> None:
        """Stop the thread and release the COM port.  Blocks up to 2 s."""
        self.stop()
        self.wait(2000)
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    def enqueue_priority_tx(self, data: bytes) -> None:
        try:
            self._priority_tx_queue.put_nowait(data)
        except queue.Full:
            # Drop and surface. A full queue means the UI is generating TX
            # commands faster than the wire can carry them. Better to lose one
            # command than silently grow memory unbounded. ASCII-only so the
            # message renders cleanly on Windows' cp1252 console.
            self.error_occurred.emit(
                "TX queue full - command dropped (UI is sending faster than the link can sustain)."
            )

    def set_polling_global(self, enabled: bool) -> None:
        with QMutexLocker(self._mutex):
            self._polling_global_enabled = enabled

    def reset_metrics(self) -> None:
        """Zero the worker-owned counters (timeouts / crc_errors / rx_bytes).

        The worker is the single source of truth for these counters and
        broadcasts them via metrics_updated. Without this method, a UI-side
        "clear" only zeros the displayed values for one frame — the next
        emission snaps them back to the worker's running totals.
        """
        with QMutexLocker(self._mutex):
            self._timeouts = 0
            self._crc_errors = 0
            self._rx_bytes = 0
        # Push the cleared values out immediately so the UI doesn't have to
        # wait for the next packet before reflecting the reset.
        self.metrics_updated.emit(0, 0, 0)

    def toggle_schedule(self, target_id: int, enabled: bool) -> None:
        with QMutexLocker(self._mutex):
            for s in self._schedules:
                if s["spec"].target_id == target_id:
                    s["enabled"] = enabled
                    # Re-enabling a previously-failed schedule clears the
                    # "already reported" flag so a subsequent build error is
                    # surfaced again instead of staying silent.
                    if enabled:
                        s.pop("_failed_reported", None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_disconnect_error(self, exc: serial.SerialException) -> bool:
        """Return True if the exception looks like a physical USB unplug."""
        msg = str(exc).lower()
        # WinError numeric codes embedded in the exception string
        for code in _DISCONNECT_WINERRORS:
            if f"winerror {code}" in msg or f"[error {code}]" in msg:
                return True
        # Common cross-platform patterns
        disconnect_phrases = (
            "device disconnected",
            "access is denied",
            "the device does not recognize the command",
            "input/output error",
            "port is closed",
            "handle is invalid",
        )
        return any(phrase in msg for phrase in disconnect_phrases)

    def _flush_batch(self) -> None:
        """Emit accumulated packets and reset the batch."""
        if self._batch:
            self.packets_received.emit(list(self._batch))
            self._batch.clear()
        self._last_emit_time = time.time()

    def _should_flush(self) -> bool:
        return (
            len(self._batch) >= _BATCH_SIZE
            or (time.time() - self._last_emit_time) >= _BATCH_INTERVAL
        )

    def _accumulate(self, packets: Iterable[ParsedPacket]) -> None:
        """Add packets to the batch and flush when threshold is reached."""
        for p in packets:
            if not p.ok:
                self._crc_errors += 1
            self._batch.append(p)
        if self._should_flush():
            self._flush_batch()

    def _check_watchdog(self) -> None:
        """Emit device_timeout if no data received within WATCHDOG_TIMEOUT."""
        silence = time.time() - self._last_rx_time
        if silence > WATCHDOG_TIMEOUT:
            if not self._watchdog_fired:
                self.device_timeout.emit()
                self._watchdog_fired = True
        else:
            self._watchdog_fired = False  # reset once data flows again

    # ------------------------------------------------------------------
    # Thread run loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        self._last_emit_time = time.time()
        try:
            self._run_loop()
        finally:
            # Flush anything still in the batch before the thread dies.
            self._flush_batch()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                # 1. Handle Priority TX (parameter editing / manual commands)
                if not self._priority_tx_queue.empty():
                    tx_data = self._priority_tx_queue.get()
                    if self._serial:
                        self._serial.write(tx_data)
                        self.tx_recorded.emit(tx_data)
                        if self.protocol.parser_type == "modbus_rtu":
                            self._await_modbus_response(tx_data, target_id=None)
                        else:
                            time.sleep(0.01)
                    continue

                # 2. Handle Polling Engine
                with QMutexLocker(self._mutex):
                    polling_enabled = self._polling_global_enabled

                polled = False
                # Polling gate: hold off until the device has either sent us
                # at least one byte (proof it is alive) OR the boot-grace
                # window has elapsed (so devices that are request/response
                # only still get polled). Hammering polls during an Arduino
                # bootloader window leaves the link stuck — the device cannot
                # answer, timeouts accumulate, and we never get out.
                grace_expired = (time.time() - self._open_time) > POLLING_BOOT_GRACE
                if polling_enabled and (self._rx_bytes > 0 or grace_expired):
                    now = time.time()
                    n = len(self._schedules)
                    # Round-robin: start scanning at _sched_cursor and wrap.
                    # Each successful poll advances the cursor by one, so the
                    # next iteration begins with the *following* schedule —
                    # not the head of the list. Guarantees every enabled
                    # schedule that is due gets visited in turn even when
                    # some entries are slow (full-timeout) and others fast.
                    for offset in range(n):
                        idx = (self._sched_cursor + offset) % n
                        sched = self._schedules[idx]
                        if sched["enabled"] and now >= sched["next_run"]:
                            self._do_poll(sched)
                            sched["next_run"] = time.time() + (sched["spec"].interval_ms / 1000.0)
                            self._sched_cursor = (idx + 1) % n
                            polled = True
                            break

                # 3. Drain incoming data (continuous / framed protocols)
                if not polled and self._serial:
                    w = self._serial.in_waiting
                    if w > 0:
                        data = self._serial.read(w)
                        self._rx_bytes += len(data)
                        self._last_rx_time = time.time()
                        self._watchdog_fired = False
                        self._parser.feed(data)
                        self._accumulate(self._parser.extract_all())
                        self.metrics_updated.emit(self._timeouts, self._crc_errors, self._rx_bytes)

                # Always check the watchdog at the end of the iteration. If we
                # only ran it inside the "not polled and no bytes waiting"
                # branch, a busy polling schedule that the device has stopped
                # responding to would never trip device_timeout — _last_rx_time
                # would simply stop advancing while polls keep firing. The
                # watchdog is debounced internally so calling it every loop
                # iteration is cheap and safe.
                self._check_watchdog()

                # Flush batch on timer even when quiet
                if self._should_flush():
                    self._flush_batch()

                time.sleep(0.005)

            except serial.SerialException as exc:
                if self._is_disconnect_error(exc):
                    # Physical unplug — clean up and notify the UI.
                    try:
                        if self._serial is not None:
                            self._serial.close()
                            self._serial = None
                    except Exception:
                        pass
                    self._flush_batch()
                    self.connection_lost.emit()
                    return  # exit the run loop gracefully
                else:
                    # Other serial error — report to UI via existing signal.
                    self.error_occurred.emit(str(exc))
                    self._stop_event.set()
                    return

            except Exception as exc:
                self.error_occurred.emit(str(exc))
                self._stop_event.set()
                return

    # ------------------------------------------------------------------
    # Polling helpers (unchanged logic, adapted to use _accumulate)
    # ------------------------------------------------------------------

    def _do_poll(self, sched: dict) -> None:
        target_id = sched["spec"].target_id
        timeout_ms = sched["spec"].timeout_ms

        if self.protocol.parser_type == "modbus_rtu":
            from ..protocol.packet_builder import build_modbus_packet
            try:
                req = build_modbus_packet(self.protocol, target_id, b"")
                self._serial.write(req)
                self.tx_recorded.emit(req)
                self._await_modbus_response(req, target_id, timeout_ms)
            except ValueError as exc:
                self._disable_failed_schedule(sched, exc)
        else:
            from ..protocol.packet_builder import build_packet
            try:
                req = build_packet(self.protocol, target_id, b"")
                self._serial.write(req)
                self.tx_recorded.emit(req)
                self._await_response(timeout_ms, target_id)
            except ValueError as exc:
                # Most common cause: target_id does not fit in the configured
                # frame_id_size, or the protocol config is otherwise malformed.
                # Without this guard, polling kept retrying every interval and
                # silently failed forever.
                self._disable_failed_schedule(sched, exc)

    def _disable_failed_schedule(self, sched: dict, exc: BaseException) -> None:
        """Disable a schedule that cannot build its request, reporting once."""
        target_id = sched["spec"].target_id
        if not sched.get("_failed_reported"):
            self.error_occurred.emit(
                f"Polling for 0x{target_id:X} disabled — could not build "
                f"request: {exc}"
            )
            sched["_failed_reported"] = True
        sched["enabled"] = False

    def _await_modbus_response(self, req: bytes, target_id: Optional[int], timeout_ms: int = 100) -> None:
        self._await_response(timeout_ms, target_id)

    def _await_response(self, timeout_ms: int, target_id: Optional[int]) -> None:
        tx_time = time.time()
        end_time = tx_time + (timeout_ms / 1000.0)
        packet_found = False

        while time.time() < end_time and not self._stop_event.is_set():
            w = self._serial.in_waiting
            if w > 0:
                data = self._serial.read(w)
                self._rx_bytes += len(data)
                self._last_rx_time = time.time()
                self._watchdog_fired = False
                self._parser.feed(data)
                for p in self._parser.extract_all():
                    if not p.ok:
                        self._crc_errors += 1
                    else:
                        if target_id is not None and p.frame_id == 1:
                            if self.protocol.parser_type == "modbus_rtu":
                                p.frame_id = target_id
                    rx_time = time.time()
                    delta_t = (rx_time - tx_time) * 1000.0
                    # For polling responses we still emit immediately (low frequency)
                    self.packets_received.emit([p])
                    packet_found = True
            if packet_found:
                break
            time.sleep(0.005)

        if not packet_found:
            self._timeouts += 1
        self.metrics_updated.emit(self._timeouts, self._crc_errors, self._rx_bytes)


def available_ports() -> Iterable[tuple[str, str]]:
    """Return a list of ``(device, description)`` tuples for every serial port.

    ``device``      – the raw port identifier passed to ``serial.Serial()``
                      e.g. ``"COM3"`` on Windows, ``"/dev/ttyUSB0"`` on Linux.
    ``description`` – a human-readable label from the OS driver database
                      e.g. ``"USB Serial Device (COM3)"``.
                      Falls back to the device string when unavailable.
    """
    return [
        (port.device, port.description or port.device)
        for port in list_ports.comports()
    ]
