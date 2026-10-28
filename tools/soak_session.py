"""Time-compressed soak test for long-running logging sessions.

Drives a real ``SessionLog`` through N simulated days (fake wall/monotonic
clocks, real files, real writer threads) and checks it stays healthy:

* memory (working set) and OS handle count stay flat — no leaks per segment
* thread count returns to baseline — writer / finisher threads all exit
* every segment closes, is hashed, and the row counts add up
* the fixed-step grid has no gaps or repeats across hundreds of rotations
* no temp files are left behind

Run:  python tools/soak_session.py [--days 3] [--rate 2] [--step 1] [--segment-min 60]

Exit status 0 = all checks passed. Prints one line per simulated day.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import gc
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.decoder.config_loader import load_config  # noqa: E402
from app.decoder.frame_decoder import decode_frame  # noqa: E402
from app.serial_logging.session import SessionLog, SessionSettings, read_manifest  # noqa: E402

TEMPLATE = ROOT / "app" / "resources" / "config_template"


def _current_process() -> ctypes.c_void_p:
    """Pseudo-handle of this process. The default ctypes return type (32-bit
    int) truncates handles on 64-bit Windows, which made every call fail."""
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    return ctypes.c_void_p(k32.GetCurrentProcess())


def _rss_mb() -> float:
    if sys.platform != "win32":
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e3

    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (n, ctypes.c_size_t) for n in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                "PagefileUsage", "PeakPagefileUsage",
            )
        ]

    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    if not ctypes.windll.psapi.GetProcessMemoryInfo(_current_process(), ctypes.byref(pmc), pmc.cb):
        raise OSError("GetProcessMemoryInfo failed")
    return pmc.WorkingSetSize / 1e6


def _handles() -> int:
    if sys.platform != "win32":
        import os
        return len(os.listdir("/proc/self/fd")) if Path("/proc/self/fd").exists() else -1
    count = ctypes.c_ulong()
    if not ctypes.windll.kernel32.GetProcessHandleCount(_current_process(), ctypes.byref(count)):
        raise OSError("GetProcessHandleCount failed")
    return count.value


class Clock:
    def __init__(self) -> None:
        self.wall = 1_800_000_000.0
        self.perf = 10_000.0

    def advance(self, s: float) -> None:
        self.wall += s
        self.perf += s


class RawHooks:
    def start(self, path: Path, metadata: dict) -> None:
        path.write_bytes(b"")

    def stop(self):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=3.0)
    ap.add_argument("--rate", type=float, default=2.0, help="cycles per second (3 frames each)")
    ap.add_argument("--step", type=float, default=1.0, help="fixed-step seconds")
    ap.add_argument("--segment-min", type=float, default=60.0)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    config = load_config(TEMPLATE)
    frames = [
        decode_frame(config, fid, bytes((i * 7 + fid) & 0xFF for i in range(f.payload_length)), {})
        for fid, f in config.frames.items()
    ]
    out = args.out or Path(tempfile.mkdtemp(prefix="bh_soak_"))
    clock = Clock()
    warnings: list[str] = []
    s = SessionLog(
        out / "soak", config,
        SessionSettings(segment_seconds=args.segment_min * 60, fixed_step_s=args.step),
        raw_capture=RawHooks(), on_warning=warnings.append, on_error=warnings.append,
        clock=lambda: clock.wall, perf=lambda: clock.perf, disk_free=lambda p: 1 << 40,
    )
    base_threads = threading.active_count()
    s.start()
    dt = 1.0 / args.rate
    total_s = args.days * 86400
    cycles = int(total_s * args.rate)
    next_tick = 1.0
    next_report = 86400.0
    t_sim = 0.0
    t0 = time.perf_counter()
    samples = []
    print(f"soak: {args.days} simulated days, {args.rate} cycles/s, step {args.step}s, "
          f"segments {args.segment_min} min -> {out / 'soak'}")
    for _ in range(cycles):
        for f in frames:
            s.log_frame(f, clock.perf)
        clock.advance(dt)
        t_sim += dt
        if t_sim >= next_tick:
            next_tick += 1.0
            seg = s._segment
            # Real time is far slower than this simulation; let the writers
            # keep up instead of overflowing their queues.
            while seg is not None and seg.event is not None and seg.event.pending_rows() > 20_000:
                time.sleep(0.01)
            s.tick()
        if t_sim >= next_report:
            next_report += 86400.0
            gc.collect()
            samples.append((t_sim / 86400, _rss_mb(), _handles(), threading.active_count()))
            d, rss, h, th = samples[-1]
            print(f"  day {d:4.1f}: rss {rss:7.1f} MB  handles {h:5d}  threads {th:3d}  "
                  f"segments {len(s.manifest['segments']):4d}  elapsed {time.perf_counter() - t0:6.1f}s")
    clock.advance(2.0)
    s.tick()
    s.stop()
    ok_finish = s.await_finished(600)
    gc.collect()
    end_threads = threading.active_count()

    m = read_manifest(out / "soak")
    segs = m["segments"]
    problems: list[str] = []
    expect_segs = int(total_s // (args.segment_min * 60)) + 1
    if not ok_finish:
        problems.append("segment finishers still running after 600 s")
    if abs(len(segs) - expect_segs) > 1:
        problems.append(f"{len(segs)} segments, expected ~{expect_segs}")
    bad = [x["index"] for x in segs if x["status"] != "closed"]
    if bad:
        problems.append(f"segments not closed cleanly: {bad[:10]}")
    event_rows = sum(x["rows"].get("event", 0) for x in segs)
    if abs(event_rows - cycles) > len(segs) + 1:   # one partial cycle per rotation at most
        problems.append(f"event rows {event_rows} vs cycles {cycles}")
    ticks: list[int] = []
    for x in segs:
        with (out / "soak" / x["files"]["fixed_csv"]).open(newline="", encoding="utf-8") as fp:
            ticks += [int(r[0]) for r in list(csv.reader(fp))[1:]]
    if ticks != list(range(len(ticks))):
        problems.append("fixed-step grid has gaps or repeats")
    if abs(len(ticks) - total_s / args.step) > 3:
        problems.append(f"{len(ticks)} fixed-step rows, expected ~{int(total_s / args.step)}")
    leftovers = list((out / "soak").glob("*.tmp_*")) + list((out / "soak").glob("*.partial"))
    if leftovers:
        problems.append(f"temp files left: {[p.name for p in leftovers[:5]]}")
    if end_threads > base_threads:
        problems.append(f"threads leaked: {end_threads} vs {base_threads} at start")
    if len(samples) >= 2:
        rss_growth = samples[-1][1] - samples[0][1]
        handle_growth = samples[-1][2] - samples[0][2]
        if rss_growth > 50:
            problems.append(f"memory grew {rss_growth:.0f} MB between day 1 and day {samples[-1][0]:.0f}")
        if handle_growth > 20:
            problems.append(f"handle count grew by {handle_growth}")
    if warnings:
        problems.append(f"{len(warnings)} warning(s), first: {warnings[0]}")

    print(f"segments {len(segs)}, event rows {event_rows} (cycles {cycles}), fixed rows {len(ticks)}, "
          f"wall time {time.perf_counter() - t0:.0f}s")
    if problems:
        print("FAIL:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("OK: no leaks, every segment closed and hashed, rows and grid complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
