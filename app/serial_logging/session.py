"""Long-duration logging sessions (Plane.md Part A, Part H, F9–F11).

BMS labs log for days, months or years. A single growing workbook cannot
hold that (Excel caps a sheet at 1,048,576 rows, ~29 h at 10 Hz), so a
session is a folder of rotated segments plus a manifest::

    <session>/
      session.json              manifest, rewritten atomically
      config/                   copy of the configuration that was used
      seg_0001_event.csv/.xlsx  event log: one wide row per cycle
      seg_0001_fixed.csv/.xlsx  fixed-step log: one row per grid tick
      seg_0001_rejected.csv     frames that failed CRC / framing (F9)
      seg_0001_sequence.csv     sequence-counter gaps / repeats / resets (F12)
      seg_0001.bhraw            lossless raw capture (written by the worker)
      seg_0002_…

Segments rotate on a time interval (default 1 h) and before any log reaches
``max_segment_rows``, so every ``.xlsx`` fits in one sheet. A closed segment
is compiled to ``.xlsx`` and hashed on a background thread; capture never
waits for it.

Fixed-step rows (Part H) are generated from the frames' receive timestamps:
row *n* is stamped ``t0 + n × step`` and holds the newest value of every
signal received at or before that instant, plus its age. Rows therefore do
not depend on when a timer fires or how busy the GUI is; a stall only delays
when rows are written, never what they contain.

Times: each segment anchors wall-clock time to the monotonic receive clock
at its start, so timestamps never jump with NTP or DST and re-sync hourly.
``time_utc`` / ``time_local`` are ISO 8601 with milliseconds and offset.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import queue
import shutil
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Tuple

from ..decoder.frame_decoder import DecodedFrame
from ..decoder.types import FrameConfig
from .decoded_logger import CSV_ENCODING, DecodedLogger, csv_cell, finalize_temp_log

_LOG = logging.getLogger("bytehound.serial_logging.session")

SESSION_FORMAT = "bytehound-session"
SESSION_FORMAT_VERSION = 1
MANIFEST_NAME = "session.json"

# Fixed-step rows for quiet periods are emitted this long after their grid
# time, so frames still in flight (batching, pipe to the GUI) arrive first.
QUIET_MARGIN_S = 1.0
_DISK_CHECK_INTERVAL_S = 30.0
_HEARTBEAT_INTERVAL_S = 60.0
# Warn when this many closed segments are still being finished at once.
FINISH_BACKLOG_WARN = 3
_WRITER_QUEUE_SIZE = 1_000_000

Key = Tuple[Any, str]


# ---------------------------------------------------------------------------
# Settings and small helpers
# ---------------------------------------------------------------------------

@dataclass
class SessionSettings:
    segment_seconds: float = 3600.0
    max_segment_rows: int = 1_000_000      # keeps each .xlsx within one sheet
    event_log: bool = True
    fixed_step_s: Optional[float] = None   # None = fixed-step logging off
    stale_steps: int = 3                   # a value older than this many steps is stale
    hold_stale: bool = True                # False: stale cells are left blank
    disk_warn_bytes: int = 10 * 1024 ** 3
    disk_stop_bytes: int = 2 * 1024 ** 3


class RawCaptureHooks(Protocol):
    def start(self, path: Path, metadata: Dict[str, Any]) -> None: ...
    def stop(self) -> Optional[str]: ...
    # Optional: switch to a new file with no gap and return the old
    # file's error. Without it rotation falls back to stop() + start(),
    # which loses whatever arrives in between.
    # def rotate(self, path: Path, metadata: Dict[str, Any]) -> Optional[str]: ...


def iso_utc(wall: float) -> str:
    return datetime.fromtimestamp(wall, timezone.utc).isoformat(timespec="milliseconds")


def iso_local(wall: float) -> str:
    return datetime.fromtimestamp(wall).astimezone().isoformat(timespec="milliseconds")


def write_manifest(folder: Path, data: Dict[str, Any]) -> None:
    """Atomically replace ``session.json`` (temp file + rename)."""
    target = folder / MANIFEST_NAME
    tmp = folder / (MANIFEST_NAME + ".partial")
    with tmp.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2, default=str)
        fp.flush()
        os.fsync(fp.fileno())
    os.replace(tmp, target)


def read_manifest(folder: Path) -> Dict[str, Any]:
    with (Path(folder) / MANIFEST_NAME).open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    if data.get("format") != SESSION_FORMAT:
        raise ValueError(f"{folder} is not a Bytehound session")
    return data


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _copy_config(source: Optional[Path], dest: Path) -> Dict[str, Any]:
    """Copy the configuration into the session and fingerprint it."""
    info: Dict[str, Any] = {"source": str(source) if source else ""}
    if source is None or not Path(source).exists():
        return info
    source = Path(source)
    dest.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in source.rglob("*") if p.is_file()) if source.is_dir() else [source]
    h = hashlib.sha256()
    for f in files:
        rel = f.relative_to(source) if source.is_dir() else Path(f.name)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
        h.update(str(rel).replace("\\", "/").encode("utf-8") + b"\0")
        h.update(f.read_bytes())
    info["copy"] = str(dest.name)
    # What to pass to load_config to read the copy back (offline rebuild).
    info["load"] = dest.name if source.is_dir() else f"{dest.name}/{source.name}"
    info["files_sha256"] = h.hexdigest()
    info.update(_config_fingerprint(source))
    return info


def _config_fingerprint(source: Path) -> Dict[str, Any]:
    """Content fingerprint of the configuration (Part C6): the same
    configuration saved as xlsx, CSV or JSON has the same fingerprint, unlike
    ``files_sha256``. Best effort: a source that cannot be read gives none."""
    try:
        from ..decoder import canonical

        return {"fingerprint": canonical.fingerprint(canonical.import_config(source))}
    except Exception:
        _LOG.warning("Configuration fingerprint not computed for %s", source, exc_info=True)
        return {}


# ---------------------------------------------------------------------------
# Background CSV writer (fixed-step and rejected-frame logs)
# ---------------------------------------------------------------------------

_STOP = object()


class CsvSegmentWriter:
    """Writes rows on its own thread; optionally compiles ``.xlsx`` on close.

    With ``compile_to`` the rows stream to ``<compile_to>.tmp_data`` (the same
    temp naming as :class:`DecodedLogger`, so crash recovery treats both
    alike) and close() produces ``<stem>.csv`` + ``<stem>.xlsx``. Without it,
    rows go straight to ``path``.
    """

    def __init__(
        self,
        header: List[str],
        *,
        path: Optional[Path] = None,
        compile_to: Optional[Path] = None,
        metadata: Optional[Dict[str, Any]] = None,
        flush_interval: float = 0.5,
    ) -> None:
        if (path is None) == (compile_to is None):
            raise ValueError("give exactly one of path / compile_to")
        self._compile_to = compile_to
        if compile_to is not None:
            self.data_path = compile_to.parent / (compile_to.name + ".tmp_data")
            self.meta_path = compile_to.parent / (compile_to.name + ".tmp_meta")
            with self.meta_path.open("w", encoding="utf-8") as fp:
                json.dump(metadata or {}, fp, default=str)
        else:
            self.data_path = path  # type: ignore[assignment]
            self.meta_path = None
        self._metadata = dict(metadata or {})
        self._flush_interval = flush_interval
        self._queue: "queue.Queue[Any]" = queue.Queue(maxsize=_WRITER_QUEUE_SIZE)
        self.rows_written = 0
        self.dropped = 0
        self.error: Optional[str] = None
        self._fp = self.data_path.open("w", encoding=CSV_ENCODING, newline="")
        self._writer = csv.writer(self._fp)
        self._writer.writerow(header)
        self._fp.flush()
        self._thread = threading.Thread(
            target=self._loop, name=f"CsvSegmentWriter[{self.data_path.name}]", daemon=False
        )
        self._thread.start()

    def write(self, row: List[Any]) -> None:
        if self.error is not None:
            # The writer thread has stopped: queueing would only grow memory.
            self.dropped += 1
            return
        try:
            self._queue.put_nowait(row)
        except queue.Full:
            self.dropped += 1  # disk wedged for a very long time; counted in the manifest

    def write_many(self, rows: Iterable[List[Any]]) -> None:
        for row in rows:
            self.write(row)

    def close(self) -> None:
        """Ask the writer to drain, finish the file and exit (non-blocking)."""
        self._queue.put(_STOP)

    def join(self, timeout: Optional[float] = None) -> bool:
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _loop(self) -> None:
        last_flush = time.monotonic()
        try:
            while True:
                item = self._queue.get()
                if item is _STOP:
                    break
                self._writer.writerow([csv_cell(c) for c in item])
                self.rows_written += 1
                now = time.monotonic()
                if now - last_flush >= self._flush_interval:
                    self._fp.flush()
                    last_flush = now
        except Exception as exc:
            self.error = f"{self.data_path.name}: {exc}"
            _LOG.exception("CSV segment writer failed")
        finally:
            try:
                self._fp.flush()
                self._fp.close()
            except Exception:
                pass
            if self._compile_to is not None and self.error is None:
                exc = finalize_temp_log(
                    self.data_path, self.meta_path, self._compile_to, self._metadata, keep_csv=True,
                    isolate=True,
                )
                if exc is not None:
                    self.error = f"{self._compile_to.name}: {exc}"


# ---------------------------------------------------------------------------
# Fixed-step sampling (Part H)
# ---------------------------------------------------------------------------

def fixed_step_columns(config: FrameConfig) -> List[Tuple[Key, str]]:
    """(key, header) for every signal and calculation, in config order."""
    cols: List[Tuple[Key, str]] = []
    for spec in config.all_signals:
        if not spec.enabled:
            continue
        label = f"0x{spec.frame_id:X}.{spec.signal_name}"
        cols.append(((spec.frame_id, spec.signal_name), f"{label} ({spec.unit})" if spec.unit else label))
    for calc in config.calc_groups:
        if getattr(calc, "enabled", True):
            name = f"{calc.group} {calc.stat}"
            cols.append((("calc", name), f"{name} ({calc.unit})" if calc.unit else name))
    return cols


class FixedStepSampler:
    """Turns timestamped decoded frames into rows on an exact time grid.

    Row *n* has grid time ``t0 + n * step`` (multiplied, never accumulated, so
    there is no drift over months) and holds, for every signal, the newest
    value received at or before that time and its age in ms. A value older
    than ``stale_steps`` steps is stale: held, or blank if ``hold_stale`` is
    False. Rows are only produced once their time is known to be complete —
    when a later frame arrives (:meth:`feed`) or when the caller advances the
    clock for quiet periods (:meth:`advance`) — so they never miss a frame
    that was still in flight, and none is ever skipped.
    """

    def __init__(
        self,
        columns: List[Tuple[Key, str]],
        step_s: float,
        t0_perf: float,
        *,
        stale_steps: int = 3,
        hold_stale: bool = True,
        wall_of: Callable[[float], float],
    ) -> None:
        if step_s <= 0:
            raise ValueError("step must be positive")
        self._keys = [k for k, _ in columns]
        self._labels = [lbl for _, lbl in columns]
        self.step = float(step_s)
        self.t0 = float(t0_perf)
        self._stale_after = stale_steps * self.step
        self._hold = hold_stale
        self._wall_of = wall_of
        self._latest: Dict[Key, Tuple[Any, float]] = {}
        self.next_index = 0

    @property
    def header(self) -> List[str]:
        cols = ["tick", "time_utc", "time_local", "elapsed_s"]
        for label in self._labels:
            cols += [label, f"{label}.age_ms"]
        cols.append("stale_signals")
        return cols

    def grid_time(self, n: int) -> float:
        return self.t0 + n * self.step

    def feed(self, decoded: DecodedFrame, rx_perf: float) -> List[List[Any]]:
        # Grid points strictly before this frame are complete now.
        rows = self._emit_while(lambda t: t < rx_perf)
        for sig in (*decoded.signals, *decoded.calculations):
            if sig.status != "ok" or sig.scaled_value is None:
                continue
            key = ("calc", sig.signal_name) if sig.is_calculated else (sig.frame_id, sig.signal_name)
            self._latest[key] = (sig.scaled_value, rx_perf)
        return rows

    def advance(self, until_perf: float) -> List[List[Any]]:
        """Emit every grid row at or before ``until_perf`` (quiet periods)."""
        return self._emit_while(lambda t: t <= until_perf)

    def _emit_while(self, cond: Callable[[float], bool]) -> List[List[Any]]:
        rows: List[List[Any]] = []
        while True:
            t = self.grid_time(self.next_index)
            if not cond(t):
                return rows
            rows.append(self._row(self.next_index, t))
            self.next_index += 1

    def _row(self, n: int, t: float) -> List[Any]:
        wall = self._wall_of(t)
        row: List[Any] = [n, iso_utc(wall), iso_local(wall), round(n * self.step, 6)]
        stale = 0
        for key in self._keys:
            entry = self._latest.get(key)
            if entry is None:
                row += ["", ""]
                stale += 1
                continue
            value, at = entry
            age = t - at
            is_stale = age > self._stale_after
            stale += is_stale
            row += ["" if (is_stale and not self._hold) else value, int(round(age * 1000))]
        row.append(stale)
        return row


# ---------------------------------------------------------------------------
# Session orchestration
# ---------------------------------------------------------------------------

_STOP_RAW = object()
_INTEGRITY_GAUGES = frozenset({"buffered_bytes", "rx_service_gap_max_ms"})


class _RawHooksNone:
    records = False   # writes no file: the manifest must not list one

    def start(self, path: Path, metadata: Dict[str, Any]) -> None:
        return None

    def stop(self) -> Optional[str]:
        return None


class _Segment:
    def __init__(self, index: int, wall0: float, perf0: float) -> None:
        self.index = index
        self.wall0 = wall0
        self.perf0 = perf0
        self.event: Optional[DecodedLogger] = None
        self.fixed: Optional[CsvSegmentWriter] = None
        self.rejected: Optional[CsvSegmentWriter] = None
        self.rejected_count = 0
        self.sequence: Optional[CsvSegmentWriter] = None
        self.sequence_events = 0
        self.integrity_start: Dict[str, Any] = {}


class SessionLog:
    """Writes one logging session as rotated segments with a manifest.

    ``log_frame`` / ``log_rejected`` may be called from the capture worker's
    thread while the GUI thread calls ``tick`` / ``stop`` / the connection
    methods: everything that touches the open segment or the fixed-step
    sampler is serialised by ``_seg_lock`` (task.md Phase 1: logging moved
    off the GUI thread). Lock order is ``_seg_lock`` then ``_lock``. Writers,
    segment finishing and xlsx compilation run on their own threads.
    """

    def __init__(
        self,
        folder: Path,
        config: FrameConfig,
        settings: SessionSettings,
        *,
        config_source: Optional[Path] = None,
        metadata: Optional[Dict[str, str]] = None,
        app_version: str = "",
        polling_mode: bool = False,
        raw_capture: Optional[RawCaptureHooks] = None,
        on_warning: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        clock: Callable[[], float] = time.time,
        perf: Callable[[], float] = time.perf_counter,
        disk_free: Optional[Callable[[Path], int]] = None,
    ) -> None:
        self.folder = Path(folder)
        self.config = config
        self.settings = settings
        self._config_source = Path(config_source) if config_source else None
        # Configuration of the segments being written: "config" (the one the
        # session started with) or "config_N" after change_config.
        self._config_id = "config"
        self._config_info: Dict[str, Any] = {}
        self._metadata = dict(metadata or {})
        self._app_version = app_version
        self.polling_mode = polling_mode
        self._raw = raw_capture or _RawHooksNone()
        self._warn = on_warning or (lambda msg: _LOG.warning(msg))
        self._error = on_error or (lambda msg: _LOG.error(msg))
        self._clock = clock
        self._perf = perf
        self._disk_free = disk_free or (lambda p: shutil.disk_usage(p).free)

        self._lock = threading.Lock()          # guards the manifest
        self._seg_lock = threading.RLock()     # guards the open segment + sampler
        self._summary_lock = threading.Lock()  # serialises summary updates
        self._manifest: Dict[str, Any] = {}
        self._segment: Optional[_Segment] = None
        self._finishers: List[threading.Thread] = []
        self._sampler: Optional[FixedStepSampler] = None
        self._integrity: Dict[str, Any] = {}
        self._gap_start: Optional[float] = None
        self._last_disk_check = float("-inf")
        self._disk_warned = False
        self._last_heartbeat = 0.0
        self.stopped_for_disk = False
        self.decoded_dropped = 0
        self.session_perf0 = 0.0

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:
        with self._seg_lock:
            self._start()

    def _start(self) -> None:
        if (self.folder / MANIFEST_NAME).exists():
            raise FileExistsError(f"{self.folder} already contains a session")
        self.folder.mkdir(parents=True, exist_ok=True)
        wall0, self.session_perf0 = self._clock(), self._perf()
        self.session_wall0 = wall0
        config_info = _copy_config(self._config_source, self.folder / "config")
        self._config_info = config_info
        self._manifest = {
            "format": SESSION_FORMAT,
            "format_version": SESSION_FORMAT_VERSION,
            "app_version": self._app_version,
            "status": "recording",
            "started_utc": iso_utc(wall0),
            "ended_utc": None,
            "last_alive_utc": iso_utc(wall0),
            "config": config_info,
            "settings": asdict(self.settings),
            "metadata": self._metadata,
            "segments": [],
            "gaps": [],
            "events": [],
        }
        if self.settings.fixed_step_s:
            self._sampler = FixedStepSampler(
                fixed_step_columns(self.config),
                self.settings.fixed_step_s,
                self.session_perf0,
                stale_steps=self.settings.stale_steps,
                hold_stale=self.settings.hold_stale,
                wall_of=self._wall_of,
            )
        self._open_segment(1)

    def stop(self, reason: str = "stopped") -> None:
        """Close the open segment and finish the session (non-blocking;
        use :meth:`await_finished` to wait for the last xlsx/hash)."""
        with self._seg_lock:
            self._stop(reason)

    def _stop(self, reason: str) -> None:
        if self._segment is not None:
            self._close_segment(reason)
        with self._lock:
            if self._gap_start is not None:
                self._end_gap_locked(self._clock())
            self._manifest["status"] = "closed"
            self._manifest["ended_utc"] = iso_utc(self._clock())
            self._save_locked()

    def is_finishing(self) -> bool:
        self._finishers = [t for t in self._finishers if t.is_alive()]
        return bool(self._finishers)

    def await_finished(self, timeout: Optional[float] = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        for t in list(self._finishers):
            t.join(None if deadline is None else max(0.0, deadline - time.monotonic()))
        return not self.is_finishing()

    # Interface used by the GUI's "finishing log" progress dialog.
    def is_draining(self) -> bool:
        return self.is_finishing()

    def await_drain(self, timeout: Optional[float] = None) -> bool:
        return self.await_finished(timeout)

    def pending_rows(self) -> int:
        return sum(1 for t in self._finishers if t.is_alive())

    @property
    def manifest(self) -> Dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._manifest, default=str))

    @property
    def segment_index(self) -> Optional[int]:
        return self._segment.index if self._segment else None

    # -- data -------------------------------------------------------------

    def _wall_of(self, perf_t: float) -> float:
        seg = self._segment
        if seg is None:
            return self._clock() - (self._perf() - perf_t)
        return seg.wall0 + (perf_t - seg.perf0)

    def log_frame(self, decoded: DecodedFrame, rx_perf: float) -> None:
        with self._seg_lock:
            seg = self._segment
            if seg is None:
                return
            if seg.event is not None:
                elapsed_ms = int((rx_perf - self.session_perf0) * 1000)
                seg.event.log_frame(decoded, elapsed_ms, wall=self._wall_of(rx_perf))
            if self._sampler is not None and seg.fixed is not None:
                seg.fixed.write_many(self._sampler.feed(decoded, rx_perf))

    def log_rejected(self, raw: bytes, frame_id: Optional[int], error: str, rx_perf: float) -> None:
        """Record a frame that failed CRC / framing checks (F9)."""
        with self._seg_lock:
            self._log_rejected(raw, frame_id, error, rx_perf)

    def log_sequence_event(self, frame_id: int, kind: str, expected: int, received: int, missing: int,
                           rx_perf: float) -> None:
        """Record a sequence-counter gap / repeat / reset (F12): frames lost
        before they reached the PC leave no other trace."""
        with self._seg_lock:
            seg = self._segment
            if seg is None:
                return
            if seg.sequence is None:
                seg.sequence = CsvSegmentWriter(
                    ["time_utc", "time_local", "elapsed_ms", "frame_id", "kind", "expected", "received",
                     "missing"],
                    path=self.folder / f"seg_{seg.index:04d}_sequence.csv",
                )
            wall = self._wall_of(rx_perf)
            seg.sequence.write([
                iso_utc(wall), iso_local(wall), int((rx_perf - self.session_perf0) * 1000),
                f"0x{frame_id:X}", kind, expected, received, missing,
            ])
            seg.sequence_events += 1

    def _log_rejected(self, raw: bytes, frame_id: Optional[int], error: str, rx_perf: float) -> None:
        seg = self._segment
        if seg is None:
            return
        if seg.rejected is None:
            seg.rejected = CsvSegmentWriter(
                ["time_utc", "time_local", "elapsed_ms", "frame_id", "error", "raw_hex"],
                path=self.folder / f"seg_{seg.index:04d}_rejected.csv",
            )
        wall = self._wall_of(rx_perf)
        seg.rejected.write([
            iso_utc(wall), iso_local(wall), int((rx_perf - self.session_perf0) * 1000),
            "" if frame_id is None else f"0x{frame_id:X}", error or "", raw.hex(" ").upper(),
        ])
        seg.rejected_count += 1

    def set_integrity(self, snapshot: Dict[str, Any]) -> None:
        flat = dict(snapshot)
        # Driver error flags arrive as a nested dict; flatten them so the
        # per-segment counters in session.json include them.
        for name, count in (flat.pop("driver_errors", None) or {}).items():
            flat[f"driver_{name}"] = count
        with self._seg_lock:
            self._integrity = flat
            if self._segment is not None and not self._segment.integrity_start:
                self._segment.integrity_start = dict(flat)

    def set_polling_mode(self, enabled: bool) -> None:
        with self._seg_lock:
            self.polling_mode = enabled
            if self._segment and self._segment.event is not None:
                self._segment.event.polling_mode = enabled

    def tick(self) -> None:
        """Housekeeping, ~1 Hz: quiet-period fixed-step rows, rotation, disk
        guard, heartbeat."""
        with self._seg_lock:
            self._tick()

    def _tick(self) -> None:
        seg = self._segment
        now_perf = self._perf()
        if seg is not None:
            # A CSV writer thread that hit a write error (disk full) has
            # stopped; report it now, not when the segment closes.
            for w in (seg.fixed, seg.rejected, seg.sequence):
                if w is not None and w.error and not getattr(w, "_reported", False):
                    w._reported = True
                    self._error(w.error)
        if seg is not None and self._sampler is not None and seg.fixed is not None:
            seg.fixed.write_many(self._sampler.advance(now_perf - QUIET_MARGIN_S))
        if seg is not None and self._rotation_due(seg):
            raw_error, raw_started = self._rotate_raw(seg.index + 1)
            self._close_segment("rotation", raw_error=raw_error)
            self._open_segment(seg.index + 1, raw_started=raw_started)
        self._check_disk()
        wall = self._clock()
        if wall - self._last_heartbeat >= _HEARTBEAT_INTERVAL_S:
            self._last_heartbeat = wall
            with self._lock:
                self._manifest["last_alive_utc"] = iso_utc(wall)
                self._save_locked()

    # -- connection gaps (F11) ------------------------------------------

    def connection_lost(self, reason: str) -> None:
        """Close the current segment and start a gap; the session continues."""
        with self._seg_lock:
            self._connection_lost(reason)

    def _connection_lost(self, reason: str) -> None:
        if self._segment is not None:
            self._close_segment(f"connection lost: {reason}")
        with self._lock:
            self._gap_start = self._clock()
            self._manifest["gaps"].append({"start_utc": iso_utc(self._gap_start), "end_utc": None, "reason": reason})
            self._save_locked()

    def connection_restored(self) -> None:
        with self._seg_lock:
            self._connection_restored()

    def _connection_restored(self) -> None:
        with self._lock:
            self._end_gap_locked(self._clock())
            self._save_locked()
            next_index = len(self._manifest["segments"]) + 1
        self._open_segment(next_index)

    def _end_gap_locked(self, wall: float) -> None:
        if self._gap_start is not None and self._manifest["gaps"]:
            self._manifest["gaps"][-1]["end_utc"] = iso_utc(wall)
            self._manifest["gaps"][-1]["seconds"] = round(wall - self._gap_start, 3)
        self._gap_start = None

    def change_config(self, config: FrameConfig, config_source: Optional[Path] = None) -> str:
        """Use ``config`` from the next segment on (Part C decision 3: a
        configuration activated while connected reconnects, and the session
        continues in a new segment). Only allowed during a gap, so no
        segment ever mixes two configurations. The new configuration is
        copied into the session as ``config_N/``; every segment records the
        configuration it used. Returns the copy's id."""
        with self._seg_lock:
            if self._segment is not None:
                raise RuntimeError("the configuration can only change between segments (during a gap)")
            with self._lock:
                changes = self._manifest.setdefault("config_changes", [])
                copy_id = f"config_{len(changes) + 2}"
                first_segment = len(self._manifest["segments"]) + 1
            source = Path(config_source) if config_source else None
            info = _copy_config(source, self.folder / copy_id)
            self.config = config
            self._config_source = source
            self._config_id = copy_id
            self._config_info = info
            if self._sampler is not None:
                # Same grid (t0, step) and row numbering; the new columns.
                old = self._sampler
                self._sampler = FixedStepSampler(
                    fixed_step_columns(config),
                    self.settings.fixed_step_s,
                    old.t0,
                    stale_steps=self.settings.stale_steps,
                    hold_stale=self.settings.hold_stale,
                    wall_of=self._wall_of,
                )
                self._sampler.next_index = old.next_index
            with self._lock:
                changes.append({"id": copy_id, "utc": iso_utc(self._clock()),
                                "first_segment": first_segment, **info})
                self._save_locked()
            name = source.name if source else "(no file)"
            self._event(f"Configuration changed to {name} from segment {first_segment} ({copy_id})")
            return copy_id

    # -- segments -----------------------------------------------------------

    def _seg_path(self, index: int, kind: str, ext: str) -> Path:
        return self.folder / f"seg_{index:04d}_{kind}{ext}"

    def _segment_meta(self, index: int, wall0: float) -> Dict[str, Any]:
        return {
            **self._metadata,
            "session": self.folder.name,
            "segment": str(index),
            "segment_started_utc": iso_utc(wall0),
            "config_files_sha256": self._config_info.get("files_sha256", ""),
            "config_fingerprint": self._config_info.get("fingerprint", ""),
        }

    def _raw_meta(self, index: int, wall0: float) -> Dict[str, Any]:
        return {
            "log_started_perf": self.session_perf0,
            "polling_mode": self.polling_mode,
            "config_source": str(self._config_source or ""),
            "log_metadata": self._segment_meta(index, wall0),
        }

    def _rotate_raw(self, next_index: int) -> tuple:
        """Move the raw capture to the next segment's file before the
        current segment closes, so no received byte falls between the two
        files. Returns (old file's error, whether the new file started)."""
        rotate = getattr(self._raw, "rotate", None)
        if rotate is None:
            return self._raw.stop(), False
        path = self.folder / f"seg_{next_index:04d}.bhraw"
        try:
            return rotate(path, self._raw_meta(next_index, self._clock())), True
        except Exception as exc:
            self._warn(f"Raw capture not rotated to segment {next_index}: {exc}")
            return self._raw.stop(), False

    def _open_segment(self, index: int, *, raw_started: bool = False) -> None:
        """Open segment ``index``. A failure (folder not writable, disk
        full, file locked) is recorded in session.json before it is
        raised: no segment is open afterwards and nothing more can be
        written, and the folder must say why the recording stopped."""
        try:
            self._open_segment_files(index, raw_started=raw_started)
        except Exception as exc:
            _LOG.exception("Could not open segment %d", index)
            try:
                self._event(f"Recording stopped: segment {index} could not be opened: {exc}")
            except Exception:
                _LOG.exception("Could not record the failure in session.json")
            raise

    def _open_segment_files(self, index: int, *, raw_started: bool = False) -> None:
        seg = _Segment(index, self._clock(), self._perf())
        meta = self._segment_meta(index, seg.wall0)
        files: Dict[str, str] = {}
        if self.settings.event_log:
            target = self._seg_path(index, "event", ".xlsx")
            seg.event = DecodedLogger(
                target, self.config, metadata=meta, polling_mode=self.polling_mode,
                keep_csv=True, time_columns=True, on_warning=self._warn,
                # Without this a write error (disk full) disabled the logger
                # with no report: every later frame was dropped silently.
                on_error=self._error,
            )
            seg.event.open()
            files["event_csv"] = target.with_suffix(".csv").name
            files["event_xlsx"] = target.name
        if self._sampler is not None:
            target = self._seg_path(index, "fixed", ".xlsx")
            seg.fixed = CsvSegmentWriter(
                self._sampler.header, compile_to=target,
                metadata={**meta, "fixed_step_s": str(self.settings.fixed_step_s)},
            )
            files["fixed_csv"] = target.with_suffix(".csv").name
            files["fixed_xlsx"] = target.name
        raw_path = self.folder / f"seg_{index:04d}.bhraw"
        if raw_started:
            files["raw"] = raw_path.name
        else:
            try:
                self._raw.start(raw_path, self._raw_meta(index, seg.wall0))
                if getattr(self._raw, "records", True):
                    files["raw"] = raw_path.name
            except Exception as exc:
                self._warn(f"Raw capture not started for segment {index}: {exc}")
        seg.integrity_start = dict(self._integrity)
        self._segment = seg
        with self._lock:
            self._manifest["segments"].append({
                "index": index,
                "status": "open",
                "started_utc": iso_utc(seg.wall0),
                "ended_utc": None,
                "config": self._config_id,
                "files": files,
            })
            self._save_locked()

    def _rotation_due(self, seg: _Segment) -> bool:
        if self._clock() - seg.wall0 >= self.settings.segment_seconds:
            return True
        limit = self.settings.max_segment_rows
        if seg.event is not None and seg.event.rows_written + seg.event.pending_rows() >= limit:
            return True
        return seg.fixed is not None and seg.fixed.rows_written + seg.fixed._queue.qsize() >= limit

    def _close_segment(self, reason: str, *, raw_error: Any = _STOP_RAW) -> None:
        seg, self._segment = self._segment, None
        if seg is None:
            return
        if raw_error is _STOP_RAW:
            raw_error = self._raw.stop()
        if seg.event is not None:
            seg.event.close(timeout=0.0)
        if seg.fixed is not None:
            seg.fixed.close()
        if seg.rejected is not None:
            seg.rejected.close()
        if seg.sequence is not None:
            seg.sequence.close()
        # Counters become per-segment deltas; gauges (a level or a running
        # maximum, not a count) are recorded as their value at close.
        integrity = {
            k: v if k in _INTEGRITY_GAUGES else v - seg.integrity_start.get(k, 0)
            for k, v in self._integrity.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        }
        ended = self._clock()
        with self._lock:
            entry = self._manifest["segments"][-1]
            entry.update({
                "status": "closing",
                "ended_utc": iso_utc(ended),
                "close_reason": reason,
                "rejected_frames": seg.rejected_count,
                "sequence_events": seg.sequence_events,
                "integrity": integrity,
            })
            if raw_error:
                entry["raw_capture_error"] = raw_error
            self._save_locked()
        t = threading.Thread(
            target=self._finish_segment, args=(seg, entry), name=f"SegmentFinisher[{seg.index}]", daemon=False
        )
        t.start()
        # Drop finished threads: on Windows every retained Thread object keeps
        # ~2 OS handles (its locks are semaphores), which grew without bound
        # over a months-long session (found by tools/soak_session.py).
        self._finishers = [f for f in self._finishers if f.is_alive()]
        self._finishers.append(t)
        # Finishing slower than rotation piles segments up (each holds its
        # CSV until compiled): make the backlog visible.
        backlog = len(self._finishers)
        if backlog >= FINISH_BACKLOG_WARN and backlog > getattr(self, "_backlog_warned", 0):
            self._backlog_warned = backlog
            self._warn(f"{backlog} segments are still being finished (xlsx / analysis cache); "
                       "the PC is not keeping up with the rotation interval")

    def _finish_segment(self, seg: _Segment, entry: Dict[str, Any]) -> None:
        """Wait for the writers, then record row counts, sizes and hashes."""
        errors: List[str] = []
        rows: Dict[str, int] = {}
        if seg.event is not None:
            seg.event.await_drain(None)
            rows["event"] = seg.event.rows_written
            if seg.event.error:
                errors.append(seg.event.error)
            entry_dropped = seg.event.total_dropped
            if entry_dropped:
                self.decoded_dropped += entry_dropped
        else:
            entry_dropped = 0
        for name, w in (("fixed", seg.fixed), ("rejected", seg.rejected), ("sequence", seg.sequence)):
            if w is None:
                continue
            w.join()
            rows[name] = w.rows_written
            if w.error:
                errors.append(w.error)
            if w.dropped:
                errors.append(f"{name}: {w.dropped} row(s) dropped (writer queue full)")
        # Analysis caches (Part B) so the Analysis Suite opens any session
        # length instantly. Derived data: a failure is a warning, not an
        # error, and the Analysis Suite rebuilds a missing cache on open.
        notes: List[str] = []
        from ._isolated import run_isolated, timeout_for
        from .session_analysis import _CACHE_SUFFIX, build_segment_cache
        for kind in ("event", "fixed"):
            name = entry["files"].get(f"{kind}_csv")
            if not name or not (self.folder / name).exists():
                continue
            try:
                csv_path = self.folder / name
                final = csv_path.with_name(csv_path.stem + _CACHE_SUFFIX)
                partial = final.with_name(final.name + ".partial")
                cache = run_isolated(build_segment_cache, csv_path, self.session_wall0,
                                     timeout=timeout_for(csv_path), leftovers=[partial, final])
                entry["files"][f"{kind}_analysis"] = cache.name
            except Exception as exc:
                notes.append(f"analysis cache for {name} not built: {exc}")
                _LOG.warning("Analysis cache for %s failed", name, exc_info=True)
        sizes: Dict[str, int] = {}
        hashes: Dict[str, str] = {}
        for name in entry["files"].values():
            path = self.folder / name
            if path.exists():
                sizes[name] = path.stat().st_size
                if not name.endswith((".xlsx", "_analysis.npz")):
                    hashes[name] = _sha256(path)
            else:
                errors.append(f"{name} missing after close")
        for key, w in (("rejected_csv", seg.rejected), ("sequence_csv", seg.sequence)):
            if w is not None:
                name = w.data_path.name
                entry["files"][key] = name
                sizes[name] = w.data_path.stat().st_size
                hashes[name] = _sha256(w.data_path)
        with self._lock:
            entry.update({
                "status": "closed" if not errors else "closed_with_errors",
                "rows": rows,
                "decoded_dropped": entry_dropped,
                "bytes": sizes,
                "sha256": hashes,
            })
            if errors:
                entry["errors"] = errors
            if notes:
                entry["warnings"] = notes
            self._save_locked()
        self._extend_summaries(entry)
        for e in errors:
            self._warn(f"Segment {seg.index}: {e}")

    def _extend_summaries(self, entry: Dict[str, Any]) -> None:
        """Add the closed segment to the session summaries so the Analysis
        Suite opens a session of any length instantly (Part B). Only the new
        segment is read; finishers are serialised so the summary grows in
        segment order."""
        from .session_analysis import SessionSource

        with self._summary_lock:
            for kind in ("event", "fixed"):
                if f"{kind}_analysis" not in entry.get("files", {}):
                    continue
                try:
                    SessionSource(self.folder, kind=kind).ensure_summary()
                except Exception:
                    _LOG.warning("Session summary (%s) not updated", kind, exc_info=True)

    # -- disk guard ---------------------------------------------------------

    def _check_disk(self) -> None:
        now = self._clock()
        if now - self._last_disk_check < _DISK_CHECK_INTERVAL_S:
            return
        self._last_disk_check = now
        try:
            free = self._disk_free(self.folder)
        except OSError as exc:
            self._warn(f"Could not read free disk space: {exc}")
            return
        self.disk_free_bytes = free
        if free < self.settings.disk_stop_bytes:
            self.stopped_for_disk = True
            self._event(f"Disk almost full ({free / 1e9:.1f} GB free): logging stopped")
            self._error(
                f"Logging stopped: only {free / 1e9:.1f} GB free on the log drive "
                f"(stop level {self.settings.disk_stop_bytes / 1e9:.1f} GB). All data up to now is "
                f"saved in {self.folder}. Free space or choose another drive, then start logging again."
            )
        elif free < self.settings.disk_warn_bytes and not self._disk_warned:
            self._disk_warned = True
            self._event(f"Disk space low: {free / 1e9:.1f} GB free")
            self._warn(
                f"Log drive is getting full: {free / 1e9:.1f} GB free. Logging stops automatically "
                f"below {self.settings.disk_stop_bytes / 1e9:.1f} GB."
            )
        elif free >= self.settings.disk_warn_bytes:
            self._disk_warned = False

    def _event(self, text: str) -> None:
        with self._lock:
            self._manifest["events"].append({"utc": iso_utc(self._clock()), "text": text})
            self._save_locked()

    def _save_locked(self) -> None:
        try:
            write_manifest(self.folder, self._manifest)
        except OSError as exc:
            _LOG.error("Could not write %s: %s", self.folder / MANIFEST_NAME, exc)


# ---------------------------------------------------------------------------
# Crash / power-loss recovery
# ---------------------------------------------------------------------------

def recover_session(folder: Path) -> bool:
    """Finish a session that was still recording when the app stopped.

    Compiles every segment's leftover temp data (keeping the CSV), marks
    unfinished segments ``recovered`` and the session ``recovered``. Returns
    True if anything was recovered. Never deletes data it cannot rebuild.
    """
    folder = Path(folder)
    try:
        manifest = read_manifest(folder)
    except (OSError, ValueError):
        return False
    if manifest.get("status") not in ("recording", "closing"):
        return False
    for tmp in sorted(folder.glob("*.tmp_data")):
        target = tmp.with_name(tmp.name[: -len(".tmp_data")])
        meta = tmp.with_name(target.name + ".tmp_meta")
        metadata: Dict[str, Any] = {}
        if meta.exists():
            try:
                metadata = json.loads(meta.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        exc = finalize_temp_log(tmp, meta, target, metadata, keep_csv=True)
        if exc is not None:
            _LOG.error("Recovery of %s produced only CSV: %s", tmp, exc)
    for seg in manifest.get("segments", []):
        if seg.get("status") in ("open", "closing"):
            seg["status"] = "recovered"
            seg.setdefault("ended_utc", None)
            if not seg["ended_utc"]:
                seg["ended_utc"] = manifest.get("last_alive_utc")
            sizes = {}
            for name in seg.get("files", {}).values():
                p = folder / name
                if p.exists():
                    sizes[name] = p.stat().st_size
            seg["bytes"] = sizes
    for gap in manifest.get("gaps", []):
        if not gap.get("end_utc"):
            gap["end_utc"] = manifest.get("last_alive_utc")
    manifest["status"] = "recovered"
    manifest["ended_utc"] = manifest.get("ended_utc") or manifest.get("last_alive_utc")
    manifest.setdefault("events", []).append(
        {"utc": iso_utc(time.time()), "text": "Recovered after the app stopped unexpectedly"}
    )
    write_manifest(folder, manifest)
    return True


def find_unfinished_sessions(root: Path, max_depth: int = 2) -> List[Path]:
    """Session folders under ``root`` whose manifest says they were still recording."""
    out: List[Path] = []
    root = Path(root)
    if not root.exists():
        return out
    candidates = [root] + [p for p in root.iterdir() if p.is_dir()]
    if max_depth > 1:
        candidates += [q for p in root.iterdir() if p.is_dir() for q in p.iterdir() if q.is_dir()]
    for folder in candidates:
        m = folder / MANIFEST_NAME
        if not m.exists():
            continue
        try:
            if read_manifest(folder).get("status") in ("recording", "closing"):
                out.append(folder)
        except (OSError, ValueError):
            continue
    return out


def _segment_configs(folder: Path, manifest: Dict[str, Any], config: FrameConfig):
    """Which configuration decodes a segment. A session that never changed
    configuration uses ``config`` (unchanged behaviour). After a change, each
    segment uses the copy it was recorded with; a copy that cannot be read
    falls back to ``config``."""
    from ..decoder.config_loader import load_config

    changes = manifest.get("config_changes") or []
    if not changes:
        return lambda seg: config
    infos = {"config": manifest.get("config", {}), **{c["id"]: c for c in changes if c.get("id")}}
    cache: Dict[str, FrameConfig] = {}

    def pick(seg: Dict[str, Any]) -> FrameConfig:
        cid = seg.get("config", "config")
        if cid not in cache:
            load = infos.get(cid, {}).get("load")
            try:
                cache[cid] = load_config(folder / load) if load else config
            except Exception:
                _LOG.warning("Session config copy %s not readable; using the active configuration", cid,
                             exc_info=True)
                cache[cid] = config
        return cache[cid]

    return pick


def rebuild_session_event_logs(folder: Path, config: FrameConfig) -> int:
    """Regenerate every segment's event log from its raw capture (F10).

    Writes ``seg_NNNN_event_rebuilt.xlsx`` next to each original, records it
    in the manifest, and returns the number of segments rebuilt. Originals
    are never modified.
    """
    from .raw_capture import rebuild_decoded_log

    folder = Path(folder)
    manifest = read_manifest(folder)
    configs = _segment_configs(folder, manifest, config)
    rebuilt = 0
    for seg in manifest.get("segments", []):
        raw_name = seg.get("files", {}).get("raw")
        if not raw_name or not (folder / raw_name).exists():
            continue
        out = folder / f"seg_{int(seg['index']):04d}_event_rebuilt.xlsx"
        frames = rebuild_decoded_log(folder / raw_name, configs(seg), out)
        seg.setdefault("files", {})["event_rebuilt_xlsx"] = out.name
        seg["rebuilt_frames"] = frames
        rebuilt += 1
    manifest.setdefault("events", []).append(
        {"utc": iso_utc(time.time()), "text": f"Event logs rebuilt from raw capture for {rebuilt} segment(s)"}
    )
    write_manifest(folder, manifest)
    return rebuilt
