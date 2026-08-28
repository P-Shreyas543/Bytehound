# Bytehound User Guide

Welcome to **Bytehound**! This tool is for developers, engineers, and test/debug users who need a configurable, reliable way to interface with serial devices. The application follows an industry-standard layout and provides features for dynamic data decoding, plotting, logging, and command transmission.

For the in-depth, illustrated handbook see **Help → View Documentation** inside the app (it opens `app/resources/index.html`).

## Table of Contents

1. [Getting Started](#getting-started)
2. [User Interface Overview](#user-interface-overview)
3. [Configuration Workflow](#configuration-workflow)
4. [Connecting to a Serial Device](#connecting-to-a-serial-device)
5. [Viewing and Visualizing Data](#viewing-and-visualizing-data)
6. [Logging](#logging)
7. [Transmitting Commands (TX)](#transmitting-commands-tx)
8. [Themes and Layout](#themes-and-layout)
9. [Build & Distribution](#build--distribution)
10. [Auto-Update Architecture](#auto-update-architecture)

---

## Getting Started

```bash
pip install -r requirements.txt
python -m app.main
```

---

## User Interface Overview

- **Menu Bar**: `File`, `Edit`, `View`, `Device`, `Tools`, `Help`.
- **Toolbar**: Port selector, Refresh, Baud, Connect.
- **Left Dock — Settings & Status**: serial line settings, decoder status, recent configs, group filter.
- **Center**: live decoded variables table with a search/filter input.
- **Right Dock — Analysis & Controls**: tabs for Live Plot, Bitfields, Enums, TX Commands.
- **Bottom Dock — Raw Console**: hex RX/TX log.

Any closed dock can be re-opened from the **View** menu. View → Reset Window Layout restores the default arrangement.

---

## Configuration Workflow

A core tenet: **no variables or frame structures are hard-coded**. Everything is driven by CSV files (or an `.xlsx` workbook).

### Exporting a Template
1. **File → Export Template** to save a `frame_config_template.xlsx`.

### Editing the Configuration

> **Note on `FrameConfig` vs `Variables`:**
> `FrameConfig` is the overall container representing the entire configuration. You **do not** need to fill a separate `FrameConfig` sheet alongside `Variables`. In modern configs, you only configure the sheets below.

#### Sheet Overview & Requirements:
- **`Protocol` (Required)** — Framing rules:
  - `profile_name`: Name for your protocol profile.
  - `parser_type` *(optional, default `framed`)*:
    - `framed`: Standard custom microcontroller / UART framing.
    - `waveshare_can_variable_length` (or `waveshare_can`, `variable_length`): Waveshare USB-CAN Variable-Length protocol (`0xAA ... 0x55`).
    - `waveshare_can_20_bytes` (or `fixed_20_bytes`): Waveshare USB-CAN Fixed 20-Byte protocol (`0xAA 0x55 ...`).
  - `header_hex`: Sync header bytes in hex (e.g. `AA55` or `0xAA 0x55`).
  - `frame_id_size`: Size of frame ID in bytes (e.g. `1`, `2`, or `4` for CAN).
  - `length_size`: Size of payload length field in bytes (`1` or `2`).
  - `crc_type`: CRC algorithm (e.g. `crc16_modbus`, `crc8`, `none`, `sum8`, `xor8`).
  - `footer_hex` *(optional)*: Trailing footer bytes if applicable.
- **`Variables` / `FrameVariables` (Required for decoding)** — Payload byte layout per frame:
  - `id_or_address`: Frame ID in hex (e.g. `0x10`) or decimal.
  - `signal_name`: Variable name (e.g. `Battery_Voltage`, `Temperature`).
  - `start_byte`: Zero-indexed byte offset inside the payload (or left empty for auto-packing).
  - `data_type`: Type (`uint8`, `int8`, `uint16`, `int16`, `uint32`, `int32`, `float32`, `float64`, `boolean`).
  - `byte_order`: `little_endian` (`le`) or `big_endian` (`be`).
  - `scale` & `offset`: Multiplier and additive offset (Engineering value = `raw * scale + offset`).
  - `unit`: Display unit (e.g. `V`, `A`, `°C`, `RPM`).
  - `count` *(optional)*: Number of elements if this variable is an array.
  - `group` *(optional)*: Category tag for UI grouping and filtering.
- **`Frames` (Optional / Recommended)** — Frame metadata:
  - `frame_id`: Frame ID matching `id_or_address`.
  - `frame_name`: Human-readable name for the frame.
  - `length` *(optional)*: Expected payload length in bytes.
  - `direction` *(optional)*: `rx`, `tx`, or `rxtx`.
  *(Note: If the `Frames` sheet is omitted, frames are auto-created from the entries in `Variables`)*.
- **`Bitfields` (Optional)** — Per-bit names for variables with `data_type: bitfield`.
- **`Enums` (Optional)** — Value-to-label mappings for enumerated status variables.
- **`CalcGroups` (Optional)** — Group statistics (`min`, `max`, `diff`, `sum`, `avg`) over array variables.
- **`TxCommands` / `TxCommandFields` (Optional)** — Outbound command packets and editable parameter fields.
- **`SerialDefaults` (Optional)** — Default connection parameters (`baud_rate`, `parity`, `stop_bits`, `data_bits`).

### Importing a Configuration
1. **File → Import Config**.
2. Select your config **workbook** (`.xlsx`/`.xlsm`), or select **any** `.csv` inside a config folder (the app will load that folder).
3. Verify in **Decoder Status** on the left.

Recently used configs are stored and accessible via the dropdown in the Decoder Status box.

---

## Connecting to a Serial Device

1. Plug in the device.
2. Choose your **COM port** (the list auto-refreshes when ports are plugged/unplugged) and **Baud**.
3. (Optional) Adjust Data bits / Stop bits / Parity / Timeout in the left panel.
4. Click **Connect**.

Data flows into the raw console and live table.

---

## Viewing and Visualizing Data

### Live Table
Updates in real time. Array variables expand into per-index rows. Use the search box and the **Variable Groups** filter to narrow down. Toggle **Show calculated values** to include CalcGroup statistics.

### Live Plot
- Tick variables in the **Select Variables to Plot** list (clicking a row toggles the checkbox).
- Choose a rolling time **Window**.
- **⏸ Pause / ▶ Live** (Space) freezes or resumes the rolling view; clicking ▶ Live also re-fits the Y axis and snaps X back to `0 → now`.
- **Export** writes the visible series to CSV.

### Bitfields & Enums
Tabs showing live ON/OFF state per named bit and the active enum label per variable.

---

## Logging

### Recording
1. **Device → Start Logging** and choose a base filename.
2. Three artifacts are produced alongside the chosen filename:
   - `<name>_raw.csv` — raw timestamped hex log.
   - `<name>_decoded.xlsx` — Excel workbook with a `Metadata` sheet (app, port, baud, config path, session start, etc.) and a `Data` sheet (decoded signals, one row per frame). Finalised on Stop Logging.
   - `<name>_session/` — snapshot of the active configuration.
3. **Device → Stop Logging** to finalize.

The default log directory is `~/Documents/Bytehound` and a 📂 button next to the logging status opens it.

To inspect a recorded run after the fact, open the matching `*_decoded.xlsx` in the **Analysis Suite** (*Tools → Analysis Suite*). It supports time cursors, statistics over an X-range, smoothing, and overlaying multiple runs.

---

## Transmitting Commands (TX)

If your config defines `TxCommands`:
1. Open the **TX Commands** tab.
2. Pick a command. Editable numeric fields, boolean flag toggles, and live telemetry readbacks (`Current: X`) appear next to field inputs.
3. Enter physical values or boolean states — the app validates bounds (`min_value`, `max_value`) and packs them into raw bytes (with sequential boolean flags bit-packed into byte flags).
4. **Build** previews the framed packet (header + frame_id + length + payload + CRC) with interactive field tooltips in the byte visualizer.
5. **Send** transmits over the active serial port.

---

## Themes and Layout

- **View → Theme**: Dark, Light, or System (auto). Choice persists across sessions.
- **View → Toolbar / Settings & Status / Analysis & Controls / Raw Console**: toggle docks/toolbar.
- **View → Reset Window Layout**: restore the default arrangement.
- Window geometry and dock layout are saved automatically on close.

---

## Build & Distribution

### Requirements
1. `pip install pyinstaller`
2. [Inno Setup](https://jrsoftware.org/isinfo.php).

### PyInstaller
```bash
pyinstaller Bytehound.spec
```
Output lives in `dist/Bytehound`.

### Inno Setup
Open `installer.iss` in the Inno Setup Compiler and press F9. The offline installer is produced in `installer_output/`. The default install location is `Program Files\Bytehound`.

---

## Auto-Update Architecture

The app contains an embedded auto-updater (`app/updater.py`).

1. **Help → Check for Updates** reads `version.json` and fetches the remote manifest URL.
2. Versions are compared as `[major, minor, patch]` tuples.
3. If a newer version exists, the user is prompted to download and install.
4. The downloaded installer is launched silently (`/SILENT`) and the app exits.

To publish a new version: bump `version.json`, rebuild with PyInstaller + Inno Setup, and host the new installer + manifest at the URLs configured in `version.json`.
