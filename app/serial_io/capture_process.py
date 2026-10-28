"""Run the capture worker in its own process.

Why
---
``PollingWorker`` reads, parses and decodes on a ``QThread``. That keeps the
GUI's event loop free, but not the GIL: at high frame rates the worker's
Python code and the GUI's 60 Hz redraw take turns, and the UI stutters.
Running the same worker in a child process gives it its own interpreter.
The GUI process only receives finished batches.

Shape
-----
* :class:`CaptureClient` is a drop-in for ``PollingWorker`` on the GUI side:
  same signals, same methods, same ``settings`` / ``is_open``.
* The child (:func:`_host_main`) builds a real ``PollingWorker`` and forwards
  every signal back over a pipe. Commands go the other way.
* Children are spawned ahead of time (:func:`prewarm`) and reused across
  connections, so Connect does not pay for process start-up.
* If the child dies, the client emits ``connection_lost`` exactly as a USB
  unplug would, so the existing reconnect logic applies unchanged.
* If the parent dies, the child sees EOF on the pipe, closes the port and
  exits.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
import queue
import threading
from typing import Any, List, Optional

import serial
from PySide6.QtCore import QObject, Signal

from ..decoder.types import FrameConfig, PollingScheduleSpec, ProtocolConfig

_LOG = logging.getLogger("bytehound.serial_io.capture_process")

# Signals forwarded from the child's PollingWorker, in PollingWorker order.
_SIGNALS = (
    "packets_received", "metrics_updated", "error_occurred", "warning_occurred",
    "tx_recorded", "wire_recorded", "connection_lost", "device_timeout",
    "backpressure_changed", "poll_latency", "integrity_updated",
)

_OPEN_TIMEOUT_S = 20.0     # covers a cold spawn (interpreter + imports) on a slow PC
_CALL_TIMEOUT_S = 15.0     # stop_raw_capture drains the file; allow slow disks
_CLOSE_TIMEOUT_S = 5.0     # PollingWorker.close itself waits up to 2.5 s


class CaptureProcessError(RuntimeError):
    """The capture process could not be started or stopped responding."""


# ---------------------------------------------------------------------------
# Child side
# ---------------------------------------------------------------------------

def _host_main(conn) -> None:
    """Child entry point: serve open/call/close requests until told to stop."""
    from PySide6.QtCore import Qt
    from .serial_worker import PollingWorker

    send_lock = threading.Lock()

    def send(msg) -> None:
        # Worker-thread signal forwards and main-thread replies share the pipe.
        with send_lock:
            try:
                conn.send(msg)
            except (OSError, EOFError, ValueError):
                pass

    def forwarder(name: str):
        return lambda *args: send(("sig", name, args))

    class _PipeLogHandler(logging.Handler):
        # The parent owns bytehound.log; two processes rotating one file
        # would clash, so records are relayed instead.
        def emit(self, record: logging.LogRecord) -> None:
            try:
                send(("log", record.levelno, record.name, record.getMessage(), self.format(record)
                      if record.exc_info else None))
            except Exception:
                pass

    root = logging.getLogger()
    root.handlers[:] = [_PipeLogHandler()]
    root.setLevel(logging.INFO)

    worker: Optional[PollingWorker] = None
    send(("ready", os.getpid()))
    try:
        while True:
            try:
                msg = conn.recv()
            except (EOFError, OSError):
                break  # parent is gone
            op, req_id = msg[0], msg[1]
            if op == "open":
                settings, protocol, schedules, decode_config = msg[2:]
                try:
                    worker = PollingWorker(settings, protocol, schedules, decode_config=decode_config)
                    for name in _SIGNALS:
                        getattr(worker, name).connect(forwarder(name), Qt.ConnectionType.DirectConnection)
                    worker.open()
                    send(("reply", req_id, True, None))
                except Exception as exc:
                    worker = None
                    send(("reply", req_id, False, f"{type(exc).__name__}: {exc}"))
            elif op == "call":
                name, args = msg[2], msg[3]
                try:
                    result = getattr(worker, name)(*args) if worker is not None else None
                    ok = True
                except Exception as exc:
                    result, ok = f"{type(exc).__name__}: {exc}", False
                if req_id is not None:
                    send(("reply", req_id, ok, result))
            elif op == "close":
                if worker is not None:
                    try:
                        worker.close()
                    except Exception:
                        _LOG.exception("capture worker close failed")
                    worker = None
                send(("closed", req_id))
            elif op == "shutdown":
                break
    finally:
        if worker is not None:
            try:
                worker.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Warm process pool (parent side)
# ---------------------------------------------------------------------------

class _Child:
    def __init__(self) -> None:
        ctx = mp.get_context("spawn")
        self.conn, child_conn = ctx.Pipe(duplex=True)
        self.proc = ctx.Process(target=_host_main, args=(child_conn,), name="BytehoundCapture", daemon=True)
        self.proc.start()
        child_conn.close()
        self.pid: Optional[int] = self.proc.pid

    def alive(self) -> bool:
        return self.proc.is_alive()

    def kill(self) -> None:
        try:
            self.conn.send(("shutdown", None))
        except (OSError, EOFError, ValueError):
            pass
        self.proc.join(1.0)
        if self.proc.is_alive():
            self.proc.kill()
            self.proc.join(1.0)
        try:
            self.conn.close()
        except OSError:
            pass


_pool_lock = threading.Lock()
_idle: List[_Child] = []


def prewarm() -> None:
    """Start one idle capture process in the background, if none is waiting."""
    with _pool_lock:
        _idle[:] = [c for c in _idle if c.alive()]
        if _idle:
            return
        try:
            _idle.append(_Child())
        except Exception:
            _LOG.warning("Could not prewarm capture process", exc_info=True)


def _take() -> _Child:
    with _pool_lock:
        while _idle:
            child = _idle.pop()
            if child.alive():
                return child
            child.kill()
    return _Child()


def _give_back(child: _Child) -> None:
    with _pool_lock:
        if child.alive() and not _idle:
            _idle.append(child)
            return
    child.kill()


def shutdown_pool() -> None:
    """Stop idle capture processes (call on app exit)."""
    with _pool_lock:
        children, _idle[:] = list(_idle), []
    for c in children:
        c.kill()


# ---------------------------------------------------------------------------
# GUI-side proxy
# ---------------------------------------------------------------------------

class CaptureClient(QObject):
    """``PollingWorker`` stand-in whose work happens in a child process."""

    packets_received = Signal(list)
    metrics_updated = Signal(int, int, int)
    error_occurred = Signal(str)
    warning_occurred = Signal(str)
    tx_recorded = Signal(bytes)
    wire_recorded = Signal(str, bytes, object)
    connection_lost = Signal()
    device_timeout = Signal()
    backpressure_changed = Signal(bool)
    poll_latency = Signal(int, float)
    integrity_updated = Signal(object)

    def __init__(
        self,
        settings,
        protocol: ProtocolConfig,
        schedules: List[PollingScheduleSpec],
        decode_config: Optional[FrameConfig] = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.protocol = protocol
        self._schedules = list(schedules)
        self._decode_config = decode_config
        self._child: Optional[_Child] = None
        self._reader: Optional[threading.Thread] = None
        self._replies: "queue.Queue[tuple]" = queue.Queue()
        self._req = 0
        self._send_lock = threading.Lock()
        self._open = False
        self._closing = False

    # -- state -------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def child_pid(self) -> Optional[int]:
        return self._child.pid if self._child is not None else None

    # -- plumbing ------------------------------------------------------------

    def _next_id(self) -> int:
        self._req += 1
        return self._req

    def _send(self, msg) -> None:
        if self._child is None:
            raise CaptureProcessError("capture process is not running")
        with self._send_lock:
            try:
                self._child.conn.send(msg)
            except (OSError, EOFError, ValueError) as exc:
                raise CaptureProcessError(f"capture process unreachable: {exc}") from exc

    def _await(self, req_id: int, timeout: float) -> tuple:
        while True:
            try:
                reply = self._replies.get(timeout=timeout)
            except queue.Empty:
                raise CaptureProcessError("capture process did not respond") from None
            if reply[0] == "dead":
                raise CaptureProcessError("capture process exited")
            if reply[1] == req_id:
                return reply

    def _read_loop(self, child: _Child) -> None:
        """Pump child → GUI. Signals emitted here are queued to GUI-thread slots."""
        conn = child.conn
        while True:
            try:
                msg = conn.recv()
            except (EOFError, OSError):
                self._replies.put(("dead", None))
                if self._open and not self._closing:
                    self._open = False
                    _LOG.error("Capture process exited unexpectedly (pid %s)", child.pid)
                    self.connection_lost.emit()
                return
            kind = msg[0]
            if kind == "sig":
                name, args = msg[1], msg[2]
                if name == "connection_lost":
                    self._open = False
                getattr(self, name).emit(*args)
            elif kind == "reply":
                self._replies.put(msg)
            elif kind == "log":
                _, level, name, text, exc_text = msg
                tail = f"\n{exc_text}" if exc_text else ""
                logging.getLogger(name).log(level, "[capture pid %s] %s%s", child.pid, text, tail)
            elif kind == "closed":
                self._replies.put(msg)
                return  # child is idle again; hand the pipe back
            # "ready" needs no action.

    def _call(self, name: str, *args: Any, wait: bool = False) -> Any:
        if self._child is None:
            return None
        req_id = self._next_id() if wait else None
        self._send(("call", req_id, name, args))
        if not wait:
            return None
        _, _, ok, value = self._await(req_id, _CALL_TIMEOUT_S)
        if not ok:
            raise CaptureProcessError(value)
        return value

    # -- PollingWorker API -------------------------------------------------

    def open(self) -> None:
        if self._open:
            return
        self._closing = False
        self._child = _take()
        self._reader = threading.Thread(
            target=self._read_loop, args=(self._child,), name="CaptureReader", daemon=True
        )
        self._reader.start()
        req_id = self._next_id()
        try:
            self._send(("open", req_id, self.settings, self.protocol, self._schedules, self._decode_config))
            _, _, ok, err = self._await(req_id, _OPEN_TIMEOUT_S)
        except CaptureProcessError:
            self._discard_child()
            raise
        if not ok:
            # Port-level failure (busy, missing, refused). The child is fine:
            # hand it back for the next attempt and raise like PollingWorker.
            self._release_child()
            raise serial.SerialException(err)
        self._open = True

    def stop(self) -> None:
        self.close()

    def close(self) -> None:
        if self._child is None:
            return
        self._closing = True
        self._open = False
        req_id = self._next_id()
        try:
            self._send(("close", req_id))
            self._await(req_id, _CLOSE_TIMEOUT_S)
        except CaptureProcessError:
            self._discard_child()
            return
        self._release_child()

    def _release_child(self) -> None:
        """Return the child to the pool once its reader has stopped.

        The reader stops after it relays the child's "closed" reply, so a
        close must already have been acknowledged (``close()``) or is sent
        here (failed ``open()``). Exactly one "closed" per hand-back keeps the
        pipe clean for the next client.
        """
        child, self._child = self._child, None
        if child is None:
            return
        reader, self._reader = self._reader, None
        if reader is not None and reader.is_alive() and not self._closing:
            req_id = self._next_id()
            try:
                with self._send_lock:
                    child.conn.send(("close", req_id))
            except (OSError, EOFError, ValueError):
                child.kill()
                return
        if reader is not None:
            reader.join(_CLOSE_TIMEOUT_S)
            if reader.is_alive():
                child.kill()
                return
        _give_back(child)

    def _discard_child(self) -> None:
        child, self._child = self._child, None
        if child is not None:
            child.kill()
        if self._reader is not None:
            self._reader.join(1.0)
            self._reader = None

    def wait(self, msecs: int = 0) -> bool:
        return True

    def isRunning(self) -> bool:  # noqa: N802 - mirrors QThread
        return self._open

    def enqueue_priority_tx(self, data: bytes) -> None:
        self._call("enqueue_priority_tx", data)

    def set_polling_global(self, enabled: bool) -> None:
        self._call("set_polling_global", enabled)

    def set_pipelining(self, enabled: bool, depth: int = 2, gap_ms: Optional[int] = None) -> None:
        self._call("set_pipelining", enabled, depth, gap_ms)

    def toggle_schedule(self, target_id: int, enabled: bool) -> None:
        self._call("toggle_schedule", target_id, enabled)

    def reset_metrics(self) -> None:
        self._call("reset_metrics")

    def set_backpressure(self, throttled: bool) -> None:
        self._call("set_backpressure", throttled)

    def start_raw_capture(self, path, metadata: Optional[dict] = None) -> None:
        try:
            self._call("start_raw_capture", str(path), metadata, wait=True)
        except CaptureProcessError as exc:
            raise OSError(str(exc)) from exc

    def stop_raw_capture(self) -> Optional[str]:
        try:
            return self._call("stop_raw_capture", wait=True)
        except CaptureProcessError as exc:
            return str(exc)

    def rotate_raw_capture(self, path, metadata: Optional[dict] = None) -> Optional[str]:
        try:
            return self._call("rotate_raw_capture", str(path), metadata, wait=True)
        except CaptureProcessError as exc:
            raise OSError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Self-test (bytehound --selftest-capture)
# ---------------------------------------------------------------------------

def selftest(frames_to_send: int = 600, timeout_s: float = 30.0) -> int:
    """End-to-end check that a capture process can be spawned and stream data.

    Plays a TCP device on loopback with the bundled template config, opens a
    :class:`CaptureClient` against it and waits for every frame to arrive
    decoded. Meant for verifying a frozen build. Returns a process exit code.
    """
    import socket
    import sys
    import time
    from pathlib import Path

    from PySide6.QtCore import QCoreApplication

    from ..decoder.config_loader import load_config
    from ..protocol.packet_builder import build_packet
    from .serial_worker import SerialSettings

    def say(msg: str) -> None:
        # A windowed (frozen) build has no stdout; the log file always works.
        _LOG.info("selftest-capture: %s", msg)
        if sys.stdout is not None:
            print(msg)

    app = QCoreApplication.instance() or QCoreApplication([])
    config = load_config(Path(__file__).resolve().parents[1] / "resources" / "config_template")
    frames = [
        build_packet(config.protocol, fid, bytes((i + fid) & 0xFF for i in range(f.payload_length)))
        for fid, f in config.frames.items()
    ]
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def device() -> None:
        conn, _ = srv.accept()
        conn.sendall(b"".join(frames[i % len(frames)] for i in range(frames_to_send)))
        time.sleep(timeout_s)
        conn.close()

    threading.Thread(target=device, daemon=True).start()
    got: list = []
    t0 = time.perf_counter()
    client = CaptureClient(
        SerialSettings(port="127.0.0.1", connection_type="tcp", host="127.0.0.1", port_num=port),
        config.protocol, [], decode_config=config,
    )
    client.packets_received.connect(lambda batch: got.extend(batch))
    try:
        client.open()
        say(f"capture process pid {client.child_pid} opened in {time.perf_counter() - t0:.2f}s")
        end = time.monotonic() + timeout_s
        while len(got) < frames_to_send and time.monotonic() < end:
            app.processEvents()
            time.sleep(0.01)
    except Exception as exc:
        say(f"FAIL: {type(exc).__name__}: {exc}")
        return 1
    finally:
        client.close()
        shutdown_pool()
        srv.close()
    decoded = sum(1 for p, d, _ in got if p.ok and d is not None)
    ok = decoded == frames_to_send
    say(f"{'OK' if ok else 'FAIL'}: {decoded}/{frames_to_send} frames decoded via capture process "
          f"in {time.perf_counter() - t0:.2f}s")
    return 0 if ok else 1
