# Bytehound C++ Migration Plan

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
