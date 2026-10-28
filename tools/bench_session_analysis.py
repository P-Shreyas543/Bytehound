"""Benchmark the Analysis Suite's session reader on a synthetic long session.

Generates a session of hourly segments at a fixed row rate (analysis caches
plus manifest; the CSVs are placeholders because the reader only uses the
caches), then times what the Analysis Suite does:

  * open the session (manifest, signal list)
  * overview window of the whole session for 3 signals
  * zoom windows: 1 day, 1 hour, 2 minutes
  * exact statistics of one signal over the whole session
  * 200 cursor reads at random times

Targets (Plane.md Part B): 30-day overview < 5 s, zoom window < 1 s.

Run:  python tools/bench_session_analysis.py [--days 30] [--rate 10] [--signals 10]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.serial_logging.session import MANIFEST_NAME, SESSION_FORMAT, SESSION_FORMAT_VERSION  # noqa: E402
from app.serial_logging.session_analysis import (  # noqa: E402
    LEVELS, QUANTILES, SessionSource, _bucket_aggregates,
)


def generate(folder: Path, days: float, rate: float, n_signals: int, seed: int = 1) -> int:
    folder.mkdir(parents=True, exist_ok=True)
    start = datetime(2027, 1, 1, tzinfo=timezone.utc)
    rng = np.random.default_rng(seed)
    hours = int(days * 24)
    rows_per_seg = int(3600 * rate)
    names = [f"0x{0x1000 + i:X}.Signal_{i} (V)" for i in range(n_signals)]
    segments = []
    for h in range(hours):
        t = h * 3600.0 + np.arange(rows_per_seg) / rate
        arrays = {"t": t, "signals": np.array(names, dtype=object)}
        for i, name in enumerate(names):
            slow = 3.7 + 0.4 * np.sin(2 * np.pi * t / (86400 * (1 + i / 7)))
            y = np.round(slow + rng.normal(0, 0.002, t.size), 3)     # realistic 1 mV steps
            arrays[f"c/{name}"] = y
            for level in LEVELS:
                b, agg = _bucket_aggregates(t, y, level)
                arrays[f"L{level}/b"] = b
                for k, v in agg.items():
                    arrays[f"L{level}/{name}/{k}"] = v
            arrays[f"q/{name}"] = np.percentile(y, QUANTILES)
            arrays[f"q/{name}/n"] = np.array([y.size])
        csv_name = f"seg_{h + 1:04d}_event.csv"
        (folder / csv_name).write_text("", encoding="utf-8")
        np.savez_compressed(folder / f"seg_{h + 1:04d}_event_analysis.npz", **arrays)
        s0 = start + timedelta(hours=h)
        segments.append({
            "index": h + 1, "status": "closed",
            "started_utc": s0.isoformat(timespec="milliseconds"),
            "ended_utc": (s0 + timedelta(hours=1)).isoformat(timespec="milliseconds"),
            "files": {"event_csv": csv_name, "event_analysis": f"seg_{h + 1:04d}_event_analysis.npz"},
            "rows": {"event": rows_per_seg},
        })
        if (h + 1) % 48 == 0:
            print(f"  generated {h + 1}/{hours} segments", flush=True)
    manifest = {
        "format": SESSION_FORMAT, "format_version": SESSION_FORMAT_VERSION, "status": "closed",
        "started_utc": start.isoformat(timespec="milliseconds"), "segments": segments, "gaps": [], "events": [],
    }
    (folder / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    return hours * rows_per_seg


def timed(label: str, fn):
    t0 = time.perf_counter()
    out = fn()
    dt = time.perf_counter() - t0
    print(f"  {label:44s} {dt * 1000:9.1f} ms")
    return out, dt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=30)
    ap.add_argument("--rate", type=float, default=10, help="rows per second")
    ap.add_argument("--signals", type=int, default=10)
    ap.add_argument("--folder", type=Path, default=None, help="reuse an already generated session")
    args = ap.parse_args()

    folder = args.folder or Path(tempfile.mkdtemp(prefix="bh_long_")) / "session"
    if not (folder / MANIFEST_NAME).exists():
        print(f"generating {args.days} days x {args.rate} rows/s x {args.signals} signals -> {folder}")
        t0 = time.perf_counter()
        rows = generate(folder, args.days, args.rate, args.signals)
        size = sum(p.stat().st_size for p in folder.glob("*.npz")) / 1e9
        print(f"  {rows:,} rows, caches {size:.2f} GB, {time.perf_counter() - t0:.0f} s")

    print("timings (cold, first access):")
    if not (folder / "event_summary.npz").exists():
        first = SessionSource(folder)
        timed("first open: build + save session summary", first.ensure_summary)
    def reopen():
        src = SessionSource(folder)
        src.ensure_summary()
        return src
    src, t_open = timed("open session (summary saved)", reopen)
    params = src.signals()[:3]
    dur = src.duration
    w, t_over = timed(f"overview {dur / 86400:.0f} days, 3 signals", lambda: src.window(params, 0, dur))
    print(f"    level {w.level} s, {w.x.size} points")
    mid = dur / 2
    results = {"open": t_open, "overview": t_over}
    for label, span in (("1 day", 86400), ("1 hour", 3600), ("2 minutes", 120)):
        w, dt = timed(f"zoom {label}", lambda span=span: src.window(params, mid, mid + span))
        print(f"    level {w.level} s, {w.x.size} points")
        results[f"zoom {label}"] = dt
    st, t_stats = timed("exact stats, whole session, 1 signal", lambda: src.stats(params[0], 0, dur))
    print(f"    n={st.n:,} mean={st.mean:.6f} std={st.std:.6f} (percentiles approx: {st.approx_percentiles})")
    rng = np.random.default_rng(3)
    _, t_cur = timed("200 cursor reads (random times)",
                     lambda: [src.value_at(params[0], float(x)) for x in rng.uniform(0, dur, 200)])
    print(f"    {t_cur / 200 * 1000:.1f} ms per read on average (cold segments)")

    ok = results["overview"] < 5.0 and all(results[k] < 1.0 for k in results if k.startswith("zoom"))
    print("TARGETS MET" if ok else "TARGETS MISSED", "(overview < 5 s, zoom < 1 s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
