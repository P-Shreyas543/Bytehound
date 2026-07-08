?# Bytehound — Developer Specification

This document is a **build-from-scratch blueprint** for the Bytehound.
A developer (or coding agent) given only this file and the listed dependencies
should be able to reproduce the app: same architecture, same protocol, same
config schema, same UI panels, same file formats, and same packaged binary.

It is *not* a user manual. For end-user instructions, see [app/resources/index.html](app/resources/index.html).

---

## Table of Contents

1. [Application Overview](#1-application-overview)
2. [Branding & Logo Files](#2-branding--logo-files)
3. [Goal & Non-Goals](#3-goal--non-goals)
4. [Tech Stack](#4-tech-stack)
5. [Project Layout](#5-project-layout)
6. [Runtime Architecture & Data Flow](#6-runtime-architecture--data-flow)
7. [Configuration Schema (Excel / CSV)](#7-configuration-schema-excel--csv)
8. [Protocol Layer](#8-protocol-layer)
9. [Decoder Pipeline](#9-decoder-pipeline)
10. [Serial I/O & Polling Engine](#10-serial-io--polling-engine)
11. [TX Commands & Parameter Editor](#11-tx-commands--parameter-editor)
12. [Logging Formats](#12-logging-formats)
13. [Advanced UI/IO Control & Performance](#13-advanced-uiio-control--performance)
14. [UI Specification](#14-ui-specification)
15. [Analysis Suite](#15-analysis-suite)
16. [Auto-Updater](#16-auto-updater)
17. [Settings Persistence](#17-settings-persistence)
18. [Packaging & Build](#18-packaging--build)
19. [Testing Requirements](#19-testing-requirements)
20. [Acceptance Criteria](#20-acceptance-criteria)

---

## 1. Application Overview

| Property              | Value                                              |
|-----------------------|----------------------------------------------------|
| **App Name**          | Bytehound                                     |
| **Developer**         | Shreyas P                                          |
| **Version**           | 0.4.2 (sourced from [version.json](version.json))  |
| **Platform**          | Windows 10 / 11 (x64). Code is cross-platform but the shipped binary targets Windows. |
| **Window Size**       | 1400 × 900 px                                      |
| **Window Title**      | `Bytehound v<Version>` (e.g. `Bytehound v0.1.0`) |
| **Executable Name**   | `Bytehound.exe`                            |
| **Logging Format**    | `*_raw.csv` (timestamped hex frames, streamed) + `*_decoded.xlsx` (two sheets: `Metadata` key/value + `Data` per-signal scaled values; finalised on Stop). See §12. |
| **Plotting Library**  | pyqtgraph (live plot in main window + Analysis Suite) |
| **Settings Storage**  | `QSettings("Bytehound", "Bytehound")` → Windows registry `HKCU\Software\Bytehound\Bytehound` |
| **Update Manifest**   | `manifest_url` field in [version.json](version.json) |

---

## 2. Branding & Logo Files

All branding assets live in [branding/](branding/) at the repo root and are
copied next to `Bytehound.exe` after every build by [build.py](build.py).
They are **not** bundled via the PyInstaller spec's `datas` (see §18 for why).

| File             | Size                                  | Purpose                                                              | Used By                                  |
|------------------|---------------------------------------|----------------------------------------------------------------------|------------------------------------------|
| `logo_sq.ico`    | 256×256 (with 16/32/48/64/128 frames) | Window icon, taskbar icon, exe icon, installer icon                  | `app/main.py`, `app/ui/main_window.py`, future `installer.iss` |
| `logo_sq.png`    | 512×512                               | PNG fallback for renderers that don't accept `.ico`                  | About box / future plugin UIs            |
| `logo_rec.png`   | ~512×200                              | Rectangular logo for in-window banners (top-right control bar)       | Future GUI banners                       |
| `Documentation/` | —                                     | Project documentation (optional)                                     | Reference                                |

Asset resolution order at runtime (in `_find_logo()` in
[app/ui/main_window.py](app/ui/main_window.py)):

1. `<root>/branding/<name>` — preferred
2. `<root>/<name>` — fallback (matches build.py's copy target)

Where `<root>` is the repo root in dev mode and the directory containing
`Bytehound.exe` in a frozen build.

A `.gitignore` at the repo root excludes `__pycache__/`, `build/`, `dist/`,
`installer_output/`, `*.pyc`, virtual envs, editor metadata, and scratch
directories. Branding files themselves are tracked.

---

## 3. Goal & Non-Goals

**Goal.** A hardware-agnostic desktop telemetry/control dashboard that:

- Connects to a serial port (UART/USB).
- Parses framed packets *or* Modbus RTU using a user-supplied Excel/CSV
  config — no Python edits required.
- Decodes raw bytes into named, scaled engineering values, enums, and
  bitfields.
- Visualizes data live (table + plot) and lets the user send commands and
  edit parameters back to the device.
- Records sessions with per-byte fidelity for later offline analysis.

**Non-Goals.**

- No CAN, Ethernet, MQTT, or BLE transport.
- No firmware flashing.
- No authentication, accounts, or cloud sync.
- No Linux/Mac packaging targets (the app must *run* cross-platform but the
  shipped binary is Windows-only).

---

## 4. Tech Stack

Pinned in [requirements.txt](requirements.txt):

| Dependency        | Version    | Purpose                              |
|-------------------|------------|--------------------------------------|
| Python            | 3.10+      | Runtime                              |
| PySide6           | 6.6 – <7   | Qt GUI (use PySide6 *only*)          |
| pyserial          | ≥ 3.5      | Serial port I/O                      |
| pyqtgraph         | ≥ 0.13     | Live plot + analysis-suite plots     |
| pandas + openpyxl | ≥ 2.1, 3.1 | Excel config read/write              |
| pyqt-darktheme    | ≥ 1.3      | Light/dark theme                     |
| pytest            | ≥ 8.0      | Tests                                |
| numpy             | (transitive) | Plot data                          |

**Hard constraint:** the app must *not* import PyQt5/PyQt6/PySide2 at any
point. The PyInstaller spec excludes them; introducing one breaks the
frozen build.

---

## 5. Project Layout

```
Bytehound/
├── app/
│   ├── main.py                         # entry point
│   ├── commands/
│   │   └── tx_command_builder.py       # encode user inputs -> TX packet bytes
│   ├── decoder/
│   │   ├── types.py                    # frozen dataclasses for the config schema
│   │   ├── config_loader.py            # parse Excel / CSV config -> FrameConfig
│   │   ├── frame_decoder.py            # payload bytes -> DecodedFrame
│   │   ├── calculations.py             # min/max/diff/sum/avg group calcs
│   │   └── template_io.py              # export blank template + snapshot config
│   ├── protocol/
│   │   ├── crc.py                      # CRC16/MODBUS, CRC16/CCITT, CRC32
│   │   ├── packet_parser.py            # framed + Modbus RTU stream parsers
│   │   └── packet_builder.py           # mirror of parser, for TX
│   ├── serial_io/
│   │   └── serial_worker.py            # QThread: open port, poll, RX/TX
│   ├── serial_logging/
│   │   ├── raw_logger.py               # CSV writer: timestamp,direction,hex,delta_t_ms
│   │   └── decoded_logger.py           # xlsx writer: Metadata + Data sheets
│   ├── ui/                             # Qt UI layer (fully modularized)
│   │   ├── main_window.py              # QMainWindow coordinator & window events
│   │   ├── ui_builders.py              # dock, widget, and menu bar assembly
│   │   ├── theming.py                  # client styling & native OS titlebar
│   │   ├── telemetry_model.py          # custom table model for main data grid
│   │   ├── telemetry_pipeline.py       # 60 Hz GUI thread-safe flush pipeline
│   │   ├── plot_orchestration.py       # live plot orchestration & coordinate math
│   │   ├── plot_panel.py               # PlotPanel state & TimeSeriesBuffer store
│   │   ├── parameter_editor.py         # write parameter editor table
│   │   ├── tx_panel.py                 # dynamic command buttons & popup forms
│   │   ├── detail_tabs.py              # bitfields & enums detail lists
│   │   ├── polling_session.py          # auto-fetch trigger & sidebar managers
│   │   ├── logging_session.py          # start/stop logging handlers
│   │   ├── config_loader.py            # UI config file/mapper selectors
│   │   ├── popups.py                   # unified dialog boxes wrapper
│   │   ├── widgets.py                  # WarningBadge, FrameFormatWidget, StatusBadgeDelegate
│   │   ├── dialogs.py                  # modal settings & mapper dialog definitions
│   │   ├── analysis_suite.py           # post-test multi-log visualizer window
│   │   ├── analysis_widgets.py         # cursors, readouts, stats widgets
│   │   ├── analysis_theme.py           # Analysis Suite plot color palette
│   │   ├── xy_plot.py                  # X-Y scatter plotter w/ linear regression
│   │   ├── log_io.py                   # thread-safe background log file ingestion
│   │   ├── updater.py                  # updater background threads
│   │   └── updater_wiring.py           # updater GUI controller & installer launcher
│   └── resources/
│       ├── index.html                  # in-app docs (View → Documentation)
│       └── sample_raw_log.txt          # bundled sample log
├── tests/                              # pytest suite (see §19)
├── version.json                        # local version + update manifest pointer
├── requirements.txt
├── Bytehound.spec                      # PyInstaller spec
├── build.py                            # convenience wrapper around PyInstaller
├── smoke_com7.py                       # optional serial decode smoke test (requires hardware)
├── smoke_headless.py                   # optional headless integration smoke test (requires hardware)
├── smoke_stress.py                     # 13-phase stress harness (requires MCU BMS simulator)
└── instruction.md                      # this file
```

Module boundary rules:

- `app/decoder/` — pure functions, no Qt, no I/O; safe to unit-test in isolation.
- `app/protocol/` — pure functions, no Qt, no I/O.
- `app/commands/` — pure; depends only on `decoder` + `protocol`.
- `app/serial_io/` — Qt + I/O; emits signals into the UI.
- `app/serial_logging/` — file I/O only; no Qt.
- `app/ui/` — the only place Qt widgets live.

---

## 6. Runtime Architecture & Data Flow

### Threading model

- **Main thread:** Qt event loop, all widgets.
- **Worker thread (`PollingWorker(QThread)`):** owns the `serial.Serial`
  handle, runs the polling/TX/RX loop, emits signals back to the UI.
- **UpdateChecker / UpdateDownloader:** transient `QThread`s for the updater.
- **AnalysisLoader (in analysis_suite):** `QThread` for Excel ingestion so the
  live test is never blocked.

The UI **never** touches the serial port directly. All RX/TX flows through
signals/slots.

### RX path (incoming bytes)

```
serial.Serial.read(in_waiting)
    └─> ParserProtocol.feed(bytes)              # FramedParser or ModbusRtuParser
         └─> ParsedPacket  (raw, frame_id, payload, ok, error)
              └─> PollingWorker.packet_received signal
                   └─> MainWindow._on_packet_received
                        ├─> RawLogger.log("RX", raw, delta_t_ms)
                        ├─> decode_frame(config, frame_id, payload) -> DecodedFrame
                        ├─> DecodedLogger.log_frame(frame_no, decoded)
                        └─> update table / bitfield / enum widgets / plot history
```

### TX path (outgoing bytes)

```
User clicks TX button or edits a parameter
    └─> build_tx_command(config, name, values)
         └─> build_packet(protocol, frame_id, payload)   # builds full wrapped packet
              └─> PollingWorker.enqueue_priority_tx(bytes)
                   └─> worker thread writes serial, emits tx_recorded
                        └─> MainWindow logs "TX" + appends to raw console
```

Priority TX always preempts the polling schedule for the next loop iteration.

---

## 7. Configuration Schema (Excel / CSV)

The config drives everything. It is loaded from either:

- A single `.xlsx`/`.xlsm` workbook with one sheet per table, **or**
- A directory containing one `.csv` per table.

`load_config(path)` in [app/decoder/config_loader.py](app/decoder/config_loader.py)
auto-detects which.

Sheet names are normalized: lowercase, non-alphanumeric → `_`, with these
aliases:

| Excel sheet         | Internal name        |
|---------------------|----------------------|
| `FrameVariables`    | `variables`          |
| `FrameConfig`       | `frame_config`       |
| `CalcGroups`        | `calc_groups`        |
| `TxCommands`        | `tx_commands`        |
| `TxCommandFields`   | `tx_command_fields`  |
| `SerialDefaults`    | `serial_defaults`    |
| `PollingSchedule`   | `polling_schedule`   |

### 5.1 `protocol` (required, exactly one enabled row)

| Column                  | Type    | Notes                                                  |
|-------------------------|---------|--------------------------------------------------------|
| `profile_name`          | str     | Free text                                              |
| `header_hex`            | hex     | Required, non-empty (e.g. `AA 55`)                     |
| `frame_id_size`         | int     | Bytes                                                  |
| `frame_id_byte_order`   | enum    | `big` \| `little`                                      |
| `length_size`           | int     | Bytes                                                  |
| `length_meaning`        | enum    | Only `payload_only` is supported                       |
| `crc_type`              | enum    | `crc16_modbus` \| `crc16_ccitt` \| `crc32` \| `none`   |
| `crc_size`              | int     | Bytes                                                  |
| `crc_byte_order`        | enum    | `big` \| `little`                                      |
| `crc_coverage`          | enum    | Only `header_to_payload` is supported                  |
| `footer_hex`            | hex     | Optional                                               |
| `escape_mode`           | enum    | Only `none` is supported                               |
| `raw_log_format`        | str     | `hex` (spaced) or `compact` (contiguous) — drives RawLogger hex column |
| `enabled`               | bool    | Default true                                           |
| `parser_type`           | enum    | `framed` (default) \| `modbus_rtu`                     |
| `tx_pad_length`         | int?    | Pad TX to this many bytes (optional)                   |
| `inter_frame_delay_ms`  | int     | Default 10                                             |

### 5.2 `frames` (optional when `variables` is present)

| Column           | Type | Notes                                  |
|------------------|------|----------------------------------------|
| `frame_id`       | hex  | e.g. `0x10` or `10`                    |
| `frame_name`     | str  | Display name                           |
| `payload_length` | int? | If set, decoder warns on mismatch      |
| `direction`      | str  | `rx` (default)                         |
| `enabled`        | bool | Default true                           |
| `description`    | str  | Optional                               |

If `frames` is omitted, frame definitions are auto-derived from `variables`.

### 5.3 `variables` (preferred schema)

| Column          | Type  | Notes                                                                                  |
|-----------------|-------|----------------------------------------------------------------------------------------|
| `id_or_address` | hex   | Frame ID (framed) or register address (Modbus)                                         |
| `signal_name`   | str   | Required, unique within frame                                                          |
| `data_type`     | enum  | `uint8 \| int8 \| uint16 \| int16 \| uint32 \| int32 \| float32 \| float64`            |
| `count`         | int   | Default 1; >1 expands into `name 1`, `name 2`, … with consecutive byte offsets         |
| `byte_order`    | enum  | `little` (default) \| `big`                                                            |
| `scale`         | float | Default 1.0                                                                            |
| `offset`        | float | Default 0.0                                                                            |
| `unit`          | str   | Display unit                                                                           |
| `group`         | str   | Used by `calc_groups`                                                                  |
| `register_type` | str   | Modbus register class (informational)                                                  |
| `read_write`    | str   | `R` (default) \| `W` \| `RW`                                                           |
| `min_value`     | float?| For UI clamping                                                                        |
| `max_value`     | float?| For UI clamping                                                                        |
| `description`   | str   | Optional                                                                               |
| `enabled`       | bool  | Default true                                                                           |

`start_byte` is **computed**: signals within a frame are packed in declared order.

### 5.4 Legacy `frame_config` (kept for backward compat)

Flat table with explicit `start_byte`, `byte_length`, `endianness`,
`data_type` ∈ `{int, uint, float}`. Loader uses this only if `variables` is
absent.

### 5.5 `bitfields`

| Column          | Type | Notes                                          |
|-----------------|------|------------------------------------------------|
| `id_or_address` | hex  | Frame ID                                       |
| `signal_name`   | str  | Must reference an existing variable            |
| `bit_index`     | int  | 0..N-1                                         |
| `label`         | str  | Bit name shown in UI                           |
| `active_text`   | str  | Default `ON`                                   |
| `inactive_text` | str  | Default `OFF`                                  |

### 5.6 `enums`

| Column          | Type | Notes                              |
|-----------------|------|------------------------------------|
| `id_or_address` | hex  | Frame ID                           |
| `signal_name`   | str  | Must reference an existing variable|
| `value`         | int  | Raw integer                        |
| `label`         | str  | Display label                      |

### 5.7 `calc_groups`

| Column         | Type  | Notes                                         |
|----------------|-------|-----------------------------------------------|
| `group_name`   | str   | Must match a `group` used by ≥1 variable      |
| `operations`   | str   | Pipe-separated subset of `min\|max\|diff\|sum\|avg` |
| `unit`         | str   | Optional                                      |
| `frame_id`     | hex?  | Restrict to one frame                         |
| `enabled`      | bool  | Default true                                  |

### 5.8 `tx_commands`

| Column         | Type  | Notes                                                          |
|----------------|-------|----------------------------------------------------------------|
| `command_name` | str   | Unique, used as the TX button label                            |
| `id_or_address`| hex   | Frame ID for the outgoing packet                               |
| `payload_hex`  | hex   | Static payload prefix (optional, may be empty)                 |
| `description`  | str   | Optional                                                       |
| `enabled`      | bool  | Default true                                                   |

### 5.9 `tx_command_fields`

| Column        | Type   | Notes                                                   |
|---------------|--------|---------------------------------------------------------|
| `command_name`| str    | FK to `tx_commands.command_name`                        |
| `signal_name` | str    | Field label                                             |
| `data_type`   | enum   | Same set as `variables.data_type`                       |
| `byte_order`  | enum   | `little` (default) \| `big`                             |
| `scale`       | float  | Default 1.0                                             |
| `offset`      | float  | Default 0.0                                             |
| `unit`        | str    |                                                         |
| `min_value`   | float? | Enforced at encode time                                 |
| `max_value`   | float? | Enforced at encode time                                 |
| `default`     | float? | Pre-fill value                                          |

Encoded as: `raw = round((user_value - offset) / scale)` then packed as the
declared int/float type. Float fields use `struct.pack`.

### 5.10 `serial_defaults`

`baud_rate, data_bits, stop_bits, parity, timeout_ms` — single row, optional.

### 5.11 `polling_schedule`

| Column          | Type | Notes                                                    |
|-----------------|------|----------------------------------------------------------|
| `id_or_address` | hex  | Target frame ID (framed) or register addr (Modbus)       |
| `interval_ms`   | int  | Polling cadence                                          |
| `timeout_ms`    | int  | Per-request response wait                                |
| `enabled`       | bool | Default true                                             |

### Validation rules (loader must enforce)

- Exactly one enabled `protocol` row.
- All required columns present per table.
- `bitfields`/`enums`/`calc_groups` must reference known variables/groups.
- Within a frame, signals must not overlap in byte range.
- Duplicate signal names within a frame → `ConfigError`.

Errors are raised as `ConfigError(ValueError)` with a row-numbered message.

---

## 8. Protocol Layer

### 6.1 Framed parser

Wire format:

```
[ header ][ frame_id (N bytes, big/little) ][ length (M bytes) ][ payload (length bytes) ][ CRC ][ footer? ]
```

Algorithm (`FramedParser._try_parse_one`):

1. If buffer < `len(header)`, return `(None, 0)` (need more data).
2. If `header` not in buffer, drop everything except the trailing `len(header)-1`
   bytes (might be a partial header).
3. If header isn't at offset 0, skip to it.
4. If buffer < fixed header+id+length+crc+footer, wait.
5. Read declared `payload_length`; if buffer < total, wait.
6. Compute CRC over `header..end-of-payload`; compare against received CRC.
7. Verify footer if present.
8. On any mismatch, emit `ParsedPacket(ok=False, error=...)` and **advance by 1 byte**
   (resync). On success, advance by full frame size.

### 6.2 Modbus RTU parser

Lightweight implementation supporting function codes 3, 4, 6, 16 and exception
responses (FC ≥ 0x80). CRC is fixed at CRC16/MODBUS, byte order little-endian.
Parser returns the slave address as `frame_id`; the worker rewrites it to the
register address for downstream decoding.

### 6.3 CRC implementations ([app/protocol/crc.py](app/protocol/crc.py))

- `crc16_modbus` — poly 0x8005 reflected (effective 0xA001), init 0xFFFF.
- `crc16_ccitt` — CCITT-FALSE, poly 0x1021, init 0xFFFF.
- `crc32` — `zlib.crc32`.
- `none` — returns 0, never validated.

### 6.4 Packet builder ([app/protocol/packet_builder.py](app/protocol/packet_builder.py))

Mirror of the parser. Inputs: `ProtocolConfig`, `frame_id`, `payload`. Output:
fully wrapped bytes ready to write to the wire.

For Modbus, `build_modbus_packet`:

- Empty payload → FC 03 read, qty=1.
- 2-byte payload → FC 06 single-register write.
- Larger payload → FC 16 multi-register write.

`tx_pad_length` (if set) zero-pads `coverage` (header..payload) before CRC so
every TX frame is exactly `tx_pad_length` bytes on the wire — required for
MCUs that use buffer-full / DMA-complete RX interrupts (`HAL_UART_Receive_IT`).
CRC is computed *over* the padding, so the receiver's checksum still validates.

Validation (raised as `ValueError`, caught by `CommandBuildError` upstream):

- `tx_pad_length < crc_size + len(footer)` → no room for CRC, rejected.
- Built frame > `tx_pad_length` → command is too big to fit, rejected with the
  offending frame ID and actual byte count so the user can either raise
  `tx_pad_length` or shrink the command payload.

Silent oversize sends are not allowed — better to error loudly than confuse
a buffer-full RX firmware with a frame that's too long.

---

## 9. Decoder Pipeline

`decode_frame(config, frame_id, payload) -> DecodedFrame` is pure.

1. Look up `signals_by_frame[frame_id]`. Unknown ID → `DecodedFrame(error=...)`.
2. For each `SignalSpec`:
   - Slice `payload[start_byte:end_byte]`. Short payload → `status="Payload too short..."`.
   - Decode raw:
     - `float` → `struct.unpack` `<f`/`<d` (or `>f`/`>d`).
     - `int`/`uint` → `int.from_bytes(byteorder, signed=...)`.
   - `scaled = raw * scale + offset`.
   - Look up enum label (by `(frame_id, source_name or signal_name)`).
   - Decode bitfield map (only for int raw values).
   - Compose `display_value`: enum label > active bit names > formatted scaled.
3. After all signals, run `_calculate_groups`:
   - For each `CalcGroupSpec` whose `frame_id` matches (or is None), aggregate
     scaled values from signals in that group; emit a synthetic
     `DecodedSignal(is_calculated=True)`.
4. Emit warnings for payload-length mismatches and trailing extra bytes.

Output dataclasses:

```python
@dataclass
class DecodedSignal:
    frame_id, frame_name, signal_name
    raw_value, scaled_value, unit, status
    group, index, enum_label, bit_values
    display_value, is_calculated

@dataclass
class DecodedFrame:
    frame_id, frame_name
    signals: list[DecodedSignal]
    calculations: list[DecodedSignal]
    warnings: list[str]
    error: str | None
```

---

## 10. Serial I/O & Polling Engine

`PollingWorker(QThread)` in [app/serial_io/serial_worker.py](app/serial_io/serial_worker.py).

### Signals

- `packets_received(list[ParsedPacket])` — batched, one emit per worker iteration
- `metrics_updated(int timeouts, int crc_errors, int rx_bytes)`
- `error_occurred(str)`
- `tx_recorded(bytes)`
- `connection_lost()` — USB physically unplugged
- `device_timeout()` — connected but no data for the watchdog window (debounced)

### Construction

```python
PollingWorker(SerialSettings, ProtocolConfig, list[PollingScheduleSpec])
```

Schedules are stored as `{spec, next_run, enabled}` so the UI can toggle
individual schedule rows at runtime via `toggle_schedule(target_id, enabled)`.

### Run loop (`run()`)

Each iteration, **in this priority order**:

1. **Priority TX**: drain at most one entry from the priority TX queue, write
   it, emit `tx_recorded`. For Modbus, block briefly to await the response so
   the next request doesn't collide.
2. **Polling**: if `_polling_global_enabled` is true *and* the boot-grace gate
   has cleared (see below), scan the schedule list **round-robin** starting at
   `_sched_cursor`, find the first enabled schedule whose `next_run <= now`,
   send its request, await response (or time out), advance `_sched_cursor`
   past it, and reschedule. Only one poll per loop iteration to interleave
   with priority TX.
3. **Drain RX**: if no poll happened, read whatever is in the input buffer,
   feed the parser, emit `packets_received` (batched) for the iteration.
4. **Watchdog**: every iteration, debounce `device_timeout` if `_rx_bytes`
   has been flat for `WATCHDOG_SILENCE_MS` ms.
5. Sleep 10 ms.

### Round-robin polling cursor

`_sched_cursor: int` is an index into `_schedules`. The polling scan starts at
this index and wraps. After a successful poll, the cursor advances to the
*next* index so the following iteration begins one step further down the list,
not back at index 0.

This guarantees **fairness** when multiple schedules are due simultaneously:
without the cursor, a fast schedule near the top of the list (or a dummy
frame whose poll blocks for the full `timeout_ms` while earlier schedules
become re-due) could starve schedules near the tail indefinitely. The
classic symptom was the last `polling_schedule` row never getting a TX even
though it was enabled — verified in the field with a five-schedule config
where the fifth frame ID was never queried. With the cursor, every enabled
schedule is visited in turn; only intervals (not list position) determine
poll frequency.

Toggling a schedule via `toggle_schedule(target_id, enabled)` does not shift
the cursor — disabled entries are simply skipped on the next pass.

Counters: `_timeouts`, `_crc_errors`, `_rx_bytes` are emitted via
`metrics_updated` after each batch. `reset_metrics()` (mutex-guarded) zeroes
all three so *Edit → Clear* and *Import Config* start from a clean slate.

### Boot-grace gate

`POLLING_BOOT_GRACE = 2.5` seconds. After `open()` succeeds, polling stays
suppressed until *either* the first RX byte arrives *or* the grace expires.
This prevents the worker from hammering an MCU-style device that auto-
resets on DTR (USB-CDC bootloader window is ~1.5 s) and getting stuck with a
silent link. NXP/STM32 boards that don't auto-reset clear the grace
immediately on the first response.

### Bounded TX queue

The priority TX queue is `queue.Queue(maxsize=256)`. `enqueue_priority_tx`
uses `put_nowait` and emits `error_occurred("TX queue full")` if a flood of
writes outpaces the wire — instead of unbounded memory growth.

### Failed-schedule disable

If `build_packet` raises `ValueError` for a poll target (e.g. the user
loaded a config whose `polling_schedule` references a frame ID with no
`tx_pad_length` and no payload), `_disable_failed_schedule(target_id)` flags
that row as disabled for the rest of the session and logs the reason. This
keeps a single bad row from flooding the error log every cycle.

`available_ports()` wraps `serial.tools.list_ports.comports()` for the UI's
port combo.

### Unsolicited Data & Collision Detection

To prevent hardware bus collisions on half-duplex UART configurations, the main window monitors incoming packets when the auto-fetch polling scheduler is disabled. 

- **Trigger**: If a valid framed packet arrives while `polling_action` is unchecked, `_unsolicited_detected` is flagged `True` in [TelemetryPipelineMixin._handle_packet](file:///c:/Users/Shreyas/Documents/Python/Bytehound/app/ui/telemetry_pipeline.py#L138).
- **Warning**: When the user subsequently requests to enable Auto-Fetch, the app detects this flag and prompts a `QMessageBox.warning` warning:
  > **Potential Collision Warning**
  > The connected device is already streaming data automatically (unsolicited). Enabling Auto-Fetch (polling) may cause transmission collisions and corrupt the data. Do you want to enable Auto-Fetch anyway?
- **Behavior**: The user can choose to abort (defaulting the action check back to false) or explicitly override the warning to proceed with active polling. The flag resets to `False` on any serial connection state transition.

---

## 11. TX Commands & Parameter Editor

`build_tx_command(config, name, values)`:

1. Look up `TxCommandSpec` by name.
2. Start payload with `bytes.fromhex(payload_hex)`.
3. For each `TxCommandFieldSpec`, take `values[field_name]` (or `default`),
   clamp-validate against `min_value`/`max_value`, encode per `data_type` +
   `byte_order` + `scale`/`offset`, append to payload.
4. Pass to `build_packet(protocol, frame_id, payload)`.

Errors raise `CommandBuildError(ValueError)` with a human-readable reason
(missing value, out of range, doesn't fit).

UI exposes:

- **TX Commands panel** — one button per enabled command. Buttons with no
  fields send immediately; buttons with fields open a small inline form.
- **Parameter Editor** — a flat `signal_name → QLineEdit` form for "writable"
  signals. Pressing Enter encodes and enqueues a TX.

---

## 12. Logging Formats

### `*_raw.csv` — `RawLogger`

Header: `timestamp,direction,hex,delta_t_ms`

```
2026-05-08 14:22:01.123,RX,AA 55 00 10 00 04 12 34 56 78 9A BC,2.4
```

- `timestamp` is local time, millisecond resolution (`%Y-%m-%d %H:%M:%S.%f`
  truncated to ms).
- `direction` ∈ `{RX, TX}`.
- `hex` is space-separated, uppercase.
- `delta_t_ms` is the request-to-response latency for polled responses (else 0.0).

### `*_decoded.xlsx` — `DecodedLogger`

Excel workbook with two sheets:

* **`Metadata`** — header row `Key | Value`, then one row per metadata
  entry sorted alphabetically. Populated by `_build_log_metadata()` in
  `main_window.py` and includes `app`, `app_version`, `baud_rate`,
  `config_source`, `decoded_file`, `logging_mode`, `raw_file`,
  `serial_port`, `session_started`.
* **`Data`** — header row, then one row per **complete poll cycle** in
  wide format. The header is grouped into **per-frame blocks**, one block
  per frame in `FrameConfig.frames` insertion order:

  ```
  <frame_A>.elapsed_ms | <frame_A>.frame_id | <frame_A>.<signal 1> | ... |
  <frame_B>.elapsed_ms | <frame_B>.frame_id | <frame_B>.<signal 1> | ...
  ```

Cycle Buffer pattern:

- Each incoming `log_frame()` updates an in-memory slot keyed by `frame_id`.
- The **trigger frame** is the LAST frame in `FrameConfig.frames`. When it
  arrives, the buffer is examined:
  - The cycle is emitted as one wide row containing all data received so far, then the buffer is cleared.
  - If any cycle frames were missing, their cells are left blank in the spreadsheet. No data is dropped.
- Buffer is always cleared on trigger arrival — no stale data carries across
  cycles.
- The block label `<frame>` is `frame_name` from config, or `0xNNNN` if no
  name is set.
- `<frame>.elapsed_ms` is the integer ms-since-log-start at which that
  particular frame was decoded — so each block carries its own arrival time.
- `<frame>.frame_id` is the hex string (e.g. `0x1000`).
- Signal columns reuse the existing `name (unit)` form, all dot-prefixed by
  the block label so cross-frame name collisions are impossible.
- Calculations land in their parent frame's block; calcs with no explicit
  `frame_id` fan out across every frame that contributes to the calc group.
- Values are scaled engineering numbers only.

**Persistence model.** The raw CSV logger streams rows to disk and flushes
periodically (`flush_interval`, default 0.5 s) so a crash loses ≤ one
buffer. The decoded `DecodedLogger` uses openpyxl write-only mode and
**only writes to disk when `close()` is called** (on Stop Logging or
shutdown). An app crash before Stop loses the decoded workbook; the raw
CSV is unaffected.

When logging starts, the active config is snapshotted next to the log via
`snapshot_config(...)` so the file is self-describing.

---

## 13. Advanced UI/IO Control & Performance

This section documents the performance optimizations, failure recovery, and real-time safety mechanisms handling telemetry stream anomalies.

### 13.1 Auto-Reconnect (Exponential Backoff)

For rugged laboratory or field use where physical USB cables can be bumped, the app supports transparent port reopening:
- **Trigger**: When `serial_worker` raises `connection_lost` (e.g., OS detects device unplugged), the app tears down the session status (without clearing live graphs or table values) and schedules reconnect.
- **Backoff Interval**: Retry events occur on a timer sequence starting at 1.0 s, doubling every failed attempt up to a maximum interval of 16.0 s (e.g., 1s, 2s, 4s, 8s, 16s).
- **Manual Control**: Toggling the connection button or disabling the "Auto-reconnect on disconnect" option in [ConnectionDialog](file:///c:/Users/Shreyas/Documents/Python/Bytehound/app/ui/dialogs.py) clears the timer and aborts the backoff schedule. Auto-reconnect re-establishes the port only; logging and active fetching are left stopped to prevent incomplete file writes or unexpected command streams.

### 13.2 Live Plot Memory Cap (`TimeSeriesBuffer`)

To prevent memory bloat and UI lag on multi-hour high-speed telemetry runs, the Live Plot utilizes `TimeSeriesBuffer` (defined in [plot_panel.py](file:///c:/Users/Shreyas/Documents/Python/Bytehound/app/ui/plot_panel.py)) instead of standard unbounded buffers:
- **Chunked Layout**: Samples are stored in contiguous memory blocks of size 16,384 (`CHUNK_SIZE`). This drastically reduces the overhead of Python object allocations.
- **Soft Cap Limit**: A user-configurable `max_samples` (configured under *Plot Settings*) triggers O(1) oldest chunk-dropping when exceeded.
- **Render Optimization**: Instead of fetching the entire history, the plot panel requests only visible data using `arrays_since(t_min)`. Along with setting `setClipToView(True)` and `setDownsampling(auto=True, method='peak')`, this guarantees that plotting paint cost remains proportional to the visible width, not total session length.

### 13.3 Queue Saturation Warning Badge

When the system cannot process incoming serial packets or write raw log lines to disk fast enough:
- **Detection**: If the priority queue fills up or the raw log flush queue becomes saturated, `error_occurred` notifies the UI with `"queue full"` or `"saturated"`.
- **Indicator**: A yellow `⚠️ Queue Saturated` badge is displayed in the QStatusBar.
- **Action**: Hovering details that data drops are occurring. Clicking the badge dismisses the indicator.

### 13.4 Frame Format Diagram

To aid developers in checking on-wire byte placement without inspecting the config spreadsheet:
- **Widget**: `FrameFormatWidget` dynamically parses the loaded `FrameConfig` and constructs a color-coded graphic grid.
- **Palette**: 
  - **Amber**: Header
  - **Emerald**: Frame ID
  - **Indigo**: Length
  - **Teal**: Signals / Payload Fields
  - **Pink**: CRC Checksum
  - **Grey**: Footer
  - **Muted**: Unused payload gaps
- **Interactive Tooltips**: Hovering over any signal byte slice reveals its data type, offset, size, and configured scaling values. It renders both RX frame structures and TX command definitions.

---

## 14. UI Specification

### Window

`QMainWindow`, title "Bytehound", default size 1400×820. Uses
`QSettings("Bytehound", "Bytehound")` for persistence (window state,
theme, last config path, last port/baud).

Theme: `qdarktheme.setup_theme("dark"|"light"|"auto", corner_shape="rounded")`,
applied at app start with the saved value (resolved through
`resolve_theme()` — see §Theme).

**Window sizing.** `MainWindow.__init__` calls `self.resize(1280, 780)` for
the default size and `self.setMinimumSize(640, 480)` to declare the
supported floor. To keep the actual floor at that value, the wide plot
control bar in `_build_plot_tab()` uses elastic policies on the hint label
(`QSizePolicy.Ignored, Preferred` so it clips on narrow windows instead of
holding the row hostage) and a relaxed `_hover_label.setMinimumWidth(120)`.
This is what makes the app fit a 50% / 50% screen split on a 1080p
display via Win+Left / Win+Right.

### Menus

The menu bar exposes six top-level menus, grouped by industry-standard
operational targets. Items are wired to `QAction`s defined in
`_build_actions()` and assembled in `_build_menus()`. Every action carries a
Material Design icon via [`qtawesome`](https://github.com/spyder-ide/qtawesome)
(`mdi6.<name>`); the helper `_icon()` degrades gracefully to an empty `QIcon`
if `qtawesome` is missing at runtime.

#### File
| Item | Slot | Behavior |
|------|------|----------|
| **Import Config** | `_on_load_config` | Pick a `.xlsx` / `.xlsm` workbook or a directory of CSVs. Loaded via `load_config(path)`. Path persists in `QSettings` key `config/last_path` and auto-loads next launch. |
| **Export Template** | `_on_export_template` | Write a blank dictionary template via `export_excel_template(...)`. |
| — separator — |  |  |
| **Exit** | `self.close` | Saves window geometry/state and quits. |

#### Edit
| Item | Slot | Behavior |
|------|------|----------|
| **Copy Value** (`Ctrl+Shift+C`) | `_on_copy_value` | Copies the selected table cell's text to the system clipboard. Window-scoped shortcut, so it always copies the data table's current cell regardless of focus. |
| **Clear Console / Log** | `_on_clear` | Wipes live UI state — table values, console buffer, activity log, plot history. Does not touch settings or connection. |

#### View

Built dynamically in `_populate_view_menu()`. Items in order:

| Item | Behavior |
|------|----------|
| **Panels** (submenu) | Toggle visibility of each dockable panel via `dock.toggleViewAction()`. Entries: **Connection**, **Live Plot**, **Bitfields**, **Enums**, **TX Commands**, **Parameter Editor**, **Raw Console**, **Activity Log**. State persists via `QMainWindow.saveState`. |
| **Reset Window Layout** | Restores docks/toolbar to their default arrangement. |
| **Config Info...** | Displays the active configuration profile summary and the graphical, byte-aligned **Frame Format Diagram** (slot `_on_show_config_info`). |
| **Theme** (submenu) | Exclusive checkable group: **Dark** / **Light** / **System**. Calls `_apply_theme(key)`. Persists to `QSettings("ui/theme")` and immediately `sync()`s so a crash before normal shutdown cannot lose the selection. **System** stores `"auto"`; every downstream painter resolves that to the actual OS theme via `resolve_theme()` (see §Theme). Re-applies the Windows dark/light title bar to every open top-level widget. |

#### Device
| Item | Slot | Behavior |
|------|------|----------|
| **Connect / Disconnect** | `_on_toggle_connect` | Opens or closes the `PollingWorker` against the selected port/baud. Label flips between "Connect" and "Disconnect". |
| **Start / Stop Auto-Fetch** | `_on_toggle_polling` | Toggles the continuous query schedule (`worker.set_polling_global`). Checkable; label flips. |
| **Start / Stop Logging** | `_on_toggle_logging` | Toggles writing `*_raw.csv` + `*_decoded.xlsx` under `~/Documents/Bytehound/Logs/`. Disabled until a config is loaded. |

#### Tools
| Item | Slot | Behavior |
|------|------|----------|
| **Analysis Suite** | `_on_analysis_suite` | Launches the non-modal Analysis Suite window (see §15). |

#### Help
| Item | Slot | Behavior |
|------|------|----------|
| **View Documentation** | `_on_view_docs` | Opens [app/resources/index.html](app/resources/index.html) in the default browser. |
| **Check for Updates** | `_on_check_updates` | Spawns `UpdateChecker` (see §16). |
| **Copy Diagnostics** | `_on_copy_diagnostics` | Gathers system info, configuration, counters, and log tail to the clipboard for troubleshooting. |
| **Report Issue...** | `_on_report_issue` | Opens a dialog to report software issues. |
| — separator — |  |  |
| **About Bytehound** | `_on_info` | Shows version + developer dialog. |

### Toolbar

Built in `_build_toolbar()`. The toolbar is streamlined to prioritize primary
hardware actions and configuration loading. Order, left to right:

**Import Config** | **Export Template** | **Connect** | **Start Auto-Fetch**

- **Visual hierarchy:** **Connect** and **Start Auto-Fetch** are the primary
  hardware actions. Both `QToolButton`s carry `objectName="primaryAction"` and
  pick up the green pill QSS (`#388E3C` background, `#4CAF50` hover,
  `#2E7D32` pressed, white bold text). Their `ToolButtonStyle` is forced to
  `ToolButtonTextOnly` so the green pill is never broken by an inline icon.
  Other actions use the default toolbar styling, with their `mdi6` icon shown
  alongside text.
- **Start / Stop Logging** is **not** in the toolbar — it lives only under
  *Device → Start Logging*.

The Connection dock (renamed from "Settings" in the dock title; `objectName`
remains `SettingsDock` so saved layouts keep working) additionally exposes a
port `QComboBox`, a baud `QComboBox`, and a **Refresh Ports** action.

### Status column pill badges

The Status column uses a custom `_StatusBadgeDelegate(QStyledItemDelegate)`
that overrides `paint()` to draw a rounded pill behind centered white bold
text. Tailwind palette:

- **OK** (text contains `ok` and not `error`) → `#10B981` (emerald-500).
- **Error / Fault** (text contains `error` or `fail`) → `#EF4444` (rose-500).
- **Warn / unknown non-empty** → `#F59E0B` (amber-500).
- Empty text or `"-"` falls through to the default delegate (no pill).

The status-bar LED keeps the Material `#66BB6A` / `#ef5350` colors — denser
table badges and a single-dot indicator are intentionally allowed to use
slightly different palettes so each reads cleanly at its own size.

### QMenu hover style

A custom QSS rule overrides qdarktheme's default slate-gray menu hover with a
Tailwind brand-blue accent (`#2563EB` blue-600) and 4px-rounded items, applied
to **every** `QMenu` in the app — top menu bar, the table's right-click
context menu, theme/panel submenus, every `QMessageBox` action menu. Item
padding is `6px 24px`; menu container padding is `5px`; separators use
`palette(mid)` with `4px 8px` margins.

### Status bar

`QStatusBar` at the bottom of the main window. Three regions, left → right:

1. **LED dot** (`⬤`) — `#ef5350` (red) when disconnected, `#66BB6A` (green)
   when connected. Tooltip mirrors the state. Color is set in
   `_set_connection_ui()`
   ([main_window.py:1740](app/ui/main_window.py#L1740)).
2. **Status text** — short transient messages (e.g. `Connected to COM5`,
   `Theme: dark`, `Error: ...`).
3. **Counters** (right-justified, permanent) — `packets / errors / RX bytes /
   TX bytes`, updated from `PollingWorker.metrics_updated`.

### Theme & native title bar (Windows)

Theming has three layers:

1. **Client area** — `qdarktheme.setup_theme("dark"|"light"|"auto",
   corner_shape="rounded")`, applied at startup with the saved
   `QSettings("ui/theme")` value and again from `_apply_theme()` on every
   user toggle. The user's raw selection (including `"auto"` for System) is
   what gets persisted, so the next launch reopens in the same mode.
2. **Card / dock / table QSS overrides** — `build_card_qss(theme)` in
   [theming.py](app/ui/theming.py) assembles `_QSS_BASE` plus either
   `_QSS_DARK_OVERRIDES` or `_QSS_LIGHT_OVERRIDES`. The full stylesheet is
   re-installed on the `MainWindow` on every toggle via `_apply_card_qss()`,
   which is why explicit per-theme rules cascade reliably (palette() in a
   widget stylesheet does NOT — see "palette-cache caveat" below).
3. **Native Windows title bar** — qdarktheme cannot reach the OS-drawn title
   bar (the strip with min/max/close). `_apply_windows_dark_titlebar()`
   ([main_window.py:87](app/ui/main_window.py#L87)) calls
   `DwmSetWindowAttribute` with `DWMWA_USE_IMMERSIVE_DARK_MODE` (attribute 20,
   falling back to 19 on older Windows 10 builds).

#### System theme ("auto") resolution

`_apply_theme(theme)` accepts `"dark"`, `"light"`, or `"auto"`. The user's
raw choice is persisted, but the rest of the codebase branches on a binary
`dark`/`light` — every site (toolbar tints, plot palette, status badges,
title bar, plot chip backgrounds) used to do `if theme == "dark": ... else: ...`
which silently treated `"auto"` as light regardless of the actual OS theme.

`resolve_theme(theme)` ([theming.py](app/ui/theming.py)) is the central
resolver:

- Pass `"dark"` / `"light"` through unchanged.
- For `"auto"` (or any other value), inspect the live
  `QApplication.palette().color(QPalette.ColorRole.Window)` — qdarktheme
  has already installed the OS-aware palette by the time we ask. Lightness
  < 128 → `"dark"`, else → `"light"`.
- If no `QApplication` is alive yet, fall back to `"dark"`.

Every theme-branching site in `app/ui/*` (theming, widgets, ui_builders,
main_window, plot_orchestration) routes through `resolve_theme()` before
choosing colours. `build_card_qss("auto")` resolves internally so external
callers (Analysis Suite) don't need to think about it.

#### palette-cache caveat — and the fix

Qt's QSS engine resolves `palette(role)` references **once** at
`setStyleSheet` time and caches the concrete colour forever. Changing the
`QApplication.palette()` (as qdarktheme does on theme switch) does NOT
invalidate that cache, so labels styled with `color: palette(mid)` stay on
the previous theme's colour. Two complementary mitigations are in place:

1. **Explicit per-theme rules in the cascaded QSS** (preferred). Secondary
   text widgets carry `objectName`s — `#hintLabel` (editor info, dialog
   hints), `#auxReadout` (session clock, Hz rate), `#hoverReadout` (plot
   hover) — and the dark/light override blocks include `QLabel#name { color: #hex }`
   rules. Because the MainWindow stylesheet is fully replaced on each toggle,
   these update reliably.
2. **`_refresh_palette_dependent_widgets()`** as a safety net. After every
   theme change, walks the descendant tree and `QApplication.topLevelWidgets()`,
   re-setting (clear + unpolish/polish + re-apply) the stylesheet on any
   widget whose stylesheet still contains `palette(`. Covers transient
   dialogs and any future widget that uses `palette()` without us tracking it.

Coverage for **every** top-level widget — main window, Analysis Suite,
X-Y Plotter, updater progress dialog, and every `QMessageBox` /
`QInputDialog` / `QFileDialog` popup — is provided by `TitleBarThemeFilter`
([main_window.py](app/ui/main_window.py)), an application-wide event filter
installed on the `QApplication` in [app/main.py](app/main.py). The filter
listens for `QEvent.Show` and applies the dark/light variant based on
`resolve_theme(QSettings("ui/theme"))`. When the user toggles the theme at
runtime, `_apply_theme()` also walks `QApplication.topLevelWidgets()` and
re-applies to every currently-open window.

### Connection error dialog

When `PollingWorker.open()` raises (e.g. WinError 31, "Access is denied",
"Could not open port"), `_format_serial_open_error(port, exc)`
([main_window.py](app/ui/main_window.py)) wraps the exception in a
plain-English `QMessageBox.critical` body — listing the most common causes
(unplugged device, port held by another app, stale port entry) — and appends
the raw exception text on a final `Details:` line so nothing is lost.

### Central widget — Main Data Table

`QTableWidget` with these columns:

```
Frame | Group | Variable | Start B. | Data Type | Raw | Value | Unit | Status | Updated
```

The `Variable` cell carries a small checkbox; checking it adds the signal to
the Live Plot. Plot history is a `TimeSeriesBuffer` of `(t_seconds, value)`
per signal (configured and capped in *Plot Settings*).

### Dockable panels (all `QDockWidget`)

**Float-to-window promotion.** Every dock listed below — Live Plot,
Bitfields, Enums, TX Commands, Parameter Editor, Raw Console, Activity Log
— has its `topLevelChanged` signal wired to `_promote_dock_to_window()`
([ui_builders.py](app/ui/ui_builders.py)). When the user pops the dock out
(drag off the main window, or double-click its title bar), the helper
upgrades it from Qt's default tool-window chrome to a real `Qt.Window` with
`WindowMinMaxButtonsHint | WindowCloseButtonHint | WindowSystemMenuHint`,
then re-`show()`s it so the new chrome takes effect. Drop it back into a
dock area and Qt restores the docked-tab look automatically. This is what
gives popped-out docks the standard `—  ▢  ✕` controls and lets the user
maximise the Live Plot onto a second monitor or minimise individual
panels independently of the main window.

- **Connection** (top-left): Port `QComboBox`, Baud `QComboBox`, Refresh,
  Connect/Disconnect, Polling toggle.
- **Bitfields**: per-bit ON/OFF indicators grouped by signal.
- **Enums**: current decoded enum label per enum-typed signal.
- **Raw Console**: scrollable hex dump of every RX/TX line, color-coded.
- **Activity Log**: app events (config load, connect, log start/stop, serial errors) **and any user-facing popups**. Message boxes are logged via `_log_popup(...)` before showing (`INFO`/`WARN`/`ERROR`/`QUESTION`/`ABOUT`).
- **TX Commands**: one button per enabled `tx_commands` row.
- **Parameter Editor**: flat table of writable signals (`read_write ∈ {W, RW}`).
  Columns: Frame ID | Signal | Live Value | Write (QLineEdit + Write button).
  Validators: `QIntValidator` for integer types, `QDoubleValidator` (C locale)
  for float types. Pressing Enter submits the write. Writable range shown in
  tooltip. If no writable signals are defined, a spanning informational row
  is shown instead of a blank table.
  Write is currently implemented for **Modbus RTU** only; framed-protocol write
  shows a not-yet-implemented popup.
- **Live Plot** (multi-grid `pg.GraphicsLayoutWidget`):

  #### Architecture
  `pg.PlotWidget` replaced by `pg.GraphicsLayoutWidget` (`self._gl_widget`).
  Each subplot is a `pg.PlotItem` wrapped in a `PlotPanel` dataclass:

  ```python
  @dataclass
  class PlotPanel:
      plot_item:     pg.PlotItem
      assigned_keys: List[Tuple[int, str]]  # (frame_id, signal_name)
      curves:        Dict[Tuple[int, str], pg.PlotDataItem]
  ```

  All panels' X-axes are linked via `setXLink` — panning one panel pans all.

  #### Grid layouts

  ```python
  GRID_LAYOUTS = {
      "1×1": (1, 1), "1×2": (1, 2), "2×1": (2, 1),
      "1×3": (1, 3), "3×1": (3, 1), "2×2": (2, 2),
      "2×4": (2, 4), "4×2": (4, 2),
  }
  ```

  Layout selection persists to `QSettings("plot/layout")`. On layout change,
  `_rebuild_plot_grid(rows, cols, restore=True)` is called; it saves the old
  panel key lists, clears the canvas, and redistributes old keys across the
  new panels round-robin.

  #### Per-panel variable strip

  A `QWidget` strip sits above each subplot. It contains:
  - A label (e.g. `P1:`)
  - One coloured chip `QPushButton` per assigned signal (click to remove)
  - A `+ Add` button → `QInputDialog` picker of all config signals

  Strip widgets live in a `QVBoxLayout` (`self._panel_strip_layout`) in a
  `QScrollArea` above the `GraphicsLayoutWidget`.

  #### View modes

  | Mode | `_plot_live` | Behaviour |
  |---|---|---|
  | 📊 Live | `True` | `setXRange(0, current_t × 1.05)` every redraw tick |
  | 🔍 Explore | `False` | No auto X-update; user-initiated pan/zoom |

  Switching between modes:
  - Any user pan/zoom fires `_on_plot_range_changed` → sets `_plot_live = False`
    and visually checks the Pause button.
  - **⏸ Pause / ▶ Live** toggle button (and `Space` shortcut) is the single
    control. Going to Live sets `_plot_live = True`, re-enables Y auto-range
    on every panel, and calls `_redraw_plot()` immediately so X snaps back
    to `(0, current_t)`.

  Re-entrancy guard: `self._plot_range_changing` is set `True` around any
  internal `setXRange` call so `_on_plot_range_changed` ignores it.

  #### Time axis (`_TimeAxisItem`)

  The bottom axis is a custom `pg.AxisItem` subclass in
  [plot_panel.py](app/ui/plot_panel.py) with two modes:

  - **Elapsed** (default): seconds since session start, rendered by
    `_format_elapsed_time(seconds, spacing)`.
  - **Clock**: wall-clock `HH:MM:SS` rendered from `session_start + seconds`.

  `_format_elapsed_time` picks decimal precision from the tick `spacing`
  pyqtgraph hands it, so zoomed-in views read as distinct values instead
  of repeating the same label:

  | Tick spacing  | Decimals | Example   |
  |---------------|----------|-----------|
  | ≥ 1 s         | 0        | `3s`      |
  | ≥ 0.1 s       | 1        | `1.5s`    |
  | ≥ 0.01 s      | 2        | `1.12s`   |
  | < 0.01 s      | 3        | `1.127s`  |
  | ≥ 10 s spacing or `\|seconds\| ≥ 60` |   | `2:30` (mm:ss) |

  Tick placement uses a `_nice_step()` 1/2/5×10ⁿ progression sized from a
  per-axis `min_label_px` budget, so labels stay readable across zoom levels.

  #### Data pipeline

  `_plot_history: defaultdict(deque(maxlen=1500))` keyed by `(frame_id, signal_name)`.
  All signals with `status == "ok"` and a non-None `scaled_value` are appended.
  `_redraw_plot()` runs at 60 Hz (driven by `_ui_timer`) and iterates over all
  `PlotPanel` objects, refreshing curves with `autoDownsample=True, clipToView=True`.

  #### Persistence keys (QSettings)

  | Key | Value |
  |---|---|
  | `plot/layout` | Layout name string, e.g. `"2×1"` |
  | `plot/panel/{i}/keys` | List of `[frame_id, signal_name]` lists |

  QSettings serialises `int` frame IDs as strings; the restore path always
  casts via `(int(k[0]), str(k[1]))` before use.

All panels persist their dock area and visibility via `QMainWindow.saveState`.

### Connection lifecycle

- **Connect**: instantiate `PollingWorker(SerialSettings, protocol, schedules)`,
  call `open()`, wire up signals, flip LED green.
- **Disconnect**: `worker.close()`, drop reference, flip LED red.
- **Toggle Polling**: `worker.set_polling_global(enabled)`. Reflects in the
  status bar.

---

## 15. Analysis Suite

A separate non-modal `QMainWindow` (implemented in [analysis_suite.py](file:///c:/Users/Shreyas/Documents/Python/Bytehound/app/ui/analysis_suite.py)) launched from *Tools → Analysis Suite*.

### 15.1 Ingestion & Multitasking
- **Background Loader**: File loading runs in `LogLoaderThread` so GUI events (panning, rendering) never hitch.
- **Log Ingestion**: Automatically reads files from local directories (`~/Documents/Bytehound/Logs/` and `~/Documents/Bytehound/Analysis/` are auto-created).
- **Import Schema Mapper**: Uses [SchemaMapperDialog](file:///c:/Users/Shreyas/Documents/Python/Bytehound/app/ui/dialogs.py) to override sheet names, elapsed-time column headers, and scale factors. The mapper matches and scales raw timestamps into standard elapsed seconds on load.

### 15.2 Advanced Visualization & Subplot Layouts
- **Dynamic Stacked Layout**: Central plotting uses a custom grid with vertical splitters. The user can toggle subplots, mix multiple parameters in the same subplot, or reorder, split, merge, and delete subplots from the sidebar.
- **Normalized View**: Toggling subplot normalization overlays signals with completely different physical units by scaling their curves to a unified 0-1 min-max range.
- **Smoothing Filter**: Applies a rolling-average window filter per subplot to clean up high-frequency sensor noise.
- **Time Offset Alignment**: Real-time offset entry fields in the sidebar shift individual log files by a designated delta-T (seconds) to align runs that did not start simultaneously.
- **Axis Modes**: Toggles X-axis between elapsed duration (mm:ss) and absolute wall-clock timestamp (HH:MM:SS) derived from the log file's metadata header.

### 15.3 Analytics & Math Channels
- **Draggable Cursors**: Draggable vertical and horizontal crosshair cursors (placed on a single subplot or fanned out to all linked subplots) update a live cursor readout grid showing values and coordinate deltas.
- **Statistics Panel**: Automatically calculates min, max, mean, standard deviation, count ($n$), and 5th/95th percentiles ($P_5/P_{95}$) for all checked parameters over the currently visible X zoom window.
- **Custom Math Channels**: Allows developers to add virtual parameters defined by expressions, calculated vectorially using numpy. Supports derivative/gradient (`diff([Param])`, `deriv([Param])`) and trapezoidal integration (`integral([Param])`, `cumsum([Param])`). Channels are persisted globally in QSettings.

### 15.4 Scatter Plotting (X-Y Plotter)
- **Scatter Mode**: [XYPlotWindow](file:///c:/Users/Shreyas/Documents/Python/Bytehound/app/ui/xy_plot.py) displays one parameter directly against another to identify cross-signal correlations.
- **Linear Regression Overlay**: Fits and renders a linear regression line, displaying the computed R-squared ($R^2$) coefficient.
- **Theme-Awareness**: Scatter plotter adjusts symbols (circle, square, triangle, etc.), point sizes, grid alphas, and palette styles to match the active light/dark/system theme.

---

## 16. Auto-Updater

Files: [app/ui/updater.py](app/ui/updater.py), [version.json](version.json).

`version.json` (shipped):

```json
{
  "version": "0.1.0",
  "Developer": "Shreyas P",
  "manifest_url": "https://.../version.json",
  "installer_url": "https://.../Bytehound_Setup_X.Y.Z.exe",
  "release_notes": "...",
  "sha256": "<hex sha256 of the installer .exe>"
}
```

### `version.json` location

`updater.py` resolves `version.json` via `_project_root()`:

- **Dev mode:** `Path(__file__).resolve().parents[2]` → repo root.
- **Frozen build:** `Path(sys.executable).resolve().parent` →
  the directory containing `Bytehound.exe`.

This mirrors `main_window._project_root()`. A previous `parent.parent` walk
resolved to `app/` and produced *FileNotFoundError: …\\app\\version.json* on
every check.

### Flow

1. *Help → Check for Updates* spawns `UpdateChecker(QThread)`.
2. Checker fetches the remote `manifest_url`, compares numeric `version`
   tuples (`[int, ...]`), emits
   `update_available(version, installer_url, release_notes, sha256)` or
   `up_to_date()`.
3. UI confirms with the user, spawns
   `UpdateDownloader(url, dest_path, expected_sha256)` — streams 8 KB chunks
   to `%TEMP%/Bytehound_Update.exe` while updating a running
   `hashlib.sha256()`.
4. After the download completes, the hex digest is compared against
   `expected_sha256` (case-insensitive). On mismatch the partial file is
   deleted and `error` is emitted with both expected and actual digests.
   If the remote manifest has **no** `sha256` field at all the downloader
   refuses to install rather than launching an unverified binary.
5. On a passing checksum, `launch_installer(path)` spawns the installer with
   `/SILENT` and `sys.exit(0)`s the app.

### `sha256` field

`build.py` runs Inno Setup *before* `write_sha256()`, then hashes the
produced installer at `installer_output/Bytehound_Setup_<version>.exe`
and writes the hex digest into the in-tree `version.json`. The published
manifest (the one `manifest_url` points at) must carry the same digest —
both `build.py` and the manifest must be updated together for an auto-update
release.

Network errors are surfaced to the user; the app never crashes on a failed
update check.

---

## 17. Settings Persistence

`QSettings("Bytehound", "Bytehound")` keys (Windows registry
`HKCU\Software\Bytehound\Bytehound`):

| Key                    | Type    | Meaning                                       |
|------------------------|---------|-----------------------------------------------|
| `ui/theme`             | str     | `"dark"` \| `"light"` \| `"auto"` (System)    |
| `window/geometry`      | bytes   | `saveGeometry()`                              |
| `window/state`         | bytes   | `saveState()`                                 |
| `serial/last_port`     | str     | Pre-select on next launch                     |
| `serial/last_baud`     | int     |                                               |
| `config/last_path`     | str     | Auto-load on next launch                      |
| `plot/layout`          | str     | Grid layout name, e.g. `"2×1"`                |
| `plot/panel/{i}/keys`  | list    | `[[frame_id, signal_name], …]` per panel      |
| `conn/auto_reconnect`  | bool    | Auto-reconnect enabled/disabled state         |
| `plot/history_max_samples` | int | Soft limit capacity cap for Live Plot history |
| `plot/window_seconds`  | int     | Live Plot default time window in seconds      |
| `analysis/math_channels` | dict  | Custom math channel formulas by name          |
| `import/sheet_names`   | str     | Import sheet list overrides (comma-separated) |
| `import/elapsed_cols`  | str     | Import elapsed columns list overrides         |
| `import/elapsed_scales`| str     | Import unit scale map (seconds multiplier)    |
| `analysis/layout`      | str     | Grid layout configuration for Analysis subplots|

Note: QSettings serialises all values (including int frame IDs) as strings.
The restore path in `_rebuild_plot_grid` always casts via `(int(k[0]), str(k[1]))`
to ensure the keys match `_plot_history`'s `(int, str)` tuples.

Reset is via *Edit → Clear* (clears live state, not settings) plus a manual
"reset layout" action under *View*.

---

## 18. Packaging & Build

### Spec — [Bytehound.spec](Bytehound.spec)

Key constraints:

- `pathex=[]` (PyInstaller resolves from the spec's directory).
- `datas=[('version.json', '.'), ('app/resources/*', 'app/resources/')]` plus
  whatever `collect_all('PySide6')` and `collect_all('shiboken6')` add.
- `hiddenimports=['pyqtgraph', 'numpy', 'openpyxl', 'serial', 'pandas', 'qdarktheme']`
  plus the hidden imports returned by the two `collect_all()` calls above.
- `excludes=['PyQt5', 'PyQt6', 'PySide2']` — **mandatory**; PyInstaller refuses
  to bundle two Qt bindings.
- Two-folder build (`exclude_binaries=True` on `EXE`, then `COLLECT`).
- `console=False`, `upx=True`, `name='Bytehound'`.
- `collect_all('shiboken6')` is required so PySide6's
  `_additional_dll_directories()` finds `_internal/shiboken6/` next to
  `_internal/PySide6/` at runtime — without it, PySide6 falls back to
  `<exe-dir>/shiboken6/libshiboken/` and crashes on import.

### Logo Integration Code Pattern

**Critical:** logo files (`logo_sq.ico`, `logo_sq.png`, `logo_rec.png`) must
**NOT** be added to the PyInstaller spec's `datas`. PyInstaller's `COLLECT`
mode places `datas` inside `_internal/`, but Windows installers, the exe
metadata, and tools that look for an icon "next to the executable" expect them
at the exe root.

The pattern, implemented in [build.py](build.py):

```python
BRANDING_DIR = ROOT / "branding"
BRANDING_PATTERNS = ("*.ico", "*.png")

def copy_branding() -> int:
    if not BRANDING_DIR.exists():
        return 0
    files = []
    for pattern in BRANDING_PATTERNS:
        files.extend(BRANDING_DIR.glob(pattern))
    for src in files:
        shutil.copy2(src, DIST_DIR / src.name)
    return len(files)
```

`copy_branding()` runs after PyInstaller succeeds, before `make_zip()`. The
runtime locator `_find_logo()` in [app/ui/main_window.py](app/ui/main_window.py)
then looks in `<exe-dir>/branding/` first and falls back to `<exe-dir>/`
(matching the build.py copy target).

### `build.py`

Convenience wrapper. Steps, in order:

1. Wipe `build/` and `dist/` (unless `--no-clean`).
2. Run `pyinstaller --noconfirm Bytehound.spec`.
3. Copy `branding/*.ico` and `branding/*.png` to `dist/Bytehound/`.
4. Run **Inno Setup** (`ISCC.exe installer.iss`) to produce
   `installer_output/Bytehound_Setup_<version>.exe`. Skipped with a
   warning if `ISCC.exe` is not on PATH.
5. Compute SHA-256 of the produced installer and write it to
   `version.json`'s `sha256` field. Step 4 must run before step 5 because
   the digest is taken from the Inno Setup output, not from the inner
   `Bytehound.exe`.
6. Zip the dist folder to `dist/Bytehound_<version>.zip` (unless
   `--no-zip`). Version is read from [version.json](version.json).

Flags: `--no-clean`, `--no-zip`. Output:
`dist/Bytehound/Bytehound.exe` and
`installer_output/Bytehound_Setup_<version>.exe`.

### Release smoke test (frozen build)

Before tagging a release, run the frozen build on a **clean Windows VM**
(no repo checkout, no Python installed) and verify:

- **Config template path:** File → Export Template succeeds and writes a
  workbook generated from `app/resources/config_template/`.
- **Version manifest:** Help → About shows the expected version from
  `version.json` (and `Copy Diagnostics` reports `Frozen: True`).
- **Docs bundle:** Help → View Documentation opens the packaged
  `app/resources/index.html`.
- **Logging location:** a log file is created at
  `%APPDATA%\Bytehound\logs\bytehound.log` on first launch.
- **COM enumeration:** Connection dialog opens and populates the port list
  without errors (a device is not required, just the scan).

### Inno Setup (`installer.iss`)

Targets Inno Setup 6. Notes:

- Do **not** set `Flags: checked` on `[Tasks]` entries — that flag was
  removed in Inno 6 and `ISCC` rejects it.
- Do **not** set `WizardResizable` — obsolete in Inno 6.
- The installer ships the entire `dist/Bytehound/` tree; the
  `[Setup]` `AppId` must remain stable across releases so upgrades replace
  the previous install instead of side-by-side installing it.

### Manual build

```powershell
pyinstaller --noconfirm Bytehound.spec
```

The first build is slow (~minutes); incremental builds (`build.py --no-clean`)
are faster.

### Title bar dark mode (Windows)

The Qt-level `qdarktheme.setup_theme(...)` styles the *client area* but does
not theme the Windows OS title bar (the strip with the window title and
min/max/close buttons). Use the DWM API:

```python
import ctypes
DWMWA_USE_IMMERSIVE_DARK_MODE = 20  # 19 on older Windows 10 builds
value = ctypes.c_int(1 if dark else 0)
ctypes.windll.dwmapi.DwmSetWindowAttribute(
    int(widget.winId()),
    DWMWA_USE_IMMERSIVE_DARK_MODE,
    ctypes.byref(value),
    ctypes.sizeof(value),
)
```

Apply this in `MainWindow.showEvent` (so the HWND exists) and again from
`_apply_theme(theme)` whenever the user toggles light/dark.

---

## 19. Testing Requirements

Pytest suite under `tests/`. Required coverage:

- `test_crc.py` — golden CRC vectors for each algorithm.
- `test_packet_builder.py` / `test_packet_parser.py` — round-trip a built
  packet through the parser; CRC mismatch is rejected; truncated input waits;
  garbage prefix is resynced.
- `test_modbus_framing.py` — FC 03/04/06/16 and exception responses.
- `test_frame_decoder.py` — short-payload status, scaling, enum lookup,
  bitfield split, calculated groups.
- `test_calculations.py` — each stat (`min/max/diff/sum/avg`).
- `test_config_loader.py` — required-column errors, overlap detection,
  legacy `frame_config`, Excel + CSV equivalence.
- `test_tx_command_builder.py` — encode int/float fields, range validation,
  static-payload prefix, missing-value error.
- `test_tx_padding.py` — `tx_pad_length` zero-pads correctly before CRC.
- `test_polling_worker.py` — schedule cadence, priority TX preempts polling
  (use a fake serial transport).
- `test_logging.py` — raw CSV row format + append-with-header logic; decoded xlsx data sheet and metadata sheet contents.
- `test_boot_smoke.py` — headless boot smoke for the `MainWindow` mixin
  stack. Constructs `MainWindow` under `QT_QPA_PLATFORM=offscreen` and
  exercises one representative method per mixin (Theming, PlotOrchestration,
  DetailTabs, TxPanel, ConfigLoader, LoggingSession, PollingSession, Popups,
  UpdaterWiring). Catches the class of bugs that "import-level OK" smoke
  can't: missing cross-mixin references, attribute-ordering issues in
  `__init__`, and missing module imports that only fire when a method is
  actually called. Includes runtime-path coverage too:
  `test_apply_decoded_with_synthetic_frame` pushes a synthetic `DecodedFrame`
  through `_apply_decoded` (exercises `_format_number` and the live-cell
  staging path); `test_fit_panel_y_now_with_seeded_data` seeds the
  `_plot_history` ring buffer and triggers `_fit_panel_y_now` (exercises the
  `np.nanmin`/`nanmax` autofit branch); `test_theme_auto_resolves` guards
  the System / `"auto"` theme path.

Pure-function modules (`decoder/`, `protocol/`, `commands/`, `serial_logging/`)
must be testable without Qt installed.

Run:

```powershell
pytest -q
```

### Optional hardware smoke tests

Three ad-hoc scripts at the repo root are useful for manual verification on a
machine with a real device attached. They are **not** part of the pytest suite:

- [smoke_com7.py](smoke_com7.py) — quick serial decode smoke test (defaults to `COM7` @ `115200`).
- [smoke_headless.py](smoke_headless.py) — headless (no GUI) end-to-end run that exercises every protocol-layer feature against a real serial device.
- [smoke_stress.py](smoke_stress.py) — 13-phase stress harness (CRC bursts, device-silence windows, TX flood, polling-toggle storm, reconnect cycles, watchdog timing, rapid config reload). Drives the MCU BMS simulator via the 0x1002/0x1003/0x1004 stress hooks.

These are named `smoke_*.py` (not `test_*.py`) so pytest does not auto-collect them — they open real serial ports at import time.

Run:

```powershell
python smoke_headless.py --port COM7 --seconds 6 --target-voltage 58.5
```

The script exits with a non-zero code equal to the number of failed checks, and prints a `PASSED / FAILED` summary. It groups checks into eight sections:

| § | Section | What it verifies |
|---|---------|------------------|
| 0 | Config sanity | `0x3000` frame, `Status_Bits` bitfield (8 named bits), `Mode` enum (5 labels), `Set_Voltage_Limit` field schema |
| 1 | Parameter editor (offline) | `build_tx_command("Set_Voltage_Limit", {"voltage_v": 58.5})` produces byte-exact packet `AA5501200249023C9EEE`; out-of-range values (e.g. 99 V) are rejected by `min_value`/`max_value` |
| 2 | Live serial | `PollingWorker` opens the port and runs for the configured duration |
| 3 | Polling | Frames `0x1000`, `0x2000`, `0x3000` all received with zero CRC errors |
| 4 | Bitfields | `Status_Bits` `bit_values` dict contains all 8 named bits from `bitfields.csv` |
| 5 | Enums | `Mode` `enum_label` resolves to one of `{Idle, Charging, Discharging, Fault, Service}` |
| 6 | TX commands | Both `Reset` (static payload) and `Set_Voltage_Limit` (parameterized) appear in `tx_recorded` |
| 7 | Round-trip | After `Set_Voltage_Limit(58.5 V)` the simulator's next `0x2000` frame reflects the new value (closes the parameter-editor loop end-to-end) |

### MCU BMS Simulator

[MCU_BMS_Simulator/MCU_BMS_Simulator.ino](MCU_BMS_Simulator/MCU_BMS_Simulator.ino) is a single-file sketch for any MCU with hardware Serial (e.g. Mega 2560). It is the reference fixture for `smoke_headless.py`. It implements:

**TX (board → PC), continuous streams:**

| Frame | Cadence | Payload |
|------|--------|---------|
| `0x1000 BMS_Status`   | 100 ms | `uint16 Voltage` LE (scale 0.1) + `int16 Current` LE (scale 0.1) |
| `0x2000 BMS_Settings` | 500 ms | `uint16 Voltage_Limit` LE (scale 0.1) |
| `0x3000 Status_Flags` | 200 ms | `uint8 Status_Bits` (bitfield, 8 named bits) + `uint8 Mode` (enum 0..4) |

**RX (PC → board), command handlers:**

| Frame | Payload | Behavior |
|------|---------|----------|
| `0x1000 / 0x2000 / 0x3000` (length 0) | — | Empty-payload poll; replies with the corresponding telemetry frame immediately |
| `0x1001 Reset`              | `FF FF`           | Resets `Voltage`, `Current`, `Status_Bits`, `Mode` to defaults |
| `0x2001 Set_Voltage_Limit`  | `uint16 LE` (scale 0.1, range 40.0–60.0 V) | Updates the streamed `Voltage_Limit` and re-emits `0x2000` immediately so the round-trip is observable in one tick |
| `0x1002 Stress_Mode`        | `uint8`           | `1` = 5× streaming cadence (every 20 ms), `0` = back to normal — used by `smoke_stress.py` to exercise the parser/UI under high RX rate |
| `0x1003 Force_CRC_Errors`   | `uint8 N`         | Send the next `N` 0x1000 frames with a deliberately wrong CRC to verify the **Errors** counter increments and the parser resyncs cleanly |
| `0x1004 Go_Silent`          | `uint8 seconds`   | Stop streaming for `N` seconds — verifies the host watchdog (`device_timeout`) fires and the **Lat / Frames** counters stop climbing |

The sketch contains a byte-by-byte RX state machine that validates the full frame (header `AA 55`, frame ID LE, length, payload, CRC16 Modbus LE, footer `EE`) before dispatching to a command handler. Bytes that fail any check are silently discarded and the parser resyncs on the next `AA 55`.

Flash via MCU IDE 1.8 / 2.x at 115200 baud; no external libraries.

### Lint & pre-commit gate

Ruff is configured in [pyproject.toml](pyproject.toml) with the `E`, `F`,
`W`, `B` rule families (defaults plus flake8-bugbear). Two helpers wrap
the common invocations:

- [scripts/lint.ps1](scripts/lint.ps1) — `.\scripts\lint.ps1` runs the
  full ruleset over `app/`, `tests/`, and `scripts/`. `.\scripts\lint.ps1 -Fast`
  narrows to `F821,F822,F823` (undefined names / bad `__all__` / pre-assignment
  references) for sub-second feedback. Resolves `.venv\Scripts\ruff.exe`
  explicitly so it works without the venv activated.
- [.git/hooks/pre-commit](.git/hooks/pre-commit) — installed locally
  (not tracked); runs `ruff check --select F821,F822,F823` against
  the **staged** Python files only and blocks the commit on any hit.
  This catches the class of bug that a `python -c "import ..."` smoke
  passes but a running app crashes on — exactly what triggered the
  `_format_number` and missing-`np` failures during the mixin refactor.
  Bypass with `git commit --no-verify` only when justified.

---

## 20. Acceptance Criteria

The build is "done" when:

1. **Round-trip:** A packet built by `build_packet` for any supported
   `ProtocolConfig` parses cleanly through the matching `ParserProtocol`,
   yielding the same `frame_id` and `payload`.
2. **Config-driven:** Editing only the Excel/CSV config (no Python changes)
   is sufficient to support a new device's frames, signals, bitfields, enums,
   TX buttons, and polling schedule.
3. **Crash-free I/O:** Disconnecting mid-stream, hot-plugging the device, and
   sending malformed bytes do not crash the app — only counters tick up.
   Logging stops automatically on disconnect.
4. **Persistent UX:** Window layout, theme, last port/baud, last config path,
   live plot layout, and per-panel signal assignments survive a restart.
5. **Multi-grid plot:** The Live Plot correctly renders 1–8 subplots, all
   X-linked. Per-panel variable assignment works from the strip and from the
   right-click table context menu. Live mode (0→now) and Explore mode (frozen
   on pan/zoom) switch correctly. Pause/Live toggle (Space) snaps back to Live.
7. **Theme-aware icons:** All menu and toolbar icons (File, Edit, View,
   Device, Tools, Help) update their tint when the user switches Dark ↔ Light.
8. **Parameter Editor:** Only RW/W signals appear. Live Value column updates
   in real time. Enter key submits write same as the Write button.
9. **Frozen build:** `python build.py` produces
   `dist/Bytehound/Bytehound.exe` that launches and works
   identically to the dev run, with no PyQt5/6/PySide2 in the bundle.
10. **Tests:** `pytest -q` is green on Windows + Python 3.10.
