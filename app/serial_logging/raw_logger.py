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
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping, TextIO

_FLUSH_INTERVAL = 0.5  # seconds between explicit OS-level flushes
_LOG = logging.getLogger("bytehound.serial_logging.raw")

ErrorCallback = Callable[[str], None]


class RawLogger:
    COLUMNS = ["timestamp", "direction", "hex", "delta_t_ms"]

    def __init__(
        self,
        path: str | Path,
        *,
        flush_interval: float = _FLUSH_INTERVAL,
        metadata: Mapping[str, str] | None = None,
        on_error: ErrorCallback | None = None,
    ) -> None:
        self.path = Path(path)
        self._fp: TextIO | None = None
        self._writer: "csv._writer | None" = None
        self._last_flush: float = 0.0
        self._flush_interval = float(flush_interval)
        self._metadata = dict(metadata) if metadata else {}
        self._on_error = on_error
        self._disabled = False

    def __enter__(self) -> "RawLogger":
        self.open()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def open(self) -> None:
        if self._disabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.path.exists() or self.path.stat().st_size == 0

        # Refuse to append to an existing file whose header does not match
        # the current schema. Silently writing rows with a different column
        # count corrupts the CSV (header says 3 cols, data has 4) and breaks
        # pandas, Excel, and the app's own replay parser.
        if not new_file:
            existing = self._read_existing_header()
            if existing != self.COLUMNS:
                raise ValueError(
                    f"Cannot append to {self.path.name}: existing header "
                    f"{existing} does not match expected {self.COLUMNS}. "
                    f"Choose a new filename or delete the old log."
                )

        self._fp = self.path.open("a", encoding="utf-8", newline="")
        self._writer = csv.writer(self._fp)
        self._last_flush = time.monotonic()
        if new_file:
            self._write_metadata()
            self._writer.writerow(self.COLUMNS)

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

    def log(self, direction: str, raw: bytes, timestamp: datetime | None = None, delta_t_ms: float = 0.0) -> None:
        if self._disabled:
            return
        try:
            if self._writer is None:
                self.open()
            if self._writer is None or self._fp is None:
                return
            ts = (timestamp or datetime.now()).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self._writer.writerow([ts, direction.upper(), raw.hex(" ").upper(), f"{delta_t_ms:.1f}"])
            # Periodic flush — avoids an OS syscall on every single frame.
            now = time.monotonic()
            if self._flush_interval <= 0 or now - self._last_flush >= self._flush_interval:
                self._fp.flush()
                self._last_flush = now
        except Exception as exc:
            self._handle_error("write", exc)

    def _read_existing_header(self) -> list[str]:
        with self.path.open("r", encoding="utf-8") as fp:
            for line in fp:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                return [c.strip() for c in stripped.split(",")] if stripped else []
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
        _LOG.error("RawLogger %s error", context, exc_info=True)
        if self._on_error is not None:
            self._on_error(f"Raw log {context} error for {self.path.name}: {exc}")
