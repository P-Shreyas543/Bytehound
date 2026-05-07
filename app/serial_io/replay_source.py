"""Read raw log files and replay the captured bytes.

Two formats are accepted transparently:

* **CSV (current)** — columns ``timestamp,direction,hex`` with a header row.
* **Plain text (legacy)** — ``YYYY-MM-DD HH:MM:SS.mmm, RX|TX, AA 55 ...``
  one row per line, no header.

Only RX rows are replayed by default (TX is the host's own output).
Lines that don't parse are skipped and counted, not raised — robustness
matters more than strictness on a log file we want to inspect.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Tuple


@dataclass
class ReplayRow:
    timestamp: str
    direction: str
    raw_bytes: bytes


def parse_log_file(path: str | Path) -> Tuple[List[ReplayRow], List[str]]:
    """Return (rows, skipped_line_errors) for a raw log file."""
    rows: List[ReplayRow] = []
    errors: List[str] = []
    p = Path(path)
    with p.open("r", encoding="utf-8") as fp:
        for lineno, line in enumerate(fp, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if _is_csv_header(stripped):
                continue
            row, err = _parse_log_line(stripped)
            if err is not None:
                errors.append(f"line {lineno}: {err}")
            elif row is not None:
                rows.append(row)
    return rows, errors


def _is_csv_header(line: str) -> bool:
    """Detect the CSV header row written by :class:`RawLogger`."""
    parts = [p.strip().lower() for p in line.split(",", 2)]
    return parts == ["timestamp", "direction", "hex"]


def replay_bytes(
    rows: List[ReplayRow], *, directions: tuple[str, ...] = ("RX",)
) -> Iterator[bytes]:
    """Yield each row's raw bytes in order. By default only RX is replayed."""
    for row in rows:
        if row.direction.upper() in directions:
            yield row.raw_bytes


def _parse_log_line(line: str) -> Tuple[ReplayRow | None, str | None]:
    parts = [p.strip() for p in line.split(",", 2)]
    if len(parts) != 3:
        return None, f"expected 'timestamp, direction, hex' but got {line!r}"
    timestamp, direction, hex_str = parts
    cleaned = hex_str.replace(" ", "").replace("0x", "").replace("0X", "")
    if len(cleaned) % 2 != 0:
        return None, f"odd-length hex string: {hex_str!r}"
    try:
        raw = bytes.fromhex(cleaned)
    except ValueError as exc:
        return None, f"invalid hex {hex_str!r}: {exc}"
    return ReplayRow(timestamp=timestamp, direction=direction, raw_bytes=raw), None
