"""Microbenchmark: ring buffer vs deque-pair for plot history.

The live-plot pipeline used to back each (signal -> history) entry with a
pair of bounded deques and convert them to numpy via ``np.fromiter`` on
every redraw. The Python-level fromiter loop dominates the redraw cost
once buffers fill up.

This script compares the two implementations on the operations the plot
loop actually performs:

* steady-state append:  per-sample cost.
* full retrieve:        deque -> np.fromiter vs ring -> arrays().
* mixed:                N appends followed by one retrieve, repeated.

Usage:
    python scripts\bench_ring_buffer.py
    python scripts\bench_ring_buffer.py --capacity 6000 --reps 5000
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _bench(label: str, fn, reps: int) -> tuple[str, float]:
    # Warm up so import / first-call costs don't pollute the headline number.
    for _ in range(min(reps, 5)):
        fn()
    t0 = time.perf_counter()
    for _ in range(reps):
        fn()
    t1 = time.perf_counter()
    return label, (t1 - t0) / reps * 1e6  # microseconds per rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capacity", type=int, default=6000, help="buffer capacity (default 6000)")
    ap.add_argument("--reps", type=int, default=2000, help="repetitions per benchmark (default 2000)")
    ap.add_argument("--samples-per-cycle", type=int, default=16,
                    help="appends between each retrieve in the mixed test (default 16, ~1 kHz / 60 Hz)")
    args = ap.parse_args()

    # Import here so the import time isn't part of the warmup loop.
    from app.ui.main_window import _RingBuffer

    cap = args.capacity
    reps = args.reps

    # ── pre-build saturated containers ────────────────────────────────
    # Both are "full ring" so the retrieve path exercises the
    # full-buffer code path on the ring side (np.concatenate) and a
    # full-deque conversion on the deque side.
    def fresh_full_deques():
        xs, ys = deque(maxlen=cap), deque(maxlen=cap)
        for i in range(cap):
            xs.append(float(i))
            ys.append(float(i) * 0.5)
        return xs, ys

    def fresh_full_ring():
        rb = _RingBuffer(cap)
        for i in range(cap):
            rb.append(float(i), float(i) * 0.5)
        return rb

    print(f"capacity={cap}  reps={reps}  samples-per-cycle={args.samples_per_cycle}")
    print()

    # ── append throughput ─────────────────────────────────────────────
    def deque_append():
        xs, ys = deque(maxlen=cap), deque(maxlen=cap)
        for i in range(args.samples_per_cycle):
            xs.append(float(i))
            ys.append(float(i) * 0.5)

    def ring_append():
        rb = _RingBuffer(cap)
        for i in range(args.samples_per_cycle):
            rb.append(float(i), float(i) * 0.5)

    results = []
    results.append(_bench(f"deque pair  append x{args.samples_per_cycle}", deque_append, reps))
    results.append(_bench(f"_RingBuffer append x{args.samples_per_cycle}", ring_append, reps))

    # ── full retrieve (saturated buffer) ──────────────────────────────
    xs_d, ys_d = fresh_full_deques()
    rb = fresh_full_ring()

    def deque_to_numpy():
        a = np.fromiter(xs_d, dtype=float, count=len(xs_d))
        b = np.fromiter(ys_d, dtype=float, count=len(ys_d))
        return a, b

    def ring_to_numpy():
        return rb.arrays()

    results.append(_bench("deque pair  -> np.fromiter (full)", deque_to_numpy, reps))
    results.append(_bench("_RingBuffer.arrays()      (full)", ring_to_numpy, reps))

    # ── full retrieve (half-full buffer — zero-copy slice on the ring) ─
    xs_h, ys_h = deque(maxlen=cap), deque(maxlen=cap)
    for i in range(cap // 2):
        xs_h.append(float(i))
        ys_h.append(float(i) * 0.5)
    rb_h = _RingBuffer(cap)
    for i in range(cap // 2):
        rb_h.append(float(i), float(i) * 0.5)

    def deque_to_numpy_half():
        a = np.fromiter(xs_h, dtype=float, count=len(xs_h))
        b = np.fromiter(ys_h, dtype=float, count=len(ys_h))
        return a, b

    def ring_to_numpy_half():
        return rb_h.arrays()

    results.append(_bench("deque pair  -> np.fromiter (half)", deque_to_numpy_half, reps))
    results.append(_bench("_RingBuffer.arrays()      (half)", ring_to_numpy_half, reps))

    # ── mixed: N appends + 1 retrieve, like real redraw ticks ─────────
    def mixed_deque():
        xs, ys = deque(maxlen=cap), deque(maxlen=cap)
        for _ in range(cap):  # fill
            xs.append(0.0)
            ys.append(0.0)
        for _cycle in range(60):  # 1 second of 60 Hz redraws
            for j in range(args.samples_per_cycle):
                xs.append(float(j))
                ys.append(float(j))
            np.fromiter(xs, dtype=float, count=len(xs))
            np.fromiter(ys, dtype=float, count=len(ys))

    def mixed_ring():
        rb = _RingBuffer(cap)
        for _ in range(cap):
            rb.append(0.0, 0.0)
        for _cycle in range(60):
            for j in range(args.samples_per_cycle):
                rb.append(float(j), float(j))
            rb.arrays()

    results.append(_bench("mixed (60 ticks, full buf) deque",  mixed_deque,  max(reps // 50, 20)))
    results.append(_bench("mixed (60 ticks, full buf) ring",   mixed_ring,   max(reps // 50, 20)))

    # ── report ─────────────────────────────────────────────────────────
    width = max(len(r[0]) for r in results)
    for label, us in results:
        print(f"  {label.ljust(width)}  {us:>10.2f} us")

    # Speedup table for the full-retrieve numbers (most-important path).
    print()
    deq_full = next(us for label, us in results if "fromiter (full)" in label)
    rng_full = next(us for label, us in results if "arrays()      (full)" in label)
    deq_half = next(us for label, us in results if "fromiter (half)" in label)
    rng_half = next(us for label, us in results if "arrays()      (half)" in label)
    print(f"  full-buffer retrieve speedup:  {deq_full / rng_full:.1f}x")
    print(f"  half-buffer retrieve speedup:  {deq_half / rng_half:.1f}x")
    return 0


if __name__ == "__main__":
    sys.exit(main())
