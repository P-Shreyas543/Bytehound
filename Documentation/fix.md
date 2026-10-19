# Bytehound — threading & memory fixes

Tracking list for the capture/threading/memory rework. Items are ticked as they
land with tests passing. Struck items were dropped after reading the code; the
reason is noted next to them.

## Phase 0 — Baseline

- [x] Record baseline test results: `pytest` 469 passed, 1 failed
      (`test_high_throughput_burst_and_pre_decoding` — stale test still unpacking
      2-tuples after the worker moved to `(packet, decoded, rx_perf)`; fixed).
      `smoke_headless.py --skip-device` 26/26.
- [x] Repeatable high-rate benchmark with no hardware (TCP loopback source → real
      `MainWindow` offscreen): GUI-thread stall (p50/p99/max), packets/s shown,
      packets dropped, process RSS — `tools/bench_capture.py`
- [x] Record baseline benchmark numbers in this file (see Results, `head` rows)

## Phase 1 — Corrections to the original review

- [x] Decoded log already streams to a temp CSV and compiles `.xlsx` on stop, with
      crash recovery on next launch. Fix the stale `decoded_logger.py` docstring
      that still says a crash loses the workbook.
- ~~Add display decimation~~ — already done (`setClipToView` + peak downsampling
  in `plot_panel._configure_live_curve`).
- ~~Replace sleep-polling with blocking reads~~ — the `in_waiting` poll loop is
  deliberate tuning for Windows USB-CDC and 2 Mbaud links (see comments in
  `serial_worker.py`); the TX path is already a `queue.Queue`. Not changing it
  without hardware to validate on.
- ~~Store plot values as float32~~ — loses precision on uint32 counters
  (> 2^24), e.g. cumulative energy/charge. Stays float64.

## Phase 2 — Lossless capture

- [x] Raw capture file (`.bhraw`): every RX read and TX write, timestamped,
      written from the capture side whenever logging is on, on its own writer
      thread. Never drops; independent of the GUI.
- [x] `rebuild_decoded_log(raw, config, out)` — regenerate the decoded log
      offline from a `.bhraw` file (same parser + decoder as live); exposed as
      Tools → Rebuild Decoded Log
- [x] Decoded-log drop warning points the user at the raw file / rebuild
- [x] Tests: raw round-trip, rebuild matches live decoded output

## Phase 3 — Capture in a separate process

- [x] `CaptureClient`: same signals and methods as `PollingWorker`, backed by a
      child process that runs the polling/parse/decode loop
- [x] Child is warm-started at app launch so Connect isn't slowed by process spawn
- [x] Open errors (port busy, bad port) still raise synchronously → same popup
- [x] Child crash/kill surfaces as `connection_lost` in the GUI
- [x] Setting to fall back to the in-thread worker (Connect dialog checkbox;
      also automatic if the process can't start)
- [x] Works in the frozen PyInstaller build: `Bytehound.exe --selftest-capture`
      → capture process up in 0.46 s, 600/600 frames decoded, exit 0, no
      processes left behind. `app/main.py` now imports the GUI lazily so each
      spawned child doesn't load Qt Widgets / the main window.
- [x] Tests
- [x] Benchmark vs baseline — **process mode did not pay off; it is now
      opt-in and thread mode is the default.** At ≥3000 frames/s the GUI
      process spends more time unpickling every decoded batch than it saved
      on decode (3000 fps: p99 stall 195 ms vs 34 ms in thread mode; 6000 fps:
      falls behind). The code, tests and frozen-build support stay, behind
      *Capture in a separate process (experimental)*. Making it worthwhile
      means sending compact array batches instead of objects — follow-up.

## Phase 4 — Memory

- [x] `TimeSeriesBuffer` rewritten as one contiguous, growable array pair:
      no 256 KB pre-allocation per signal, zero-copy reads, no duplicate
      "frozen" cache. 200 signals × 100k samples: 52.5 → 0 MB before data,
      682 → 360 MB after full-history redraws, full read 34.5 → 0.4 ms/redraw
- [x] Plot history cap as a memory budget (MB) across all signals instead of a
      per-signal sample count (Plot Settings; default 512 MB; settings
      migration v3 drops the old key)
- [x] Shared time column per frame — **not doing.** After the buffer
      rewrite plot memory equals the raw samples and is bounded by the
      budget; a shared x column would only lengthen history within the same
      budget, at the cost of gap/NaN handling in every plot, hover and export
      path. GUI RSS in the benchmark is dominated by Qt/pyqtgraph, not history.
- [x] Columnar (numpy) decode — **not doing.** Profiling the GUI process in
      capture-process mode shows decode is gone from it; what remains is
      per-packet UI bookkeeping. Fixed that instead: table cells are now
      formatted once per 60 Hz flush for the newest value per row, not for
      every packet (was 24k `strftime` + 155k number formats per 12k frames).

## Phase 5 — Background jobs

- [x] Never leave a half-written `.xlsx`: every log compile/recovery now saves
      to `<name>.xlsx.partial` and renames into place (`_atomic.py`). The temp
      data is only deleted after that, so an exit mid-save is redone on the
      next launch. (Making the recovery thread non-daemon instead would block
      app exit for minutes on a large log.)
- ~~Consolidate all one-off QThreads into a pool~~ — churn with no user-visible
  benefit; each already has a clear owner and lifetime.

## Phase 6 — Verify

- [x] `ruff check app tests` clean
- [x] Full `pytest` green: 565 passed, 0 failed (34–37 min, run twice).
      The process then exits with code 139 — an access violation in the final
      garbage collection at interpreter shutdown (PySide teardown, no Python
      frame). Pre-existing: the same suite on 11b7527 exits 139 too. Tracked
      in Plane.md §0.11.
- [x] `smoke_headless.py --skip-device` 26/26 and offscreen launch smoke 7/7 green
- [x] Final benchmark table in this file

## Results

`python tools/bench_capture.py --rate N --seconds 10 [--log] --mode thread|process`,
TCP loopback device in a separate process, real `MainWindow` offscreen, 3 runs
each (frame counts summed, other columns median). Stall = how late a 5 ms GUI
timer fires. `head` = commit 11b7527 before this work; `new_thread` = current
default; `new_process` = opt-in capture process. Windows 11, 8 logical cores.

| fps | log | build | shown/sent | UI dropped | stall p50 | stall p99 | stall max | GUI RSS |
|---|---|---|---|---|---|---|---|---|
| 1000 | off | head | 29990/29990 | 0 | 10.53 ms | 37 ms | 129 ms | 221 MB |
| 1000 | off | new_thread | 30000/30000 | 0 | 0.01 ms | 11 ms | 22 ms | 171 MB |
| 1000 | off | new_process | 29970/29970 | 0 | 0.00 ms | 9 ms | 21 ms | 172 MB |
| 1000 | on | head | 29990/29990 | 0 | 10.74 ms | 43 ms | 338 ms | 222 MB |
| 1000 | on | new_thread | 29990/29990 | 0 | 0.01 ms | 8 ms | 305 ms | 173 MB |
| 1000 | on | new_process | 29980/29980 | 0 | 0.02 ms | 15 ms | 624 ms | 172 MB |
| 3000 | off | head | 90000/90000 | 0 | 0.57 ms | 61 ms | 190 ms | 224 MB |
| 3000 | off | new_thread | 89970/89970 | 0 | 6.40 ms | 34 ms | 118 ms | 176 MB |
| 3000 | off | new_process | 90000/90000 | 0 | 10.84 ms | 195 ms | 232 ms | 180 MB |
| 3000 | on | head | 89970/89970 | 0 | 0.17 ms | 189 ms | 2230 ms | 230 MB |
| 3000 | on | new_thread | 89940/89940 | 0 | 10.56 ms | 35 ms | 1467 ms | 177 MB |
| 3000 | on | new_process | 89940/89940 | 0 | 11.92 ms | 95 ms | 2705 ms | 177 MB |
| 6000 | off | head | 129340/179940 | 620 | 40.58 ms | 1368 ms | 1368 ms | 327 MB |
| 6000 | off | new_thread | 179940/179940 | 0 | 14.24 ms | 454 ms | 496 ms | 202 MB |
| 6000 | off | new_process | 147460/179220 | 2740 | 18.13 ms | 2150 ms | 2150 ms | 291 MB |
| 6000 | on | head | 138280/180000 | 6080 | 32.10 ms | 2626 ms | 2626 ms | 364 MB |
| 6000 | on | new_thread | 180000/180000 | 0 | 30.99 ms | 1618 ms | 1618 ms | 219 MB |
| 6000 | on | new_process | 172860/179880 | 0 | 15.12 ms | 1142 ms | 2264 ms | 255 MB |

Shown < sent with 0 UI drops means the run ended with frames still in flight
(the app had fallen behind). Main take-aways: at 6000 fps `head` failed to
show 28 % (log off) / 23 % (log on) of frames and stalled up to 2.6 s;
`new_thread` showed every frame with lower worst-case stalls and ~110–145 MB
less memory. At 1000 fps the median GUI stall went from 10.5 ms to 0.01 ms.
Not every column improved: at 3000 fps the *median* stall of `new_thread` is
higher than `head` (6.4 vs 0.6 ms) while its p99/max are much lower.
Single-machine numbers with run-to-run noise (max stall varies most).
