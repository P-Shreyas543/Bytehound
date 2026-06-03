# Bytehound Project Requirements Document (PRD)

## 1. Introduction & Overview

Bytehound is a hardware-agnostic Python-based desktop application designed for hardware, firmware, and embedded systems developers. It provides a real-time environment for framed serial data logging, decoding, command transmission (TX), parameter editing, and live signal visualization. 

Unlike traditional serial monitors that dump raw hex values or require custom Python scripts for each hardware project, Bytehound is **completely driven by user-defined CSV or Excel configurations**. The layout of binary packets, telemetry structures, register maps, and control commands are loaded dynamically from a configuration file, allowing developer teams to adapt the tool to any custom UART or Modbus RTU protocol without recompiling or altering the source code.

---

## 2. Target Audience & Core Goals

### Target Audience
* **Embedded Software Engineers** debugging custom microcontrollers (STM32, NXP, AVR, ESP32).
* **Hardware Test Engineers** performing automated logging or battery management system (BMS) stress-testing.
* **Systems Integrators** working with Modbus RTU sensors, actuators, and industrial devices.

### Core Goals
* **Configuration-Driven Architecture**: Eliminate hard-coded frame layouts. All packet structures, scaling factors, enums, and command fields are described in user-editable spreadsheets.
* **Accurate Protocol Decoding**: Support custom UART framed protocols (with configurable headers, footers, length bytes, and CRCs) as well as standard Modbus RTU.
* **Low-Latency Live Visualization**: Deliver high-performance, real-time multi-grid oscilloscope plotting (60 Hz UI refresh) alongside dynamic tabular views.
* **Bi-directional Control**: Enable sending parameterized commands and editing registers via an inline parameter editor.
* **Self-Contained Offline Execution**: Run locally as a compiled Windows executable without external server dependencies, database installations, cloud sync, or user logins.

---

## 3. System & Environmental Requirements

### 3.1 Software Requirements
* **Operating Systems**: Native support for Microsoft Windows 10 & Windows 11 (x64 architecture). 
* **Python Runtime Compatibility**: Python 3.10 – 3.12 (aligned with the PySide6 version requirements).
* **Key Dependencies**:
  * **UI Framework**: PySide6 (v6.6 – <7.0) — *exclusive binding; PyQt5/PyQt6/PySide2 are strictly excluded*.
  * **Plotting Engine**: pyqtgraph (≥ 0.13) for high-performance canvas rendering.
  * **Serial Communications**: pyserial (≥ 3.5) for interface interaction.
  * **Data Processing & Excel**: pandas (≥ 2.1) and openpyxl (≥ 3.1).
  * **UI Theme**: pyqt-darktheme (≥ 1.3) for runtime style injection.

### 3.2 Hardware Requirements
* **Host PC**: Standard x64 Windows machine with at least one physical USB/UART COM port, virtual COM port (VCP), or USB-to-Serial converter (e.g., FTDI, CH340, CP210x).
* **Target Device**: Any microcontroller, BMS, PLC, or serial device capable of communicating over UART or RS-485 at standard baud rates (e.g., 9600, 115200, etc.) conforming to the loaded configuration profile.

---

## 4. Functional Requirements

### 4.1 Configuration Ingestion & Schema Support
The application must dynamically load its runtime telemetry structure from either a single Excel workbook (`.xlsx`/`.xlsm`) or a directory containing a series of `.csv` files. The configuration is divided into the following sheets:

* **`protocol`** *(Required)*: Configures the wire-framing attributes (header, frame ID size and byte order, payload length size, CRC type, CRC coverage, footer, parser type, and inter-frame delays).
* **`frames`** *(Optional)*: Defines mapping between raw Frame IDs (hex) and descriptive frame names, direction, and expected payload sizes.
* **`variables`** *(Required)*: Declares individual signal specifications within frames (data type, byte order, scale factor, offset, engineering units, grouping, read/write permissions, and clamping range).
* **`bitfields`** *(Optional)*: Maps bit-level offsets within integer signals to user-friendly status labels and active/inactive status text.
* **`enums`** *(Optional)*: Maps raw integer values of a signal to human-readable state labels (e.g., `0` -> `Idle`, `1` -> `Charging`).
* **`calc_groups`** *(Optional)*: Configures runtime mathematical aggregates (`min`, `max`, `sum`, `diff`, `avg`) over signals sharing a common group label.
* **`tx_commands`** *(Optional)*: Configures named outbound commands, their target frame IDs, and any static hex payloads.
* **`tx_command_fields`** *(Optional)*: Configures parameterized variables embedded within a TX command (data type, scale, offset, constraints, defaults).
* **`serial_defaults`** *(Optional)*: Defines initial baud rate, parity, stop bits, data bits, and timeout limits.
* **`polling_schedule`** *(Optional)*: Specifies query intervals and timeouts for individual frames on request-response systems.

### 4.2 Serial Port Operations & Robustness
* **Port Discovery**: Automatically detect and list all active COM ports connected to the Windows host.
* **Connection Lifecycle**: Support clean connection and disconnection states via the UI toolbar.
* **Auto-Reconnect**: Provide an option to automatically reconnect to a dropped serial port (e.g., when a USB-to-serial cable is unplugged and plugged back in) utilizing an exponential backoff retry mechanism (1 s → 16 s).
* **Boot-Grace Gate**: Implement a 2.5-second polling suppression delay upon port connection to accommodate microcontroller bootloader cycles (preventing connection lockup on auto-reset DTR lines).
* **Fairness Polling**: Execute polling schedules using a round-robin cursor to ensure fast or blocked schedules do not starve other telemetry requests.

### 4.3 Data Decoding Pipeline
* **Stream Parsing**: Accumulate incoming bytes in a circular buffer and run a sliding-window parser to extract valid frames.
* **On-Wire Verification**: Validate incoming frames using CRC algorithms (CRC16/Modbus, CRC16/CCITT-FALSE, CRC32).
* **Resynchronization**: If a packet contains corrupted bytes, advance the buffer by 1 byte and scan again, ensuring the decoder recovers immediately.
* **Signal Unpacking**: Extract raw bytes from the payload based on computed signal offsets, unpack as signed/unsigned integers or IEEE 754 float types, and apply:
  $$\text{Scaled Value} = (\text{Raw Value} \times \text{Scale}) + \text{Offset}$$
* **Calculations**: Compute group aggregates in real time as synthetic signals appended to the parent frame.

### 4.4 Data Logging Engine
* **Raw Log**: Stream every incoming (RX) and outgoing (TX) packet to a `*_raw.csv` file.
  * Columns: `timestamp`, `direction`, `hex` (uppercase spaced), `delta_t_ms`.
  * The raw logger must flush to disk every 0.5 seconds to minimize data loss in the event of a system crash.
* **Decoded Log**: Write decoded and scaled engineering values to a structured Excel (`*_decoded.xlsx`) workbook.
  * Sheet 1 (`Metadata`): Stores key-value parameters detailing the app version, port configuration, and session start.
  * Sheet 2 (`Data`): Stores synchronized telemetry cycles in wide format. The data is aligned using a trigger frame (the last frame declared in the configuration). When the trigger frame arrives, a complete wide row is committed to disk, containing arrival times and signal values for all frames.
  * Writing to the decoded Excel file must be executed on a separate thread using write-only structures to avoid blocking UI operations.

### 4.5 Post-Test Analysis Suite
* Provide a separate, non-modal window allowing users to load and visualize historic `*_decoded.xlsx` files.
* Support loading multiple logs simultaneously on a stacked plot grid.
* Enable placement of interactive cursors to measure coordinate points, time delta, and value delta.
* Feature an X-Y scatter mode to plot two signals against each other (e.g., current vs. voltage).

---

## 5. Non-Functional & Quality Requirements

### 5.1 Performance & Responsiveness
* **60 Hz Render Refresh**: The UI update timer must drive live chart and data table redrawing at approximately 60 Hz to match high-framerate screens.
* **Threading Isolation**: The main UI thread must not handle serial interface reads, database writes, or file exports. A background `QThread` (`PollingWorker`) must capture, buffer, and verify serial packets, communicating with the UI via Qt signals.
* **OpenGL Acceleration**: Enable hardware-accelerated plot rendering within `pyqtgraph` where supported by the host.

### 5.2 Usability & Layout Constraints
* **Responsive Design**: The application layout must fit down to a 640×480 px screen floor, enabling developers to split a standard 1080p display between Bytehound and their IDE.
* **Dockable Windows**: All functional blocks (plot, bitfields, enums, command panel, parameter editor) must be drag-and-drop dock widgets, with support for popping out into fully qualified native OS windows with standard minimize/maximize buttons.
* **Persistence**: Persist user window geometry, dock locations, layout options, last port/baud settings, and active plot signal keys across restarts in the Windows Registry via `QSettings`.

### 5.3 Reliability & Diagnostics
* **Robust Exception Handling**: Intercept all unhandled exceptions globally and redirect tracebacks to a rotating `bytehound.log` file.
* **Diagnostics Screen**: Provide a modal crash dialog on uncaught exceptions, allowing users to copy the error traceback directly to their clipboard for bug reporting.
* **CLI Validation Tool**: Support a validation CLI option (`python -m app.main --validate <config_file>`) to allow automated continuous integration checking of Excel/CSV configurations.
