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

import logging
import queue
import select
import socket
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional

import serial
from serial.tools import list_ports
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker

from ..protocol.packet_parser import ParsedPacket, create_parser
from ..decoder.frame_decoder import decode_frame
from ..decoder.types import FrameConfig, PollingScheduleSpec, ProtocolConfig
from ..serial_logging.raw_capture import RX, TX, RawCapture

_LOG = logging.getLogger("bytehound.serial_io.worker")


def list_available_ports() -> List[str]:
    """Return a list of available serial COM port device names."""
    try:
        return [p.device for p in list_ports.comports()]
    except Exception:
        return []


def auto_detect_primary_port() -> Optional[str]:
    """Auto-detect the most likely connected hardware serial port."""
    try:
        ports = list_ports.comports()
        if not ports:
            return None
        # Prefer USB / Serial devices over virtual / bluetooth ports
        for p in ports:
            desc = (p.description or "").lower()
            if "usb" in desc or "serial" in desc or "uart" in desc or "ch340" in desc or "ftdi" in desc or "cp210" in desc:
                return p.device
        return ports[0].device
    except Exception:
        return None


# Socket receive buffer requested from the OS. The default (64 KiB on
# Windows) overflows during bursts and the OS then drops UDP datagrams
# silently (Plane.md F5). 4 MiB holds ~20 s at 2 Mbaud-equivalent rates.
SOCKET_RCVBUF_BYTES = 4 * 1024 * 1024
# Largest possible UDP payload; a smaller recv() size truncates (or on
# Windows errors on) bigger datagrams (Plane.md F4).
_UDP_MAX_DATAGRAM = 65535
_TCP_RECV_CHUNK = 65536
_SEND_TIMEOUT_S = 2.0


def _enlarge_rcvbuf(sock: socket.socket) -> int:
    """Ask for a large receive buffer; return the size the OS granted."""
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, SOCKET_RCVBUF_BYTES)
    except OSError:
        _LOG.warning("Could not enlarge socket receive buffer", exc_info=True)
    try:
        granted = int(sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF))
    except (OSError, TypeError, ValueError):
        _LOG.warning("Could not read socket receive buffer size", exc_info=True)
        return 0
    if granted < SOCKET_RCVBUF_BYTES // 2:
        _LOG.warning(
            "Socket receive buffer is %d bytes (requested %d); bursts may be dropped by the OS",
            granted, SOCKET_RCVBUF_BYTES,
        )
    return granted


def _send_all(sock: socket.socket, data: bytes, kind: str) -> int:
    """Write every byte on a non-blocking socket, or raise.

    ``socket.send`` may write only part of ``data``; the remainder of a
    command would be lost without an error.
    """
    view = memoryview(data)
    deadline = time.monotonic() + _SEND_TIMEOUT_S
    while view:
        try:
            sent = sock.send(view)
            view = view[sent:]
        except BlockingIOError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise serial.SerialException(
                    f"{kind} socket write timed out with {len(view)} of {len(data)} bytes unsent"
                ) from None
            select.select([], [sock], [], remaining)
    return len(data)


class TcpSocketWrapper:
    def __init__(self, host: str, port: int, timeout: float = 0.05):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._socket = None
        self._is_open = False
        self._buffer = bytearray()
        self.rcvbuf_bytes = 0  # receive buffer granted by the OS, set on open()
        self._peer_closed = False  # remote end closed; buffered bytes still delivered

    def open(self):
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.rcvbuf_bytes = _enlarge_rcvbuf(self._socket)
            self._socket.settimeout(2.0)  # connection timeout
            self._socket.connect((self.host, self.port))
            self._socket.setblocking(False)
            self._is_open = True
            self._buffer = bytearray()
            self._peer_closed = False
        except Exception as e:
            self._is_open = False
            if self._socket:
                self._socket.close()
            raise serial.SerialException(f"Failed to connect to TCP server {self.host}:{self.port}: {e}") from e

    @property
    def is_open(self) -> bool:
        return self._is_open

    def write(self, data: bytes) -> int:
        if not self._is_open or not self._socket:
            raise serial.SerialException("Socket not open")
        try:
            return _send_all(self._socket, data, "TCP")
        except serial.SerialException:
            raise
        except Exception as e:
            raise serial.SerialException(f"TCP socket write error: {e}") from e

    def read(self, size: int = 1) -> bytes:
        if not self._is_open or not self._socket:
            raise serial.SerialException("Socket not open")
        try:
            self._fill_buffer()
        except serial.SerialException:
            raise
        except Exception as e:
            raise serial.SerialException(str(e)) from e
        self._raise_if_drained_and_closed()
        res = bytes(self._buffer[:size])
        del self._buffer[:size]
        return res

    @property
    def in_waiting(self) -> int:
        if not self._is_open or not self._socket:
            return 0
        try:
            self._fill_buffer()
        except serial.SerialException:
            raise
        except Exception as e:
            raise serial.SerialException(str(e)) from e
        self._raise_if_drained_and_closed()
        return len(self._buffer)

    def _raise_if_drained_and_closed(self) -> None:
        """Report the peer's close only once every byte received before it
        has been handed over (Plane.md F15)."""
        if self._peer_closed and not self._buffer:
            raise serial.SerialException("TCP connection closed by remote peer")

    def reset_input_buffer(self):
        self._buffer.clear()
        while True:
            try:
                data = self._socket.recv(4096)
                if not data:
                    break
            except (BlockingIOError, socket.timeout):
                break
            except Exception:
                break

    def close(self):
        self._is_open = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    def _fill_buffer(self):
        if self._peer_closed:
            return
        while True:
            try:
                r, _, _ = select.select([self._socket], [], [], 0)
                if not r:
                    break
                data = self._socket.recv(_TCP_RECV_CHUNK)
                if not data:
                    # Peer closed. Keep what is buffered: it is delivered
                    # first, then the close is reported (used to raise here
                    # and lose the device's last bytes).
                    self._peer_closed = True
                    break
                self._buffer.extend(data)
            except BlockingIOError:
                break
            except socket.timeout:
                break
            except serial.SerialException:
                raise
            except OSError as e:
                raise serial.SerialException(f"TCP socket read error: {e}") from e


class UdpSocketWrapper:
    def __init__(self, host: str, port: int, local_port: int = 0, timeout: float = 0.05):
        self.host = host
        self.port = port
        self.local_port = local_port
        self.timeout = timeout
        self._socket = None
        self._is_open = False
        self._buffer = bytearray()
        self.rcvbuf_bytes = 0  # receive buffer granted by the OS, set on open()

    def open(self):
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.rcvbuf_bytes = _enlarge_rcvbuf(self._socket)
            if self.local_port > 0:
                self._socket.bind(("", self.local_port))
            self._socket.connect((self.host, self.port))
            self._socket.setblocking(False)
            self._is_open = True
            self._buffer = bytearray()
        except Exception as e:
            self._is_open = False
            if self._socket:
                self._socket.close()
            raise serial.SerialException(f"Failed to initialize UDP socket: {e}") from e

    @property
    def is_open(self) -> bool:
        return self._is_open

    def write(self, data: bytes) -> int:
        if not self._is_open or not self._socket:
            raise serial.SerialException("Socket not open")
        try:
            return _send_all(self._socket, data, "UDP")
        except serial.SerialException:
            raise
        except Exception as e:
            raise serial.SerialException(f"UDP socket write error: {e}") from e

    def read(self, size: int = 1) -> bytes:
        if not self._is_open or not self._socket:
            raise serial.SerialException("Socket not open")
        try:
            self._fill_buffer()
        except serial.SerialException:
            raise
        except Exception as e:
            raise serial.SerialException(str(e)) from e
        res = bytes(self._buffer[:size])
        del self._buffer[:size]
        return res

    @property
    def in_waiting(self) -> int:
        if not self._is_open or not self._socket:
            return 0
        try:
            self._fill_buffer()
        except serial.SerialException:
            raise
        except Exception as e:
            raise serial.SerialException(str(e)) from e
        return len(self._buffer)

    def reset_input_buffer(self):
        self._buffer.clear()
        while True:
            try:
                data = self._socket.recv(4096)
                if not data:
                    break
            except (BlockingIOError, socket.timeout):
                break
            except Exception:
                break

    def close(self):
        self._is_open = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    def _fill_buffer(self):
        while True:
            try:
                r, _, _ = select.select([self._socket], [], [], 0)
                if not r:
                    break
                data = self._socket.recv(_UDP_MAX_DATAGRAM)
                self._buffer.extend(data)
            except ConnectionResetError:
                # Windows reports an ICMP "port unreachable" (device port
                # briefly closed, e.g. rebooting) as WSAECONNRESET on the
                # next recv. For UDP that is only a notice — treating it as an
                # unplug would end the session. Skip it and keep reading.
                _LOG.debug("UDP: ignored ICMP port-unreachable notice")
                continue
            except BlockingIOError:
                break
            except socket.timeout:
                break
            except OSError as e:
                raise serial.SerialException(f"UDP socket read error: {e}") from e


# Windows comm error flags reported by ClearCommError (Plane.md F7).
COMM_ERROR_FLAGS = {
    0x0001: "rx_buffer_overflow",  # CE_RXOVER: driver input buffer full, bytes lost
    0x0002: "hardware_overrun",    # CE_OVERRUN: UART FIFO overrun, bytes lost
    0x0004: "parity_error",        # CE_RXPARITY
    0x0008: "framing_error",       # CE_FRAME: usually wrong baud rate or noise
    0x0010: "break",               # CE_BREAK
}


def _empty_comm_errors() -> Dict[str, int]:
    return {name: 0 for name in COMM_ERROR_FLAGS.values()}


if sys.platform == "win32":
    import ctypes

    from serial import win32 as _win32
    from serial.serialutil import PortNotOpenError

    class ErrorTrackingSerial(serial.Serial):
        """pyserial port that keeps the driver's error flags.

        pyserial's ``in_waiting`` and ``read()`` call ``ClearCommError`` and
        discard the flags, so receive-buffer overflows and UART overruns —
        bytes lost before they ever reach us — were invisible. This calls
        ``ClearCommError`` first and counts each flag in ``comm_errors``.
        Residual gap: an error raised in the microseconds between our call
        and pyserial's own call inside ``read()`` is still cleared unseen.
        """

        def __init__(self, *args, **kwargs) -> None:
            self.comm_errors: Dict[str, int] = _empty_comm_errors()
            super().__init__(*args, **kwargs)

        def _poll_comm_errors(self) -> int:
            flags = _win32.DWORD()
            comstat = _win32.COMSTAT()
            if not _win32.ClearCommError(self._port_handle, ctypes.byref(flags), ctypes.byref(comstat)):
                raise serial.SerialException(f"ClearCommError failed ({ctypes.WinError()!r})")
            value = flags.value
            if value:
                for bit, name in COMM_ERROR_FLAGS.items():
                    if value & bit:
                        self.comm_errors[name] += 1
            return comstat.cbInQue

        @property
        def in_waiting(self) -> int:
            if not self.is_open:
                raise PortNotOpenError()
            return self._poll_comm_errors()

        def read(self, size: int = 1) -> bytes:
            if self.is_open:
                self._poll_comm_errors()
            return super().read(size)
else:
    # pyserial exposes no line-status errors on POSIX; counts stay at zero
    # and integrity_snapshot() reports them as unavailable.
    ErrorTrackingSerial = serial.Serial


# Tuning constants
_BATCH_SIZE = 50          # emit after accumulating this many packets …
_BATCH_INTERVAL = 0.016  # … or after this many seconds (≈ 60 Hz), whichever is first
WATCHDOG_TIMEOUT = 3.0   # seconds of silence before emitting device_timeout
# Driver-side receive buffer requested at open (Plane.md F16). When the
# reader stalls longer than the buffer lasts, the USB-serial bridge drops the
# overflow upstream with no driver error flag. 4 MiB would hold ~21 s at
# 2 Mbaud. It is a request: pyserial passes it to SetupComm without checking
# the result and a driver may grant less. Measured on the ST-LINK VCP only.
RX_DRIVER_BUFFER = 4 * 1024 * 1024
POLLING_BOOT_GRACE = 2.5
CONSECUTIVE_TIMEOUT_DISABLE_THRESHOLD = 5
POLL_RESPONSE_GRACE_MS = 50
POLL_TX_GAP_FLOOR_MS = 100
POLL_PIPELINE_TX_GAP_FLOOR_MS = 100
_DISCONNECT_WINERRORS = {5, 22, 31, 1167}


@dataclass(frozen=True)
class SerialSettings:
    port: str
    baud_rate: int = 115200
    data_bits: int = 8
    stop_bits: float = 1
    parity: str = "N"
    timeout_ms: int = 50
    auto_reconnect: bool = False
    connection_type: str = "serial"
    host: str = "127.0.0.1"
    port_num: int = 8000
    local_port: int = 0


class PollingWorker(QThread):
    # This worker writes decoded frames to the attached logging session on
    # its own thread (set_session_sink); the GUI must not log them again.
    logs_sessions = True

    # Batch of parsed packets (may include bad CRC frames)
    packets_received = Signal(list)
    metrics_updated = Signal(int, int, int)   # timeouts, crc_errors, rx_bytes
    # Where every received byte went, cumulative for this connection and
    # never reset by reset_metrics() (Plane.md F3). See integrity_snapshot().
    integrity_updated = Signal(object)
    error_occurred = Signal(str)
    warning_occurred = Signal(str)
    tx_recorded = Signal(bytes)
    wire_recorded = Signal(str, bytes, object)  # direction, raw bytes, datetime

    # Hardware-safety signals
    connection_lost = Signal()   # USB physically unplugged
    device_timeout = Signal()    # connected but no data for WATCHDOG_TIMEOUT s
    backpressure_changed = Signal(bool)  # emitted when backpressure throttle engages/releases

    # Diagnostics — UI can surface "avg poll latency 12 ms" per target.
    # Args: (target_id, latency_ms). target_id == -1 for non-addressable
    # protocols.
    poll_latency = Signal(int, float)

    def __init__(
        self,
        settings: SerialSettings,
        protocol: ProtocolConfig,
        schedules: List[PollingScheduleSpec],
        decode_config: Optional[FrameConfig] = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.protocol = protocol
        # When supplied, packets are decoded on this worker thread before
        # being emitted so the GUI thread never blocks on decode work.
        # decode_frame is pure (no shared state); the FrameConfig is treated
        # read-only for the worker's lifetime — the GUI must not mutate it
        # while a session is live. None = pre-decoding disabled (tests).
        self._decode_config: Optional[FrameConfig] = decode_config

        self._schedules = [
            {
                "spec": s,
                "next_run": time.monotonic(),
                "enabled": s.enabled,
                # Consecutive timeouts since last successful response.
                # Reset on success; threshold-based auto-disable lives in
                # _record_poll_timeout / _record_poll_success.
                "consecutive_timeouts": 0,
                # Sticky flag set the first time the device returns a valid
                # response for this target_id. Once true, auto-disable
                # never fires for the schedule — late/slow responses are a
                # device-pacing problem, not a "wrong target" problem.
                # Lets us be aggressive about disabling targets the device
                # genuinely doesn't recognise without ever killing one
                # that's just slow.
                "ever_responded": False,
            }
            for s in schedules
        ]
        # Round-robin cursor into _schedules. The polling loop scans starting
        # here instead of from index 0 every time, so a schedule near the top
        # of the list can't starve schedules further down (which happened when
        # a dummy frame's timeout blocked the loop long enough for earlier
        # schedules to become due again before the cursor reached the tail).
        self._sched_cursor: int = 0
        self._parser = create_parser(protocol)
        self._signal_state: Dict[str, Dict[str, float]] = {}

        self._serial: serial.Serial | None = None
        self._stop_event = threading.Event()          # thread-safe shutdown flag
        self._polling_global_enabled = False
        self._last_tx_time: float = 0.0
        self._flush_rx_before_polling = False

        # Pipelined polling: when enabled, the loop sends up to
        # _pipeline_depth poll requests without waiting for each response,
        # then matches replies by frame_id as they arrive. Cuts cycle time
        # on devices with slow turnaround (the wait time becomes parallel
        # rather than serial). Disabled by default; protocols that can't
        # tag responses (Modbus RTU) silently force it off — see
        # set_pipelining().
        self._pipelining_enabled: bool = False
        self._pipeline_depth: int = 2
        # Minimum spacing between pipelined TXs. ``None`` means "use the
        # module default ``POLL_PIPELINE_TX_GAP_FLOOR_MS``"; a number lets
        # the UI override the floor per session. Devices that don't drop
        # frames at the default 100 ms can tune this down for higher
        # throughput; flaky ones can tune it up.
        self._pipeline_tx_gap_ms: Optional[int] = None
        # In-flight poll bookkeeping. Only mutated on the worker thread.
        # Each entry: {"target_id": int, "tx_time": float, "deadline": float}
        self._in_flight: List[dict] = []

        # Bounded queue so a buggy UI loop pushing TX commands faster than
        # the worker can drain them cannot grow without limit and OOM.
        # 256 is a generous cap — far above any human-driven rate.
        self._priority_tx_queue: queue.Queue[bytes] = queue.Queue(maxsize=256)
        self._mutex = QMutex()

        self._timeouts = 0
        self._crc_errors = 0
        self._rx_bytes = 0

        # Batch-emission state. Items are (packet, decoded_or_None) tuples.
        # decoded is populated when _decode_config is set and packet.ok;
        # always None for bad-CRC packets and when pre-decoding is disabled.
        self._batch: List[tuple] = []
        self._last_emit_time: float = 0.0

        # Watchdog state. Monotonic clock — immune to system-clock jumps
        # (NTP step, DST, manual change). If we used time.time() here a
        # backward jump would make the watchdog fire spuriously and a
        # forward jump would make device_timeout fire late or never.
        self._last_rx_time: float = time.monotonic()
        self._watchdog_fired = False  # debounce: only emit once per silence window
        # Set in open() — used by the polling-boot-grace gate in _run_loop.
        self._open_time: float = time.monotonic()

        # metrics_updated emission throttle. Without this the signal fires on
        # every read iteration; at 115200 baud with continuous data that
        # floods the Qt event queue with hundreds of redundant updates per
        # second. ~10 Hz is plenty for a status-bar readout.
        self._last_metrics_emit: float = 0.0
        self._METRICS_INTERVAL = 0.1  # seconds

        # Frame error reporting throttle
        self._last_frame_error_emit: float = 0.0
        self._last_frame_error_msg: str = ""
        self._consecutive_frame_errors: int = 0

        # Backpressure state (PuTTY-inspired downstream consumer flow control)
        self._backpressure_throttled: bool = False
        self._backpressure_events: int = 0
        self._open_purged_bytes: int = 0
        # Longest time bytes sat waiting in the driver before this thread
        # read them (Plane.md F16). Compared with the driver buffer it says
        # how close a link came to silent upstream loss.
        self._last_rx_service: float = 0.0
        self._rx_service_gap_max: float = 0.0
        # Set while a sequential poll waits, so a response read during a TX
        # gap wait still ends that wait.
        self._await_target: Optional[int] = None
        self._await_hit: bool = False
        # Exceptions raised by the parser while feeding received bytes.
        self._parse_errors: int = 0
        # Polls a late schedule skipped instead of bursting to catch up.
        self._polls_missed: int = 0
        # Logging session written from this thread (task.md Phase 1: per-
        # frame logging cost the GUI thread most of its time at high rates).
        # Read once per _accumulate call; assignment is atomic.
        self._session_sink = None
        self._session_log_errors: int = 0
        self._last_sink_warning: float = 0.0
        # Sequence-counter gap detection (Plane.md F12): frames lost before
        # they reached the PC (USB bridge, network, device) leave no other
        # trace. Only when the config declares counters.
        from ..decoder.sequence import SequenceTracker
        counters = getattr(decode_config, "sequence_counters", None) or {}
        self._seq_tracker = SequenceTracker(dict(counters)) if counters else None
        self._last_seq_warning: float = 0.0

        # Lossless wire capture while logging is on. Written from this thread
        # right after each read/write; the GUI only starts and stops it.
        self._raw_capture: Optional[RawCapture] = None
        # Held while a read/write is recorded and while the capture is
        # swapped, so a segment rotation cannot close the file a record is
        # about to go into (the record would be dropped).
        self._raw_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def set_backpressure(self, throttled: bool) -> None:
        """Signal downstream consumer backpressure status (e.g. from UI).

        When throttled=True the batching window is lengthened so the GUI
        receives fewer, larger batches. Polling and reading are never paused:
        that would leave gaps in the log (Plane.md F2).
        """
        changed = False
        with QMutexLocker(self._mutex):
            if self._backpressure_throttled != throttled:
                self._backpressure_throttled = throttled
                changed = True
                if throttled:
                    self._backpressure_events += 1
                    _LOG.debug("PollingWorker: Backpressure throttle engaged (event #%d)", self._backpressure_events)
                else:
                    _LOG.debug("PollingWorker: Backpressure throttle released")
        if changed:
            self.backpressure_changed.emit(throttled)

    @property
    def is_backpressured(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._backpressure_throttled

    @property
    def backpressure_events(self) -> int:
        with QMutexLocker(self._mutex):
            return self._backpressure_events

    def open(self) -> None:
        if self.is_open:
            return
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.winmm.timeBeginPeriod(1)
            except Exception:
                pass
        if self.settings.connection_type == "tcp":
            self._serial = TcpSocketWrapper(
                host=self.settings.host,
                port=self.settings.port_num,
                timeout=0.05,
            )
            self._serial.open()
        elif self.settings.connection_type == "udp":
            self._serial = UdpSocketWrapper(
                host=self.settings.host,
                port=self.settings.port_num,
                local_port=self.settings.local_port,
                timeout=0.05,
            )
            self._serial.open()
        else:
            self._serial = ErrorTrackingSerial(
                port=self.settings.port,
                baudrate=self.settings.baud_rate,
                bytesize=self.settings.data_bits,
                stopbits=self.settings.stop_bits,
                parity=self.settings.parity,
                # Hardcode OS read timeout to 50ms so the run loop frequently checks
                # _stop_event. The user's protocol timeout is enforced logically.
                # Prevents main-thread close() from crashing if protocol timeout > 2s.
                timeout=0.05,
                write_timeout=0.05,
            )
            try:
                self._serial.set_buffer_size(rx_size=RX_DRIVER_BUFFER, tx_size=65536)
            except Exception:
                pass
            try:
                # Bytes left over from before this connection (cold-boot
                # fragments). No session exists yet, so dropping them loses
                # no logged data — but the amount is recorded (Plane.md F6).
                self._open_purged_bytes = self._serial.in_waiting
                self._serial.reset_input_buffer()
                if self._open_purged_bytes:
                    _LOG.info(
                        "Discarded %d stale bytes waiting on %s at connect",
                        self._open_purged_bytes, self.settings.port,
                    )
            except Exception:
                pass
        self._stop_event.clear()
        self._last_rx_time = time.monotonic()
        self._last_emit_time = time.monotonic()
        # Used by the polling gate in _run_loop — see POLLING_BOOT_GRACE.
        self._open_time = time.monotonic()
        # Highest normal priority so other work on the PC cannot starve the
        # reads (Plane.md F8). Not TimeCritical: the loop busy-polls while
        # data flows and must not starve the rest of the system.
        self.start(QThread.Priority.HighestPriority)


    def stop(self) -> None:
        """Signal the run loop to exit.  Thread-safe; may be called from any thread."""
        self._stop_event.set()

    def close(self) -> None:
        """Stop the thread and release the COM port.  Blocks up to 2 s."""
        self.stop()
        # Unblock any pending OS read/write calls by closing the serial handle.
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
        if not self.wait(2000):
            _LOG.warning("Worker thread did not exit within 2s; terminating thread.")
            self.terminate()
            self.wait(500)
        self._serial = None
        self.stop_raw_capture()
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass

    def set_session_sink(self, session) -> None:
        """Log every frame decoded from now on to ``session`` (a SessionLog),
        or stop logging with ``None``. Thread-safe."""
        self._session_sink = session

    def start_raw_capture(self, path, metadata: Optional[dict] = None) -> None:
        """Start recording every RX/TX byte to a ``.bhraw`` file."""
        self.stop_raw_capture()
        cap = RawCapture(path, metadata)
        with self._raw_lock:
            self._raw_capture = cap

    def rotate_raw_capture(self, path, metadata: Optional[dict] = None) -> Optional[str]:
        """Switch recording to a new file with no gap: every chunk lands
        in exactly one of the two files. Returns the old writer's error."""
        cap = RawCapture(path, metadata)
        with self._raw_lock:
            old, self._raw_capture = self._raw_capture, cap
        if old is None:
            return None
        old.close()
        return old.error

    def stop_raw_capture(self) -> Optional[str]:
        """Stop recording and drain the file to disk. Returns a writer error, if any."""
        with self._raw_lock:
            cap, self._raw_capture = self._raw_capture, None
        if cap is None:
            return None
        cap.close()
        return cap.error

    def _read_rx(self, size: int) -> tuple[bytes, float]:
        """Read from the port and stamp the read once, for both the raw
        capture and the decoded batch."""
        data = self._serial.read(size)
        t = time.perf_counter()
        if data and self._raw_capture is not None:
            with self._raw_lock:
                if self._raw_capture is not None:
                    self._raw_capture.write(RX, t, data)
        return data, t

    def enqueue_priority_tx(self, data: bytes) -> None:
        try:
            self._priority_tx_queue.put_nowait(data)
        except queue.Full:
            # Drop and surface. A full queue means the UI is generating TX
            # commands faster than the wire can carry them. Better to lose one
            # command than silently grow memory unbounded. ASCII-only so the
            # message renders cleanly on Windows' cp1252 console.
            self.warning_occurred.emit(
                "TX queue full - command dropped (UI is sending faster than the link can sustain)."
            )

    def set_polling_global(self, enabled: bool) -> None:
        with QMutexLocker(self._mutex):
            if enabled and not self._polling_global_enabled:
                self._flush_rx_before_polling = True
                # Polls not sent while polling was off were not "missed":
                # bring stale due times up to now (they fire immediately,
                # as before) so the off period is not counted as skipped.
                now = time.monotonic()
                for sched in self._schedules:
                    sched["next_run"] = max(sched["next_run"], now)
            self._polling_global_enabled = enabled
        if enabled:
            effective_gap = (
                self._pipeline_tx_gap_ms
                if self._pipeline_tx_gap_ms is not None
                else POLL_PIPELINE_TX_GAP_FLOOR_MS if self._pipelining_enabled else POLL_TX_GAP_FLOOR_MS
            )
            _LOG.info(
                "Polling started: pipelining=%s depth=%d tx_gap=%dms timeout_disable_threshold=%d",
                self._pipelining_enabled, self._pipeline_depth,
                effective_gap, CONSECUTIVE_TIMEOUT_DISABLE_THRESHOLD,
            )
            self._warn_if_schedule_exceeds_gap(self._effective_tx_gap_ms(effective_gap))

    def _warn_if_schedule_exceeds_gap(self, gap_ms: int) -> None:
        """Polls are spaced at least ``gap_ms`` apart, so a schedule asking
        for more polls per second than that allows is silently stretched.
        Say so once when polling starts."""
        if gap_ms <= 0:
            return
        demand = sum(1000.0 / s["spec"].interval_ms for s in self._schedules
                     if s["enabled"] and s["spec"].interval_ms > 0)
        capacity = 1000.0 / gap_ms
        if demand > capacity * 1.001:
            self.warning_occurred.emit(
                f"Poll schedule asks for {demand:.1f} polls/s but the {gap_ms} ms TX gap allows at "
                f"most {capacity:.1f}/s - every interval will run about {demand / capacity:.1f}x "
                "longer than configured. Lower the TX gap (Configure Poll Schedule) or lengthen intervals."
            )

    def set_pipelining(
        self,
        enabled: bool,
        depth: int = 2,
        gap_ms: Optional[int] = None,
    ) -> None:
        """Enable/disable pipelined polling.

        In pipelined mode the worker sends up to ``depth`` poll requests
        without waiting for each response, then matches replies by
        ``frame_id`` as they stream in. Cuts the total cycle time when the
        device's per-request turnaround is the bottleneck.

        ``gap_ms`` overrides the default per-TX spacing
        (``POLL_PIPELINE_TX_GAP_FLOOR_MS``). Pass ``None`` to use the
        default. Tune it up if the device drops frames at the default
        spacing, down for higher throughput on hardware that can take it.

        Modbus RTU is silently forced off — its responses don't carry a
        register-address tag we can use to demux out-of-order replies.
        """
        depth = max(1, min(int(depth), 16))
        if depth <= 1:
            enabled = False
        with QMutexLocker(self._mutex):
            self._pipelining_enabled = enabled
            self._pipeline_depth = depth
            if gap_ms is not None:
                self._pipeline_tx_gap_ms = max(0, int(gap_ms))
            if not enabled:
                # Worker will clear _in_flight during reset
                self._flush_rx_before_polling = True
        effective_gap = (
            self._pipeline_tx_gap_ms
            if self._pipeline_tx_gap_ms is not None
            else POLL_PIPELINE_TX_GAP_FLOOR_MS
        )
        _LOG.info(
            "Pipelining set: enabled=%s depth=%d tx_gap=%dms",
            enabled, depth, effective_gap,
        )

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
        self._emit_metrics_throttled(force=True)

    def toggle_schedule(self, target_id: int, enabled: bool) -> None:
        with QMutexLocker(self._mutex):
            for s in self._schedules:
                if s["spec"].target_id == target_id:
                    was_enabled = s["enabled"]
                    s["enabled"] = enabled
                    # Re-enabling a previously-failed schedule clears the
                    # "already reported" flag so a subsequent build error is
                    # surfaced again instead of staying silent.
                    if enabled:
                        s.pop("_failed_reported", None)
                        # Re-enabling after an auto-disable gives the schedule
                        # a fresh budget — otherwise it would re-disable on
                        # the very next timeout. The user explicitly asked to
                        # retry; honour that.
                        s["consecutive_timeouts"] = 0
                        # Reset the run timer so a re-enabled schedule waits
                        # one full interval before firing. The original code
                        # left next_run at the (long past) time.time() from
                        # __init__, which made re-enable fire immediately —
                        # surprising behaviour, especially right after a pause.
                        if not was_enabled:
                            s["next_run"] = time.monotonic() + (s["spec"].interval_ms / 1000.0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _advance_next_run(self, sched: dict, now: float) -> None:
        """Fixed-rate schedule (Plane.md F20): the next poll is due one
        interval after this one was *due*, not after it finished. Measuring
        from completion stretched every period by the wait for its turn, the
        TX gap and the round trip (0x1000 at 100 ms ran 10-25 % slow on the
        NUCLEO rig). A schedule that is already late for its next poll is
        realigned to ``now`` rather than firing a burst of catch-up polls; the
        polls skipped that way are counted (integrity ``polls_missed``)."""
        interval = sched["spec"].interval_ms / 1000.0
        nxt = sched["next_run"] + interval
        if nxt > now:
            sched["next_run"] = nxt
            return
        if interval > 0:
            missed = int((now - nxt) / interval)
            sched["missed"] = sched.get("missed", 0) + missed
            self._polls_missed += missed
        sched["next_run"] = now

    def _is_disconnect_error(self, exc: Exception) -> bool:
        """Return True if the exception looks like a physical USB unplug or network drop."""
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
            "not functioning",
            "connection reset",
            "connection aborted",
            "broken pipe",
        )
        return any(phrase in msg for phrase in disconnect_phrases)

    def _flush_batch(self) -> None:
        """Emit accumulated packets and reset the batch."""
        if self._batch:
            self.packets_received.emit(list(self._batch))
            self._batch.clear()
        self._last_emit_time = time.monotonic()

    def _should_flush(self) -> bool:
        with QMutexLocker(self._mutex):
            throttled = self._backpressure_throttled
        target_size = _BATCH_SIZE * 2 if throttled else _BATCH_SIZE
        target_interval = _BATCH_INTERVAL * 2 if throttled else _BATCH_INTERVAL
        return (
            len(self._batch) >= target_size
            or (time.monotonic() - self._last_emit_time) >= target_interval
        )

    def _accumulate(self, packets: Iterable[ParsedPacket], rx_perf: Optional[float] = None) -> None:
        """Add packets to the batch and flush when threshold is reached.

        When ``_decode_config`` is set, decode each good-CRC packet here on
        the worker thread so the GUI thread receives ``(packet, decoded)``
        tuples and skips its decode call. Bad-CRC packets carry ``None``
        for the decoded slot since the payload isn't trustworthy.

        Every valid packet whose ``frame_id`` matches a known schedule
        resets that schedule's consecutive-timeout counter — this
        rescues slow devices whose response time straddles ``timeout_ms``
        (e.g. a 500 ms timeout with a 510 ms-typical response). Without
        this reset, ~half the responses would arrive after their
        in-flight deadline expired and the schedule would auto-disable
        even though the device is actually answering.

        Each item carries ``rx_perf`` (``time.perf_counter()`` when the bytes
        were read; callers parse straight after reading). The GUI uses it for
        plot X values, log ``elapsed_ms`` and console timestamps, so they show
        when data arrived rather than when the 60 Hz UI flush got to it.
        RX bytes reach the console through these batches too; there is no
        per-packet ``wire_recorded`` emit for RX, which flooded the GUI event
        queue at high frame rates.
        """
        cfg = self._decode_config
        if rx_perf is None:
            rx_perf = time.perf_counter()
        first = len(self._batch)
        for p in packets:
            if not p.ok:
                self._crc_errors += 1
                self._consecutive_frame_errors += 1
                self._batch.append((p, None, rx_perf))
                if p.error:
                    self._emit_frame_error_throttled(p.error)
                continue
            self._consecutive_frame_errors = 0
            # Any valid response counts as a "the device is alive" signal —
            # reset the counter even if the in-flight entry already expired.
            self._record_poll_success(p.frame_id)
            if cfg is None:
                decoded = None
            else:
                try:
                    decoded = decode_frame(cfg, p.frame_id, p.payload, self._signal_state)
                except Exception:  # pragma: no cover - defensive: decode bugs
                    # Don't kill the worker on a decode error. Fall back to
                    # letting the GUI re-decode (which will surface the error
                    # via the existing path).
                    _LOG.exception("decode_frame raised on frame_id=0x%04X", p.frame_id)
                    decoded = None
            self._batch.append((p, decoded, rx_perf))
            if self._seq_tracker is not None and decoded is not None:
                self._check_sequence(p.frame_id, decoded, rx_perf)
        sink = self._session_sink
        if sink is not None:
            self._log_to_session(sink, self._batch[first:])
        if self._should_flush():
            self._flush_batch()

    def _check_sequence(self, frame_id: int, decoded, rx_perf: float) -> None:
        spec = self._seq_tracker.specs.get(frame_id)
        if spec is None:
            return
        value = next((sig.raw_value for sig in decoded.signals if sig.signal_name == spec.signal_name), None)
        if value is None:
            return
        event = self._seq_tracker.observe(frame_id, int(value))
        if event is None:
            return
        sink = self._session_sink
        if sink is not None:
            try:
                sink.log_sequence_event(event.frame_id, event.kind, event.expected, event.received,
                                        event.missing, rx_perf)
            except Exception:
                self._session_log_errors += 1
                _LOG.exception("Recording a sequence event failed")
        if event.kind == "gap":
            now = time.monotonic()
            if now - self._last_seq_warning >= 10.0:
                self._last_seq_warning = now
                total = self._seq_tracker.totals()["seq_missing"]
                self.warning_occurred.emit(
                    f"Frames lost before reaching the PC: frame 0x{frame_id:X} counter jumped "
                    f"{event.expected} -> {event.received} ({event.missing} missing, {total} so far)"
                )

    def _log_to_session(self, sink, items: List[tuple]) -> None:
        """Write this read's frames to the session, in arrival order. A
        failure is counted (integrity) and reported, never fatal to capture."""
        for p, decoded, t in items:
            try:
                if p.ok:
                    if p.frame_id is not None and decoded is not None:
                        sink.log_frame(decoded, t)
                    elif p.frame_id is not None:
                        self._session_log_errors += 1
                else:
                    sink.log_rejected(p.raw, p.frame_id, p.error or "", t)
            except Exception as exc:
                self._session_log_errors += 1
                now = time.monotonic()
                if now - self._last_sink_warning >= 5.0:
                    self._last_sink_warning = now
                    _LOG.exception("Logging a frame to the session failed")
                    self.warning_occurred.emit(f"Session logging error ({self._session_log_errors} so far): {exc!r}")

    def _check_watchdog(self) -> None:
        """Emit device_timeout if no data received within WATCHDOG_TIMEOUT."""
        silence = time.monotonic() - self._last_rx_time
        if silence > WATCHDOG_TIMEOUT:
            if not self._watchdog_fired:
                self.device_timeout.emit()
                self._watchdog_fired = True
        else:
            self._watchdog_fired = False  # reset once data flows again

    def integrity_snapshot(self) -> dict:
        """Cumulative byte/frame accounting for this connection.

        ``parser_bytes_in`` equals ``frame_bytes_ok + frame_bytes_rejected +
        discarded_bytes + overflow_bytes + buffered_bytes`` for unescaped
        protocols; escape-layer losses are in ``unframer_dropped_*``.
        """
        st = self._parser.stats
        return {
            "parser_bytes_in": st.bytes_in,
            "frames_ok": st.frames_ok,
            "frame_bytes_ok": st.frame_bytes_ok,
            "frames_rejected": st.frames_rejected,
            "frame_bytes_rejected": st.frame_bytes_rejected,
            "discarded_bytes": st.discarded_bytes,
            "overflow_bytes": st.overflow_bytes,
            "unframer_dropped_frames": st.unframer_dropped_frames,
            "unframer_dropped_bytes": st.unframer_dropped_bytes,
            "buffered_bytes": self._parser.buffered_bytes,
            "poll_timeouts": self._timeouts,
            "purged_at_connect": self._open_purged_bytes,
            "rx_service_gap_max_ms": round(self._rx_service_gap_max * 1000.0, 1),
            "parse_errors": self._parse_errors,
            "polls_missed": self._polls_missed,
            **(self._seq_tracker.totals() if self._seq_tracker is not None else {}),
            "session_log_errors": self._session_log_errors,
            # None = this transport cannot report driver errors (TCP/UDP, POSIX).
            "driver_errors": dict(errs) if (errs := getattr(self._serial, "comm_errors", None)) else None,
        }

    def _emit_metrics_throttled(self, *, force: bool = False) -> None:
        """Emit metrics_updated at most once per ``_METRICS_INTERVAL``.

        Called from hot paths (every loop iteration that has RX) so the
        signal queue doesn't fill with redundant updates at high baud rates.

        ``force=True`` bypasses the throttle but still updates the cooldown
        so the next throttled call sees a fresh timestamp. Used by callers
        like ``reset_metrics`` that need the UI updated immediately.
        """
        now = time.monotonic()
        if force or (now - self._last_metrics_emit) >= self._METRICS_INTERVAL:
            self.metrics_updated.emit(self._timeouts, self._crc_errors, self._rx_bytes)
            self.integrity_updated.emit(self.integrity_snapshot())
            self._last_metrics_emit = now

    def _emit_frame_error_throttled(self, msg: str) -> None:
        """Emit a frame error warning, throttling to avoid UI spam on streaming links.

        Isolated single-packet wire glitches (<0.1% rate on USB-UART adapters like CH340
        at 2,000,000 baud) are counted in self._crc_errors and displayed in the status bar.
        Warnings in the Activity Log are reserved for sustained failures (>= 5 consecutive
        errors without any valid frames, indicating wrong baud rate or cable fault),
        throttled to at most once per 10 seconds.
        """
        now = time.monotonic()
        _LOG.debug("Frame Error: %s (consecutive=%d)", msg, self._consecutive_frame_errors)

        if self._consecutive_frame_errors >= 5:
            base_msg = msg.split(':')[0]
            if (now - self._last_frame_error_emit) >= 10.0:
                self.warning_occurred.emit(f"Frame Error: {msg} (persistent frame errors; check baud rate or wiring)")
                self._last_frame_error_emit = now
                self._last_frame_error_msg = base_msg

    def _effective_tx_gap_ms(self, min_gap_ms: int = 0) -> int:
        return max(
            0,
            int(getattr(self.protocol, "inter_frame_delay_ms", 0)),
            int(min_gap_ms),
        )

    def _respect_inter_frame_delay(self, min_gap_ms: int = 0) -> None:
        """Honor protocol.inter_frame_delay_ms before consecutive TX frames.

        Gap is measured from the previous TX (not from RX). Codex's
        polling investigation showed this is the cadence the BMS
        firmware expects — keeping it stable here.
        """
        delay_ms = self._effective_tx_gap_ms(min_gap_ms)
        if delay_ms <= 0 or self._last_tx_time <= 0.0:
            return
        # Keep reading while waiting: a 100 ms sleep here was 20 kB of
        # unread data at 2 Mbaud for every command sent (Plane.md F17).
        until = self._last_tx_time + delay_ms / 1000.0
        while (remaining := until - time.monotonic()) > 0:
            self._drain_pending_rx()
            time.sleep(min(remaining, 0.002))

    def _write_serial(self, data: bytes, *, min_gap_ms: int = 0) -> int:
        """Write to the serial port, applying the configured TX gap."""
        if self._serial is None:
            return 0
        self._respect_inter_frame_delay(min_gap_ms)
        written = self._serial.write(data)
        self._last_tx_time = time.monotonic()
        if self._raw_capture is not None:
            with self._raw_lock:
                if self._raw_capture is not None:
                    self._raw_capture.write(TX, time.perf_counter(), data)
        self.wire_recorded.emit("TX", data, datetime.now())
        return written

    def _drain_pending_rx(self) -> List[ParsedPacket]:
        """Parse and emit bytes already waiting before the next TX.

        Some request/response devices can leave late frames in the driver
        buffer. Draining them before the next poll keeps latency accounting
        tied to the request that is about to be sent, while still delivering
        the stale-but-valid data to the UI.
        """
        return self._service_rx()

    def _service_rx(self) -> List[ParsedPacket]:
        """Read whatever is waiting, parse it, match it to polls in flight
        and queue it for emission. Every read in the worker goes through
        here."""
        if self._serial is None:
            return []
        w = self._serial.in_waiting
        now = time.monotonic()
        if w <= 0:
            self._last_rx_service = now
            return []
        if self._last_rx_service:
            self._rx_service_gap_max = max(self._rx_service_gap_max, now - self._last_rx_service)
        self._last_rx_service = now
        data, rx_perf = self._read_rx(w)
        self._rx_bytes += len(data)
        self._last_rx_time = now
        self._watchdog_fired = False
        try:
            self._parser.feed(data)
            extracted = self._parser.extract_all()
        except Exception:
            # The run loop recovers, but bytes in flight may be lost: count
            # it so the session's integrity record shows it (it was silent).
            self._parse_errors += 1
            raise
        if extracted:
            if self._pipelining_enabled and self._in_flight:
                self._match_in_flight_responses(extracted)
            if self._await_target is not None and not self._await_hit:
                self._await_hit = any(self._is_response_match(p, self._await_target) for p in extracted)
            self._accumulate(extracted, rx_perf)
            self._emit_metrics_throttled()
        return extracted

    def _reset_rx_state_for_polling_start(self) -> None:
        """Prepare for Auto-Fetch without discarding any received data.

        Bytes already waiting are real device data: they are decoded and
        delivered *before* the first poll is sent, so they can never be
        mistaken for that poll's response. The parser keeps a partial frame
        (it completes with the next bytes) and undelivered batch items stay
        queued. Only in-flight poll bookkeeping is reset. (This used to call
        ``reset_input_buffer()`` and clear the parser and batch, which threw
        away frames — Plane.md Part F, F1.)
        """
        self._in_flight.clear()
        if self._serial is not None:
            self._drain_pending_rx()
        self._last_rx_time = time.monotonic()
        self._watchdog_fired = False

    # ------------------------------------------------------------------
    # Thread run loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        self._last_emit_time = time.monotonic()
        try:
            self._run_loop()
        finally:
            # Flush anything still in the batch before the thread dies.
            self._flush_batch()
            if self._serial is not None:
                try:
                    self._serial.close()
                except Exception:
                    pass
                self._serial = None
            if sys.platform == "win32":
                try:
                    import ctypes
                    ctypes.windll.winmm.timeEndPeriod(1)
                except Exception:
                    pass

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                # 1. Handle Priority TX (parameter editing / manual commands)
                if not self._priority_tx_queue.empty():
                    tx_data = self._priority_tx_queue.get()
                    if self._serial:
                        # Honour gap in priority TX to prevent dropping polls!
                        gap_ms = (self._pipeline_tx_gap_ms if self._pipeline_tx_gap_ms is not None else POLL_TX_GAP_FLOOR_MS)
                        self._write_serial(tx_data, min_gap_ms=gap_ms)
                        self.tx_recorded.emit(tx_data)
                    # Removed `continue` so RX can drain immediately after priority TX!

                # 2. Read settings under the lock
                with QMutexLocker(self._mutex):
                    polling_enabled = self._polling_global_enabled
                    pipelining = self._pipelining_enabled
                    pipe_depth = self._pipeline_depth
                    flush_rx_before_polling = self._flush_rx_before_polling
                    if flush_rx_before_polling:
                        self._flush_rx_before_polling = False

                if flush_rx_before_polling:
                    self._reset_rx_state_for_polling_start()

                # 3. Drain incoming data.
                # In pipelined mode we ALWAYS drain RX here so that responses to in-flight requests
                # are matched promptly before we check for expirations or send new requests.
                # In serial mode, we also drain any unsolicited/late traffic.
                rx_before = self._rx_bytes
                if self._serial:
                    try:
                        self._service_rx()
                    except (TypeError, AttributeError):
                        if self._stop_event.is_set():
                            break
                        raise

                # 4. Handle Polling Engine
                polled = False
                # Polling gate: hold off until the device has either sent us
                # at least one byte (proof it is alive) OR the boot-grace
                # window has elapsed (so devices that are request/response
                # only still get polled). Hammering polls during an Arduino
                # bootloader window leaves the link stuck — the device cannot
                # answer, timeouts accumulate, and we never get out.
                # Polling never pauses for GUI backpressure: a paused poll is
                # a gap in the log (Plane.md F2). The GUI copes by coalescing
                # what it displays; logging does not depend on GUI speed.
                grace_expired = (time.monotonic() - self._open_time) > POLLING_BOOT_GRACE
                if polling_enabled and (self._rx_bytes > 0 or grace_expired):
                    if pipelining:
                        # Pipelined: fire as many due polls as the depth budget
                        # allows; responses are matched by frame_id in the RX
                        # drain above.
                        self._expire_in_flight()
                        while len(self._in_flight) < pipe_depth:
                            sched = self._pick_due_schedule_for_pipeline()
                            if sched is None:
                                break
                            if self._send_polling_tx_nowait(sched):
                                self._advance_next_run(sched, time.monotonic())
                                polled = True
                            else:
                                break
                    else:
                        now = time.monotonic()
                        n = len(self._schedules)
                        # Snapshot the due schedule under the lock, then release
                        # before _do_poll which blocks for up to timeout_ms.
                        chosen_sched = None
                        with QMutexLocker(self._mutex):
                            for offset in range(n):
                                idx = (self._sched_cursor + offset) % n
                                sched = self._schedules[idx]
                                if sched["enabled"] and now >= sched["next_run"]:
                                    chosen_sched = sched
                                    self._sched_cursor = (idx + 1) % n
                                    break
                        if chosen_sched is not None:
                            self._do_poll(chosen_sched)
                            self._advance_next_run(chosen_sched, time.monotonic())
                            polled = True

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

                # Adaptive idle sleep.
                # When data was just read, yield/sleep minimally (0.1ms) to drain
                # OS buffers immediately and prevent overflows at 2,000,000 baud.
                # When idle, sleep 2ms (with 1ms Windows timer resolution enabled).
                had_rx = self._rx_bytes > rx_before
                if had_rx:
                    sleep_s = 0.0001
                else:
                    sleep_s = 0.002
                    if not polled and self._schedules:
                        can_doze = not (pipelining and self._in_flight)
                        if can_doze:
                            with QMutexLocker(self._mutex):
                                next_due_iter = (
                                    s["next_run"] for s in self._schedules if s["enabled"]
                                )
                                next_due = min(next_due_iter, default=None)
                            if next_due is not None:
                                until_due = next_due - time.monotonic()
                                if until_due > 0.02:
                                    sleep_s = 0.02
                time.sleep(sleep_s)

            except (serial.SerialException, OSError) as exc:
                if self._is_disconnect_error(exc) or isinstance(exc, OSError):
                    # Physical unplug — clean up and notify the UI.
                    try:
                        if self._serial is not None:
                            self._serial.close()
                            self._serial = None
                    except Exception:
                        _LOG.warning(
                            "Serial close during disconnect handling failed",
                            exc_info=True,
                        )
                    self._flush_batch()
                    self.connection_lost.emit()
                    return  # exit the run loop gracefully
                else:
                    # Other serial error — report once and keep running. The
                    # original code killed the thread on any non-disconnect
                    # SerialException, which meant a single transient I/O
                    # blip stopped polling forever until the user manually
                    # reconnected. Stay alive; let the watchdog or the user
                    # diagnose if it persists.
                    self.warning_occurred.emit(f"Transient serial error: {exc}")
                    time.sleep(0.05)
                    continue

            except Exception as exc:
                if self._stop_event.is_set():
                    break
                # Non-serial exception (parse error, ValueError in build_packet,
                # etc.). Report it, log a short cool-down, and keep running.
                _LOG.exception("Worker recovered from unexpected error")
                self.warning_occurred.emit(f"Worker recovered from: {exc!r}")
                time.sleep(0.05)
                continue

    # ------------------------------------------------------------------
    # Polling helpers (unchanged logic, adapted to use _accumulate)
    # ------------------------------------------------------------------

    def _do_poll(self, sched: dict) -> None:
        target_id = sched["spec"].target_id
        timeout_ms = sched["spec"].timeout_ms
        # Honour the user-configured tx-gap setting if they've set one
        # via the Configure Poll Schedule dialog; otherwise fall back to
        # the serial-mode floor. Lets the dialog spinbox tune both modes
        # without a rebuild, which matters for diagnosing devices whose
        # response rate is sensitive to TX cadence.
        gap_ms = (
            self._pipeline_tx_gap_ms
            if self._pipeline_tx_gap_ms is not None
            else POLL_TX_GAP_FLOOR_MS
        )

        from ..protocol.packet_builder import build_packet
        try:
            req = build_packet(self.protocol, target_id, b"")
            self._drain_pending_rx()
            self._write_serial(req, min_gap_ms=gap_ms)
            self.tx_recorded.emit(req)
            self._await_response(timeout_ms, target_id)
        except ValueError as exc:
            # Most common cause: target_id does not fit in the configured
            # frame_id_size, or the protocol config is otherwise malformed.
            # Without this guard, polling kept retrying every interval and
            # silently failed forever.
            self._disable_failed_schedule(sched, exc)

    # ------------------------------------------------------------------
    # Pipelined polling helpers
    # ------------------------------------------------------------------

    def _expire_in_flight(self) -> None:
        """Drop in-flight requests whose deadline has passed and count them
        as timeouts. Called once per loop iteration in pipelined mode.

        Logs parser buffer state at DEBUG level on each expiration so a
        bytehound.log review can show whether the response arrived as a
        bad-CRC fragment or never reached the parser at all.
        """
        if not self._in_flight:
            return
        now = time.monotonic()
        kept: List[dict] = []
        for item in self._in_flight:
            if now >= item["deadline"]:
                self._timeouts += 1
                self._record_poll_timeout(item["target_id"])
                _LOG.debug(
                    "Poll timeout 0x%04X: in_flight=%d parser_buf=%d serial_waiting=%d",
                    item["target_id"],
                    len(self._in_flight) - 1,
                    getattr(self._parser, "buffered_bytes", -1),
                    self._serial.in_waiting if self._serial else -1,
                )
            else:
                kept.append(item)
        self._in_flight = kept

    def _pick_due_schedule_for_pipeline(self) -> Optional[dict]:
        """Round-robin pick of the next due schedule whose target_id is not
        already in flight (prevents queuing two requests for the same id and
        making latency matching ambiguous)."""
        if not self._schedules:
            return None
        now = time.monotonic()
        in_flight_ids = {it["target_id"] for it in self._in_flight}
        n = len(self._schedules)
        for offset in range(n):
            idx = (self._sched_cursor + offset) % n
            sched = self._schedules[idx]
            if (
                sched["enabled"]
                and now >= sched["next_run"]
                and sched["spec"].target_id not in in_flight_ids
            ):
                self._sched_cursor = (idx + 1) % n
                return sched
        return None

    def _send_polling_tx_nowait(self, sched: dict) -> bool:
        """Build and write a poll request without awaiting the response.
        Records the request in _in_flight. Returns False on either:
        (a) build failed (schedule gets auto-disabled), or
        (b) gap-floor hasn't elapsed yet (caller should drain RX and
            retry on the next loop iteration).

        Critically, this method does NOT sleep to honour the gap. The
        gap is enforced by REFUSING to TX, not by blocking. That keeps
        the outer run loop free to drain RX continuously during the
        wait — important on Windows USB CDC where in_waiting may not
        report bytes until something actively reads. Previously a 30 ms
        gap could swallow an in-flight response because the worker was
        asleep when the response landed.

        Honours ``POLL_PIPELINE_TX_GAP_FLOOR_MS`` between TXs — the probe
        showed 10 ms back-to-back spacing can drop the BMS reply even
        though 25 ms is reliable. Without this floor the pipelined path
        was firing at the protocol's bare ``inter_frame_delay_ms`` (10 ms
        in the user's config), which produced the intermittent 0x9001
        timeouts in production logs.
        """
        from ..protocol.packet_builder import build_packet
        target_id = sched["spec"].target_id
        timeout_ms = sched["spec"].timeout_ms
        try:
            req = build_packet(self.protocol, target_id, b"")
        except ValueError as exc:
            self._disable_failed_schedule(sched, exc)
            return False
        if self._serial is None:
            return False
        self._drain_pending_rx()
        gap_ms = (
            self._pipeline_tx_gap_ms
            if self._pipeline_tx_gap_ms is not None
            else POLL_PIPELINE_TX_GAP_FLOOR_MS
        )

        # Check gap manually instead of sleeping
        delay_ms = self._effective_tx_gap_ms(gap_ms)
        if delay_ms > 0 and self._last_tx_time > 0:
            if (time.monotonic() - self._last_tx_time) < (delay_ms / 1000.0):
                return False

        self._write_serial(req, min_gap_ms=0)
        self.tx_recorded.emit(req)
        tx_time = time.monotonic()
        self._in_flight.append({
            "target_id": target_id,
            "tx_time": tx_time,
            "deadline": tx_time + (timeout_ms / 1000.0),
        })
        return True

    def _match_in_flight_responses(self, packets: Iterable[ParsedPacket]) -> None:
        """For each valid packet, clear the oldest matching in-flight entry
        and emit poll_latency. Unmatched packets stay in the batch as
        normal traffic."""
        if not self._in_flight:
            return
        now = time.monotonic()
        for p in packets:
            if not p.ok:
                continue
            for i, item in enumerate(self._in_flight):
                if item["target_id"] == p.frame_id:
                    latency_ms = (now - item["tx_time"]) * 1000.0
                    try:
                        self.poll_latency.emit(p.frame_id, latency_ms)
                    except Exception:
                        _LOG.debug("poll_latency emit failed", exc_info=True)
                    self._record_poll_success(p.frame_id)
                    del self._in_flight[i]
                    break

    def _find_schedule_by_target(self, target_id: int) -> Optional[dict]:
        """Locate a schedule by target_id, or None. O(n) — n is small."""
        for s in self._schedules:
            if s["spec"].target_id == target_id:
                return s
        return None

    def _record_poll_timeout(self, target_id: Optional[int]) -> None:
        """Bump the per-schedule consecutive-timeout counter and auto-disable
        once the threshold is crossed, BUT only for targets the device
        has never responded to.

        Why the ever_responded guard: a slow device may take several
        seconds to send its first response for a given target_id (e.g.
        an MCU that queues poll responses behind other work). With
        pipeline_depth=2 and a 500 ms timeout, several timeouts can
        accumulate before the first late response arrives — auto-disable
        would falsely kill a working schedule. Once we've ever heard
        from this target, treat it as "device-paced" and let the
        late-response reset in ``_accumulate`` keep the counter sane.
        """
        if target_id is None:
            return
        sched = self._find_schedule_by_target(target_id)
        if sched is None or not sched.get("enabled"):
            return
        sched["consecutive_timeouts"] = sched.get("consecutive_timeouts", 0) + 1
        if sched.get("ever_responded", False):
            return  # device just slow on this target — don't disable.
        if sched["consecutive_timeouts"] >= CONSECUTIVE_TIMEOUT_DISABLE_THRESHOLD:
            with QMutexLocker(self._mutex):
                sched["enabled"] = False
                sched["consecutive_timeouts"] = 0  # reset for next enable
            self.error_occurred.emit(
                f"Polling for 0x{target_id:X} auto-disabled after "
                f"{CONSECUTIVE_TIMEOUT_DISABLE_THRESHOLD} consecutive timeouts "
                f"with no response ever received. "
                f"Re-enable from Configure Poll Schedule once the device is "
                f"answering this target."
            )

    def _record_poll_success(self, target_id: int) -> None:
        """Reset the consecutive-timeout counter and mark the target as having
        ever responded — the ever_responded flag is the auto-disable guard
        that protects slow-but-working targets from being killed."""
        sched = self._find_schedule_by_target(target_id)
        if sched is not None:
            sched["consecutive_timeouts"] = 0
            sched["ever_responded"] = True

    def _disable_failed_schedule(self, sched: dict, exc: BaseException) -> None:
        """Disable a schedule that cannot build its request, reporting once.

        Mutex-protected so a concurrent ``toggle_schedule`` from the UI
        can't race on the ``enabled`` write.
        """
        target_id = sched["spec"].target_id
        with QMutexLocker(self._mutex):
            if not sched.get("_failed_reported"):
                # Emit outside the lock would be safer (avoid blocking
                # signal-receiver thread if it tries to re-enter), but in
                # practice error_occurred is queued cross-thread, so it
                # returns immediately. Holding the lock here is fine.
                self.error_occurred.emit(
                    f"Polling for 0x{target_id:X} disabled — could not build "
                    f"request: {exc}"
                )
                sched["_failed_reported"] = True
            sched["enabled"] = False

    def _await_modbus_response(self, req: bytes, target_id: Optional[int], timeout_ms: int = 100) -> None:
        self._await_response(timeout_ms, target_id)

    @staticmethod
    def _is_response_match(p: ParsedPacket, target_id: Optional[int]) -> bool:
        """Predicate: is ``p`` the response to a poll for ``target_id``?

        - ``target_id is None`` → any *valid* packet wins. Used by the
          priority-TX path where the caller hand-built the request and we
          don't know which slave (if any) was addressed.
        - ``target_id is set``  → require ``frame_id == target_id`` (modbus
          frames are patched to satisfy this before we get here).
        - Bad-CRC frames never satisfy a response wait.
        """
        if not p.ok:
            return False
        if target_id is None:
            return True
        return p.frame_id == target_id

    def _await_response(self, timeout_ms: int, target_id: Optional[int]) -> None:
        """Wait up to ``timeout_ms`` for the response to a poll TX.

        Improvements over the original:
        * **Strict response matching.** Only a frame whose ``frame_id``
          matches ``target_id`` ends the wait. Streaming/unrelated frames
          that arrive in the window are still emitted (they're real data)
          but don't short-circuit the wait — that was a long-standing
          mis-attribution bug.
        * Packets go through ``_accumulate`` (batching pipeline) instead of
          one ``packets_received.emit`` per frame, so high-rate polls don't
          flood the UI signal queue.
        * The priority TX queue is **pumped during the wait** so a user-
          typed parameter write isn't blocked for up to ``timeout_ms``.
        * ``metrics_updated`` is throttled to a single emission at the end
          of the await — the polling loop itself is low-frequency so this
          is plenty.
        * Poll latency is reported on a dedicated signal so the UI can
          surface it (e.g. "avg poll latency 12 ms").
        """
        tx_time = time.monotonic()
        effective_timeout_ms = max(0, int(timeout_ms)) + POLL_RESPONSE_GRACE_MS
        end_time = tx_time + (effective_timeout_ms / 1000.0)
        self._await_target, self._await_hit = target_id, False
        try:
            packet_found = self._await_loop(end_time)
        finally:
            self._await_target = None

        if not packet_found:
            self._timeouts += 1
            self._record_poll_timeout(target_id)
            _LOG.debug(
                "Poll timeout 0x%04X (serial): parser_buf=%d serial_waiting=%d",
                target_id if target_id is not None else -1,
                getattr(self._parser, "buffered_bytes", -1),
                self._serial.in_waiting if self._serial else -1,
            )
        else:
            if target_id is not None:
                self._record_poll_success(target_id)
            # Latency = round-trip time from TX to the matching response.
            latency_ms = (time.monotonic() - tx_time) * 1000.0
            try:
                self.poll_latency.emit(target_id if target_id is not None else -1, latency_ms)
            except Exception:
                # Signal-emit failure here is non-fatal (UI lost one latency
                # sample), but log it so we'd notice if it became chronic.
                _LOG.debug("poll_latency emit failed", exc_info=True)
        # Route through the throttle so this tail emit doesn't bypass the
        # rate-limit that the rest of the worker honours. Forcing on timeout
        # would defeat the throttle on protocols where every poll times out
        # transiently. At ~poll-interval cadence the throttle is naturally
        # satisfied on the happy path.
        self._emit_metrics_throttled()

    def _await_loop(self, end_time: float) -> bool:
        while time.monotonic() < end_time and not self._stop_event.is_set():
            # Pump priority TX during the wait window. We only send ONE
            # priority frame per iteration so we don't starve the response
            # we're nominally waiting for. The UI rate is human-driven, so
            # a single per-5ms-tick is plenty.
            if not self._priority_tx_queue.empty() and self._serial:
                try:
                    tx_data = self._priority_tx_queue.get_nowait()
                    self._write_serial(tx_data)
                    self.tx_recorded.emit(tx_data)
                except queue.Empty:
                    pass

            # Every frame (matching or not) is emitted through batching —
            # unrelated continuous-stream packets are still real data. Only
            # a *matching* packet ends the wait (_service_rx sets
            # _await_hit), so a streaming frame cannot mask a missing poll
            # response.
            self._service_rx()
            if self._await_hit:
                return True
            time.sleep(0.005)
        return self._await_hit


def available_ports() -> Iterable[tuple[str, str]]:
    """Return a list of ``(device, description)`` tuples for every serial port.

    Retrieves manufacturer name, USB VID, PID, and formats the description.
    Highlight/sorts ports matching common chipsets (FTDI, STMicroelectronics,
    NXP, WCH, Silicon Labs, Prolific) to the top of the list.
    """
    ports_with_meta = []
    for port in list_ports.comports():
        dev = port.device
        desc = port.description or dev
        mfg = port.manufacturer or ""
        vid = port.vid
        pid = port.pid

        details = []
        if mfg:
            details.append(f"Mfg: {mfg}")
        if vid is not None and pid is not None:
            details.append(f"VID:PID={vid:04X}:{pid:04X}")

        detail_str = f" ({', '.join(details)})" if details else ""
        formatted_desc = f"{desc}{detail_str}"

        is_common = False
        if mfg:
            mfg_l = mfg.lower()
            if any(k in mfg_l for k in ("ftdi", "stmicro", "nxp", "wch", "silicon", "prolific")):
                is_common = True
        if vid is not None:
            # Common USB VIDs:
            # 0x0403: FTDI
            # 0x0483: STMicroelectronics
            # 0x1FC9: NXP
            # 0x1A86: WCH (CH340/CH341)
            # 0x10C4: Silicon Labs (CP210x)
            # 0x067B: Prolific
            if vid in (0x0403, 0x0483, 0x1FC9, 0x1A86, 0x10C4, 0x067B):
                is_common = True

        priority = 0 if is_common else 1
        ports_with_meta.append((priority, dev, formatted_desc))

    ports_with_meta.sort(key=lambda x: (x[0], x[1]))
    return [(p[1], p[2]) for p in ports_with_meta]
