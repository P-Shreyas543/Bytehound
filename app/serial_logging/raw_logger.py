"""Raw packet log writer (CSV).

Writes a CSV with columns ``timestamp,direction,hex``. The hex field
keeps space-separated bytes for human readability (e.g. ``AA 55 00 10``).
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import TextIO


class RawLogger:
    COLUMNS = ["timestamp", "direction", "hex", "delta_t_ms"]

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._fp: TextIO | None = None
        self._writer: "csv._writer | None" = None

    def __enter__(self) -> "RawLogger":
        self.open()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.path.exists() or self.path.stat().st_size == 0
        self._fp = self.path.open("a", encoding="utf-8", newline="")
        self._writer = csv.writer(self._fp)
        if new_file:
            self._writer.writerow(self.COLUMNS)

    def close(self) -> None:
        if self._fp is not None:
            self._fp.close()
            self._fp = None
            self._writer = None

    def log(self, direction: str, raw: bytes, timestamp: datetime | None = None, delta_t_ms: float = 0.0) -> None:
        if self._writer is None:
            self.open()
        assert self._writer is not None and self._fp is not None
        ts = (timestamp or datetime.now()).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self._writer.writerow([ts, direction.upper(), raw.hex(" ").upper(), f"{delta_t_ms:.1f}"])
        self._fp.flush()
