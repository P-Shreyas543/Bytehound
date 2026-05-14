"""Decoded signal CSV log writer.

Buffered I/O
------------
``log_frame()`` writes to the file object's in-memory buffer but only
calls the OS-level ``flush()`` every ``FLUSH_INTERVAL`` seconds (default
0.5 s) to avoid per-frame syscall overhead at high baud rates. A final
``flush()`` is guaranteed when the logger is closed.
"""

from __future__ import annotations

import csv
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Mapping, TextIO, Tuple

from ..decoder.frame_decoder import DecodedFrame
from ..decoder.types import FrameConfig

_FLUSH_INTERVAL = 0.5  # seconds between explicit OS-level flushes
_LOG = logging.getLogger("bytehound.serial_logging.decoded")

ErrorCallback = Callable[[str], None]


def _format_number(value: float | int) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _signal_label(name: str, unit: str) -> str:
    return f"{name} ({unit})" if unit else name


class DecodedLogger:
    def __init__(
        self,
        path: str | Path,
        config: FrameConfig,
        *,
        flush_interval: float = _FLUSH_INTERVAL,
        metadata: Mapping[str, str] | None = None,
        on_error: ErrorCallback | None = None,
    ) -> None:
        self.path = Path(path)
        self._config = config
        self._fp: TextIO | None = None
        self._writer: csv.DictWriter | None = None
        self._last_flush: float = 0.0
        self._flush_interval = float(flush_interval)
        self._metadata = dict(metadata) if metadata else {}
        self._on_error = on_error
        self._disabled = False
        self._warned_collisions: set[str] = set()
        self._columns, self._column_by_key = self._build_columns()

    def __enter__(self) -> "DecodedLogger":
        self.open()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def open(self) -> None:
        if self._disabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.path.exists() or self.path.stat().st_size == 0

        # Same header-match check as RawLogger — refuse to append rows to a
        # file whose header was written by a different schema version.
        if not new_file:
            existing = self._read_existing_header()
            if existing != self._columns:
                raise ValueError(
                    f"Cannot append to {self.path.name}: existing header "
                    f"{existing} does not match expected {self._columns}. "
                    f"Choose a new filename or delete the old log."
                )

        self._fp = self.path.open("a", encoding="utf-8", newline="")
        self._writer = csv.DictWriter(self._fp, fieldnames=self._columns)
        self._last_flush = time.monotonic()
        if new_file:
            self._write_metadata()
            self._writer.writeheader()

    def close(self) -> None:
        if self._fp is not None:
            try:
                self._fp.flush()  # guaranteed final flush before close
            except Exception:
                pass
            try:
                self._fp.close()
            except Exception:
                pass
            self._fp = None
            self._writer = None

    def set_flush_interval(self, seconds: float) -> None:
        try:
            interval = float(seconds)
        except (TypeError, ValueError):
            interval = _FLUSH_INTERVAL
        if interval < 0:
            interval = 0.0
        self._flush_interval = interval

    def log_frame(
        self,
        decoded: DecodedFrame,
        elapsed_ms: int,
        timestamp: datetime | None = None,
    ) -> None:
        if self._disabled:
            return
        try:
            if self._writer is None:
                self.open()
            if self._writer is None or self._fp is None:
                return
            ts = (timestamp or datetime.now()).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            row = {column: "" for column in self._columns}
            row["timestamp"] = ts
            row["elapsed_ms"] = elapsed_ms

            for signal in [*decoded.signals, *decoded.calculations]:
                if signal.scaled_value is None:
                    continue
                column = self._column_by_key.get((signal.frame_id, signal.signal_name))
                if column is None:
                    continue
                row[column] = _format_number(signal.scaled_value)

            self._writer.writerow(row)
            # Periodic flush — avoids an OS syscall after every single signal row.
            now = time.monotonic()
            if self._flush_interval <= 0 or now - self._last_flush >= self._flush_interval:
                self._fp.flush()
                self._last_flush = now
        except Exception as exc:
            self._handle_error("write", exc)

    def _build_columns(self) -> Tuple[List[str], Dict[Tuple[int, str], str]]:
        columns = ["timestamp", "elapsed_ms"]
        column_by_key: Dict[Tuple[int, str], str] = {}
        used_labels = set(columns)

        for spec in self._config.all_signals:
            base_label = _signal_label(spec.signal_name, spec.unit)
            label = self._resolve_label(base_label, spec.frame_name, spec.frame_id, used_labels)
            columns.append(label)
            column_by_key[(spec.frame_id, spec.signal_name)] = label

        frames_by_group: Dict[str, List[int]] = {}
        for spec in self._config.all_signals:
            if not spec.group:
                continue
            frames = frames_by_group.setdefault(spec.group, [])
            if spec.frame_id not in frames:
                frames.append(spec.frame_id)

        for calc in self._config.calc_groups:
            if calc.frame_id is not None:
                frame_ids = [calc.frame_id]
            else:
                frame_ids = frames_by_group.get(calc.group, [])
            if not frame_ids:
                continue
            for frame_id in frame_ids:
                frame_name = self._config.frame_names.get(frame_id, f"0x{frame_id:04X}")
                signal_name = f"{calc.group} {calc.stat}"
                base_label = _signal_label(signal_name, calc.unit)
                label = self._resolve_label(base_label, frame_name, frame_id, used_labels)
                columns.append(label)
                column_by_key[(frame_id, signal_name)] = label

        return columns, column_by_key

    def _resolve_label(
        self,
        base_label: str,
        frame_name: str,
        frame_id: int,
        used_labels: set[str],
    ) -> str:
        if base_label not in used_labels:
            used_labels.add(base_label)
            return base_label

        prefix = frame_name or f"0x{frame_id:04X}"
        label = f"{prefix}.{base_label}"
        if base_label not in self._warned_collisions:
            _LOG.warning(
                "DecodedLogger duplicate column label %r; using %r for frame 0x%04X",
                base_label,
                label,
                frame_id,
            )
            self._warned_collisions.add(base_label)
        if label in used_labels:
            label = f"{prefix}[0x{frame_id:04X}].{base_label}"
        used_labels.add(label)
        return label

    def _read_existing_header(self) -> list[str]:
        with self.path.open("r", encoding="utf-8", newline="") as fp:
            for line in fp:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                reader = csv.reader([line])
                return next(reader, [])
        return []

    def _write_metadata(self) -> None:
        if not self._metadata or self._fp is None:
            return
        for key in sorted(self._metadata):
            value = str(self._metadata[key]).replace("\n", " ").strip()
            self._fp.write(f"# {key}: {value}\n")

    def _handle_error(self, context: str, exc: Exception) -> None:
        if self._disabled:
            return
        self._disabled = True
        self.close()
        _LOG.error("DecodedLogger %s error", context, exc_info=True)
        if self._on_error is not None:
            self._on_error(f"Decoded log {context} error for {self.path.name}: {exc}")
