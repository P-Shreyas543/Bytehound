"""Raw packet log writer (CSV).

Writes a CSV with columns ``timestamp,direction,hex``. The hex field
keeps space-separated bytes for human readability (e.g. ``AA 55 00 10``).

Buffered I/O
------------
``log()`` writes to the file object's in-memory buffer but only calls the
OS-level ``flush()`` every ``FLUSH_INTERVAL`` seconds (default 0.5 s) to
avoid per-frame syscall overhead at high baud rates. A final ``flush()`` is
guaranteed when the logger is closed.
"""

from __future__ import annotations

import csv
import time
from datetime import datetime
from pathlib import Path
from typing import TextIO

_FLUSH_INTERVAL = 0.5  # seconds between explicit OS-level flushes


class RawLogger:
    COLUMNS = ["timestamp", "direction", "hex", "delta_t_ms"]

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._fp: TextIO | None = None
        self._writer: "csv._writer | None" = None
        self._last_flush: float = 0.0

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
        self._last_flush = time.monotonic()
        if new_file:
            self._writer.writerow(self.COLUMNS)

    def close(self) -> None:
        if self._fp is not None:
            self._fp.flush()  # guaranteed final flush before close
            self._fp.close()
            self._fp = None
            self._writer = None

    def log(self, direction: str, raw: bytes, timestamp: datetime | None = None, delta_t_ms: float = 0.0) -> None:
        if self._writer is None:
            self.open()
        assert self._writer is not None and self._fp is not None
        ts = (timestamp or datetime.now()).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self._writer.writerow([ts, direction.upper(), raw.hex(" ").upper(), f"{delta_t_ms:.1f}"])
        # Periodic flush — avoids an OS syscall on every single frame.
        now = time.monotonic()
        if now - self._last_flush >= _FLUSH_INTERVAL:
            self._fp.flush()
            self._last_flush = now
