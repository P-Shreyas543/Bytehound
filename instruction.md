# Serial-MonitorApp — Build Instructions

## Goal

Build a Python desktop application for framed serial data logging, decoding, and visualization, similar in workflow to Docklight, but with a configurable frame decoder that users can edit through Excel or CSV files.

The application must not hard-code device-specific frame variables, frame layout, scale factors, bitfields, enum values, or calculation groups in Python code. All frame definitions must come from user-editable configuration files bundled with the app and editable through templates exported by the UI.

The product name is **Serial-MonitorApp** (display name "Serial Monitor"). Publisher: Decibels.

## Intended Users

The app is for engineers and test/debug users who connect to a serial device, receive raw data frames, decode values, inspect variables live, log test data, and modify frame definitions as firmware/protocols change.

## Recommended Technology

Use Python with PySide6 for the desktop UI.

Reason:
- PySide6 is suitable for a Docklight-like desktop tool.
- It supports tables, dockable panels, menus, serial-port controls, plots, file dialogs, and long-running serial reads.
- It can be packaged later with PyInstaller.

Useful libraries:
- `PySide6` for GUI.
- `pyserial` for serial communication.
- `pandas` and `openpyxl` for CSV/Excel import/export.
- `pyqtgraph` for fast live plotting.
- `struct` for binary decoding.
- `csv` or `pandas` for logs.

Alternative UI options can be discussed before implementation:
- `Textual` for terminal UI.
- `Dear PyGui` for fast engineering tools.
- `Streamlit` for quick browser-based dashboards.

Default recommendation: PySide6 + pyserial + pyqtgraph.

## Core Features

### 1. Serial Port Connection

The app should provide:
- Port selection.
- Baud rate selection.
- Data bits, stop bits, parity, and timeout settings.
- Connect and disconnect buttons.
- RX and TX byte counters.
- Connection status indicator.
- Raw RX view.
- Optional TX/send panel for manual commands.

Serial settings must be user configurable from the UI.

### 1.1 Dual-Engine Protocol Support
The application supports two parsing engines, selectable dynamically via the configuration file:
- **Custom Framed Protocol**: Synchronizes on header/footer bytes, validates variable or fixed length payloads, uses configurable CRC.
- **Modbus RTU**: Strict adherence to Modbus RTU standard (Function Codes 03, 04, 06, 16) with dynamic frame sizing.

### 1.2 Active Polling Engine (Data-on-Request)
A background `QThread` polling engine handles cyclic data requests without blocking the UI.
- Maintains a user-defined `polling_schedule`.
- Executes Modbus Read Requests or Custom TX queries at precise intervals.
- Handles queue interleaving to ensure priority writes (from the Parameter Editor) do not collide with scheduled polling traffic.

### 1.3 Line Diagnostics
The application tracks detailed communication quality:
- Records Timeouts, CRC Errors, and dropped bytes.
- Tracks `delta_t` (latency) between TX request and RX response for active polling nodes.

### 2. Raw Data Logging

The app should log raw received packets and/or decoded values. The user must be able to choose, at the point of starting a session, whether to capture **raw only**, **decoded only**, or **both**.

Required log options:
- Log as hex text inside CSV.
- Log with timestamps.
- Include packet direction, `RX` or `TX`, in raw logs.
- Save raw session logs as **CSV** with header `timestamp,direction,hex,delta_t_ms` (replay-compatible).
- Save decoded session logs as CSV. Parquet output is optional/future.
- Start and stop logging from the UI.
- Choose log file path.
- Save the active configuration snapshot with each session.

### 2.1 Parameter Editing (Live Writes)
A dedicated "Parameter Editor" panel allows users to modify live variables over the connection.
- Displays all writable variables (configured as `W` or `RW`).
- Enqueues priority writes to the polling engine.
- Translates user inputs into valid Modbus Write commands (Function Codes 06/16) or Custom TX commands.

The app should not lose raw data even if decoding fails. When the user opts out of raw logging (decoded only), live decoding still continues — only the on-disk raw file is skipped.

### 3. Configurable Frame Decoding

The frame decoder must be driven only by external configuration files. The app should decode framed packets with header, frame ID, length, payload, CRC, and optional footer. The default development protocol does not use a footer. The variable configuration maps payload bytes only; framing and CRC validation are handled by the generic protocol parser.

The user should be able to:
- Download/export a default frame template from the app.
- Edit the template in Excel or any CSV editor.
- Import the modified template back into the app.
- Reload decoder configuration without changing Python code.
- Select from recent configurations on startup.

The app must validate the imported configuration and show errors clearly.

### 3.1 Multi-Frame Support

The app must support multiple frame IDs.

Examples:
- `0x100`: Overall pack voltage/current.
- `0x101`: Cell voltages 1-4.
- `0x102`: Cell voltages 5-8.
- `0x200`: Temperature sensors.
- `0x300`: Fault flags.

Each decoded variable must belong to a configured frame ID.

### 3.2 Offline Replay

The app must support offline decoding from saved raw logs.

Offline replay should:
- Load a raw log file.
- Apply a selected configuration.
- Decode packets as if they were arriving from the serial port.
- Allow plotting, decoded export, and error review.

### 3.3 TX Command Builder

The app must include a TX command builder driven by command templates from the configuration file.

The user should be able to:
- Select a named command.
- Edit command parameters where allowed.
- Build the payload from the template.
- Wrap the command with header, frame ID, length, CRC, and footer.
- Send the command through the active serial port.

No TX command payloads should be hard-coded in Python.

### 4. Live Decoded Variables Table

The app should show decoded variables in a live table.

Suggested columns:
- Variable name.
- Group.
- Index, for array variables.
- Raw value.
- Scaled value.
- Unit.
- Last update time.
- Decode status.

For variables with `count > 1`, the UI should expand them as separate rows, for example:
- `Cell Voltage 1`
- `Cell Voltage 2`
- `Cell Voltage 3`

### 5. Live Visualization

The app should support plotting selected decoded variables.

Expected plotting features:
- Select variables to plot.
- Plot value against timestamp.
- Pause and resume plot.
- Clear plot.
- Auto-scale axis.
- Export plotted data.
- Use a rolling live plot window, configurable from the UI.

Grouped variables like cell voltages and temperatures should be easy to select together.

Live plots should keep only a rolling time window in memory for rendering, for example the last 1 to 5 minutes. Full session data must still be saved to disk through the logging system.

### 6. Calculated Groups

The app should support calculated values based on configured groups.

Example calculations:
- Minimum.
- Maximum.
- Difference.
- Sum.
- Average.

These calculations must also come from a configuration file, not from hard-coded Python dictionaries.

Example:

```python
CALC_GROUPS = {
    "Cells": {"unit": "V", "stats": ["min", "max", "diff", "sum", "avg"]},
    "Temps": {"unit": "Deg C", "stats": ["max", "avg"]},
}
```

The actual application should load the equivalent information from CSV or Excel.

### 7. Bitfield Decoding

For variables marked as `Bitfield`, the app should decode each bit using names from the configuration file.

Example:
- `FET Status`
  - Bit 0: `Main FET Status`
  - Bit 1: `Pre Charge FET Status`

The UI should show bit names and current states.

### 8. Enum Decoding

For variables marked as `Enum`, the app should allow enum value mappings from configuration.

Example:
- `BMS State`
  - `0 = Init`
  - `1 = Idle`
  - `2 = Charge`
  - `3 = Discharge`

Enum names and values must be editable from CSV or Excel.

## Configuration Files

Use Excel as the user-friendly master format and CSV as the simple exchange format.

Recommended default file:

```text
frame_config.xlsx
```

Recommended sheets:
- `Protocol`
- `Frames`
- `FrameVariables`
- `Bitfields`
- `Enums`
- `CalcGroups`
- `TxCommands`
- `TxCommandFields`
- `SerialDefaults`

The app may also support equivalent CSV files:
- `protocol.csv`
- `frames.csv`
- `frame_variables.csv`
- `bitfields.csv`
- `enums.csv`
- `calc_groups.csv`
- `tx_commands.csv`
- `tx_command_fields.csv`
- `serial_defaults.csv`

### Protocol Sheet

This sheet defines the packet wrapper. It is generic app behavior and should not define payload variables.

Required columns:

| Column | Required | Example | Description |
| --- | --- | --- | --- |
| profile_name | Yes | Default BMS | User visible protocol profile |
| header_hex | Yes | AA55 | Start-of-frame bytes |
| frame_id_size | Yes | 2 | Number of frame ID bytes |
| frame_id_byte_order | Yes | big | Byte order for frame ID |
| length_size | Yes | 1 | Number of payload length bytes |
| length_meaning | Yes | payload_only | Length field meaning |
| crc_type | Yes | crc16_modbus | CRC/checksum algorithm |
| crc_size | Yes | 2 | CRC byte count |
| crc_byte_order | Yes | little | CRC transmission byte order |
| crc_coverage | Yes | header_to_payload | Bytes included in CRC calculation |
| footer_hex | No | | End-of-frame bytes, blank when unused |
| escape_mode | No | none | Optional byte-stuffing/escaping mode |
| raw_log_format | Yes | timestamp_direction_hex | Raw log row format |
| enabled | No | TRUE | Active protocol profile |

Supported `crc_type` values for the first version:
- `crc16_modbus`
- `crc16_ccitt`
- `crc32`
- `none`, for test-only use

The selected production default should be CRC16 unless the device protocol requires CRC32.

Default development protocol values:

| Setting | Value |
| --- | --- |
| Header bytes | `AA 55` |
| Footer bytes | None |
| Frame ID size | 2 bytes |
| Frame ID byte order | Big endian |
| Length size | 1 byte |
| Length meaning | Payload length only |
| CRC type | CRC16-Modbus |
| CRC polynomial | `0x8005` |
| CRC initial value | `0xFFFF` |
| CRC reflected input | TRUE |
| CRC reflected output | TRUE |
| CRC XOR output | `0x0000` |
| CRC transmitted byte order | Little endian, low byte first |
| CRC coverage | Header through payload: header, frame ID, length, payload |
| Escape/byte-stuffing | None |
| Raw log format | `YYYY-MM-DD HH:MM:SS.mmm, RX/TX, AA 55 ...` |

### Frames Sheet

Required columns:

| Column | Required | Example | Description |
| --- | --- | --- | --- |
| frame_id | Yes | 0x100 | Frame identifier |
| frame_name | Yes | Pack Summary | User visible frame name |
| payload_length | No | 8 | Expected payload length, blank if variable |
| direction | No | rx | `rx`, `tx`, or `both` |
| enabled | No | TRUE | Whether this frame is active |
| description | No | Overall pack values | User notes |

### FrameVariables Sheet

Required columns:

| Column | Required | Example | Description |
| --- | --- | --- | --- |
| frame_id | Yes | 0x100 | Must match Frames.frame_id |
| name | Yes | Pack Voltage | User visible variable name |
| fmt | Yes | uint16 | Data type |
| unit | No | V | Engineering unit |
| factor | No | 0.001 | Scale multiplier |
| offset | No | 0 | Scale offset after multiplier |
| count | No | 7 | Number of repeated values |
| group | No | Cells | Group name for arrays/calculations |
| byte_order | No | little | little or big |
| enabled | No | TRUE | Whether this variable is decoded |
| description | No | Total pack voltage | User notes |

Supported `fmt` values:
- `uint8`
- `int8`
- `uint16`
- `int16`
- `uint32`
- `int32`
- `float32`
- `float64`

Scaling formula:

```text
scaled_value = raw_value * factor + offset
```

If `factor` is blank, use `1`.
If `offset` is blank, use `0`.
If `count` is blank, use `1`.

### Bitfields Sheet

Required columns:

| Column | Required | Example | Description |
| --- | --- | --- | --- |
| frame_id | Yes | 0x300 | Frame containing the variable |
| variable_name | Yes | FET Status | Must match FrameVariables.name |
| bit_index | Yes | 0 | Bit number |
| bit_name | Yes | Main FET Status | User visible bit name |
| active_text | No | ON | Text for bit value 1 |
| inactive_text | No | OFF | Text for bit value 0 |

### Enums Sheet

Required columns:

| Column | Required | Example | Description |
| --- | --- | --- | --- |
| frame_id | Yes | 0x300 | Frame containing the variable |
| variable_name | Yes | BMS State | Must match FrameVariables.name |
| value | Yes | 1 | Raw enum value |
| label | Yes | Idle | User visible enum text |

### CalcGroups Sheet

Required columns:

| Column | Required | Example | Description |
| --- | --- | --- | --- |
| frame_id | No | 0x101 | Optional frame restriction, blank for cross-frame group |
| group | Yes | Cells | Must match FrameVariables.group |
| unit | No | V | Unit for calculated value |
| stat | Yes | min | Calculation name |
| enabled | No | TRUE | Whether calculation is enabled |

Supported `stat` values:
- `min`
- `max`
- `diff`
- `sum`
- `avg`

### TxCommands Sheet

Required columns:

| Column | Required | Example | Description |
| --- | --- | --- | --- |
| command_name | Yes | Request Fault Codes | User visible command name |
| frame_id | Yes | 0x300 | TX frame ID |
| payload_hex | No | 0102 | Static payload bytes, if no editable fields |
| description | No | Requests current fault flags | User notes |
| enabled | No | TRUE | Whether command is available in UI |

### TxCommandFields Sheet

Required columns:

| Column | Required | Example | Description |
| --- | --- | --- | --- |
| command_name | Yes | Set Charge Current | Must match TxCommands.command_name |
| field_name | Yes | Current Limit | User visible field name |
| fmt | Yes | uint16 | Field data type |
| unit | No | A | Engineering unit |
| factor | No | 0.1 | User value to raw value scaling |
| offset | No | 0 | User value offset |
| byte_order | No | little | Field byte order |
| min | No | 0 | Minimum allowed user value |
| max | No | 100 | Maximum allowed user value |
| default | No | 10 | Default user value |

### SerialDefaults Sheet

Suggested columns:

| Column | Example |
| --- | --- |
| baud_rate | 115200 |
| data_bits | 8 |
| stop_bits | 1 |
| parity | N |
| timeout_ms | 100 |

## Example Template Data

The bundled template should include rows equivalent to this sample configuration. The frame IDs below are examples and must be editable by the user.

Example `Frames` rows:

| frame_id | frame_name | payload_length | direction |
| --- | --- | --- | --- |
| 0x100 | Pack Summary | | rx |
| 0x101 | Cell Voltages | | rx |
| 0x200 | Temperatures | | rx |
| 0x300 | Status And Faults | | rx |
| 0x400 | Lifetime Counters | | rx |

Example `FrameVariables` rows:

| frame_id | name | fmt | unit | factor | count | group | byte_order |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0x100 | Pack Voltage | uint16 | V | 0.001 | 1 | | little |
| 0x100 | Pack Current | int32 | A | 0.001 | 1 | | little |
| 0x100 | Load Voltage | uint16 | V | 0.001 | 1 | | little |
| 0x100 | SoC (OCV) | uint16 | % | 0.1 | 1 | | little |
| 0x100 | SoC (Coulomb) | uint16 | % | 0.1 | 1 | | little |
| 0x101 | Cell Voltage | uint16 | V | 0.001 | 7 | Cells | little |
| 0x200 | BCC Temperature | int16 | Deg C | 0.1 | 1 | | little |
| 0x200 | Cell Temperature | int16 | Deg C | 0.1 | 7 | Temps | little |
| 0x200 | Bal. Resistor Temp | int16 | Deg C | 0.1 | 3 | | little |
| 0x200 | Pre-Charge Res. Temp | int16 | Deg C | 0.1 | 1 | | little |
| 0x200 | MOSFET Temp | int16 | Deg C | 0.1 | 2 | | little |
| 0x200 | Ambient Temp | int16 | Deg C | 0.1 | 1 | | little |
| 0x300 | Get Value Status | uint8 | Enum | 1 | 1 | | little |
| 0x300 | FET Status | uint8 | Bitfield | 1 | 1 | | little |
| 0x300 | Balancing Status | uint8 | Bitfield | 1 | 1 | | little |
| 0x300 | Fault Status | uint16 | Bitfield | 1 | 1 | | little |
| 0x300 | BMS State | uint8 | Enum | 1 | 1 | | little |
| 0x400 | SoH | uint8 | % | 1 | 1 | | little |
| 0x400 | Cycle Count | uint16 | Cycles | 1 | 1 | | little |
| 0x400 | Cumulative Cap | uint32 | Ah | 1 | 1 | | little |

## Protocol And Frame Parser Requirements

The serial parser should:
- Synchronize on configured start-of-frame/header bytes.
- Read the configured 2-byte frame ID field as big endian by default.
- Read the configured 1-byte payload length field.
- Read exactly the configured payload byte count.
- Validate CRC16-Modbus before decoding by default.
- Treat the CRC as little endian by default.
- Validate configured footer bytes only if a footer is configured.
- Route the payload to the correct decoder by frame ID.
- Preserve rejected packets in the raw log with error status.
- Recover from corrupted streams by searching for the next valid header.

The payload decoder should:
- Decode only the payload bytes, not header, frame ID, length, CRC, or footer.
- Read variables sequentially according to the imported configuration order for that frame ID.
- Use each variable's `fmt`, `count`, `factor`, `offset`, `byte_order`, and `enabled` values.
- Support mixed byte order per variable.
- Expand counted variables into indexed values.
- Decode bitfields using the Bitfields sheet.
- Decode enum labels using the Enums sheet.
- Compute configured group statistics.
- Report incomplete payload errors.
- Report extra byte warnings if the received payload is longer than the configured structure.

## Confirmed Protocol Decisions

These decisions are now part of the app requirements:

1. Use a framed serial packet with header, payload, CRC, and optional footer.
2. Header/start bytes are `AA 55`.
3. No footer is used in the default development protocol.
4. Frame ID is 2 bytes, big endian.
5. Length is 1 byte and means payload length only.
6. CRC is CRC16-Modbus with polynomial `0x8005`, initial value `0xFFFF`, reflected input/output, and XOR output `0x0000`.
7. CRC bytes are transmitted little endian, low byte first.
8. No escape or byte-stuffing is used.
9. Byte order must be configurable per variable.
10. The frame variable config describes payload only.
11. TX commands must be template-driven from Excel/CSV.
12. Multiple frame IDs are required.
13. Both raw logs and decoded logs are required.
14. Raw logs use timestamp, direction, and raw hex string.
15. Live plots use a rolling time window, while all data is saved to disk.
16. Offline replay from saved raw logs is required.
17. Configuration is selected manually, with recent configurations stored in user AppData.

## Unit Test Sample Frame

Use this sample concept for the first parser unit test:

| Field | Value |
| --- | --- |
| Header | `AA 55` |
| Frame ID | `00 10` |
| Length | `04` |
| Payload | `0F A0 0B B8` |
| Payload meaning | Two 16-bit cell voltages: 4000 mV and 3000 mV |
| CRC bytes | `BE 70` |
| Raw frame | `AA 55 00 10 04 0F A0 0B B8 BE 70` |

For this unit test, define frame `0x0010` with one payload variable:

| frame_id | name | fmt | unit | factor | count | group | byte_order |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0x0010 | Cell Voltage | uint16 | V | 0.001 | 2 | Cells | big |

CRC verification:

Using the CRC16-Modbus settings above, calculated over:

```text
AA 55 00 10 04 0F A0 0B B8
```

the CRC result is `0x70BE`, transmitted little endian as:

```text
BE 70
```

The corrected raw hex string for parser tests is:

```text
AA 55 00 10 04 0F A0 0B B8 BE 70
```

Example raw log row:

```text
2026-05-04 12:37:37.125, RX, AA 55 00 10 04 0F A0 0B B8 BE 70
```

## UI Layout

Recommended main window layout:

- Top toolbar:
  - Serial port selector.
  - Baud rate selector.
  - Connect/disconnect.
  - Start/stop logging.
  - Import config.
  - Export template.

- Left panel:
  - Serial settings.
  - Decoder configuration status.
  - Variable group selector.

- Center panel:
  - Live decoded variables table.

- Bottom panel:
  - Raw RX/TX console.

- Right or tabbed panel:
  - Live plots.
  - Bitfield view.
  - Enum/status view.

## Data Logging Requirements

The app should support:
- Raw data log with timestamp.
- Decoded variable log with timestamp.
- Calculation log with timestamp.
- Config snapshot stored with or near each log session.

Recommended decoded CSV columns:

| Column | Description |
| --- | --- |
| timestamp | Local timestamp |
| frame_number | Incrementing frame count |
| variable | Variable name |
| index | Array index if applicable |
| raw_value | Raw decoded value |
| scaled_value | Scaled engineering value |
| unit | Unit |
| group | Group name |
| status | OK or decode error |

## Error Handling

The app should clearly display:
- Serial connection errors.
- Config file missing.
- Invalid config column.
- Unsupported data format.
- Duplicate variable names where not allowed.
- Bitfield mapping for unknown variables.
- Enum mapping for unknown variables.
- Incomplete frame.
- CRC/checksum failure, if applicable.
- Decode overflow or insufficient bytes.

The UI should keep running even if one frame fails to decode.

## Testing Requirements

Testing must be done before considering the app complete.

Required tests:
- Load valid Excel config.
- Load valid CSV config.
- Reject missing required columns.
- Reject unsupported `fmt`.
- Parse a complete framed packet with header, frame ID, length, payload, CRC, and optional footer.
- Reject packet with invalid CRC.
- Recover from corrupted serial bytes and resync at the next header.
- Route multiple frame IDs to the correct payload decoder.
- Decode sample binary payload for each configured frame ID.
- Decode counted variables.
- Decode bitfields.
- Decode enums.
- Calculate group stats.
- Build TX command packet from template.
- Replay saved raw log offline.
- Handle incomplete frame safely.
- Write raw log.
- Write decoded log.

Recommended test strategy:
- Unit tests for config loading.
- Unit tests for frame decoding.
- Unit tests for calculations.
- A fake serial data generator for UI/manual testing.

## Project Structure

```text
Serial-MonitorApp/
  instruction.md
  README.md
  user_guide.md
  requirements.txt
  Serial-MonitorApp.spec        # PyInstaller build spec
  installer.iss                 # Inno Setup installer script
  version.json                  # Local version + remote manifest URL
  app/
    main.py
    updater.py                  # Auto-update checker/downloader
    ui/
      main_window.py            # Single QMainWindow with dockable layout
    serial_io/
      serial_worker.py
      fake_serial.py            # Used only by tests
      replay_source.py
    protocol/
      packet_parser.py
      packet_builder.py
      crc.py
    decoder/
      config_loader.py
      frame_decoder.py
      calculations.py
      template_io.py
      types.py
    commands/
      tx_command_builder.py
    serial_logging/                # Contains logging utilities for raw and decoded data
      raw_logger.py
      decoded_logger.py
    resources/
      index.html                # In-app user manual
      sample_raw_log.txt        # Bundled sample capture for tests/replay
      frame_config_template.xlsx # Bundled default config workbook
  tests/
    conftest.py
    test_calculations.py
    test_config_loader.py
    test_crc.py
    test_fake_serial.py
    test_frame_decoder.py
    test_logging.py
    test_packet_builder.py
    test_packet_parser.py
    test_replay.py
    test_tx_command_builder.py
```

### UI organisation (current)

The window uses one central widget (the live decoded variables table with a search box, group filter, and "Show calculations" toggle in a row above the table) and a set of independent Qt dock widgets:

- **Settings dock** (left) — two cards:
  - **Connection** — Port + Refresh, Baud, Data bits, Stop bits, Parity, Timeout, and a Connect button mirroring the toolbar action.
  - **Config** — Recent Configs dropdown + Load button, active config path, parsed protocol summary, frame/variable/TX counts, current logging filename, and a 📂 button that opens the default log folder.
- **Analysis docks** (right, tabbed) — `Live Plot`, `Bitfields`, `Enums`, `TX Commands`. Each is its own dock; users can rearrange or detach them individually.
- **Log docks** (bottom, tabbed) — `Raw Console` (RX/TX/ERR hex stream) and `Activity Log` (high-level application events with millisecond timestamps).

The toolbar carries the most-used actions (Import Config, Export Template, Load Raw Log, Start/Stop Logging, Connect, and the Decibels logo). Port/baud selectors live in the Settings dock, not the toolbar.

The menu bar is `File / Edit / View / Panels / Run / Help`:

- **View** — `Theme` submenu (Dark / Light / System, backed by `pyqtdarktheme` and persisted via `QSettings`), `Auto-Range Plot` (Ctrl+R), and `Reset Window Layout`.
- **Panels** — toggle actions for the toolbar, the Settings dock, an `Analysis ▸` submenu (Live Plot / Bitfields / Enums / TX Commands), and a `Logs ▸` submenu (Raw Console / Activity Log). Closed docks are always reopenable from this menu.

The status bar shows a connection LED, the latest status text, and a counter line (`frames`, `errors`, `RX` / `TX` byte totals, and `buffered` — bytes still sitting in the parser awaiting a complete frame).

Window geometry and dock state are saved on close via `QSettings` and restored at startup.

The fake-stream UI action has been removed for production. `app/serial_io/fake_serial.py` remains as a unit-test helper.

## Implementation Rule

No frame variable list should be written directly in the Python source code.

Allowed in Python:
- Generic packet parsing logic.
- Generic packet building logic.
- Generic CRC implementations.
- Generic decoder logic.
- Generic supported data type table.
- Generic config validation.
- Generic UI table/plot logic.

Not allowed in Python:
- Hard-coded protocol header/footer values for a specific device.
- Hard-coded frame IDs for a specific device.
- Hard-coded `Pack Voltage`.
- Hard-coded `Cell Voltage`.
- Hard-coded `Fault Status`.
- Hard-coded bit names.
- Hard-coded cell count.
- Hard-coded calculation groups.
- Hard-coded TX command payloads.

All user-specific frame structure must come from Excel or CSV configuration.

## First Implementation Milestone

Using the confirmed default development protocol, the first milestone should be:

1. Create config template files.
2. Implement config loader and validator.
3. Implement generic packet parser with CRC validation.
4. Implement generic binary payload decoder by frame ID.
5. Implement packet builder for TX command templates.
6. Add unit tests for parsing and decoding one sample complete frame.
7. Build minimal PySide6 UI for importing config and decoding fake serial/replay data.

Only after this milestone should live serial plotting and full Docklight-style tooling be added.
