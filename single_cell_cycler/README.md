# Bytehound | Single-Cell BMS Cycler & Characterization Workstation

An industrial-grade battery cell cycler and characterization workstation tailored for single-cell Battery Management Systems (BMS) conforming to the `Experiment_6_SC_Configuration` hardware specification.

---

## Key Capabilities & Features

### 1. Unified Operator UX & Workflow (Pillar 1)
- **Unified Action Control:** Dynamic action button switching between `▶ START TEST` (Emerald `#10b981`) and `⏹ STOP TEST` (Crimson `#ef4444`), synchronized with `⏸ Pause / ▶ Resume` and `⏭ Skip Step`.
- **Dynamic Immersive Dark Theme:** Native Windows 10/11 DWM dark title bar and context-aware title: `Bytehound | Single-Cell BMS Cycler — [COM15 • Cell 2]`.
- **Dynamic Typography Scaling:** Live runtime font scaling ($10\text{ pt}$ to $16\text{ pt}$) dynamically scaling all HUD chips, tables, and plots without text clipping.
- **Interactive Tracking Crosshairs & Monospace HUD:** Hover inspection across all plots displaying exact time, voltage, current, capacity, and temperature coordinates.
- **Quick-Zoom Toolbar Controls:** 1-click `[⤢ Fit All]` and `[⏱ Current Step]` auto-framing.
- **Cell Chemistry Safety Guardrails (`IMP-03`):** Built-in presets for NMC, LFP, LTO, and Sodium-ion (Na-ion) with pre-test envelope validation.
- **Visual Recipe Timeline Profile Preview (`IMP-04`):** Interactive synthetic profile renderer visualizing voltage/current setpoints, cut-off checkpoints, and multi-cycle loops before running.

---

### 2. Advanced Electrochemical Metrology (Pillar 2)
- **Coincident Dual Y-Axis Grids:** Left ($0-6\text{ V}$) and Right ($-3\text{ A} - +3\text{ A}$) grids mathematically aligned with zero grid suppression.
- **Differential Capacity Analysis ($dQ/dV$ vs $V$, `IMP-05`):** Dedicated interactive tab with pure-NumPy Savitzky-Golay numerical smoothing, local phase transition peak detection (◆), dual-lobe `[± Butterfly]` and `[|dQ/dV|]` absolute overlays.
- **Standardized Pulse DCIR Mapping (`IMP-06`):** Standard IEC 62660-1 / USABC pulse resistance evaluation across $R_{1\text{s}}$ (ohmic), $R_{10\text{s}}$ (standard), and $R_{30\text{s}}$ (diffusion polarization) windows.
- **Aging Degradation Modeling & 80% EOL Forecasting (`IMP-07`):** Pure-NumPy linear and exponential decay regression projecting cycle number to 80% nominal cutoff with $R^2$ goodness-of-fit, Coulombic Efficiency ($\eta_{\text{CE}}\%$), Energy Efficiency ($\eta_{\text{EE}}\%$), and linked DCIR tracking.

---

### 3. Mission-Critical Test Integrity & Lab Safeguards (Pillar 3)
- **Power Loss / Crash Recovery (`IMP-08`):** Atomic state journaling (`logs/.active_test_journal.json`) using atomic rename (`os.replace`) to survive sudden workstation reboots. On startup, prompts operator to resume testing exactly from interrupted cycle/step without losing historical data.
- **Rate-of-Rise Thermal Trigger Early Warning ($dT/dt$, `IMP-09`):** Moving thermal rate evaluation triggering emergency de-energization if $dT/dt \ge 1.5^\circ\text{C}/\text{min}$ sustained for $\ge 2.5\text{ s}$ to prevent thermal runaway before dangerous absolute limits are reached.
- **Automated Pre-Flight Hardware Sanity Handshake (`IMP-10`):** Automated 4-dimension diagnostic check evaluating:
  1. *Telemetry Link & Latency:* Confirms active high-speed streaming ($< 1.0\text{ s}$).
  2. *Cell Sense Lead Voltage:* Detects detached/floating Kelvin sense leads ($0.00\text{ V}$).
  3. *Thermistor Parity & Health:* Confirms probes match within $\pm 4.0^\circ\text{C}$ of ambient, flagging open-circuit thermistors.
  4. *Idle MOSFET De-energization:* Confirms zero quiescent leakage ($|I| \le 0.050\text{ A}$) and de-energized load stages.
  Interactive `PreflightDialog` provides clear diagnostics and actionable recovery advice.

---

### 4. Automation, Reporting & Remote Telemetry (Pillar 4)
- **One-Click Diagnostic Run Exporter (`IMP-11`):** `📦 Export Run` bundles raw 10 Hz telemetry CSV, step and cycle summary CSVs, recipe JSON, application logs, and a cryptographic `manifest.json` with SHA-256 digests into a single `.zip` archive.
- **One-Click HTML / PDF Test Certification Report (`IMP-12`):** `📄 Test Report` generates an executive, self-contained HTML5 certificate with embedded pure-SVG electrochemical degradation plots, cycle breakdown audit tables, and print-to-PDF styles compliant with IEC 62660-1 / USABC.
- **Remote Lab Notifications (`IMP-13`):** Non-blocking background `WebhookNotifier` dispatches rich embed cards to Discord, Slack, and Microsoft Teams on Test Start, Safety Trips, and Test Completion. Configured via the `🔔 Webhook` toolbar dialog.

---

## Architecture & Directory Layout

```text
single_cell_cycler/
├── README.md                      # Complete system documentation
├── improvements.md                # Strategic enhancement register & product roadmap (100% completed)
├── main.py                        # GUI entry point (DWM dark title bar & app setup)
├── build.py                       # PyInstaller production build automation script
├── SingleCellCycler.spec          # PyInstaller packaging configuration
├── config/
│   ├── cycler_config.py           # Configuration loader & system defaults
│   ├── webhook_settings.json      # Remote notification settings
│   └── recipes/                   # Standard test recipes (JSON format)
├── comm/
│   ├── protocol_defs.py           # Frame IDs, bitmasks, and engineering unit scalers
│   ├── packet_codec.py            # High-speed struct binary packing/unpacking
│   ├── transceiver.py             # QThread serial transport worker with priority TX queue
│   └── webhook_notifier.py        # Asynchronous Discord/Slack/Teams webhook dispatcher
├── core/
│   ├── profile_model.py           # Recipe, step, cutoff, and chemistry data models
│   ├── aging_analysis.py          # Pure-NumPy linear & exponential degradation fitting
│   ├── dqv_analysis.py            # Savitzky-Golay dQ/dV numerical differentiation
│   ├── preflight_checker.py       # 4-dimension hardware sanity handshake
│   ├── state_journal.py           # Atomic crash recovery journaling
│   ├── cutoff_detector.py         # Deterministic cut-off criteria evaluation
│   ├── metrics_tracker.py         # Coulomb counting, energy, efficiency, and pulse DCIR
│   ├── safety_monitor.py          # BMS fault monitor, dT/dt rate-of-rise thermal trigger
│   ├── step_transition_controller.py # 4-phase relay & setpoint state machine
│   └── cycler_engine.py           # Central test execution state machine
├── data/
│   ├── async_logger.py            # Asynchronous threaded 10 Hz CSV recorder
│   ├── run_exporter.py            # Zip run packaging with SHA-256 manifest
│   ├── report_generator.py        # Publication-grade HTML/PDF test certificate generator
│   └── summary_writer.py          # Cycle and step summary CSV generator
├── ui/
│   ├── main_window.py             # Main cycler docking window, toolbar, and menus
│   ├── theme.py                   # Industrial dark theme styling & typography
│   └── widgets/
│       ├── kpi_dashboard.py       # Live digital KPI cards (V, I, T, SoC, Bus)
│       ├── profile_editor.py      # Interactive recipe step table, cutoffs & chemistry
│       ├── live_plots.py          # 5-tab live plotting suite (Strip, Temp, V-Q, dQ/dV, Aging)
│       ├── preflight_dialog.py    # Hardware sanity handshake diagnostic modal
│       ├── webhook_dialog.py      # Webhook notification settings modal
│       ├── manual_control.py      # Direct hardware switches (Relay, Loads, Charge)
│       ├── safety_panel.py        # BMS fault LED status indicators
│       └── step_tracker_table.py  # Real-time sequence execution table
└── tests/                         # Pytest automated test suite (85 tests, 100% pass)
```

---

## Operating Instructions

### 1. Launching the Application
```powershell
python -m single_cell_cycler.main
```

### 2. Live Hardware Connection
1. Connect BMS test bench via USB.
2. Select target COM Port (e.g., `COM15`) and Baud Rate (`115200`), then click **Connect**.
3. Observe automated pre-flight sanity badge: `● Pre-Flight: 4/4 Passed`. Click for diagnostics.
4. Select active cell (`Cell 1` or `Cell 2`) and load a recipe in the **Test Recipe Sequencer**.
5. Click **▶  START TEST** to begin automated cycling.

### 3. Running Automated Tests
Run the complete automated test suite (85 tests):
```powershell
pytest single_cell_cycler/tests/ -v
```

