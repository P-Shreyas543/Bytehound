# Bytehound | Single-Cell BMS Cycler & Characterization Workstation

An industrial-grade battery cell cycler and characterization workstation tailored for single-cell Battery Management Systems (BMS) conforming to the `Experiment_6_SC_Configuration` hardware specification.

---

## Key Capabilities & Features

### 1. Unified Operator UX & Modern Industrial Theme
- **Unified Action Control:** Replaced confusing dual buttons with a single dynamic action button:
  - `▶ START TEST` (Emerald `#10b981`) when idle.
  - `⏹ STOP TEST` (Crimson `#ef4444`) when active/paused.
  - Fully synchronized with `⏸ Pause / ▶ Resume` and `⏭ Skip Step` controls.
- **Dynamic Title Bar & Branding:**
  - Native Windows 10/11 DWM Immersive Dark Mode integration.
  - Context-aware title bar: `Bytehound | Single-Cell BMS Cycler — [COM15 • Cell 2]`.
  - Multi-resolution brand icons embedded into window headers, taskbars, and standalone executables.
- **Dynamic Typography Scaling:** Live runtime font scaling ($10\text{ pt}$ to $16\text{ pt}$) across the entire application, dynamically adapting plot tick fonts, table headers, cards, and status indicators.
- **Flexible Section Splitters:** User-resizable splitters between KPI dashboards, chart suites, and sequencer tabs with automatic layout coordinate preservation.

---

### 2. High-Precision Metrology & Visualization Suite
- **Synchronized Coincident Dual Y-Axis Grids:**
  - **Left Y-Axis (Cell Voltage):** $0.0\text{ V} - 6.0\text{ V}$ (Span = $6.0\text{ V}$, ticks every $1.0\text{ V}$ with $0.5\text{ V}$ sub-ticks).
  - **Right Y-Axis (Current):** $-3.0\text{ A} - +3.0\text{ A}$ (Span = $6.0\text{ A}$, ticks every $1.0\text{ A}$ with $0.5\text{ A}$ sub-ticks).
  - **Coincident Grid Lines:** Both Left and Right grids are **100% active** and mathematically aligned onto the exact same pixel heights in dark slate (`#334155`), ensuring clean readability with zero grid suppression.
- **Dynamic Auto-Wrapping & Non-Clipping:** Live X-axis auto-ranging extends from $0.0\text{ s}$ to elapsed time with safety margin ($\max(10.0\text{ s}, t_{\text{latest}}) + 1\%$), ensuring all data points remain visible without negative time offset.
- **Linked Multi-Tab Analysis:**
  - **Live Strip Charts:** Cell Voltage & Current vs Elapsed Time.
  - **Thermal Analysis:** Terminal Temperature, Cell Body Temperature, and Ambient Temperature vs Time (linked to primary X-axis).
  - **V-Q Electrochemistry Curves:** Charge and Discharge Voltage vs Capacity ($Q$) overlaid by cycle.
  - **Cycle Degradation Tracker:** Discharge Capacity ($Q_{\text{dis}}$) and Coulombic Efficiency ($\eta_C$) degradation across cycle loops.

---

### 3. Asynchronous Safe Hardware State Machine
- **Cell Multiplexing (Cell 1 vs Cell 2):**
  - Fully supports dual-cell test benches.
  - Selection of **Cell 2** asserts `Bit 1 (CELL_SELECT)` in `0x6000` while preserving safe relay sequencing.
  - During **OCV Relaxation (Rest)**: `Bit 0 (CELL_ENABLE)` is cleared to disconnect power paths while preserving `Bit 1 (CELL_SELECT)`.
- **4-Phase Step Transition Controller (`StepTransitionController`):**
  1. *Clear Unwanted:* Ensures opposing power paths (Charge vs Discharge) are turned off before reconfiguring.
  2. *Relay Sequencing:* Selects target cell with settling verification delay.
  3. *Comparator Hysteresis Reset:* Toggles comparator reset bits ($0 \to 1 \to 0$) to eliminate latching faults.
  4. *Setpoints & Readback Verification:* Applies DAC voltage/current or 4-bit load banks ($0.0\text{ A} - 3.0\text{ A}$ in $0.2\text{ A}$ increments) with auto-retry on readback mismatch.
- **Fail-Safe Zeroing:** Instantaneous emergency zeroing on Stop, BMS Trip, or Communication Watchdog timeout.

---

### 4. Telemetry Decoding & 10 Hz Logging
- **Binary Frame Ingestion:**
  - **`0x1000` (Cell Data):** Voltage ($1\text{ mV}$ resolution), Current (Signed, $1\text{ mA}$ resolution), Terminal Temp ($0.1^\circ\text{C}$), Body Temp ($0.1^\circ\text{C}$).
  - **`0x2000` (Board Parameters):** Ambient Temp ($0.1^\circ\text{C}$), Charge Bus Voltage ($10\text{ mV}$), Load Bus Voltage ($10\text{ mV}$).
  - **`0x3000` (Fault & SoC):** Hardware BMS fault flags (COV, CUV, OCC, OCD, COT, CUT), SoC OCV ($0.5\%$), SoC CC ($0.5\%$).
- **Continuous 10 Hz Telemetry Recording:** High-speed CSV logging with ISO-8601 millisecond timestamps (`YYYY-MM-DDTHH:MM:SS.ffffff`), cycle indexes, step names, and power bus states.

---

## Architecture & Directory Layout

```text
single_cell_cycler/
├── README.md                      # Complete system documentation
├── TRACKER.md                     # Verification checklists and roadmap
├── main.py                        # GUI entry point (DWM dark title bar & app setup)
├── build.py                       # PyInstaller production build automation script
├── SingleCellCycler.spec          # PyInstaller packaging configuration
├── config/
│   ├── cycler_config.py           # Configuration loader & system defaults
│   └── recipes/                   # Standard test recipes (JSON format)
│       ├── standard_capacity_test.json
│       ├── cccv_cycling_5x.json
│       ├── cccv_cycling_15x.json
│       └── dcir_pulse_characterization.json
├── comm/
│   ├── protocol_defs.py           # Frame IDs, bitmasks, and engineering unit scalers
│   ├── packet_codec.py            # High-speed struct binary packing/unpacking
│   └── transceiver.py             # QThread serial transport worker with ring buffering
├── core/
│   ├── profile_model.py           # Recipe, step, and cutoff data models
│   ├── cutoff_detector.py         # Deterministic cut-off criteria evaluation
│   ├── metrics_tracker.py         # Coulomb counting, energy, efficiency, and DCIR
│   ├── safety_monitor.py          # BMS fault monitor & emergency guardrails
│   ├── step_transition_controller.py # 4-phase relay & setpoint state machine
│   └── cycler_engine.py           # Central test execution state machine
├── data/
│   ├── async_logger.py            # Asynchronous threaded 10 Hz CSV recorder
│   └── summary_writer.py          # Cycle and step summary CSV generator
├── ui/
│   ├── main_window.py             # Main cycler docking window, menus, & toolbar
│   ├── theme.py                   # Industrial dark theme styling & typography
│   └── widgets/
│       ├── kpi_dashboard.py       # Live digital KPI cards (V, I, T, SoC, Bus)
│       ├── profile_editor.py      # Interactive recipe step table & cutoff builder
│       ├── live_plots.py          # PyQtGraph charts (V-I-t, T-t, V-Q, Degradation)
│       ├── manual_control.py      # Direct hardware switches (Relay, Loads, Charge)
│       ├── safety_panel.py        # BMS fault LED status indicators
│       └── step_tracker_table.py  # Real-time sequence execution table
└── tests/                         # Pytest automated test suite
    ├── test_cutoff_detector.py
    ├── test_cycler_engine.py
    ├── test_hardware_table.py
    ├── test_metrics_tracker.py
    ├── test_packet_codec.py
    ├── test_safety_monitor.py
    └── test_step_transition.py
```

---

## Operating Instructions

### 1. Launching the Application

Run directly with Python:
```powershell
python single_cell_cycler\main.py
```

Or via module execution from the project root:
```powershell
python -m single_cell_cycler.main
```

### 2. Live Hardware Connection (e.g., COM15)

1. Connect the BMS test bench via USB (e.g., Silicon Labs CP210x UART bridge).
2. Launch the application.
3. Select the target COM Port (e.g., `COM15`) and Baud Rate (`115200`).
4. Click **Connect**. Live telemetry frames will stream in immediately at 10 Hz.
5. In the **Target Cell** selector, choose **Cell 1** or **Cell 2** (window title updates dynamically).
6. Load or configure a test profile in the **Test Recipe Sequencer** tab.
7. Click the green **▶  START TEST** button.
   - The button switches to crimson **⏹  STOP TEST**.
   - Step execution, cut-off evaluation, and CSV data logging begin automatically.

### 3. Running Automated Tests

Run the full pytest suite:
```powershell
pytest single_cell_cycler/tests/ -v
```

Run comprehensive MNC-grade verification (covers font scaling, splitter resizing, graph auto-wrapping, coincident grids, transition retry, and physical COM15 DUT verification):
```powershell
python scratch/mnc_qa_comprehensive_test.py
```

---

## Building Standalone Executable

To compile a standalone Windows executable (`dist/SingleCellCycler.exe`) with embedded icons and recipes:
```powershell
python single_cell_cycler/build.py
```

