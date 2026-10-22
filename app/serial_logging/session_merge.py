"""Merge a logging session's hourly segments into one workbook or one per day.

A session is recorded as hourly segments so no file grows without bound;
for analysis one workbook — or one per calendar day — is easier. ``merge``
joins the segments' CSV files in order and compiles them with the same
compiler the application uses for each segment (``Metadata`` + ``Data``;
``Data_2`` … past Excel's 1,048,576-row limit). The session folder is never
modified; output goes to ``<session>/merged`` unless told otherwise.

* ``split="day"`` cuts at local midnight on each row's own timestamp.
* A configuration change during the session (different columns) starts a
  new part instead of mixing columns.
* Recorded gaps are listed in each workbook's Metadata sheet.
* ``progress(phase, done, total)`` reports rows; ``cancel()`` is honoured
  while joining and while writing; a cancelled or failed merge removes
  everything it wrote.

Used by Tools → Merge Session… (in a child process, ``merge_job``) and by
``tools/merge_session.py``.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .decoded_logger import CompileCancelled, compile_csv_to_xlsx
from .session import MANIFEST_NAME, read_manifest

Progress = Callable[[str, int, int], None]


class MergeError(Exception):
    """The session cannot be merged (reason in the message)."""


class MergeCancelled(Exception):
    """The merge was cancelled; nothing it wrote was kept."""


def session_summary(folder: Path) -> Dict[str, object]:
    """What a session folder offers for merging: logs present, rows, status.
    Raises MergeError if ``folder`` is not a session."""
    folder = Path(folder)
    if not (folder / MANIFEST_NAME).exists():
        raise MergeError(f"{folder} is not a session folder (no {MANIFEST_NAME}).")
    try:
        manifest = read_manifest(folder)
    except (OSError, ValueError) as exc:
        raise MergeError(f"{MANIFEST_NAME} cannot be read: {exc}") from exc
    segments = manifest.get("segments", [])
    kinds = {}
    for kind in ("event", "fixed"):
        segs = [s for s in segments if s.get("files", {}).get(f"{kind}_csv")]
        if segs:
            kinds[kind] = sum(int((s.get("rows") or {}).get(kind, 0) or 0) for s in segs)
    return {
        "status": manifest.get("status", ""),
        "segments": len(segments),
        "started_utc": manifest.get("started_utc", ""),
        "ended_utc": manifest.get("ended_utc", ""),
        "rows": kinds,
        "gaps": len(manifest.get("gaps", [])),
        "config_changes": len(manifest.get("config_changes", []) or []),
    }


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
        if not self.fp.closed:
            self.fp.close()


def _time_column(header: List[str]) -> int:
    for name in ("time_local", "time_utc"):
        if name in header:
            return header.index(name)
    raise MergeError("the segment logs have no time_local / time_utc column")


def merge(folder: Path, kind: str = "event", split: str = "none", out: Optional[Path] = None,
          keep_csv: bool = False, progress: Optional[Progress] = None,
          cancel: Optional[Callable[[], bool]] = None) -> List[Dict[str, object]]:
    """Merge ``folder``'s segments; returns one summary per written workbook."""
    folder = Path(folder)
    info = session_summary(folder)
    if info["status"] == "recording":
        raise MergeError("This session is still recording. Stop logging first.")
    if kind not in info["rows"]:
        raise MergeError(f"This session has no {kind} log (was {kind} logging enabled?).")
    manifest = read_manifest(folder)
    out = Path(out) if out else folder / "merged"
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{folder.name}_{kind}"
    total = int(info["rows"][kind])
    report = progress or (lambda *_a: None)
    stopped = cancel or (lambda: False)

    segments = sorted(manifest.get("segments", []), key=lambda s: int(s["index"]))
    sources = [(int(s["index"]), folder / s["files"][f"{kind}_csv"])
               for s in segments if s.get("files", {}).get(f"{kind}_csv")]
    missing = [p.name for _i, p in sources if not p.exists()]
    if missing:
        raise MergeError(f"Segment files are missing: {', '.join(missing)}")

    parts: List[_Part] = []
    written: List[Path] = []
    try:
        part: Optional[_Part] = None
        config_part = 1
        current_day: Optional[str] = None
        done = 0
        for seg_index, path in sources:
            if stopped():
                raise MergeCancelled()
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
                        label = stem + (f"_{day}" if day else "") + (f"_part{config_part}" if config_part > 1 else "")
                        part = _Part(out / f"{label}.csv.partial", header)
                        parts.append(part)
                        current_day = day
                    part.add(row, seg_index, row[ti])
                    done += 1
                    if done % 10_000 == 0:
                        if stopped():
                            raise MergeCancelled()
                        report("Joining segments", done, total)
        if part is not None:
            part.close()

        gaps = manifest.get("gaps", [])
        results: List[Dict[str, object]] = []
        for n, p in enumerate(parts, start=1):
            target = p.csv_path.with_name(p.csv_path.name.replace(".csv.partial", ".xlsx"))
            phase = f"Writing workbook {n} of {len(parts)}"
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
                "merged_by": "Bytehound session merge",
            }
            if stopped():
                raise MergeCancelled()
            report(phase, 0, p.rows)
            exc = compile_csv_to_xlsx(p.csv_path, meta, target,
                                      progress=lambda r, _ph=phase, _n=p.rows: report(_ph, r, _n),
                                      cancel=stopped)
            if isinstance(exc, CompileCancelled):
                raise MergeCancelled()
            if exc is not None:
                raise MergeError(f"Could not write {target.name}: {exc}")
            written.append(target)
            csv_target = None
            if keep_csv:
                csv_target = p.csv_path.with_name(p.csv_path.name.replace(".csv.partial", ".csv"))
                p.csv_path.replace(csv_target)
                written.append(csv_target)
            else:
                p.csv_path.unlink()
            results.append({"xlsx": str(target), "csv": str(csv_target) if csv_target else None,
                            "rows": p.rows, "first": p.first_time, "last": p.last_time,
                            "segments": list(p.segments)})
        return results
    except BaseException:
        # Cancelled or failed: keep nothing this merge wrote.
        for p in parts:
            p.close()
            p.csv_path.unlink(missing_ok=True)
        for path in written:
            Path(path).unlink(missing_ok=True)
        raise


def merge_job(folder: str, kind: str, split: str, out: Optional[str], keep_csv: bool, queue, cancel_event) -> None:
    """Child-process entry point for Tools → Merge Session…: reports through
    ``queue`` as ``("progress", phase, done, total)``, then ``("done",
    results)``, ``("cancelled",)`` or ``("error", message)``."""
    last = [0.0]

    def progress(phase: str, done: int, total: int) -> None:
        import time
        now = time.monotonic()
        if now - last[0] >= 0.2 or done == 0:
            last[0] = now
            queue.put(("progress", phase, done, total))

    try:
        results = merge(Path(folder), kind, split, Path(out) if out else None, keep_csv,
                        progress=progress, cancel=cancel_event.is_set)
        queue.put(("done", results))
    except MergeCancelled:
        queue.put(("cancelled",))
    except MergeError as exc:
        queue.put(("error", str(exc)))
    except Exception as exc:  # reported, never silent
        queue.put(("error", f"{type(exc).__name__}: {exc}"))
