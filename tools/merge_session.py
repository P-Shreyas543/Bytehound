"""Merge a logging session's hourly segments into one workbook or one per day.

A session is recorded as hourly segments (``seg_NNNN_event.csv/.xlsx``) so
no single file grows without bound during a long run. For analysis it is
easier to have the whole session — or one file per calendar day — in a
single workbook. This tool joins the segments' CSV files in order and
compiles them with the same code the application uses for each segment
(``Metadata`` sheet + ``Data``; ``Data_2`` … when a sheet would pass
Excel's 1,048,576-row limit). The session folder is never modified.

  python tools/merge_session.py <session folder>                    # one workbook
  python tools/merge_session.py <session folder> --split day        # one per day
  python tools/merge_session.py <session folder> --kind fixed       # fixed-step log
  python tools/merge_session.py <session folder> --csv              # also keep the merged CSV

Output goes to ``--out`` (default ``<session folder>/merged``), named
``<session>_<kind>[_<YYYY-MM-DD>][_partN].xlsx``. Rows are split by day on
their local timestamp. If the configuration changed during the session
(different columns), a new part starts at that segment instead of mixing
columns. Recorded gaps (unplugs, configuration changes) are listed in each
workbook's Metadata sheet.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.serial_logging.decoded_logger import compile_csv_to_xlsx  # noqa: E402
from app.serial_logging.session import MANIFEST_NAME, read_manifest  # noqa: E402


class _Part:
    """One output file being written: its temp CSV and what it covers."""

    def __init__(self, path: Path, header: List[str]) -> None:
        self.csv_path = path
        self.header = header
        self.fp = path.open("w", encoding="utf-8", newline="")
        self.writer = csv.writer(self.fp)
        self.writer.writerow(header)
        self.rows = 0
        self.segments: List[int] = []
        self.first_time: Optional[str] = None
        self.last_time: Optional[str] = None

    def add(self, row: List[str], seg_index: int, time_text: str) -> None:
        self.writer.writerow(row)
        self.rows += 1
        if not self.segments or self.segments[-1] != seg_index:
            self.segments.append(seg_index)
        self.first_time = self.first_time or time_text
        self.last_time = time_text

    def close(self) -> None:
        self.fp.close()


def _time_column(header: List[str]) -> int:
    for name in ("time_local", "time_utc"):
        if name in header:
            return header.index(name)
    raise SystemExit("segment CSV has no time_local / time_utc column")


def merge(folder: Path, kind: str = "event", split: str = "none", out: Optional[Path] = None,
          keep_csv: bool = False) -> List[Dict[str, object]]:
    """Merge ``folder``'s segments; returns one summary dict per written file."""
    folder = Path(folder)
    if not (folder / MANIFEST_NAME).exists():
        raise SystemExit(f"{folder} is not a session folder (no {MANIFEST_NAME})")
    manifest = read_manifest(folder)
    if manifest.get("status") == "recording":
        raise SystemExit("this session is still recording — stop logging first")
    out = Path(out) if out else folder / "merged"
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{folder.name}_{kind}"

    segments = sorted(manifest.get("segments", []), key=lambda s: int(s["index"]))
    sources = [(int(s["index"]), folder / s["files"][f"{kind}_csv"])
               for s in segments if s.get("files", {}).get(f"{kind}_csv")]
    missing = [str(p.name) for _i, p in sources if not p.exists()]
    if missing:
        raise SystemExit(f"segment files missing: {', '.join(missing)}")
    if not sources:
        raise SystemExit(f"no {kind} log in this session (was {kind} logging enabled?)")

    parts: List[_Part] = []
    part: Optional[_Part] = None
    config_part = 1                       # bumps when the columns change
    current_day: Optional[str] = None

    def start(header: List[str], day: Optional[str]) -> _Part:
        label = stem + (f"_{day}" if day else "") + (f"_part{config_part}" if config_part > 1 else "")
        p = _Part(out / f"{label}.csv.partial", header)
        parts.append(p)
        return p

    for seg_index, path in sources:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header is None:
                continue
            ti = _time_column(header)
            if part is not None and header != part.header:
                config_part += 1          # configuration changed: never mix columns
                part.close()
                part = None
            for row in reader:
                if not row:
                    continue
                day = row[ti][:10] if split == "day" else None
                if part is None or (split == "day" and day != current_day):
                    if part is not None:
                        part.close()
                    part = start(header, day)
                    current_day = day
                part.add(row, seg_index, row[ti])
    if part is not None:
        part.close()

    gaps = manifest.get("gaps", [])
    written: List[Dict[str, object]] = []
    for p in parts:
        target = p.csv_path.with_name(p.csv_path.name.replace(".csv.partial", ".xlsx"))
        meta = {
            "session": folder.name,
            "log": kind,
            "app_version": manifest.get("app_version", ""),
            "session_started_utc": manifest.get("started_utc", ""),
            "session_ended_utc": manifest.get("ended_utc", ""),
            "config_source": manifest.get("config", {}).get("source", ""),
            "config_fingerprint": manifest.get("config", {}).get("fingerprint", ""),
            "rows": p.rows,
            "first_row_time": p.first_time or "",
            "last_row_time": p.last_time or "",
            "segments": f"{p.segments[0]}..{p.segments[-1]} ({len(p.segments)})" if p.segments else "",
            "recorded_gaps": "; ".join(
                f"{g.get('start_utc')} → {g.get('end_utc')} ({g.get('reason', '')})" for g in gaps) or "none",
            "merged_by": "tools/merge_session.py",
        }
        exc = compile_csv_to_xlsx(p.csv_path, meta, target)
        if exc is not None:
            raise SystemExit(f"could not write {target.name}: {exc} (merged CSV kept: {p.csv_path.name})")
        csv_target = None
        if keep_csv:
            csv_target = p.csv_path.with_name(p.csv_path.name.replace(".csv.partial", ".csv"))
            p.csv_path.replace(csv_target)
        else:
            p.csv_path.unlink()
        written.append({"xlsx": target, "csv": csv_target, "rows": p.rows,
                        "first": p.first_time, "last": p.last_time, "segments": p.segments})
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", type=Path, help="session folder (contains session.json)")
    ap.add_argument("--kind", choices=("event", "fixed"), default="event")
    ap.add_argument("--split", choices=("none", "day"), default="none",
                    help="none = one workbook; day = one workbook per calendar day (local time)")
    ap.add_argument("--out", type=Path, default=None, help="output folder (default: <session>/merged)")
    ap.add_argument("--csv", action="store_true", help="also keep the merged CSV next to each workbook")
    args = ap.parse_args()
    for w in merge(args.session, args.kind, args.split, args.out, args.csv):
        size = w["xlsx"].stat().st_size / 1e6
        print(f"{w['xlsx']}  rows={w['rows']}  {w['first']} .. {w['last']}  "
              f"segments {w['segments'][0]}..{w['segments'][-1]}  {size:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
