"""Decoded signal CSV log writer."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import TextIO

from ..decoder.frame_decoder import DecodedFrame, DecodedSignal


class DecodedLogger:
    COLUMNS = [
        "timestamp",
        "frame_number",
        "frame_id",
        "frame_name",
        "variable",
        "index",
        "raw_value",
        "scaled_value",
        "display_value",
        "unit",
        "group",
        "status",
        "is_calculated",
    ]

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._fp: TextIO | None = None
        self._writer: csv.DictWriter | None = None

    def __enter__(self) -> "DecodedLogger":
        self.open()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.path.exists() or self.path.stat().st_size == 0
        self._fp = self.path.open("a", encoding="utf-8", newline="")
        self._writer = csv.DictWriter(self._fp, fieldnames=self.COLUMNS)
        if new_file:
            self._writer.writeheader()

    def close(self) -> None:
        if self._fp is not None:
            self._fp.close()
            self._fp = None
            self._writer = None

    def log_frame(
        self,
        frame_number: int,
        decoded: DecodedFrame,
        timestamp: datetime | None = None,
    ) -> None:
        for signal in [*decoded.signals, *decoded.calculations]:
            self.log_signal(frame_number, signal, timestamp)

    def log_signal(
        self,
        frame_number: int,
        signal: DecodedSignal,
        timestamp: datetime | None = None,
    ) -> None:
        if self._writer is None:
            self.open()
        assert self._writer is not None
        ts = (timestamp or datetime.now()).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self._writer.writerow(
            {
                "timestamp": ts,
                "frame_number": frame_number,
                "frame_id": f"0x{signal.frame_id:04X}",
                "frame_name": signal.frame_name,
                "variable": signal.signal_name,
                "index": "" if signal.index is None else signal.index,
                "raw_value": "" if signal.raw_value is None else signal.raw_value,
                "scaled_value": "" if signal.scaled_value is None else signal.scaled_value,
                "display_value": signal.display_value,
                "unit": signal.unit,
                "group": signal.group,
                "status": signal.status,
                "is_calculated": signal.is_calculated,
            }
        )
        if self._fp is not None:
            self._fp.flush()
