?# Serial Monitor App — Developer Specification

This document is a **build-from-scratch blueprint** for the Serial Monitor App.
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
13. [Replay Source](#13-replay-source)
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
| **App Name**          | Serial Monitor                                     |
| **Publisher**         | Decibels                                           |
| **Version**           | 0.1.0 (sourced from [version.json](version.json))  |
| **Platform**          | Windows 10 / 11 (x64). Code is cross-platform but the shipped binary targets Windows. |
| **Window Size**       | 1400 × 900 px                                      |
| **Window Title**      | `Serial Monitor v<Version>` (e.g. `Serial Monitor v0.1.0`) |
| **Website**           | https://lms.decibelslab.com/                       |
| **Executable Name**   | `Serial-MonitorApp.exe`                            |
| **Logging Format**    | CSV — `*_raw.csv` (timestamped hex frames) + `*_decoded.csv` (per-signal scaled values). See §12. |
| **Plotting Library**  | pyqtgraph (live plot in main window + Analysis Suite) |
| **Settings Storage**  | `QSettings("Decibels", "Serial-MonitorApp")` → Windows registry `HKCU\Software\Decibels\Serial-MonitorApp` |
| **Update Manifest**   | `manifest_url` field in [version.json](version.json) |

---

## 2. Branding & Logo Files

All branding assets live in [branding/](branding/) at the repo root and are
copied next to `Serial-MonitorApp.exe` after every build by [build.py](build.py).
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
`Serial-MonitorApp.exe` in a frozen build.

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
- Records and replays sessions with per-byte fidelity.

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
BMS-MonitorApp/
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
│   │   ├── serial_worker.py            # QThread: open port, poll, RX/TX
│   │   └── replay_source.py            # read raw_log.csv, yield bytes
│   ├── serial_logging/
│   │   ├── raw_logger.py               # CSV writer: timestamp,direction,hex,delta_t_ms
│   │   └── decoded_logger.py           # CSV writer: per-signal decoded values
│   ├── ui/
│   │   ├── main_window.py              # QMainWindow w/ docks, menus, panels
│   │   ├── analysis_suite.py           # post-test multi-log analyzer
│   │   └── updater.py                  # check version.json, download, install
│   └── resources/
│       ├── index.html                  # in-app docs (View → Documentation)
│       └── sample_raw_log.txt          # bundled sample log
├── tests/                              # pytest suite (see §17)
├── version.json                        # local version + update manifest pointer
├── requirements.txt
├── Serial-MonitorApp.spec              # PyInstaller spec
├── build.py                            # convenience wrapper around PyInstaller
├── test_com7.py                        # optional serial decode smoke test (requires hardware)
├── test_headless.py                    # optional headless integration smoke test (requires hardware)
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
| `raw_log_format`        | str     | Free text label                                        |
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

`tx_pad_length` (if set) zero-pads `coverage` (header..payload) before CRC.

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

- `packet_received(ParsedPacket, float delta_t_ms)`
- `metrics_updated(int timeouts, int crc_errors, int rx_bytes)`
- `error_occurred(str)`
- `tx_recorded(bytes)`

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
2. **Polling**: if `_polling_global_enabled` is true, find the first schedule
   whose `next_run <= now`, send its request, await response (or time out),
   reschedule. Only one poll per loop iteration to interleave with priority TX.
3. **Drain RX**: if no poll happened, read whatever is in the input buffer,
   feed the parser, emit `packet_received` for each extracted packet.
4. Sleep 10 ms.

Counters: `_timeouts`, `_crc_errors`, `_rx_bytes` are emitted via
`metrics_updated` after each batch.

`available_ports()` wraps `serial.tools.list_ports.comports()` for the UI's
port combo.

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

### `*_decoded.csv` — `DecodedLogger`

Header:
`timestamp,frame_number,frame_id,frame_name,variable,index,raw_value,scaled_value,display_value,unit,group,status,is_calculated`

One row per `DecodedSignal` (including calculated). `frame_id` is formatted as
`0x%04X`.

Both loggers append to existing files (writing the header only if empty) and
flush after every record so a crash never loses more than the current frame.

When logging starts, the active config is snapshotted next to the log via
`snapshot_config(...)` so the file is self-describing.

---

## 13. Replay Source

`parse_log_file(path)` accepts:

- The CSV format above (header row detected and skipped).
- Legacy plain-text rows: `YYYY-MM-DD HH:MM:SS.mmm, RX|TX, HEX BYTES`.

Returns `(rows, errors)`; bad lines are collected, not raised.

`replay_bytes(rows, directions=("RX",))` yields each row's bytes in order.
The UI feeds these into a fresh `ParserProtocol` so replay reuses the live
RX path 1:1.

---

## 14. UI Specification

### Window

`QMainWindow`, title "Serial Monitor", default size 1400×820. Uses
`QSettings("Decibels", "Serial-MonitorApp")` for persistence (window state,
theme, last config path, last port/baud).

Theme: `qdarktheme.setup_theme("dark"|"light", corner_shape="rounded")`,
applied at app start with the saved value.

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
| **Load Raw Log** | `_on_load_log` | Pick a `*_raw.csv` recording. Switches UI to replay mode. |
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
| **Theme** (submenu) | Exclusive checkable group: **Dark** / **Light** / **System**. Calls `_apply_theme(key)`. Persists to `QSettings("ui/theme")`. Re-applies the Windows dark/light title bar to every open top-level widget. |
| **Reset Window Layout** | Restores docks/toolbar to their default arrangement. |
| — separator — |  |
| **Auto-Range Plot** (`Ctrl+R`) | Resets the live plot's view box to fit current data. |

#### Device
| Item | Slot | Behavior |
|------|------|----------|
| **Connect / Disconnect** | `_on_toggle_connect` | Opens or closes the `PollingWorker` against the selected port/baud. Label flips between "Connect" and "Disconnect". |
| **Start / Stop Auto-Fetch** | `_on_toggle_polling` | Toggles the continuous query schedule (`worker.set_polling_global`). Checkable; label flips. |
| **Start / Stop Logging** | `_on_toggle_logging` | Toggles writing `*_raw.csv` + `*_decoded.csv` under `~/Documents/Serial-MonitorApp/Logs/`. Disabled until a config is loaded. |

#### Tools
| Item | Slot | Behavior |
|------|------|----------|
| **Analysis Suite** | `_on_analysis_suite` | Launches the non-modal Analysis Suite window (see §15). |

#### Help
| Item | Slot | Behavior |
|------|------|----------|
| **View Documentation** | `_on_view_docs` | Opens [app/resources/index.html](app/resources/index.html) in the default browser. |
| **Check for Updates** | `_on_check_updates` | Spawns `UpdateChecker` (see §16). |
| — separator — |  |  |
| **About Serial Monitor** | `_on_info` | Shows version + publisher dialog. |

### Toolbar

Built in `_build_toolbar()`. The toolbar is streamlined to prioritize primary
hardware actions and configuration loading. Order, left to right:

**Import Config** | **Export Template** | **Load Raw Log** | **Connect** | **Start Auto-Fetch**

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

Theming has two layers:

1. **Client area** — `qdarktheme.setup_theme("dark"|"light"|"auto",
   corner_shape="rounded")`, applied at startup with the saved
   `QSettings("ui/theme")` value and again from `_apply_theme()` on every
   user toggle.
2. **Native Windows title bar** — qdarktheme cannot reach the OS-drawn title
   bar (the strip with min/max/close). `_apply_windows_dark_titlebar()`
   ([main_window.py:87](app/ui/main_window.py#L87)) calls
   `DwmSetWindowAttribute` with `DWMWA_USE_IMMERSIVE_DARK_MODE` (attribute 20,
   falling back to 19 on older Windows 10 builds).

Coverage for **every** top-level widget — main window, Analysis Suite,
X-Y Plotter, updater progress dialog, and every `QMessageBox` /
`QInputDialog` / `QFileDialog` popup — is provided by `TitleBarThemeFilter`
([main_window.py](app/ui/main_window.py)), an application-wide event filter
installed on the `QApplication` in [app/main.py](app/main.py). The filter
listens for `QEvent.Show` and applies the dark/light variant based on the
current `QSettings("ui/theme")` value. When the user toggles the theme at
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
the **Live Plot**. Plot history is a `deque(maxlen=1500)` of `(t_seconds, value)`
per signal.

### Dockable panels (all `QDockWidget`)

- **Connection** (top-left): Port `QComboBox`, Baud `QComboBox`, Refresh,
  Connect/Disconnect, Polling toggle.
- **Bitfields**: per-bit ON/OFF indicators grouped by signal.
- **Enums**: current decoded enum label per enum-typed signal.
- **Raw Console**: scrollable hex dump of every RX/TX line, color-coded.
- **Activity Log**: app events (config load, connect, log start/stop, serial errors) **and any user-facing popups**. Message boxes are logged via `_log_popup(...)` before showing (`INFO`/`WARN`/`ERROR`/`QUESTION`/`ABOUT`).
- **TX Commands**: one button per enabled `tx_commands` row.
- **Parameter Editor**: editable fields for writable signals.
- **Live Plot**: pyqtgraph `PlotWidget`; auto-scale; plot pen color cycles per
  signal; legend uses signal name.

All panels persist their dock area and visibility via `QMainWindow.saveState`.

### Connection lifecycle

- **Connect**: instantiate `PollingWorker(SerialSettings, protocol, schedules)`,
  call `open()`, wire up signals, flip LED green.
- **Disconnect**: `worker.close()`, drop reference, flip LED red.
- **Toggle Polling**: `worker.set_polling_global(enabled)`. Reflects in the
  status bar.

### Replay mode

Loading a raw log via *File → Load Raw Log* puts the UI into a non-live mode:
the file is parsed, bytes are fed sequentially through a fresh parser, and
every panel updates as if live. No serial port is opened.

---

## 15. Analysis Suite

A separate non-modal `QMainWindow` launched from *Tools → Analysis Suite*.

### Capabilities

- Load multiple Excel `.xlsx` test logs concurrently (via a `QThread` so the
  live test isn't blocked).
- Overlay multiple parameters from multiple logs on a stacked plot grid.
- Place draggable cursors; show value/time deltas at each cursor and between
  cursors.
- X–Y scatter mode: plot any two parameters against each other.
- Color-pick per-trace, per-cursor.
- Save/load session as JSON (`SESSION_VERSION = 3`).

### Storage locations

- Logs: `~/Documents/Serial-MonitorApp/Logs/`
- Saved analysis sessions: `~/Documents/Serial-MonitorApp/Analysis/`

(directories auto-created on first use)

### Plot behavior

- Backed by `pyqtgraph` with OpenGL acceleration when available.
- Minimum panel height 80 px; vertical splitters between subplots.

The analysis suite is independent of the live decoder — it ingests rows from
exported Excel logs (typically the `*_decoded.csv` re-saved as `.xlsx`).

---

## 16. Auto-Updater

Files: [app/ui/updater.py](app/ui/updater.py), [version.json](version.json).

`version.json` (shipped):

```json
{
  "version": "0.1.0",
  "publisher": "Decibels",
  "manifest_url": "https://.../version.json",
  "installer_url": "https://.../Serial-MonitorApp_Setup_X.Y.Z.exe",
  "release_notes": "...",
  "sha256": ""
}
```

Flow:

1. *Help → Check for Updates* spawns `UpdateChecker(QThread)`.
2. Checker fetches the remote `manifest_url`, compares numeric `version`
   tuples (`[int, ...]`), emits `update_available(version, url, notes)` or
   `up_to_date()`.
3. UI confirms with the user, spawns `UpdateDownloader(QThread)` — chunks
   8 KB writes to `%TEMP%/Serial-MonitorApp_Update.exe`, emits progress.
4. On confirmation, `launch_installer(path)` spawns the installer with
   `/SILENT` and `sys.exit(0)`s the app.

Network errors are surfaced to the user; the app never crashes on a failed
update check.

---

## 17. Settings Persistence

`QSettings("Decibels", "Serial-MonitorApp")` keys (Windows registry
`HKCU\Software\Decibels\Serial-MonitorApp`):

| Key                  | Type   | Meaning                            |
|----------------------|--------|------------------------------------|
| `ui/theme`           | str    | `"dark"` \| `"light"`              |
| `window/geometry`    | bytes  | `saveGeometry()`                   |
| `window/state`       | bytes  | `saveState()`                      |
| `serial/last_port`   | str    | Pre-select on next launch          |
| `serial/last_baud`   | int    |                                    |
| `config/last_path`   | str    | Auto-load on next launch           |

Reset is via *Edit → Clear* (clears live state, not settings) plus a manual
"reset layout" action under *View*.

---

## 18. Packaging & Build

### Spec — [Serial-MonitorApp.spec](Serial-MonitorApp.spec)

Key constraints:

- `pathex=[]` (PyInstaller resolves from the spec's directory).
- `datas=[('version.json', '.'), ('app/resources/*', 'app/resources/')]` plus
  whatever `collect_all('PySide6')` and `collect_all('shiboken6')` add.
- `hiddenimports=['pyqtgraph', 'numpy', 'openpyxl', 'serial', 'pandas', 'qdarktheme']`
  plus the hidden imports returned by the two `collect_all()` calls above.
- `excludes=['PyQt5', 'PyQt6', 'PySide2']` — **mandatory**; PyInstaller refuses
  to bundle two Qt bindings.
- Two-folder build (`exclude_binaries=True` on `EXE`, then `COLLECT`).
- `console=False`, `upx=True`, `name='Serial-MonitorApp'`.
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
2. Run `pyinstaller --noconfirm Serial-MonitorApp.spec`.
3. Copy `branding/*.ico` and `branding/*.png` to `dist/Serial-MonitorApp/`.
4. Zip the dist folder to `dist/Serial-MonitorApp_<version>.zip` (unless
   `--no-zip`). Version is read from [version.json](version.json).

Flags: `--no-clean`, `--no-zip`. Output: `dist/Serial-MonitorApp/Serial-MonitorApp.exe`.

### Manual build

```powershell
pyinstaller --noconfirm Serial-MonitorApp.spec
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
- `test_logging.py` — raw + decoded CSV row format, append-with-header logic.
- `test_replay.py` — both CSV and legacy text formats; bad lines collected,
  not raised.

Pure-function modules (`decoder/`, `protocol/`, `commands/`, `serial_logging/`)
must be testable without Qt installed.

Run:

```powershell
pytest -q
```

### Optional hardware smoke tests

Two ad-hoc scripts at the repo root are useful for manual verification on a machine
with a real device attached. They are **not** part of the pytest suite:

- [test_com7.py](test_com7.py) — quick serial decode smoke test (defaults to `COM7` @ `115200`).
- [test_headless.py](test_headless.py) — headless (no GUI) run that exercises `PollingWorker`, TX enqueue, loggers, and the replay engine.

Run:

```powershell
python test_headless.py
```

---

## 20. Acceptance Criteria

The build is "done" when:

1. **Round-trip:** A packet built by `build_packet` for any supported
   `ProtocolConfig` parses cleanly through the matching `ParserProtocol`,
   yielding the same `frame_id` and `payload`.
2. **Config-driven:** Editing only the Excel/CSV config (no Python changes)
   is sufficient to support a new device's frames, signals, bitfields, enums,
   TX buttons, and polling schedule.
3. **Live ↔ Replay parity:** Replaying `*_raw.csv` produces the exact same
   table/plot/log output as the original live session.
4. **Crash-free I/O:** Disconnecting mid-stream, hot-plugging the device, and
   sending malformed bytes do not crash the app — only counters tick up.
5. **Persistent UX:** Window layout, theme, last port/baud, and last config
   path survive a restart.
6. **Frozen build:** `python build.py` produces
   `dist/Serial-MonitorApp/Serial-MonitorApp.exe` that launches and works
   identically to the dev run, with no PyQt5/6/PySide2 in the bundle.
7. **Tests:** `pytest -q` is green on Windows + Python 3.10.
