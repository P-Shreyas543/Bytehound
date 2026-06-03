# Bytehound Feature Ticket List

This document lists future development tasks for Bytehound. Each ticket represents an actionable task complete with target components, implementation details, and acceptance criteria.

---

## TKT-001: Framed-Protocol Parameter Writes
* **Priority**: High
* **Target Components**: 
  * `app/commands/tx_command_builder.py`
  * `app/ui/main_window.py`
  * `app/ui/detail_tabs.py` (Parameter Editor view)
* **Description**:
  The parameter editor currently supports parameter writing only for the Modbus RTU protocol. When a user attempts to write a parameter under a custom framed UART configuration, a "Not-Yet-Implemented" popup is shown. 
  This ticket requires extending parameter writing support to custom framed protocols:
  1. Parse the writable signal's target frame ID and value.
  2. Reconstruct the packet bytes using the existing `build_tx_command()` and `build_packet()` infrastructure.
  3. Enqueue the built command to the priority transmission queue of the `PollingWorker` thread.
* **Acceptance Criteria**:
  * Attempting a parameter write under a custom framed protocol executes without popups.
  * The parameter write builds a valid frame (verified via the raw console and unit tests).
  * Out-of-range values trigger standard validation alerts.

---

## TKT-002: Live Plot Color Customization
* **Priority**: Medium
* **Target Components**: 
  * `app/ui/plot_orchestration.py`
  * `app/ui/dialogs.py`
* **Description**:
  Currently, plot curve colors are assigned automatically using a predefined palette array. Users cannot change color assignments for individual signals.
  This task adds a color picker dialog to the live plot:
  1. Update the variable chip buttons in the plot headers. Right-clicking a chip opens a color selection dialog (`QColorDialog`).
  2. Apply the chosen color to the target plot curve and update the chip button icon.
  3. Save custom color mappings in `QSettings` under `plot/colors/<signal_name>` so choices persist across application restarts.
* **Acceptance Criteria**:
  * Right-clicking a signal chip button opens a color picker dialog.
  * Selecting a new color updates the curve color immediately without clearing the plot history.
  * Custom colors persist after closing and restarting the application.

---

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
* **Priority**: Low
* **Target Components**: 
  * `app/serial_io/serial_worker.py`
  * `app/ui/main_window.py`
* **Description**:
  The COM port selection dropdown list displays raw device names (e.g., `COM3`, `COM7`). Users must open the Windows Device Manager to identify which port corresponds to their device.
  This ticket improves hardware discovery:
  1. Update the COM port enumeration function to retrieve manufacturer name, USB VID (Vendor ID), and PID (Product ID) from `serial.tools.list_ports.comports()`.
  2. Format the dropdown list items to include these details (e.g., `COM7 (STMicroelectronics - Virtual COM Port)`).
  3. Highlight ports matching common chipsets (FTDI, STMicroelectronics, NXP, WCH) at the top of the list.
* **Acceptance Criteria**:
  * The connection port dropdown displays port names along with device descriptors.
  * Standard serial connections still work if description fields are blank or unavailable.

---

## TKT-005: Extended Modbus RTU Function Codes Support
* **Priority**: Medium
* **Target Components**: 
  * `app/protocol/packet_parser.py`
  * `app/protocol/packet_builder.py`
  * `app/decoder/config_loader.py`
* **Description**:
  The Modbus RTU parser is limited to registers (Function Codes `03`, `04`, `06`, `16`). It does not support reading or writing individual coils or discrete inputs.
  This task adds support for digital line states:
  1. Update the parser and packet builder to handle Function Codes `01` (Read Coils), `02` (Read Discrete Inputs), `05` (Write Single Coil), and `15` (Write Multiple Coils).
  2. Extend `variables` sheet validation to recognize `coil` and `discrete_input` as valid register types.
  3. Map boolean states (`0`/`1`) to enums or status text in the main data table.
* **Acceptance Criteria**:
  * Configurations using Function Codes `01`, `02`, `05`, or `15` parse correctly without triggering configuration errors.
  * Coil read queries return valid binary states in the data table.
  * Coil write requests format and transmit correct Modbus frames.

---

## TKT-006: In-App Configuration Editor
* **Priority**: Low
* **Target Components**: 
  * `app/ui/main_window.py`
  * `app/decoder/config_loader.py`
  * `app/decoder/template_io.py`
* **Description**:
  Users currently edit configurations using external spreadsheet software like Excel. This task introduces an integrated configuration editor:
  1. Add a *Tools → Configuration Editor* menu action that opens a modal window containing tabbed data grids.
  2. Implement tables for `protocol`, `frames`, `variables`, and other sheets using `QTableWidget` grids.
  3. Add a **Validate & Save** button that runs configuration check routines and saves modifications back to the source `.xlsx` or CSV directory.
* **Acceptance Criteria**:
  * Opening the configuration editor loads the active configuration sheets into editable grids.
  * Validation errors are flagged on the relevant rows in the editor interface.
  * Saving writes changes back to disk and prompts the application to reload the configuration.
