# Serial-MonitorApp

Python desktop tool for framed serial data logging, decoding, replay, TX command building, and live visualization. Driven entirely by user-editable CSV/Excel configuration — no hard-coded frame layouts.

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

## Test

```powershell
pytest -q
```

## Build

```powershell
pyinstaller Serial-MonitorApp.spec
```

The Inno Setup script `installer.iss` packages `dist/Serial-MonitorApp` into an offline installer.

## In-app User Manual

Help → View Documentation opens `app/resources/index.html` — a complete handbook covering configuration, UART frame definition, TX commands, logging, plotting, and troubleshooting.
