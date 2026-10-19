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
| BMS simulator | **NUCLEO-G474RE** with `firmware/nucleo_g474_bms_sim` (recommended: any baud, sequence counter, injection, counters), or `MCU_BMS_Simulator/MCU_BMS_Simulator.ino` on an Arduino-class board (115,200 baud only, no counter) |
| Real BMS | At least one production unit |
| Small log drive | USB stick or partition of ~5 GB (disk-full test) |

The NUCLEO firmware provides what the Arduino sketch lacks: the baud rate
is set by command (115,200 / 921,600 / 2,000,000), frame 0x4000 carries a
32-bit sequence number (any jump in the log = a lost frame), and the board
reports how many frames and bytes it sent. See its README and section 6.
The firmware drives the on-board ST-LINK virtual COM port only; testing
FTDI / CH340 / CP2102 adapters needs them wired to a second UART (not yet
in the firmware) or the Arduino sketch.

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

## 6. Automated HIL rig (NUCLEO-G474RE)

`python tools/hil/run_hil.py` (about 5 minutes; `--soak-minutes N` adds a
long session run). Every test compares the board's own counters with what
the application saw; any difference is a lost, duplicated or misclassified
byte. A JSON report is written to `artifacts/hil/`.

| Test | What it proves |
|---|---|
| `stream_115200`, `stream_921600`, `stream_2000000` | 80–90 % line load for 10 s through `PollingWorker`: frames per ID = board, bytes accounted = board bytes sent, 0x4000 sequence contiguous, raw capture RX bytes = parser input, no driver errors |
| `inject_noise_corrupt` | Noise after every 7th frame, bad CRC on every 13th: discarded bytes = noise injected, rejected frames = corrupted frames, good frames = board |
| `burst` | 20,000 cycles back to back at 2 Mbaud (100 % line rate) |
| `polling_sequential`, `polling_pipelined` | Template poll schedule: the stretch warning at the default TX gap; at 20 ms every interval honoured, responses = board replies, no timeouts |
| `watchdog` | `device_timeout` after 3 s of silence, data resumes, no false disconnect |
| `device_reset` | Target reset over SWD mid-stream: the app keeps running, the sequence restarts, at most one torn frame |
| `session_analysis` | Session logging (on the worker thread) at 921,600 baud with rotation every 7.5 s and fixed-step 0.1 s: every sequence number in the event log once, timestamps never backwards across rotations, each .xlsx = its CSV, fixed-step rows on the grid, raw capture gapless across rotations, Analysis Suite statistics and export = board |
| `gui_end_to_end` | The real MainWindow at 3,250 frames/s: logging session, every frame logged once, GUI event-loop lag (fails above 250 ms, records the GUI thread's stack while stalled), the Analysis Suite opens the result |
| `reader_pause` | The worker stops reading for 1/2/4/8/16 s at 2 Mbaud: measures how much the link buffers upstream (the driver does not report its granted size); pauses ≤ 2 s must be lossless; any loss must show as a sequence gap |
| `cpu_load` | Streaming at 2 Mbaud while every core runs a busy loop in another process |
| `shutdown_under_traffic` | Closing the connection while the board streams at 2 Mbaud with raw capture on: no error, raw capture complete |
| `seq_wraparound` | The 32-bit counter wraps 0xFFFFFFFF → 0 inside a rotating session: every value logged once, in order, unsigned (firmware 1.1.0 `SET_SEQ`) |
| `smoke_headless` | `smoke_headless.py` phases 0–19 against the board (decoding, bitfields, enums, TX commands, voltage-limit round trip, polling cadence) |

**Results 2026-10-17** (ByteHound branch `production-hardening`, firmware
1.0.0): 13 / 13 pass, also while the full unit suite ran on the same PC.
Longest wait before data was read: 32 ms (47 ms during session logging).
GUI event loop at 3,250 frames/s, eight runs after the fixes: worst
lateness 43, 59, 74, 90, 105, 105 and 152 ms, and one run with a single
4.5 s stall (not reproduced; see Plane.md 0.11). The Part G budget is
50 ms, so this is **not yet met**; the test's own limit is 250 ms.

Found by the rig (Plane.md F16–F20): read stalls at 2 Mbaud lose data
upstream with no driver error (not fixed by the larger buffer request —
see F16 correction and the reader_pause results below); commands blocked reads
for up to 110 ms; the raw capture missed ~70 ms at every segment rotation;
the default TX gap silently stretched the template poll schedule; polls were
scheduled from completion instead of at a fixed rate (10–25 % slow). Also GUI
lag from segment finishing, per-update style re-polish and the RX console.

