# Bytehound C++ Migration Plan

> **Read §0 first.** It is the single checklist of everything planned, in
> progress, blocked or deliberately dropped, so nothing gets lost. The C++
> plan proper starts at *Objective* below.

## 0. Master status and roadmap (updated 2026-10-16)

Bytehound is used by BMS manufacturers and test labs that log continuously
for **days, months or years** at high frame rates. Every item is ticked only
when implemented, tested and verified; dropped items say why. Detailed
evidence for finished threading/memory work lives in [fix.md](fix.md).

### 0.1 Release blockers (current Python release, v1.2.3)

From the production check — must be fixed before shipping:

- [x] Connection dialog ignored the saved baud (config default won) — fixed,
      `test_connection_dialog_qsettings_wins_over_config_defaults` passes
- [x] Ruff lint findings (90) — fixed; `ruff check app tests` clean
- [ ] `installer_url` (`Bytehound_Setup_1.2.3.exe`) returns HTTP 404 — upload
      the installer to the Cloudflare worker. (Homepage, `version.json` and
      `LICENSE` return 200; `report_issue` is POST-only and answers 422 to an
      empty POST, i.e. it is live.)
- [ ] `dist/Bytehound` has no `Bytehound.exe`; `Bytehound_1.2.3.zip` is from
      2026-09-12 and predates all fixes — rebuild with `build.py`, rebuild the
      installer, update `sha256` in `version.json`
- [ ] Decide which branch ships: the release fixes are on `Migration_To_C++`
      together with the threading/memory rework below

### 0.2 Done — threading, capture and memory (details in fix.md)

- [x] Lossless raw wire capture (`.bhraw`) while logging, written by the
      capture worker; **Tools → Rebuild Decoded Log** regenerates the decoded
      log from it (byte-identical rows to the live log, tested)
- [x] `TimeSeriesBuffer` rewritten (contiguous, zero-copy, no duplicate
      cache): 200 signals × 100k samples 682 → 360 MB, full read 34.5 → 0.4 ms
- [x] Plot history = one memory budget shared by all signals (default 512 MB)
- [x] Table cells formatted once per 60 Hz flush, not per packet
- [x] Atomic `.xlsx` saves (`.partial` + rename) — no half-written logs
- [x] Benchmark harness `tools/bench_capture.py` (TCP loopback, no hardware);
      vs 11b7527 at 6000 fps: all frames shown instead of 72–77 %, 110–145 MB
      less memory; median GUI stall at 1000 fps 10.5 → 0.01 ms
- [x] Capture-in-a-separate-process implemented, tested, works in the frozen
      build (`Bytehound.exe --selftest-capture`) — **but slower than the
      thread at ≥3000 fps**, so it is opt-in/experimental; thread is default
- [x] `app/main.py` imports the GUI lazily (cheap child processes, faster
      `--validate`)
- [x] Full `pytest` on the final state: 565 passed, 0 failed (run twice)

### 0.3 Part A — Long-duration logging (highest risk for BMS labs)

Today one decoded `.xlsx` per session is compiled from a temp CSV on Stop.
Excel caps a sheet at 1,048,576 rows (~29 h at 10 Hz); a month is ~26 M rows
and the compile at Stop would take hours. **Decided: hourly CSV segments,
each also converted to `.xlsx` when it closes.**

- [ ] Session folder `<session>/seg_NNNN.csv` (+ `seg_NNNN.bhraw`), rotated
      every hour (configurable 15 min – 24 h) and at a size cap
- [ ] `session.json` manifest: app version, config fingerprint + config copy,
      start/end wall time, per-segment time range / rows / status / SHA-256;
      rewritten atomically after every rotation
- [ ] Each closed segment converted to `.xlsx` in the background (≤1 M rows
      by construction); never blocks capture or the next segment
- [ ] Absolute timestamps (UTC + local) in rows, not only elapsed ms — runs
      span DST changes and clock syncs
- [ ] Disk guard: warn below 10 GB free, stop logging cleanly below 2 GB
      (both configurable); never delete data automatically; free space in the
      status bar
- [ ] Crash / power-loss recovery per segment on next launch; manifest fixed
- [ ] **Behaviour change:** logging continues across auto-reconnects (new
      segment, gap recorded) instead of stopping — a USB glitch at 3 a.m.
      must not end a month-long log
- [ ] Soak test: time-compressed multi-day run checks rotation, manifest,
      disk guard, flat memory, no file-handle leaks

### 0.4 Part B — Analysis Suite for months of data

Today the whole log is read into pandas / float64 arrays: a month at 200
signals is ~40 GB, so it cannot open.

- [ ] Open a session folder / `session.json`, not only single files
- [ ] Per-segment summaries at segment close (per-second and per-minute
      min/max/mean per signal) so any session length opens in seconds
- [ ] Multi-resolution plotting: overview from summaries, full resolution
      loaded from segments only for the visible window when zoomed in
- [ ] Statistics, cursors and exports always use full-resolution data for the
      selected range (never summaries) — stated in the UI
- [ ] Wall-clock axis across segments; disconnect gaps drawn as gaps
- [ ] Export a time range → CSV / `.xlsx` (split at 1 M rows)
- [ ] Legacy single `.xlsx` / `.csv` logs keep opening as before
- [ ] Measured targets: 30-day session overview < 5 s, zoom window < 1 s,
      bounded memory

### 0.5 Part C — Canonical protocol configuration (protocol spec, phases 2–4)

Design (from the audit): the in-memory model already exists (`types.py`
dataclasses) and every format funnels into the same "tables of rows". The
canonical JSON is the typed, structured, **pre-array-expansion** form of
those tables, compiled to `FrameConfig` through the existing loader — so
live decode, Protocol Studio and the test bench share one decoder and
decoding is unchanged by construction. This JSON is also the C++ "JSON
Configuration Contract" (Phase 1 below); the Python app is the converter that
turns customers' Excel/CSV profiles into it.

- [ ] Versioned canonical JSON + documented schema
- [ ] Structural + semantic validation in-house (no `jsonschema` dependency):
      overlaps, bounds, duplicates, invalid scaling, missing frames, circular
      calc references
- [ ] JSON load/save, migrations, deterministic fingerprint (SHA-256 of
      canonical JSON) recorded in every log and session manifest
- [ ] CSV / xlsx / legacy-table-JSON / YAML import → canonical; export back
      without loss; document anything a format cannot hold
- [ ] Import preview (errors, warnings, added / modified / removed signals),
      explicit confirm; a failed import never replaces the active config;
      previous config kept for rollback
- [ ] Remove dead duplicate helpers in `config_loader.py` (lines 327–476: an
      older copy incl. a broken `_parse_protocol`; Python uses the later copy)
- [ ] Move the Ather-specific branch in `frame_decoder.py` (frame `0x101`,
      `Drive_Mode`, `Key_Switch`) out of the generic decoder into
      configuration — decode output must stay identical (regression test)
- [ ] Document or configure the silent clamp of small negatives to 0 when
      `min_value >= 0` (`frame_decoder.py`)
- [ ] CRC stays limited to `crc16_modbus`, `crc16_ccitt`, `crc32`, `none` —
      no invented parameters; schema covers exactly what is implemented

### 0.6 Part D — Protocol Studio (protocol spec, phase 5)

Builds on the existing Config Editor / Wizard (`config_editor.py`,
`config_wizard.py`, today `QTableWidget` over raw rows).

- [ ] Configuration management: open, import, save, save as, export,
      validate, revert, name/version, dirty state
- [ ] Model/view signal editor (`QAbstractTableModel` + delegates) with
      validation feedback
- [ ] Frame layout view: byte/bit map, overlaps, out-of-bounds, CRC config
- [ ] Decoder test bench: hex frames, `.bhraw` replay, raw / engineering
      values, CRC status, expected-value comparison — same decoder as live

### 0.7 Part E — Hardening and release

- [ ] Spec regression tests: CRC vectors, partial / concatenated / noisy
      frames, byte order, signed ints, bitfields, scaling, round-trips,
      failed-import rollback, migrations, decoder equivalence
- [ ] Full pytest, smoke tests, frozen-build check including templates and
      schemas in the package
- [ ] Docs: JSON format, import workflow, session/segment format, long-run
      operating guide for labs (disk sizing, rotation, recovery)
- [ ] Known limitations and required hardware validation listed

### 0.8 Part F — Zero frame loss on the serial path (BMS-critical)

Goal: **every byte the PC receives is either decoded into a frame or
accounted for**, every gap is recorded with a reason, and frames lost
*before* reaching the PC are detected where the protocol allows it. Nothing
is ever discarded silently. Audit of the current code (2026-10-16) found
these loss points:

| # | Where | What happens today | Fix |
|---|---|---|---|
| F1 | `serial_worker.py` `_reset_rx_state_for_polling_start` | Starting Auto-Fetch calls `reset_input_buffer()` and resets the parser — frames already in the OS buffer are **thrown away** | Drain and decode them (`_drain_pending_rx` already does this) instead of discarding; count them as "pre-poll frames" |
| F2 | `_run_loop` polling gate `not backpressured` | When the GUI falls behind, **polling stops** → the device is not asked → gaps in the log | Never pause polling for UI load; the UI decimates/coalesces instead. Logging and raw capture never depend on GUI speed |
| F3 | Parser resync / `_trim_if_overflow` | Noise bytes skipped while hunting for a header, and >1 MB unmatched buffers, are dropped **without being counted** (only a log line) | Per-parser `discarded_bytes` counter + reason; byte accounting `rx_bytes = framed_bytes + discarded_bytes + buffered_bytes` checked in tests and shown in the UI |
| F4 | `UdpSocketWrapper` `recv(4096)` | Datagrams > 4096 B error out (WSAEMSGSIZE) / truncate | Receive up to 64 KiB per datagram |
| F5 | TCP/UDP sockets | OS default receive buffer → **UDP drops under bursts** | Set `SO_RCVBUF` large (e.g. 4 MiB), verify the granted size, warn if smaller |
| F6 | `open()` purge | `reset_input_buffer()` on connect drops pre-connect bytes | Keep (no session yet), but log the byte count purged |
| F7 | Serial driver / USB-UART FIFO overrun | Invisible today | Windows: poll `ClearCommError` (`CE_OVERRUN`, `CE_RXOVER`, `CE_FRAME`, `CE_RXPARITY`) via ctypes and count/log each; elsewhere use what pyserial exposes |
| F8 | Worker thread scheduling | Normal priority — CPU load elsewhere can starve reads | Raise the capture thread priority (`QThread.TimeCriticalPriority` / highest), keep `timeBeginPeriod(1)`, recommend power plan + USB selective-suspend off in the lab guide |
| F9 | Bad-CRC / malformed frames | Counted, but not in the decoded log (bytes only in `.bhraw`) | Write rejected frames with reason to a per-segment `rejected.csv`; counts in the manifest |
| F10 | Decoded-log queue full (100k) | Drops rows (raw capture keeps bytes, rebuild recovers) | Raw capture on for every logging session (already); decoded drops counted in the manifest and the UI badge; rebuild offered automatically on Stop if any were dropped |
| F11 | Reconnect | Logging stops on unplug (Part A fixes) | Continue the session; record the gap (start/end, reason) in the manifest |
| F12 | Frames lost on the wire / in the device | Undetectable without protocol help | Optional per-frame **alive / sequence counter** signal in the config (E2E-style): gaps, repeats and resets counted per frame ID and logged |
| F13 | `TcpSocketWrapper.write` / UDP write | `socket.send()` may write only part of a buffer — **the rest of a TX command was lost** without an error | Send until every byte is out (with timeout), else raise |
| F14 | UDP on Windows | An ICMP "port unreachable" (device rebooting) arrives as `WSAECONNRESET` on the next read → treated as an unplug → **session ended** | Ignore the notice for UDP and keep reading |

Progress (each with a test that fails on the old code):
F1 ✅ F2 ✅ F3 ☐ F4 ✅ F5 ✅ F6 ☐ F7 ☐ F8 ☐ F9 ☐ F10 ☐ F11 ☐ (with Part A)
F12 ☐ F13 ✅ F14 ✅ — tests in `tests/test_polling_worker.py`
(`test_polling_start_delivers_waiting_frames_instead_of_discarding`,
`test_polling_continues_while_gui_is_backpressured`) and
`tests/test_frame_loss.py`. The UDP burst test shows the old code really
lost datagrams to the OS.

Done when:

- [ ] F1–F14 implemented, each with a regression test that would have failed
      before the fix
- [ ] Integrity counters per session and per segment in `session.json`:
      bytes received, frames OK per ID, CRC errors, discarded bytes + reason,
      driver overruns, poll timeouts, decoded-log drops, sequence gaps,
      disconnect gaps
- [ ] Live integrity panel / status-bar indicator; turns amber on any loss or
      gap, with the reason
- [ ] Stress test: TCP/UDP loopback at the maximum supported rate with
      injected noise, split and concatenated frames — every byte accounted
      for, every valid frame decoded and logged exactly once
- [ ] Hardware test plan: real USB-UART at 115200 / 921600 / 2 Mbaud for
      ≥24 h with a counter-stamped simulator; zero unexplained gaps
- [ ] Lab guide: power plan, USB selective suspend, antivirus exclusions for
      the log folder, disk sizing

### 0.9 Part G — UI/UX to industry standard (no glitches, no lag)

BMS manufacturers judge the tool by its polish. Target: behaves like
established measurement software (Vector CANalyzer/CANape, NI, PCAN-View) —
predictable menus, instant response, no visual glitches, readable at any DPI.

**Menus and commands** (today: File / Edit / View / Device / Tools / Help
exist; gaps below)

- [ ] File: New / Open / Open Recent ▸ / Save / Save As / Import ▸ /
      Export ▸ / Close Session / Exit — recent configs and sessions (the
      handler `_on_load_recent_config` exists but is not in the menu)
- [ ] Edit: Copy / Copy Table / Select All / Find (Ctrl+F) / Clear; Undo/Redo
      in editors
- [ ] View: every dock toggle, Full Screen (F11), Zoom In/Out/Reset, Theme ▸,
      Reset Layout
- [ ] Device: Connect / Disconnect, Start/Stop Polling, Start/Stop Logging,
      Logging Mode ▸ (event / fixed-step, Part H), Send Command…
- [ ] Tools: Protocol Studio, Analysis Suite, Rebuild Decoded Log, Decoder
      Test Bench, **Preferences** (one dialog with pages, replacing scattered
      Logging / Plot / Connect settings)
- [ ] Help: User Guide (F1), Keyboard Shortcuts, Check for Updates, Report
      Issue, Diagnostics, About
- [ ] Standard shortcuts everywhere (Ctrl+O/S/Shift+S/Q, F5 connect, Ctrl+L
      logging, Space pause) listed in Help → Keyboard Shortcuts; mnemonics
      on every menu; no non-standard separators in the menu bar itself
- [ ] Analysis Suite uses the same menu conventions as the main window

**Responsiveness (measured, not assumed)**

- [ ] Nothing slow on the GUI thread: config load, import, validation,
      exports, log conversion, session open — all background with progress +
      cancel
- [ ] Budgets enforced by the benchmark harness and a GUI-stall probe in CI:
      input-to-response < 100 ms, live update ≤ 100 ms behind data, no GUI
      stall > 50 ms at the rated frame rate during logging
- [ ] Zero flicker: no widget rebuilds on value updates, no style re-polish
      per update (the profile showed 6.4k polish/unpolish calls), no layout
      jumps when values change width (fixed-width numeric fonts/columns)

**Visual quality**

- [ ] One typography scale (font family, sizes, weights) and one spacing
      scale used by every window; tabular (monospace-digit) numbers in tables,
      cards, cursors
- [ ] Consistent icon set and colour semantics: OK / warning / fault /
      stale / disconnected the same everywhere (table, cards, plots, status)
- [ ] Light and dark themes both complete; high-DPI 100–200 %, 4K and
      multi-monitor (moving windows between DPIs) without blur or clipping
- [ ] Startup: exactly one window, no tiny floating window, no focus
      stealing; layout state versioned, corrupt layouts reset safely
- [ ] Number display: configured precision and units consistently in
      table, cards, plots, cursors, exports

**Interaction quality**

- [ ] Recoverable problems shown as toasts / status messages / the warning
      badge — modal dialogs only for decisions; audit the ~88 popup sites
- [ ] Every error message says what happened and what to do next
- [ ] Destructive actions confirm (clear data, overwrite file, stop a
      long log); long operations are cancellable
- [ ] Empty states with guidance (no config, not connected, no data yet)
- [ ] Keyboard-only operation and accessible names on all controls;
      sensible tab order in every dialog
- [ ] State remembered: window layouts, last config, column widths, plot
      selections, Analysis Suite session

**Verification**

- [ ] Screenshot review set (light/dark × 100/150/200 % DPI) for main window,
      every dialog, Analysis Suite, Protocol Studio
- [ ] UI walkthrough checklist run before each release

### 0.10 Part H — Fixed-step logging (sample on an exact time grid)

Labs often need one row every 0.1 s / 1 s exactly, regardless of when or how
often the BMS sends each frame (e.g. to align with a cycler or climate
chamber log). Today the decoded log is event-driven (one row per poll cycle).

- [ ] Logging mode: **Event** (current) or **Fixed step**; both can run
      together into separate files of the same session
- [ ] Step options 10 ms – 60 s (presets 0.1 s, 0.5 s, 1 s, 10 s) in Preferences
      and in the Start Logging dialog
- [ ] Driftless timing: row *n* is stamped at `t0 + n × step` on the
      monotonic clock, generated in the capture worker — never by a GUI
      timer, never accumulated sleeps; late ticks are emitted on catch-up with
      their exact grid time, never skipped
- [ ] Value policy per row: latest value of every signal (sample-and-hold),
      plus per-signal **age** (ms since the value arrived) and a **stale**
      flag when older than N steps (configurable, default 3); option to leave
      stale cells blank instead of holding
- [ ] Rows written even when nothing arrived (all stale) so the grid is
      complete; disconnects shown as stale rows + gap in the manifest
- [ ] Same session folder, segments, rotation, `.xlsx` per segment, disk
      guard and crash recovery as Part A; Analysis Suite opens it natively
- [ ] Metrics: tick jitter p50/p99/max and late ticks recorded per segment
- [ ] Tests: grid exactness over a simulated week (no drift), hold/age/stale
      behaviour, catch-up after a stall, equivalence of values with the event
      log at the same instants

### 0.11 Known gaps and follow-ups (don't lose these)

- **Hardware validation still required:** `smoke_headless.py` phases 2–10
  (live serial, polling, TX on the wire) need the Arduino BMS simulator on
  COM7 — not run in this cycle. Also a real multi-day soak on a lab PC.
- **Capture process follow-up:** to beat the thread it must send compact
  numpy batches (columnar) instead of pickled `DecodedFrame` objects.
- **Test suite touches real user settings:** GUI tests construct
  `MainWindow` with the real `QSettings("Bytehound", "Bytehound")`; isolate
  them in `conftest.py`.
- **Test suite takes ~31–37 min**, mostly GUI/theme tests — worth profiling.
- **Test process crashes on exit (code 139)** after all tests pass: access
  violation in the final garbage collection (PySide/Qt teardown order, no
  Python frame). Pre-existing on 11b7527. CI would read it as a failure —
  fix by deleting Qt objects before interpreter shutdown in `conftest.py`
  (e.g. `deleteLater` + process events in a session-scoped fixture), and
  check the app's own exit path for the same pattern.
- **Running two test suites at once is not safe** while tests use the real
  registry settings — `test_window_state_schema_version_discards_stale_blobs`
  failed from exactly that race. Same fix as the settings-isolation item.
- **Smoke tooling:** the offscreen launch smoke used this cycle lives in a
  scratch script; add it to the repo (`tools/`) next to `bench_capture.py`.
- `RawLogger` (CSV/xlsx raw log) is no longer used by the app; keep or remove
  deliberately once segments land.
- Dropped on purpose (see fix.md): float32 plot storage (uint32 counters
  lose precision), blocking serial reads (USB-CDC tuning, needs hardware),
  QThread pool consolidation, shared time column, numpy columnar decode.

### 0.12 Order of work

1. Commit the fix.md work; new branch for the rest.
2. **Part F (zero frame loss)** — smallest changes with the biggest risk
   reduction; must land before long runs are trusted.
3. **Part A (long-duration logging)** together with **Part H (fixed-step
   logging)** — they share the session/segment writer.
4. **Part B (Analysis Suite)**.
5. **Part G (UI/UX)** — responsiveness items alongside each part; the menu /
   Preferences / visual pass once A, B and H have added their commands.
6. Parts C → D (protocol configuration, Protocol Studio), then E.
7. Release: 0.1 blockers, frozen build, hardware validation, UI walkthrough.

### 0.13 How this feeds the C++ migration

| Python work | C++ plan section it defines |
|---|---|
| Canonical JSON + validator + fingerprint | Phase 1 *JSON Configuration Contract* — the Python app converts Excel/CSV profiles to it, so the C++ app stays JSON-only as planned |
| Session folder + CSV segments + `.bhraw` | Phase 3 *Logging* — same on-disk format, so both apps write and read the same sessions; `.xlsx` per segment is Python-only |
| Multi-resolution Analysis Suite | Phase 6 *Analysis Suite Rewrite* |
| `tools/bench_capture.py` numbers | Phase 0 baseline and the performance gates |
| `.bhraw` captures + rebuild | Golden fixtures for byte-for-byte parity tests |
| Part F byte/frame accounting + integrity counters | Phase 2 *Transport* completion criteria and the reliability gates — the C++ worker must report the same counters |
| Part H fixed-step logger in the capture worker | Phase 3 *Logging* — driftless grid logging is a C++ requirement too |
| Part G UI/UX standards and budgets | Phases 4–5 and the performance gates |
| Process-mode result | Evidence for the Phase 2 design: worker thread + batched immutable snapshots; avoid per-object serialisation across boundaries |

## Objective

Migrate Bytehound from Python/PySide6 to a native C++20 and Qt 6 desktop application with **performance, deterministic timing, and UI responsiveness as the primary goals**. Preserve configurable protocol decoding, serial/TCP/UDP I/O, CAN support, command transmission, polling, logging, live plotting, Analysis Suite, configuration tooling, and Windows packaging.

The migrated app must start cleanly, maintain predictable telemetry timing under load, stay responsive under high-rate telemetry, and never create the unwanted tiny floating `Bytehound` window seen during startup.

## Performance-First Rules

1. Serial receive, parsing, decoding, polling, logging, Excel/CSV loading, and export never run on the UI thread.
2. No unbounded queue, log document, or chart history is permitted.
3. Incoming data is processed immediately by workers; UI presentation is coalesced at a fixed rate.
4. Every subsystem has measured latency, throughput, memory, and queue-depth metrics.
5. A feature is not complete until it passes its performance budget as well as functional tests.

## Performance Execution Order

### 1. Worker-Owned Receive Pipeline

- Keep serial/TCP/UDP receive, stream parsing, frame decoding, and calculations in the telemetry worker.
- Emit decoded batches or immutable latest-value snapshots, never a Qt signal for every packet.

### 2. Fixed-Rate UI Coalescing

- Process UI updates every 50–100 ms (10–20 FPS) by default.
- Prefer a lower, stable UI update rate over attempting to paint every incoming packet.
- Keep receive/decode timing independent from UI frame timing.

### 3. Latest-Value-Only Widget Updates

- Retain only the latest update for each signal during an UI interval.
- Update tables, cards, parameter editors, TX readbacks, detail tabs, and plots only when their displayed value changed.
- Do not reapply stylesheets or call `setText()` when text is unchanged.

### 4. Bounded, Decimated Plotting

- Keep only the required visible-window history for live drawing.
- Downsample large series to display-resolution min/max points.
- Redraw charts at 10–20 FPS.
- Reuse plot widgets and curve objects; never rebuild a plot because a value, visibility flag, or colour changed.

### 5. Bounded Text Documents

- Cap the raw console and activity log at 500–2,000 lines.
- Append batched text at the UI update interval.
- Skip console formatting entirely while its dock is hidden.

### 6. Analysis Suite as a Background, Cached Pipeline

- Load logs in workers and show a reduced preview first.
- Cache parsed numeric columns and use decimated arrays only for drawing.
- Preserve full-resolution arrays for statistics and export.
- Update only the affected curve when a log, offset, visibility state, or parameter changes.

### 7. Remove Packet-Handler Allocation and Formatting Work

The packet hot path must avoid per-packet timestamps formatted as strings, repeated list/dictionary scans, stylesheet updates, unchanged widget writes, axis-range recalculation, and unnecessary array allocations.

### 8. Profile Every Change

Measure packet decoding, UI flush, packet handling, live redraw, Analysis Suite rebuild, and Excel/CSV loading. Keep before/after timing results with each performance change.

## Target Stack

| Area | Target |
|---|---|
| Language | C++20 |
| UI | Qt 6 Widgets |
| Charts | Qt Charts or QCustomPlot; choose after performance benchmark |
| Serial | Qt Serial Port |
| TCP / UDP | Qt Network |
| Runtime configuration | Versioned JSON schema validated with Qt Core APIs |
| CAN / Waveshare | Existing protocol implementation ported into a dedicated transport adapter |
| Build | CMake + Ninja/MSVC |
| Tests | Catch2 or GoogleTest + Qt Test |
| Installer | Existing Inno Setup flow, updated for the C++ executable |

## Architecture

```text
UI thread
  MainWindow / dock layout / tables / plots / Analysis Suite
       ↑ batched immutable telemetry snapshots
Telemetry worker thread
  transport read → parser → decoder → polling scheduler → TX priority queue
       ↓ bounded logging queue
Logger worker thread
  raw CSV / decoded CSV output
```

Rules:

- The UI thread must never parse packets, decode frames, read files, write logs, or rebuild charts for every packet.
- Workers communicate using bounded queues and batched Qt signals.
- UI updates are coalesced to 10–30 FPS, regardless of incoming packet rate.
- File loading, Analysis Suite processing, and export run outside the UI thread.

## Phase 0 — Measure the Current Baseline First

1. Record supported configuration schemas and wire formats from `instruction.md`.
2. Add golden test fixtures for framed serial, SLIP, HDLC, COBS, Waveshare CAN, CRC variants, TX commands, and polling.
3. Capture current acceptance screenshots and log-output examples.
4. Benchmark startup time, memory, packet throughput, packet-to-UI latency, TX scheduling jitter, UI frame rate, log throughput, and Analysis Suite load/render time.
5. Keep Python as the reference implementation until every C++ subsystem passes equivalent tests.

## Phase 1 — Pure Core Library

Create a Qt-independent `bytehound-core` library containing:

- Versioned JSON configuration types and validation.
- JSON as the only runtime configuration source.
- Packet builder and stream parsers.
- CRC implementations.
- Frame decoding, enums, bitfields, calculations, and warnings.
- TX command encoding and boolean bit packing.

Completion criteria:

- Golden packet/config tests match current Python outputs byte-for-byte.
- No GUI or filesystem code is allowed in protocol/decoder hot paths.
- Parser/decode benchmarks establish per-packet timing budgets before UI work begins.

### JSON Configuration Contract

- One human-readable `.json` file is the complete and only configuration format.
- Include `schema_version`, protocol, frames, signals, bitfields, enums, calculation groups, TX commands, serial defaults, and polling schedules.
- Validate the complete document before starting a connection; show one actionable validation report instead of runtime popups.
- Preserve comments/user notes through explicit JSON fields, not spreadsheet formatting.
- The C++ application contains no Excel/CSV configuration import, export, parsing, or spreadsheet dependency.
- Never parse XLSX or CSV in the application.

## Phase 2 — Transport and Scheduler

Implement `TelemetryWorker` using `QThread` or a worker `QObject` moved to a thread:

- `QSerialPort`, `QTcpSocket`, and `QUdpSocket` adapters.
- Bounded priority TX queue.
- Fair round-robin polling.
- Boot grace period, watchdog, disconnect detection, retry/backoff, metrics.
- Decode packets in the worker and emit batches of latest values.

Completion criteria:

- Sustains the target device baud rate without UI involvement.
- Queue overflow is counted and surfaced, never causes unbounded memory growth.
- Priority TX preempts polling within a defined, tested latency budget.
- Polling intervals are measured for average error, worst-case error, and jitter.

## Phase 3 — Logging

Implement a dedicated logger worker with bounded queues:

- Raw packet CSV logging.
- Decoded wide-format CSV log output.
- Crash-safe temporary files and recovery.
- Rate-limited flushes and explicit shutdown drain handling.

Completion criteria:

- Logging cannot block serial receive or the UI.
- Long tests do not grow the console/activity document or memory indefinitely.
- Backpressure is measurable; a slow disk cannot silently increase memory or delay polling.

## Phase 4 — Main Qt UI

Rebuild the main UI with model/view components:

- `QAbstractTableModel` for telemetry; only changed rows emit `dataChanged`.
- Dock widgets for plots, bitfields, enums, TX commands, editor, console, and activity log.
- Fixed-rate UI update timer that applies latest telemetry snapshots.
- Bounded console and activity buffers.
- Lazy creation of optional panels, editors, and Analysis Suite.

### Mandatory Startup Window Fix

The screenshots show a blank, tiny top-level `Bytehound` window caused by restoring a floating dock/layout state during startup.

The C++ app must:

1. Create all docks docked and hidden/visible in a known default layout.
2. Restore only validated geometry after the main window is shown.
3. Never restore a floating dock automatically at startup.
4. Version the saved layout schema; discard incompatible or corrupt layouts.
5. Provide **View → Reset Layout** to clear settings deliberately.
6. Use non-modal status/toast feedback for recoverable startup events.
7. Avoid any `show()` call on a dock while applying saved state.

Completion criteria:

- Repeated cold starts create exactly one top-level application window.
- No blank, floating, modal, or focus-stealing startup windows.
- Main window becomes interactive before optional configuration, dashboard, and log-recovery work completes.

## Phase 5 — High-Performance Live Plotting

- Retain full telemetry only when needed for logging; retain a bounded display history for live plots.
- Downsample to pixel-appropriate min/max data before drawing.
- Redraw at 15–30 FPS maximum.
- Recompute axis ranges at a low fixed rate, never per packet.
- Do not recreate curves/widgets when data merely changes.

Completion criteria:

- UI remains interactive at sustained high packet rates.
- Multi-signal plots remain smooth during long sessions.
- Plot redraw time stays inside its frame budget; dropped redraws are preferable to blocking telemetry.

## Phase 6 — Analysis Suite Rewrite

- Parse logs in background workers.
- Cache loaded files and precompute numeric columns once.
- Render decimated plot data; retain source arrays for export/statistics.
- Update only changed curves when toggling a log, offset, or parameter.
- Debounce statistics, auto-fit, crosshair, and cursor updates.
- Use non-modal status feedback for recoverable file/export errors.

Completion criteria:

- Large logs load without freezing the app.
- Pan/zoom, cursor readout, overlay, export, and statistics remain responsive.
- Analysis operations publish progress and remain cancellable.

## Phase 7 — Configuration Tools and Feature Parity

Port:

- Configuration editor and protocol wizard.
- JSON configuration editor with schema-aware validation and formatting.
- Built-in JSON presets and JSON template generation.
- Parameter editor and TX commands.
- Diagnostics, user guide, updater wiring, reporting, and theme support.

Each feature moves only after a testable core API exists.

## Phase 8 — Packaging and Release

1. Build signed Windows binaries with CMake presets.
2. Package using Inno Setup.
3. Migrate settings under a new C++ application/version namespace, with safe import of compatible user settings only.
4. Run hardware smoke tests against the MCU simulators and real COM devices.
5. Release a beta alongside the Python version, then switch only after parity and performance gates pass.

## Performance, Timing, and Reliability Gates

| Metric | Gate |
|---|---|
| Startup | Main window visible in under 1 second on the release reference PC; configuration loads asynchronously afterward |
| Startup windows | Exactly one top-level Bytehound window |
| UI rate | Coalesced updates at 20–30 FPS; no UI work per incoming packet |
| Packet-to-worker latency | Measure and publish p50/p95/p99 from received byte to decoded frame |
| Packet-to-UI latency | Latest value visible within 100 ms at normal load; stale updates may be discarded rather than queued |
| Priority TX latency | Command leaves the worker queue within one worker iteration; timing verified under polling load |
| Polling jitter | Track and enforce a defined maximum jitter per configured interval |
| Parser/decode cost | Bounded benchmark per packet/frame; no heap-heavy work in the hot path |
| Memory | Bounded UI queues, console buffers, and display histories |
| Serial | No UI-thread I/O or decode work |
| Logging | Async and bounded; never blocks telemetry worker |
| Analysis Suite | Background loading, decimated plotting, cancellable long operations, responsive pan/zoom |
| Layout | Corrupt/stale settings fall back to a safe docked layout |

## Delivery Sequence

1. `bytehound-core` with parity tests.
2. Transport/scheduler/logger benchmark executable.
3. Main UI with live telemetry and startup-layout fix.
4. Live plotting and TX/editor parity.
5. Analysis Suite.
6. Config wizard/editor, installer, hardware validation, beta release.

## Migration Safety

- Do not remove the Python application until the C++ version passes the same configuration, packet, logging, and hardware tests.
- Keep test fixtures and expected decoded outputs shared between both implementations.
- Use feature flags during beta so users can fall back to the Python build if a protocol/configuration edge case is found.
- Convert existing profiles to JSON outside the C++ application before beta deployment, then compare protocol/decoder output against the original profiles during validation.
- Store every new raw and decoded session as CSV only; the C++ application has no XLSX logging dependency.

## Current Python Production Baseline

The `single_cell_cycler` Python application remains the validated production baseline while migration planning continues. Its release package includes the serial reconnect watchdog, rotating asynchronous logs, webhook retries, BMS alert identity, and tested PySide6 plot/metrology surfaces.
