# Bytehound

Python desktop tool for framed serial data logging, decoding, replay, TX command building, and live visualization. Driven entirely by user-editable CSV/Excel configuration — no hard-coded frame layouts.

## Requirements

- **Python:** 3.10 – 3.12 (matches PySide6 6.11 wheels).
- **Platforms:** developed and tested on Windows 10/11. The core (decoder, protocol, serial worker, logging) is platform-portable; the title-bar theming and installer are Windows-specific.
- **Hardware:** any serial device matching a user-defined frame protocol. The Arduino sketch in [`Arduino_BMS_Simulator/`](Arduino_BMS_Simulator/) is the reference fixture.

## Run

```powershell
pip install -r requirements.txt
python -m app.main
```

## Configuration

The app loads a single bundled Excel workbook by default. You can also load a directory of CSVs or an `.xlsx`/`.xlsm` workbook via the UI.

The bundled default config workbook is:

```text
app/resources/frame_config_template.xlsx
```

A config is split across several sheets / CSV files:

| Sheet / file | Purpose |
|---|---|
| `protocol`            | Wire framing: header, frame-id size, length size, CRC type, footer, parser type (`framed` or `modbus_rtu`). |
| `frames`              | Frame ID → frame name + payload length. |
| `variables`           | One row per decoded signal: byte offset, length, type, scale, offset, unit, group. |
| `bitfields`           | Named bit positions inside a `uint*` signal. |
| `enums`               | Integer → label map for a signal. |
| `calc_groups`         | Aggregate stats (min/max/avg/sum/diff) over a `group`. |
| `tx_commands`         | Named outbound commands (frame ID + static payload or field list). |
| `tx_command_fields`   | One row per field in a TX command (name, type, scale, range). |
| `serial_defaults`     | Initial baud / parity / timeout. |
| `polling_schedule`    | Frame IDs to poll on a fixed interval (request-response devices). |

Full schema reference: [instruction.md](instruction.md) (`§3 Config Schema`) or the in-app help (`Help → View Documentation`).

## Test

```powershell
pytest -q
```

Manual hardware smoke scripts (not auto-collected) live at the repo root: [`smoke_com7.py`](smoke_com7.py), [`smoke_headless.py`](smoke_headless.py), [`smoke_stress.py`](smoke_stress.py). They require a connected device or the Arduino BMS simulator.

## Build

```powershell
pyinstaller Bytehound.spec
```

The Inno Setup script [`installer.iss`](installer.iss) packages `dist/Bytehound` into an offline installer.

## Logs & bug reports

The app writes a rotating log file:

- **Frozen build:** `%APPDATA%\Bytehound\logs\bytehound.log`
- **Dev run:** `logs/bytehound.log` next to the repo root

5 MB per file × 3 backups. Uncaught exceptions are captured to the same log via `sys.excepthook`.

When filing a bug at <https://github.com/P-Shreyas543/Bytehound/issues>, please include:

1. The `bytehound.log` excerpt around the time of the issue.
2. The config file (CSV directory or `.xlsx`) you were loading.
3. A short description of what you were doing (connecting, polling, running an Analysis Suite query, etc.).
4. App version (Help → About Bytehound) and OS version.

## In-app User Manual

Help → View Documentation opens [`app/resources/index.html`](app/resources/index.html) — a complete handbook covering configuration, UART frame definition, TX commands, logging, plotting, and troubleshooting.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
