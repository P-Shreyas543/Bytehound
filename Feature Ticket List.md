# Bytehound Feature Ticket List

This document lists future development tasks for Bytehound. Each ticket represents an actionable task complete with target components, implementation details, and acceptance criteria.

---

## TKT-001: Framed-Protocol Parameter Writes
* **Status**: Completed (v1.1.0)
* **Target Components**: 
  * `app/commands/tx_command_builder.py`
  * `app/ui/main_window.py`
  * `app/ui/detail_tabs.py` (Parameter Editor view)

## TKT-002: Live Plot Color Customization
* **Status**: Completed (v1.1.0)
* **Target Components**: 
  * `app/ui/plot_orchestration.py`
  * `app/ui/dialogs.py`

## TKT-003: Export Log Sessions to CSV in Analysis Suite
* **Priority**: Medium
* **Target Components**: 
  * `app/ui/analysis_suite.py`
* **Description**:
  The Analysis Suite lets users load multiple historical `.xlsx` logs and overlay parameters on a common plot grid. However, there is no way to export this combined data.
  This ticket adds an export option:
  1. Add a *File → Export Current View to CSV* action in the Analysis Suite menu bar.
  2. Merge the loaded time series data onto a common timeline using interpolation or nearest-neighbor matching.
  3. Save the merged data table as a single CSV file, with columns grouped by source file and signal name.
* **Acceptance Criteria**:
  * The export action opens a file dialog to save a `.csv` file.
  * The exported CSV file contains aligned rows matching the active plot window.
  * Export operations run on a background thread (`QThread`) and display a progress dialog to keep the UI responsive.

---

## TKT-004: USB Serial Port Auto-Discovery
* **Status**: Completed (v1.1.0)
* **Target Components**: 
  * `app/serial_io/serial_worker.py`
  * `app/ui/main_window.py`

---

## TKT-005: Extended Modbus RTU Function Codes Support
* **Priority**: Medium
* **Target Components**: 
  * `app/protocol/packet_parser.py`
  * `app/protocol/packet_builder.py`
  * `app/decoder/config_loader.py`

---

## TKT-006: In-App Configuration Editor
* **Status**: Completed (v1.1.0)
* **Target Components**: 
  * `app/ui/config_editor.py`
  * `app/ui/main_window.py`

---

## TKT-007: TX Command Boolean Fields & Bit-packed Flag Encoding
* **Status**: Completed (v1.1.2)
* **Target Components**: 
  * `app/commands/tx_command_builder.py`
  * `app/decoder/config_loader.py`
  * `app/ui/tx_panel.py`
  * `app/ui/widgets.py`
* **Description**:
  Supports `bool` and `boolean` data types in outbound TX command field specifications. Multiple boolean fields in a TX command are bit-packed sequentially into byte flags (up to 8 bits per byte).
* **Acceptance Criteria**:
  * TX commands with `bool`/`boolean` fields render toggle inputs and validate 0/1 states.
  * Commands format bit-packed byte flags accurately on the wire.
  * Byte visualizer widget renders bit-packed flag breakdown tooltips.

---

## TKT-008: Live Plot Graph Panel Selection & Checkmark Feedback
* **Status**: Completed (v1.2.0)
* **Target Components**: 
  * `app/ui/telemetry_cards.py`
  * `app/ui/main_window.py`
  * `app/ui/theming.py`

---

## TKT-009: Redesigned Protocol & Frame Configuration Wizard
* **Status**: Completed (v1.2.0)
* **Target Components**: 
  * `app/ui/config_wizard.py`

---

## TKT-010: Group Calculation Header Column Binding Fix
* **Status**: Completed (v1.2.0)
* **Target Components**: 
  * `app/serial_logging/decoded_logger.py`
