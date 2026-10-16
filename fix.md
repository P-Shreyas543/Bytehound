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
- [ ] Record baseline benchmark numbers in this file

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
- [ ] Benchmark vs baseline

## Phase 4 — Memory

- [x] `TimeSeriesBuffer` rewritten as one contiguous, growable array pair:
      no 256 KB pre-allocation per signal, zero-copy reads, no duplicate
      "frozen" cache. 200 signals × 100k samples: 52.5 → 0 MB before data,
      682 → 360 MB after full-history redraws, full read 34.5 → 0.4 ms/redraw
- [x] Plot history cap as a memory budget (MB) across all signals instead of a
      per-signal sample count (Plot Settings; default 512 MB; settings
      migration v3 drops the old key)
- [ ] Shared time column per frame — decide from benchmark/RSS numbers
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

- [ ] `ruff check app tests` clean
- [ ] Full `pytest` green
- [ ] `smoke_headless.py --skip-device` and offscreen launch smoke green
- [ ] Final benchmark table in this file
