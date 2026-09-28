# Single-Cell BMS Cell Cycler

A modern, high-performance battery cell cycler and characterization workstation tailored for single-cell Battery Management Systems conforming to `Experiment_6_SC_Configuration.xlsx`.

---

## Features

- **Automated Recipe Sequencing**: Design multi-step test schedules consisting of **Constant Current Charge**, **CV / Current Taper Charge**, **OCV Relaxation (Rest)**, and **Multi-Stage Load Discharge**.
- **Deterministic Cut-off Detection**:
  - Voltage Upper & Lower Cut-offs ($V \ge V_{\text{max}}$, $V \le V_{\text{min}}$)
  - Current Taper Cut-off ($|I| \le I_{\text{cutoff}}$) for CV completion
  - Duration Time Limit ($\Delta t \ge T_{\text{max}}$)
  - Capacity Limit ($Q \ge Q_{\text{target}}$)
  - Temperature Safety Cut-offs ($T \ge T_{\text{max}}$)
  - Hardware Comparator Trip Detection
- **Real-Time Battery Metrology**:
  - Coulomb counting integration: $Q = \int I \, dt$ (Ah / mAh)
  - Energy integration: $E = \int V \cdot I \, dt$ (Wh / mWh)
  - Cycle Coulombic Efficiency $\eta_C = \frac{Q_{\text{discharge}}}{Q_{\text{charge}}} \times 100\%$
  - Cycle Energy Efficiency $\eta_E = \frac{E_{\text{discharge}}}{E_{\text{charge}}} \times 100\%$
  - DC Internal Resistance (DCIR) calculation at step transitions
- **Comprehensive Safety & Interlocks**:
  - Real-time bitfield decoding of BMS Faults: COV, CUV, OCC, OCD, COT, CUT
  - Software safety guardrails (Overvoltage, Undervoltage, Overcurrent, Thermal)
  - Communication watchdog
  - Immediate emergency hardware shutdown
- **Live High-Performance Visualization (PyQtGraph)**:
  - Synchronized dual-axis strip charts for Voltage & Current vs Time
  - Temperature vs Time
  - $V-Q$ Curves (Voltage vs Capacity charge/discharge overlaid by cycle)
  - Cycle Degradation Tracker (Capacity & Efficiency vs Cycle Number)
  - Decimated ring buffers for lag-free 25-30 FPS rendering over long tests

---

## Directory Structure

```text
single_cell_cycler/
├── README.md                      # This documentation
├── TRACKER.md                     # Roadmap and verification checklist
├── main.py                        # Application entry point
├── config/
│   ├── cycler_config.py           # Configuration loader & defaults
│   └── recipes/                   # Standard test recipes (JSON)
│       ├── standard_capacity_test.json
│       ├── cccv_cycling_5x.json
│       └── dcir_pulse_characterization.json
├── comm/
│   ├── protocol_defs.py           # Binary frame IDs, masks, engineering units
│   ├── packet_codec.py            # High-speed struct pack/unpacker
│   └── transceiver.py             # QThread serial transport worker
├── core/
│   ├── profile_model.py           # Test recipe, step, and cutoff data models
│   ├── cutoff_detector.py         # Deterministic cut-off evaluation
│   ├── metrics_tracker.py         # Coulomb counting, Wh, efficiency, DCIR
│   ├── safety_monitor.py          # BMS fault monitor & emergency shutoff
│   └── cycler_engine.py           # State machine test execution engine
├── data/
│   ├── async_logger.py            # Threaded high-speed CSV telemetry recorder
│   └── summary_writer.py          # Cycle and step summary CSV generator
├── ui/
│   ├── main_window.py             # Main cycler window & docking layout
│   ├── theme.py                   # Industrial dark styling
│   └── widgets/
│       ├── kpi_dashboard.py       # Live digital KPI cards (V, I, T, SoC, Ah, Wh)
│       ├── profile_editor.py      # Interactive recipe step table & cutoff builder
│       ├── live_plots.py          # PyQtGraph charts (V-I-t, T-t, V-Q, Aging)
│       ├── manual_control.py      # Direct hardware switches (Relay, Loads, Charge)
│       ├── safety_panel.py        # BMS fault LED status indicators
│       └── step_tracker_table.py  # Real-time sequence execution table
└── tests/                         # Pytest automated test suite
```

---

## Getting Started

### 1. Launching the Cycler Application

From the project root:
```powershell
.venv\Scripts\python -m single_cell_cycler.main
```
Or directly:
```powershell
.venv\Scripts\python single_cell_cycler\main.py
```

### 2. Operating with BMS Hardware

1. Connect your single-cell BMS board to the workstation PC via USB/UART.
2. Launch the application.
3. Select the detected BMS serial COM port (e.g., `COM3`, `COM7`) and baud rate (default: `115200`).
4. Click **Connect**. Live telemetry frames will stream in immediately, illuminating KPI cards and real-time graphs.
5. Select or customize your test recipe (e.g., `CCCV Cycling (5 Cycles)` or create your own steps with cutoff conditions).
6. Click **▶ START TEST** to execute the profile. Real-time telemetry is recorded asynchronously to the `logs/` directory.

### 3. Running Automated Tests

To run the automated pytest test suite:
```powershell
.venv\Scripts\pytest single_cell_cycler\tests -v
```
