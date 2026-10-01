"""High-performance asynchronous CSV telemetry logger."""

from __future__ import annotations

import csv
import logging
import queue
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from ..comm.packet_codec import (
    BoardParamsTelemetry,
    CellDataTelemetry,
    FaultSoCTelemetry,
)
from ..config.cycler_config import DEFAULT_LOG_DIR

logger = logging.getLogger("SingleCellCycler.AsyncLogger")

# Windows thread priority levels (SetThreadPriority)
_WIN_THREAD_PRIORITY = {"normal": 0, "above_normal": 1, "highest": 2, "time_critical": 15}


def _set_current_thread_priority(level: str) -> None:
    """Raise the calling thread's scheduling priority (Windows; elsewhere the default is kept)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentThread.restype = ctypes.c_void_p
        kernel32.SetThreadPriority.argtypes = [ctypes.c_void_p, ctypes.c_int]
        if not kernel32.SetThreadPriority(kernel32.GetCurrentThread(), _WIN_THREAD_PRIORITY.get(level, 1)):
            logger.warning(f"Could not set telemetry sampler thread priority to '{level}'")
    except Exception as exc:
        logger.warning(f"Could not set telemetry sampler thread priority: {exc}")


def _begin_fine_timer() -> bool:
    """Ask Windows for 1 ms timer resolution (default ~15.6 ms is too coarse for a 100 ms grid)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return ctypes.windll.winmm.timeBeginPeriod(1) == 0
    except Exception:
        return False


def _end_fine_timer() -> None:
    try:
        import ctypes
        ctypes.windll.winmm.timeEndPeriod(1)
    except Exception:
        pass


class AsyncTelemetryLogger:
    """Streams live telemetry records to CSV in a dedicated background thread."""

    MAX_FILE_BYTES = 256 * 1024 * 1024
    MIN_FREE_BYTES = 1 * 1024 * 1024 * 1024
    FIELDNAMES = [
        "timestamp_iso", "timestamp_epoch_s", "elapsed_s", "cycle_index", "step_index",
        "step_name", "step_type", "voltage_v", "current_a", "power_w",
        "terminal_temp_c", "body_temp_c", "ambient_temp_c", "charge_bus_v", "load_bus_v",
        "soc_ocv_pct", "soc_cc_pct", "soc_ekf_pct", "vr1_v", "vr2_v",
        "p_diag_0", "p_diag_1", "p_diag_2",
        "fault_byte", "step_capacity_mah", "step_energy_mwh",
        "total_charge_mah", "total_discharge_mah",
    ]

    SOC_FIELDS = ("soc_ocv_pct", "soc_cc_pct", "soc_ekf_pct")

    def __init__(
        self,
        log_dir: str | Path | None = None,
        interval_s: float = 0.1,
        thread_priority: str = "above_normal",
        soc_decimals: int = 2,
    ):
        # Fixed-rate sampling: while a session is open, a dedicated thread asks
        # snapshot_provider for the current record every interval_s on an absolute clock,
        # so the row cadence does not depend on telemetry arrival or on how busy the UI is.
        self.interval_s = float(interval_s)
        self.thread_priority = thread_priority
        self.soc_decimals = int(soc_decimals)
        self.snapshot_provider: Optional[Callable[[], Optional[dict]]] = None
        self._sampler_thread: Optional[threading.Thread] = None
        self._sampler_stop = threading.Event()
        self.rows_sampled = 0
        self.slots_missed = 0

        self.log_dir = Path(log_dir) if log_dir is not None else DEFAULT_LOG_DIR
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.log_dir = Path.home() / ".bytehound" / "cycler" / "logs"
            self.log_dir.mkdir(parents=True, exist_ok=True)

        self._queue: queue.Queue = queue.Queue(maxsize=10000)
        self._thread: Optional[threading.Thread] = None
        self._is_running = False
        self._file = None
        self._csv_writer = None
        self.current_log_path: Optional[Path] = None
        self._session_prefix = "cycler_run"
        self._part_index = 0
        self._disk_warning_emitted = False

    def start_session(self, session_prefix: str = "cycler_run") -> Path:
        """Start a new CSV recording session."""
        self.stop_session()

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._session_prefix = session_prefix
        self._part_index = 0
        self._disk_warning_emitted = False
        self.current_log_path = self.log_dir / f"{session_prefix}_{timestamp_str}.csv"
        self._open_file(self.current_log_path, "w")

        self._is_running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()
        self._start_sampler()
        logger.info(f"Started logging to {self.current_log_path}")
        return self.current_log_path

    def resume_session(self, log_path: str | Path) -> Path:
        """Resume recording into an existing CSV session file (IMP-08)."""
        self.stop_session()
        p = Path(log_path)
        self.current_log_path = p
        file_exists = p.exists() and p.stat().st_size > 0
        self._open_file(p, "a", write_header=not file_exists)

        self._is_running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()
        self._start_sampler()
        logger.info(f"Resumed logging to {self.current_log_path}")
        return self.current_log_path

    def log_record(self, record: dict) -> None:
        """Enqueue record for background write."""
        if not self._is_running:
            return
        # SoC columns always carry the configured number of decimals (e.g. 99.90, not 99.9)
        for key in self.SOC_FIELDS:
            value = record.get(key)
            if isinstance(value, (int, float)):
                record[key] = f"{value:.{self.soc_decimals}f}"
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            # Drop record rather than freezing UI
            pass

    # ------------------------------------------------------------------ #
    # Fixed-rate sampler                                                   #
    # ------------------------------------------------------------------ #

    def _start_sampler(self) -> None:
        if self.snapshot_provider is None:
            return
        self.rows_sampled = 0
        self.slots_missed = 0
        self._sampler_stop.clear()
        self._sampler_thread = threading.Thread(target=self._sampler_loop, name="TelemetrySampler", daemon=True)
        self._sampler_thread.start()

    def _stop_sampler(self) -> None:
        self._sampler_stop.set()
        thread = self._sampler_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        self._sampler_thread = None

    def _sampler_loop(self) -> None:
        """One record per interval on an absolute schedule: slot k is due at t0 + k * interval,
        so a late slot never delays the following ones (no drift)."""
        period = self.interval_s
        timer_period_set = _begin_fine_timer()
        _set_current_thread_priority(self.thread_priority)
        provider_failed = False
        try:
            t0 = time.perf_counter()
            slot = 0
            elapsed_base: Optional[float] = None
            while not self._sampler_stop.is_set():
                delay = t0 + slot * period - time.perf_counter()
                if delay > 0:
                    if self._sampler_stop.wait(delay):
                        break
                elif delay < -period:
                    # More than a whole interval late (PC suspended, process frozen): the missed
                    # slots cannot be recovered, continue on the same grid from the current slot
                    current = int((time.perf_counter() - t0) / period)
                    self.slots_missed += current - slot
                    slot = current
                try:
                    record = self.snapshot_provider() if self.snapshot_provider else None
                    provider_failed = False
                except Exception as exc:
                    record = None
                    if not provider_failed:      # log the first failure of a streak, not 10 per second
                        logger.error(f"Telemetry snapshot failed: {exc}", exc_info=True)
                    provider_failed = True
                if record is not None:
                    # elapsed_s is written on the sampling grid (exact multiples of the interval).
                    # The provider's own clock is only read once, to anchor the grid: Windows'
                    # monotonic clock ticks every ~16 ms, which showed up as 0.31, 0.41, 0.52 ...
                    # The timestamp columns keep the real sampling instant.
                    if isinstance(record.get("elapsed_s"), (int, float)):
                        if elapsed_base is None:
                            elapsed_base = (round(record["elapsed_s"] / period) - slot) * period
                        record["elapsed_s"] = round(elapsed_base + slot * period, 3)
                    self.log_record(record)
                    self.rows_sampled += 1
                slot += 1
        finally:
            if timer_period_set:
                _end_fine_timer()

    def stop_session(self) -> None:
        """Flush queue and close file."""
        if not self._is_running:
            return
        self._stop_sampler()
        self._is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

        # Drain remaining records
        if self._file and self._csv_writer:
            while not self._queue.empty():
                try:
                    rec = self._queue.get_nowait()
                    self._csv_writer.writerow(rec)
                except queue.Empty:
                    break
            try:
                self._file.flush()
                self._file.close()
            except Exception:
                pass
        self._file = None
        self._csv_writer = None
        logger.info("Stopped telemetry logger")

    def _worker_loop(self) -> None:
        batch = []
        last_flush = time.time()

        while self._is_running or not self._queue.empty():
            try:
                rec = self._queue.get(timeout=0.1)
                batch.append(rec)
            except queue.Empty:
                pass

            now = time.time()
            if batch and (len(batch) >= 20 or (now - last_flush) >= 0.5):
                self._write_batch(batch)
                batch.clear()
                last_flush = now

        # Session ending: rows collected since the last flush must not be lost
        if batch:
            self._write_batch(batch)

    def _write_batch(self, batch: list) -> None:
        if self._csv_writer and self._file:
            try:
                if self._disk_space_available():
                    self._csv_writer.writerows(batch)
                    self._file.flush()
                    self._rotate_if_needed()
            except Exception as exc:
                logger.error(f"Error writing CSV log: {exc}")

    def _open_file(self, path: Path, mode: str, write_header: bool = True) -> None:
        self._file = open(path, mode, newline="", encoding="utf-8")
        self.current_log_path = path
        self._csv_writer = csv.DictWriter(self._file, fieldnames=self.FIELDNAMES)
        if write_header:
            self._csv_writer.writeheader()
            self._file.flush()

    def _disk_space_available(self) -> bool:
        try:
            free_bytes = shutil.disk_usage(self.log_dir).free
            if free_bytes < self.MIN_FREE_BYTES:
                if not self._disk_warning_emitted:
                    logger.critical("Telemetry logging paused: less than 1 GB of free disk space remains.")
                    self._disk_warning_emitted = True
                return False
            return True
        except OSError as exc:
            logger.error(f"Could not check free disk space: {exc}")
            return True

    def _rotate_if_needed(self) -> None:
        if not self._file or not self.current_log_path:
            return
        if self.current_log_path.stat().st_size < self.MAX_FILE_BYTES:
            return
        self._file.close()
        self._part_index += 1
        path = self.current_log_path.with_name(
            f"{self.current_log_path.stem}_part{self._part_index:03d}.csv"
        )
        self._open_file(path, "w")
        logger.info(f"Rotated telemetry log to {path}")
