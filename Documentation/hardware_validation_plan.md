# Bytehound — Hardware Validation Plan

Tests that must be run on real equipment before a release is trusted for
long-duration BMS logging. They cover what the automated suite cannot:
real USB-UART adapters and drivers, real cables, unplugging, power loss,
full disks and multi-week runs.

The automated suite already covers (no hardware needed): byte accounting,
noise / split / corrupted frames at maximum rate over TCP and UDP
(`tests/test_frame_loss.py`), segment rotation, gaps, disk guard and crash
recovery with simulated clocks (`tests/test_session_log.py`), a 3-day
time-compressed soak (`tools/soak_session.py`), and the Analysis Suite on a
30-day session (`tools/bench_session_analysis.py`).

---

## 1. Equipment

| Item | Notes |
|---|---|
| Lab PC | Prepared per *long_run_lab_guide.md* section 1 |
| USB-serial adapters | At least one each: **FTDI** (FT232R), **CH340**, **CP2102** |
| BMS simulator | `MCU_BMS_Simulator/MCU_BMS_Simulator.ino` on an Arduino-class board |
| Real BMS | At least one production unit |
| Small log drive | USB stick or partition of ~5 GB (disk-full test) |

**Simulator changes needed before these tests** (the sketch currently runs
at a fixed 115,200 baud and has no frame counter):

1. Make the baud rate configurable (115,200 / 921,600 / 2,000,000).
2. Add a **rolling 8- or 16-bit counter** to one frame, incremented every
   frame sent. This lets the test prove no frame was lost on the way to the
   PC — compare the counter sequence in the log (any jump = a lost frame).
   It also enables Plane.md F12 (sequence-counter gap detection).

## 2. Pass criteria (all tests)

A test passes only if, for the whole run:

- **Integrity:** no unexplained discarded bytes after the first valid frame,
  `Driver errors` = 0, and `session.json` shows every segment `closed` (or
  `recovered` after a deliberate crash test).
- **Completeness:** with the counter-stamped simulator, the counter sequence
  in the event log has no jumps except inside recorded gaps.
- **Timing:** with fixed-step logging on, the `tick` column has no missing
  or repeated values across all segments.
- **Memory / handles:** Bytehound's memory (Task Manager → Details →
  *Memory (private working set)*) and *Handles* column stay flat after the
  first hour (growth < 50 MB and < 50 handles per day).
- **Responsiveness:** the window responds immediately throughout (menus,
  zoom, dragging docks) — no freezes longer than a moment.

Record the version, adapter, baud rate, start/end time, and the final
`session.json` for every run.

## 3. Test matrix

| # | Test | Duration | Setup |
|---|---|---|---|
| H1 | Baud sweep — streaming | 2 h each | Simulator streaming at 115,200 / 921,600 / 2,000,000 baud × FTDI, CH340, CP2102 |
| H2 | Baud sweep — polled | 2 h each | Same, with Auto-Fetch (sequential and pipelined) |
| H3 | 24-hour endurance | 24 h each | 115,200, 921,600 and 2,000,000 baud, fixed-step 0.1 s on, event log on |
| H4 | Unplug / replug | 30 min | Auto-reconnect on; unplug the adapter 10× at random intervals (5 s–5 min) |
| H5 | Device power cycle | 30 min | Power-cycle the simulator / BMS 10× |
| H6 | PC under load | 2 h | Run a CPU stress tool at 100 % on all cores during H1 at 2 Mbaud |
| H7 | Disk full | until stop | Log to the small drive; verify the warning, then the clean stop |
| H8 | Crash recovery | 3 runs | Kill `Bytehound.exe` in Task Manager mid-run; once with a power cut (UPS off) |
| H9 | Multi-week soak | ≥ 14 days | Real BMS, production config, 1 h segments, fixed-step 1 s |
| H10 | Live analysis | during H9 | Open the session in the Analysis Suite daily while it records |
| H11 | Live serial smoke | 15 min | `python smoke_headless.py --port COMx` (phases 2–10) against the simulator |

## 4. Procedures and expected results

**H4 Unplug / replug.** Each unplug must appear as one entry under
`"gaps"` in `session.json` with start and end times; a new segment starts
after each reconnect; Auto-Fetch resumes with the same targets; no
counter jumps outside the gaps; `Stop Logging` stays available during gaps.

**H5 Device power cycle.** As H4. Frames sent while the device boots may be
incomplete — they must show up as rejected frames or discarded bytes, never
as wrong values in the decoded log.

**H7 Disk full.** At the warning level: one warning in the Activity Log and
an entry in `session.json → events`. At the stop level: logging stops by
itself with a clear message; every segment up to that point is `closed`
with its files present.

**H8 Crash recovery.** Restart Bytehound: the Activity Log reports the
recovered session; `session.json` status is `recovered`; the segment that
was open has its CSV and `.xlsx`; row counts match what was logged up to
the crash (within the last second of data).

**H9 Multi-week soak.** Check daily: memory and handles flat, disk use
matches the estimate, status bar shows no driver errors. At the end, open
the whole session in the Analysis Suite: overview loads in seconds, zoom to
any hour loads in under a second, statistics of the full range complete.

**H11 Live serial smoke.** All phases report OK.

## 5. Report

For each test: pass / fail per criterion, the `session.json`, screenshots of
the status bar at the end, and for failures the Activity Log and
`logs/bytehound.log`. A release is ready for long-duration lab use when
H1–H8 and H11 pass on all three adapters and H9 passes on at least one
production BMS.
