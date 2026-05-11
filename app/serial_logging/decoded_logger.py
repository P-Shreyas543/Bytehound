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
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, TextIO, Tuple

from ..decoder.frame_decoder import DecodedFrame
from ..decoder.types import FrameConfig

_FLUSH_INTERVAL = 0.5  # seconds between explicit OS-level flushes


def _format_number(value: float | int) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _signal_label(name: str, unit: str) -> str:
    return f"{name} ({unit})" if unit else name


class DecodedLogger:
    def __init__(self, path: str | Path, config: FrameConfig) -> None:
        self.path = Path(path)
        self._config = config
        self._fp: TextIO | None = None
        self._writer: csv.DictWriter | None = None
        self._last_flush: float = 0.0
        self._warned_collisions: set[str] = set()
        self._columns, self._column_by_key = self._build_columns()

    def __enter__(self) -> "DecodedLogger":
        self.open()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.path.exists() or self.path.stat().st_size == 0

        # Same header-match check as RawLogger — refuse to append rows to a
        # file whose header was written by a different schema version.
        if not new_file:
            with self.path.open("r", encoding="utf-8", newline="") as fp:
                reader = csv.reader(fp)
                existing = next(reader, [])
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
            self._writer.writeheader()

    def close(self) -> None:
        if self._fp is not None:
            self._fp.flush()  # guaranteed final flush before close
            self._fp.close()
            self._fp = None
            self._writer = None

    def log_frame(
        self,
        decoded: DecodedFrame,
        elapsed_ms: int,
        timestamp: datetime | None = None,
    ) -> None:
        if self._writer is None:
            self.open()
        assert self._writer is not None and self._fp is not None
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
        if now - self._last_flush >= _FLUSH_INTERVAL:
            self._fp.flush()
            self._last_flush = now

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
            print(
                f"DecodedLogger: duplicate column label {base_label!r}; "
                f"using {label!r} for frame 0x{frame_id:04X}",
                file=sys.stderr,
            )
            self._warned_collisions.add(base_label)
        if label in used_labels:
            label = f"{prefix}[0x{frame_id:04X}].{base_label}"
        used_labels.add(label)
        return label
