"""High-performance asynchronous CSV telemetry logger."""

from __future__ import annotations

import csv
import logging
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..comm.packet_codec import (
    BoardParamsTelemetry,
    CellDataTelemetry,
    FaultSoCTelemetry,
)

logger = logging.getLogger("SingleCellCycler.AsyncLogger")


class AsyncTelemetryLogger:
    """Streams live telemetry records to CSV in a dedicated background thread."""

    def __init__(self, log_dir: str | Path = "single_cell_cycler/logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self._queue: queue.Queue = queue.Queue(maxsize=10000)
        self._thread: Optional[threading.Thread] = None
        self._is_running = False
        self._file = None
        self._csv_writer = None
        self.current_log_path: Optional[Path] = None

    def start_session(self, session_prefix: str = "cycler_run") -> Path:
        """Start a new CSV recording session."""
        self.stop_session()

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_log_path = self.log_dir / f"{session_prefix}_{timestamp_str}.csv"

        self._file = open(self.current_log_path, "w", newline="", encoding="utf-8")
        fieldnames = [
            "timestamp_iso",
            "epoch_s",
            "cycle_index",
            "step_index",
            "step_name",
            "step_type",
            "voltage_v",
            "current_a",
            "power_w",
            "terminal_temp_c",
            "body_temp_c",
            "ambient_temp_c",
            "charge_bus_v",
            "load_bus_v",
            "soc_ocv_pct",
            "soc_cc_pct",
            "fault_byte",
            "step_capacity_mah",
            "step_energy_mwh",
            "total_charge_mah",
            "total_discharge_mah",
        ]
        self._csv_writer = csv.DictWriter(self._file, fieldnames=fieldnames)
        self._csv_writer.writeheader()
        self._file.flush()

        self._is_running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()
        logger.info(f"Started logging to {self.current_log_path}")
        return self.current_log_path

    def resume_session(self, log_path: str | Path) -> Path:
        """Resume recording into an existing CSV session file (IMP-08)."""
        self.stop_session()
        p = Path(log_path)
        self.current_log_path = p
        file_exists = p.exists() and p.stat().st_size > 0
        self._file = open(self.current_log_path, "a", newline="", encoding="utf-8")
        fieldnames = [
            "timestamp_iso",
            "epoch_s",
            "cycle_index",
            "step_index",
            "step_name",
            "step_type",
            "voltage_v",
            "current_a",
            "power_w",
            "terminal_temp_c",
            "body_temp_c",
            "ambient_temp_c",
            "charge_bus_v",
            "load_bus_v",
            "soc_ocv_pct",
            "soc_cc_pct",
            "fault_byte",
            "step_capacity_mah",
            "step_energy_mwh",
            "total_charge_mah",
            "total_discharge_mah",
        ]
        self._csv_writer = csv.DictWriter(self._file, fieldnames=fieldnames)
        if not file_exists:
            self._csv_writer.writeheader()
            self._file.flush()

        self._is_running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()
        logger.info(f"Resumed logging to {self.current_log_path}")
        return self.current_log_path

    def log_record(self, record: dict) -> None:
        """Enqueue record for background write."""
        if not self._is_running:
            return
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            # Drop record rather than freezing UI
            pass

    def stop_session(self) -> None:
        """Flush queue and close file."""
        if not self._is_running:
            return
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
                if self._csv_writer and self._file:
                    try:
                        self._csv_writer.writerows(batch)
                        self._file.flush()
                    except Exception as exc:
                        logger.error(f"Error writing CSV log: {exc}")
                batch.clear()
                last_flush = now
