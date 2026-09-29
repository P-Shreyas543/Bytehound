# Bytehound Single-Cell BMS Cycler — Strategic Improvements & Product Roadmap

This document serves as the master tracking register for the Bytehound Single-Cell BMS Cycler evolutionary roadmap. Each item is formally specified with an engineering problem statement, implementation design, and MNC-grade test acceptance criteria.

We will implement and verify these enhancements **pillar by pillar**.

---

## Roadmap Progress Dashboard

| Pillar | Focus Area | Total Items | Completed | In Progress | Pending |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Pillar 1** | Operator Ergonomics & Workflow | 4 | 4 | 0 | 0 |
| **Pillar 2** | Advanced Electrochemical Metrology | 3 | 3 | 0 | 0 |
| **Pillar 3** | Mission-Critical Integrity & Safeguards | 3 | 3 | 0 | 0 |
| **Pillar 4** | Automation, Reporting & Remote Telemetry | 3 | 3 | 0 | 0 |
| **TOTAL** | | **13** | **13** | **0** | **0** |

---

## Pillar 1: Operator Ergonomics & Workflow (Lab Usability)

### `IMP-01`: Interactive Plot Crosshairs & Floating Real-Time HUD Readout
* **Priority:** `P0 (Sprint 1)`
* **Status:** `COMPLETED & VERIFIED` (2026-09-29)
* **Target Module:** `single_cell_cycler/ui/widgets/live_plots.py`
* **Problem Statement:** Researchers need to inspect exact voltage, current, and temperature at specific points on live and historical curves without guessing or manually opening raw CSV files.
* **Technical Design:**
  - Attached an infinite vertical tracking line (`pg.InfiniteLine(angle=90, movable=False)`) to `plot_vi` and `plot_temp`.
  - Connected `scene().sigMouseMoved` to interpolate the nearest sampled data point along the elapsed time axis via binary search (`np.searchsorted`).
  - Displayed a floating HUD chip styled with dark monospace pill:
    $$\text{HUD: } [⏱ 1245.2\text{s} \mid \text{V: } 3.821\text{ V} \mid \text{I: } +1.498\text{ A}]$$
  - Synchronized vertical crosshair positions across both `plot_vi` and `plot_temp`.
* **Acceptance Criteria & Test Plan:**
  1. Hovering mouse over graph renders vertical guideline at mouse X coordinate. (PASS)
  2. Text readout displays exact interpolated coordinates. (PASS)
  3. Zero FPS lag or rendering jitter during 10 Hz live streaming. (PASS)
  4. Fully verified via automated test suite `tests/test_live_plots_imp01_imp02.py`.

---

### `IMP-02`: Quick-Zoom Toolbar Controls & Axis Framing
* **Priority:** `P0 (Sprint 1)`
* **Status:** `COMPLETED & VERIFIED` (2026-09-29)
* **Target Module:** `single_cell_cycler/ui/widgets/live_plots.py`
* **Problem Statement:** After zooming in with mouse drag to inspect a voltage plateau, operators have to manually reset the view. Operators need 1-click preset view framing.
* **Technical Design:**
  - Added compact toolbar buttons above the charts:
    - `[⤢ Fit All]`: Resets X-range to $[0.0, \max(10.0, t)]$, Voltage to $[0.0, 6.0\text{ V}]$, Current to $[-3.0, +3.0\text{ A}]$, Temperature to $[0.0, 70.0^\circ\text{C}]$.
    - `[⏱ Current Step]`: Zooms X-axis to span only the active step start time to current time.
    - `[🔄 Current Cycle]`: Zooms X-axis to span the start of the current cycle.
    - `[⏪ 10m]`: Frames the last 600 seconds of elapsed test data.
    - `[⏪ 1m]`: Frames the last 60 seconds of elapsed test data.
  - Handled `sigRangeChangedManually` from PyQtGraph `ViewBox` to switch into `ZoomMode.MANUAL`, ensuring programmatic 10 Hz timer updates never fight human mouse interactions.
* **Acceptance Criteria & Test Plan:**
  1. Clicking `[Fit All]` restores canonical coincident bounds. (PASS)
  2. Clicking `[Current Step]` clamps X-axis precisely to step boundary. (PASS)
  3. Retains synchronized dual Y-axis coincident grid lines. (PASS)
  4. Fully verified via automated test suite `tests/test_live_plots_imp01_imp02.py`.

---

### `IMP-03`: Cell Chemistry Presets & Voltage Safety Guardrails
* **Priority:** `P0 (Sprint 1)`
* **Status:** `COMPLETED & VERIFIED` (2026-09-29)
* **Target Module:** `single_cell_cycler/core/profile_model.py`, `ui/widgets/profile_editor.py`, `ui/main_window.py`
* **Problem Statement:** Accidental entry of an NMC voltage cutoff ($4.2\text{ V}$) for an LFP cell ($3.65\text{ V}$ max) risks cell swelling or fire.
* **Technical Design:**
  - Added formal `ChemistryDef` models and `CHEMISTRY_PRESETS` catalog for `NMC`, `LFP`, `LTO`, `NA_ION`, and `CUSTOM`.
  - Added a **Cell Chemistry Selector** dropdown and real-time Safe Operating Window pill badge in the recipe editor header.
  - Implemented `TestRecipe.validate_chemistry_limits()` checking step voltage setpoints, charge currents, discharge currents, upper cutoffs, and lower cutoffs.
  - Visual validation: violating table cells and rows receive warning background (`#450a0a`), and an amber/red warning banner describes the specific safety breach.
  - Pre-flight blocking in `MainWindow._start_test()`: blocks test start and logs `CRITICAL` if chemistry guardrails are violated.
  - Dynamic Safety Monitor Envelope: active chemistry safe bounds ($V_{\text{min}} - 0.05\text{V}$, $V_{\text{max}} + 0.05\text{V}$) are dynamically programmed into `SafetyMonitor.limits` at test execution time.
* **Acceptance Criteria & Test Plan:**
  1. Select LFP with 4.2V charge cutoff: immediately flags violation. (PASS)
  2. Table row turns red and warning banner displays: *"Step 1: Charge setpoint 4.20V exceeds LFP safe max (3.65V)"*. (PASS)
  3. Start test is safely blocked with a modal pre-flight dialog. (PASS)
  4. Fully verified via automated test suite `tests/test_chemistry_guardrails_imp03.py`.

---

### `IMP-04`: Visual Recipe Timeline Profile Preview
* **Priority:** `P1`
* **Status:** `COMPLETED & VERIFIED` (2026-09-29)
* **Target Module:** `single_cell_cycler/ui/widgets/profile_editor.py`
* **Problem Statement:** Technicians configuring multi-step cycling recipes rely on raw numbers in table rows and cannot visually confirm if the programmed schedule matches the intended profile.
* **Technical Design:**
  - Implemented `RecipeTimelinePreview(QWidget)`: dual-axis simulated trajectory preview for $V(t)$ (cyan) and $I(t)$ (green), vertical step markers ($S_1, S_2\dots$), and loop step unrolling up to 2 iterations.
  - Embedded preview widget directly beneath step operation buttons in `RecipeEditorWidget`.
  - Dynamically synthesizes piecewise expected $V(t)$ and $I(t)$ profile segments (CC charge ramps, CV holds, Rest plateaus, CC discharge ramps) and draws the planned schedule curve with step transition boundaries and badges.
  - Automatically updates in real-time as steps are added, edited, reordered, or deleted.
* **Acceptance Criteria & Test Plan:**
  1. Adding a 1.5A Charge -> 10m Rest -> 1.2A Discharge recipe generates a 3-stage preview plot. (PASS)
  2. Reordering steps updates preview instantly. (PASS)
  3. Fully verified via automated test suite `tests/test_profile_preview_imp04.py`.
  4. Rendered screenshot captured at `scratch/test_imp04_preview_rendered.png`. (PASS)

---

## Pillar 2: Advanced Electrochemical Metrology

### `IMP-05`: Differential Capacity Analysis ($dQ/dV$ vs $V$) Interactive Tab
* **Priority:** `P1`
* **Status:** `COMPLETED & VERIFIED` (2026-09-29)
* **Target Module:** `single_cell_cycler/core/dqv_analysis.py`, `ui/widgets/live_plots.py`
* **Problem Statement:** Battery electrochemists use $dQ/dV$ plots to non-destructively track degradation mechanisms (loss of lithium inventory, active material loss, phase transitions).
* **Technical Design:**
  - Implemented pure NumPy Savitzky-Golay numerical differentiation (`compute_dq_dv`) with uniform voltage resampling ($\Delta V = 5, 10, 15\text{ mV}$) to eliminate quantization noise from $1\text{ mV}$ steps without external scientific library bloat.
  - Added local peak prominence detection (`find_dqv_peaks`) to automatically locate and annotate electrochemical phase transition voltages.
  - Added a dedicated 4th tab to `LivePlotWidget`: **dQ/dV Capacity Analysis**.
  - Built interactive controls:
    - `[± Butterfly]`: Dual-lobe view plotting Charge ($+dQ/dV$) on upper half and Discharge ($-dQ/dV$) on lower half separated by zero baseline.
    - `[|dQ/dV|]`: Overlay Absolute Differential Capacity view.
    - Grid resolution toggles: `[5 mV]`, `[10 mV]`, `[15 mV]`.
    - `[⤢ Fit]`: Auto-framing voltage and differential capacity bounds.
  - Interactive tracking crosshair with real-time HUD chip display ($V$, $dQ/dV$, active cycle/step) and phase transition peak scatter markers (◆).
  - Historical cycle curves are retained across cycles with progressive cycle palette gradient (`#38bdf8`, `#22c55e`, `#a855f7`, etc.).
* **Acceptance Criteria & Test Plan:**
  1. Tab renders $dQ/dV$ ($(\text{mAh}/\text{V})$ vs $V$) in real-time. (PASS)
  2. Peak positions align with characteristic phase transition voltages. (PASS)
  3. Zero FPS lag (< 10 ms execution for 10,000 samples). (PASS)
  4. Fully verified via automated test suites `tests/test_dqv_analysis_imp05.py` and `tests/test_live_plots_imp05.py`.
  5. Rendered screenshot captured at `scratch/test_imp05_dqv_rendered.png`. (PASS)

---

### `IMP-06`: Standardized Pulse DCIR & Resistance Mapping (IEC 62660-1 / USABC)
* **Priority:** `P2`
* **Status:** `COMPLETED & VERIFIED` (2026-09-29)
* **Target Module:** `single_cell_cycler/core/metrics_tracker.py`, `single_cell_cycler/data/summary_writer.py`
* **Problem Statement:** Current DCIR calculation only captures instantaneous transition delta without standard 10-second or 30-second pulse protocol adherence.
* **Technical Design:**
  - Implemented standardized pulse resistance evaluation across time windows:
    - $R_{1\text{s}}$: Ohmic + initial charge transfer polarization ($t \in [0.7\text{s}, 1.3\text{s}]$)
    - $R_{10\text{s}}$: Standard IEC 62660-1 / USABC pulse resistance including solid-state diffusion ($t \in [9.5\text{s}, 10.5\text{s}]$):
      $$R_{10\text{s}} = \frac{|V(t_0) - V(t_0 + 10\text{s})|}{|I_{\text{pulse}} - I_{\text{baseline}}|}$$
    - $R_{30\text{s}}$: Total polarization resistance ($t \in [29.0\text{s}, 31.0\text{s}]$)
  - Added `DCIRMeasurement` structured pulse logs with baseline voltages, pulse currents, and $\Delta I$.
  - Integrated `dcir_1s_mohm`, `dcir_10s_mohm`, and `dcir_30s_mohm` into `StepMetrics`, `CycleSummary`, and CSV exports (`write_step_summary_csv`, `write_cycle_summary_csv`).
* **Acceptance Criteria & Test Plan:**
  1. Verified against pre-calculated synthetic pulse data with known $15.0\text{ m}\Omega$, $18.0\text{ m}\Omega$, and $22.0\text{ m}\Omega$ impedances. (PASS)
  2. Values recorded in step and cycle summary CSVs with standardized columns. (PASS)
  3. Fully verified via automated test suite `tests/test_dcir_metrology_imp06.py`. (PASS)

---

### `IMP-07`: Coulombic & Energy Efficiency Degradation Trend Modeling & EOL Forecasting
* **Priority:** `P2`
* **Status:** `COMPLETED & VERIFIED` (2026-09-29)
* **Target Module:** `single_cell_cycler/core/aging_analysis.py`, `single_cell_cycler/ui/widgets/live_plots.py`
* **Problem Statement:** Long-term qualification cycling requires automated trend extrapolation to forecast when the battery cell will reach the standard $80.0\%$ End-of-Life (EOL) cutoff, while tracking Coulombic Efficiency ($\eta_{\text{CE}}$), Energy Efficiency ($\eta_{\text{EE}}$), and DCIR resistance growth.
* **Technical Design:**
  - Created pure-NumPy degradation regression engine (`core/aging_analysis.py`) implementing linear regression ($Q(n) = a \cdot n + b$) and log-linear exponential decay regression ($Q(n) = Q_0 \cdot e^{-k n}$) via `np.linalg.lstsq` without requiring SciPy wheel dependencies.
  - Implemented analytical projection to solve for cycle number $n_{\text{EOL}}$ where $Q(n_{\text{EOL}}) = 0.80 \cdot Q_{\text{initial}}$, with goodness-of-fit $R^2$ determination.
  - Integrated Tab 5 (`Cycle Aging & Health`) into `LivePlotWidget` with a vertical dual-chart splitter:
    - **Top Chart (Capacity Fade & Forecast):**
      - Discharge capacity ($Q_{\text{dis}}$, sky blue `#38bdf8`) with circular markers.
      - Charge capacity ($Q_{\text{chg}}$, emerald green `#22c55e`) with square markers.
      - Projected degradation forecast trajectory (golden yellow `#facc15` dashed curve).
      - Horizontal 80% nominal EOL target line (rose `#f43f5e` dashed line) with persistent text callout.
      - Status badges: Dynamic health retention (`● Retention: 97.9% | EOL (80%): Cycle 133`) and fade rate (`Fade: -3.80 mAh/cyc (R²: 0.999)`).
      - Regression model toggles: `[Linear]` vs `[Exp]` with active highlight styling and auto-fit button.
    - **Bottom Chart (Efficiency & Internal Resistance):**
      - Left Y-Axis: Coulombic Efficiency ($\eta_{\text{CE}}\%$, emerald `#10b981`) and Energy Efficiency ($\eta_{\text{EE}}\%$, purple `#a855f7`) with 100% reference line.
      - Linked Right Y-Axis: Standardized 10s DCIR ($R_{10\text{s}}$, amber `#f59e0b` diamond markers) synced geometrically across resizing.
    - Interactive inspection crosshairs and floating HUD chip displaying active cycle metrics upon mouse hover.
* **Acceptance Criteria & Test Plan:**
  1. Curve fitting executes in $< 5\text{ ms}$ for hundreds of cycles using pure NumPy. (PASS)
  2. Forecast updates seamlessly on cycle completion and handles single-cycle or zero-slope gracefully. (PASS)
  3. Fully verified via automated test suites `tests/test_aging_analysis_imp07.py` (3/3 passed) and `tests/test_live_plots_imp07.py` (4/4 passed).
  4. Rendered visual screenshot captured at `scratch/test_imp07_aging_rendered.png`. (PASS)

---

## Pillar 3: Mission-Critical Test Integrity & Lab Safeguards

### `IMP-08`: Power Loss / Crash Recovery & Atomic State Journaling
* **Priority:** `P1`
* **Status:** `COMPLETED & VERIFIED` (2026-09-29)
* **Target Module:** `single_cell_cycler/core/state_journal.py`, `single_cell_cycler/core/cycler_engine.py`, `ui/main_window.py`
* **Problem Statement:** Workstation reboots (e.g. Windows Update, power flicker) during 72-hour tests lose all state, forcing the operator to restart from Cycle 1.
* **Technical Design:**
  - Implemented `StateJournalManager` writing atomic JSON journal (`logs/.active_test_journal.json`) via `.tmp` file and `os.replace` to prevent corrupted files during sudden power failure.
  - Stores: Recipe name, recipe dict, active step index, current cycle index, step history, cycle summaries, cumulative Ah/Wh, active cell (Cell 1/2), and active CSV log file path.
  - Synchronized on test start, step completion, and cycle loop transitions.
  - Cleared cleanly on normal test completion, manual abort, or discard.
  - On application startup or window instantiation, `check_and_prompt_crash_recovery()` detects active journals and prompts operator:
    *"An interrupted test was detected from a previous session on Cell 2 at Cycle 1, Step 2 ('Phase 2 Discharge'). Would you like to resume testing?"*
  - Seamless resumption:
    - Restores target cell selection and recipe in profile editor.
    - Appends to existing CSV log file without duplicate headers via `AsyncTelemetryLogger.resume_session`.
    - Replays completed steps into `TrackerTableWidget` and completed cycles into `LivePlotWidget` Aging tab.
    - Restores `MetricsTracker` cumulative counters and transitions hardware directly for the interrupted step.
* **Acceptance Criteria & Test Plan:**
  1. Atomic write-and-read verifies all recipe, metrology, and cycle summary data serialized without corruption. (PASS)
  2. Crash simulation verifies fresh `CyclerEngine` resumes exactly from interrupted step with step history intact. (PASS)
  3. UI integration verifies `MainWindow` detects unclosed journal, restores cell/recipe/table/plots, and resumes logging. (PASS)
  4. Fully verified via automated test suite `tests/test_crash_recovery_imp08.py` (3/3 passed). (PASS)

---

### `IMP-09`: Rate-of-Rise Thermal Trigger Early Warning ($dT/dt$)
* **Priority:** `P1`
* **Status:** `COMPLETED & VERIFIED` (2026-09-29)
* **Target Module:** `single_cell_cycler/core/safety_monitor.py`
* **Problem Statement:** Absolute temperature limits ($T > 45^\circ\text{C}$ / $60^\circ\text{C}$) trip too late during internal micro-shorts or exothermic onset. A sharp rate-of-rise ($dT/dt > 1.5^\circ\text{C}/\text{min}$) indicates runaway before dangerous heat builds up.
* **Technical Design:**
  - Added rate-of-rise limits to `SafetyLimits`:
    - `max_temp_rate_of_rise_c_per_min = 1.5` ($^\circ\text{C}/\text{min}$)
    - `temp_rate_window_s = 15.0` (moving slope calculation window)
    - `temp_rate_sustain_s = 2.5` (persistence filter to eliminate noisy false-trips)
  - Evaluated moving temperature slope over the trailing window:
    $$\frac{dT}{dt} = \frac{T_t - T_{t-\Delta t}}{\Delta t} \times 60.0 \quad (^\circ\text{C}/\text{min})$$
  - If $dT/dt \ge 1.5^\circ\text{C}/\text{min}$ sustained for $> 2.5\text{ seconds}$, immediately triggers emergency safety trip:
    `SAFETY TRIP: Rate of temperature rise exceeded limit: {rate:.2f} °C/min (limit: 1.50 °C/min sustained for 2.5s)`
  - Immediately de-energizes all charge/discharge controls and disconnects cell relay with Priority 0 emergency commands.
* **Acceptance Criteria & Test Plan:**
  1. Synthetic thermal runaway ramp of $+3.0^\circ\text{C}/\text{min}$ triggers trip within sustain time and dispatches Priority 0 de-energization frames. (PASS)
  2. Steady high temperature ($45^\circ\text{C}$) does NOT trip rate-of-rise. (PASS)
  3. Sensor noise jitter ($\pm 0.15^\circ\text{C}$) does NOT trigger false trips. (PASS)
  4. Fully verified via automated test suite `tests/test_thermal_runaway_imp09.py` (4/4 passed). (PASS)

---

### `IMP-10`: Automated Pre-Flight Hardware Sanity Handshake
* **Priority:** `P2`
* **Status:** `COMPLETED & VERIFIED` (2026-09-29)
* **Target Module:** `single_cell_cycler/core/preflight_checker.py`, `single_cell_cycler/ui/widgets/preflight_dialog.py`, `single_cell_cycler/ui/main_window.py`
* **Problem Statement:** Technicians often start tests with a loose thermistor or disconnected voltage sense lead, resulting in aborted runs hours later or battery degradation.
* **Technical Design:**
  - Implemented `PreflightSanityChecker` (`core/preflight_checker.py`) evaluating 4 mission-critical hardware dimensions:
    1. **Telemetry Link & Communication Latency**: Checks packet arrival frequency ($< 1.0\text{ s}$ PASS, $> 2.5\text{ s}$ or offline FAIL).
    2. **Cell Sense Lead Voltage & Continuity**: Detects detached/floating Kelvin sense leads ($V < 0.50\text{ V}$) or overvoltage ($V > 4.55\text{ V}$) before load engagement.
    3. **Thermistor Parity & Probe Continuity**: Verifies terminal and body probes agree within $\pm 4.0^\circ\text{C}$ of ambient, flagging open-circuit probes ($0.0^\circ\text{C}$ or $-40^\circ\text{C}$) and severe disparity ($\Delta T > 6.0^\circ\text{C}$).
    4. **Idle MOSFET De-energization & Quiescent Leakage Current**: Confirms load resistor MOSFET readbacks and charge controls are $0\text{x00}$ with zero current flow ($|I| \le 0.050\text{ A}$), flagging shorted MOSFETs or stuck relays.
  - Built interactive modal `PreflightDialog` (`ui/widgets/preflight_dialog.py`) displaying:
    - Status column with bold indicators (`● PASS`, `▲ WARN`, `✕ FAIL`).
    - Subsystem name, measured value, expected criteria, and actionable diagnostic guidance.
    - Prominent contextual banner explaining safety state.
    - `[↻ Re-Run Sanity Check]` button for instant live re-evaluation.
  - Added toolbar status badge `btn_preflight` on `MainWindow`:
    - Auto-triggers 1.5s after serial connection.
    - Dynamically updates pill style (`● Pre-Flight: 4/4 Passed` in emerald, amber warning pill, or red failure pill).
    - Unifies pre-test checks in `_start_test`: blocks execution on critical hardware failure and prompts on advisory warnings.
* **Acceptance Criteria & Test Plan:**
  1. Detached Kelvin sense lead ($0.00\text{ V}$) blocks test start with critical diagnostic report. (PASS)
  2. Disconnected thermistor ($0.0^\circ\text{C}$) or thermal disparity ($\Delta T > 6.0^\circ\text{C}$) trips sanity failure. (PASS)
  3. Quiescent leakage current ($> 0.150\text{ A}$) or active MOSFET registers at idle fails sanity check. (PASS)
  4. Fully verified via automated test suites `tests/test_preflight_sanity_imp10.py` (5/5 passed) and `tests/test_preflight_ui_imp10.py` (4/4 passed).
  5. Visual verification screenshot captured at `scratch/test_imp10_preflight_rendered.png`. (PASS)

---

## Pillar 4: Automation, Reporting & Remote Telemetry

### `IMP-11`: One-Click "Bundle & Share Run" Diagnostic Exporter (`.zip`)
* **Priority:** `P0 (Sprint 1)`
* **Status:** `COMPLETED & VERIFIED` (2026-09-29)
* **Target Module:** `single_cell_cycler/data/run_exporter.py`, `single_cell_cycler/ui/main_window.py`
* **Problem Statement:** When an error occurs or a test completes, sending files to engineering requires manually hunting for CSVs in `logs/` and finding relevant portions of `cycler_app.txt`.
* **Technical Design:**
  - Created `export_run_package` module (`data/run_exporter.py`) automating end-to-end bundling into compressed `.zip` archives.
  - Automatically packages:
    1. Raw 10 Hz telemetry CSV (`telemetry_raw_10hz.csv`).
    2. Completed step summary CSV (`summary_steps.csv`).
    3. Completed cycle summary CSV (`summary_cycles.csv`).
    4. Test profile recipe JSON (`recipe.json`).
    5. The application log slice/tail (`diagnostic_log.txt`).
    6. A cryptographic `manifest.json` featuring format version, export timestamp, operator, machine/cell ID, execution status, cumulative throughput metrics (Ah/Wh), and per-file SHA-256 integrity digests.
  - Added toolbar button `📦 Export Run` on `MainWindow`:
    - Opens native "Save As" file dialog defaulting to `exports/Run_Cell{ID}_YYYYMMDD_HHMMSS.zip`.
    - Handles active runs, safety trips, or idle history exports.
* **Acceptance Criteria & Test Plan:**
  1. Verified full archive bundling with recipe, raw telemetry, step/cycle CSVs, log tail, and manifest. (PASS)
  2. SHA-256 hashes generated in `manifest.json` cryptographically match extracted files. (PASS)
  3. Handles partial runs, missing files, or early aborts without raising unhandled exceptions. (PASS)
  4. Fully verified via automated test suite `tests/test_run_exporter_imp11.py` (4/4 passed). (PASS)

---

### `IMP-12`: One-Click PDF / HTML Test Certification Report Generator
* **Priority:** `P1`
* **Status:** `COMPLETED & VERIFIED` (2026-09-29)
* **Target Module:** `single_cell_cycler/data/report_generator.py`, `single_cell_cycler/ui/main_window.py`
* **Problem Statement:** Lab managers, certification bodies, and clients require formal test summary certificates rather than raw CSV spreadsheets.
* **Technical Design:**
  - Implemented `generate_html_report` (`data/report_generator.py`) producing self-contained, publication-grade HTML5 battery test certificates with zero external web dependencies or heavyweight browser packages.
  - Report features:
    - **Header & Accreditation:** Bytehound branding, Certificate ID (`CERT-C{Cell}-{Timestamp}`), generation timestamp, and IEC 62660-1 / USABC compliance pill badge.
    - **Executive KPI Cards:** Initial vs Final capacity, capacity retention $\%$, capacity loss $\%$ and mAh, delivered throughput ($Wh$ and $Ah$), average Coulombic efficiency ($\overline{\eta}_{\text{CE}}\%$), and initial vs final $R_{10\text{s}}$ DCIR resistance.
    - **Embedded Pure-SVG Vector Plots:**
      1. Capacity Fade & Coulombic Efficiency vs Cycle (Discharge $Q_{\text{dis}}$, Charge $Q_{\text{chg}}$, and 80% EOL target line).
      2. DCIR Internal Resistance Evolution ($R_{10\text{s}}$ pulse resistance growth across cycles).
    - **Cycle Breakdown Audit Table:** Cycle index, charge/discharge capacity, charge/discharge energy, efficiencies ($\eta_{\text{CE}}\%$, $\eta_{\text{EE}}\%$), DCIR $R_{10\text{s}}$, and cycle durations.
    - **Dual Sign-Off Block:** Formal signature blocks for Test Engineer Verification and Laboratory Quality Manager Approval.
    - **Print-to-PDF Stylesheet:** Built-in `@media print` CSS automatically reformats background and borders for razor-sharp physical printing and browser "Save as PDF".
  - Added toolbar button `📄 Test Report` on `MainWindow`:
    - Generates report file to `reports/Certificate_Cell{ID}_{timestamp}.html`.
    - Automatically opens report in default web browser using `QDesktopServices`.
* **Acceptance Criteria & Test Plan:**
  1. Generates clean, responsive HTML report viewable in any browser and printable to PDF. (PASS)
  2. Embeds all key metrics, audit tables, and pure-SVG vector graphics without requiring external web access. (PASS)
  3. Handles empty cycles, single cycle, and completed runs cleanly. (PASS)
  4. Fully verified via automated test suite `tests/test_report_generator_imp12.py` (4/4 passed). (PASS)

---

### `IMP-13`: Remote Lab Notifications (Discord / Slack / Teams Webhooks)
* **Priority:** `P2`
* **Status:** `COMPLETED & VERIFIED` (2026-09-29)
* **Target Module:** `single_cell_cycler/comm/webhook_notifier.py`, `single_cell_cycler/ui/widgets/webhook_dialog.py`, `single_cell_cycler/ui/main_window.py`
* **Problem Statement:** Long qualification cycling runs unattended overnight. Operators need immediate alerts if a safety trip occurs or when qualification finishes.
* **Technical Design:**
  - Implemented `WebhookNotifier` (`comm/webhook_notifier.py`) with a dedicated non-blocking asynchronous queue and background worker thread to ensure zero impact on cycler 10 Hz timing or GUI responsiveness.
  - Implemented multi-platform `build_universal_payload` formatting rich embed cards compatible with:
    - **Discord Webhooks:** Rich JSON embeds with color headers, title, fields, and timestamp.
    - **Slack & Teams Incoming Webhooks:** Attachment blocks with color bars, short field layout, and footer text.
    - **Generic Endpoints:** Standard JSON payload with event type, timestamp, and metadata.
  - Supported laboratory events:
    1. `TEST_STARTED`: Channel, recipe name, chemistry, steps count, and operator tag (Emerald green).
    2. `SAFETY_TRIP`: Immediate high-priority alert with trip reason, voltage, current, and temperature (Ruby red).
    3. `TEST_COMPLETED`: Final capacity, cycles completed, total energy ($Wh$), and duration (Sky blue).
    4. `PING`: Instant diagnostic connectivity test signal.
  - Built interactive modal `WebhookSettingsDialog` (`ui/widgets/webhook_dialog.py`) with URL configuration, event checkboxes, operator tag, and live `[🔔 Test Webhook Ping]` verification with real-time status feedback.
  - Settings persisted to `single_cell_cycler/config/webhook_settings.json`.
  - Added toolbar button `🔔 Webhook` on `MainWindow`.
* **Acceptance Criteria & Test Plan:**
  1. Universal payload verified across Discord and Slack structures. (PASS)
  2. Asynchronous dispatch succeeds with HTTP 200/204 via mock test. (PASS)
  3. Network failures / timeouts fail gracefully without raising uncaught exceptions or blocking engine. (PASS)
  4. Webhook settings persist cleanly to JSON and load seamlessly on launch. (PASS)
  5. BMS serial/device identity is included in every alert; the webhook dialog supports a persistent BMS ID, with USB serial/COM fallback. (PASS)
  6. Fully verified via automated test suite `tests/test_webhook_notifier_imp13.py` (6/6 passed). (PASS)

### Reliability Hardening — Current Release

The current implementation also includes the following long-run safeguards:

- Serial transport retries after unavailable-port and I/O failures without stopping the worker thread.
- Webhook delivery retries up to three times with exponential backoff on the background worker.
- Asynchronous CSV logs rotate at 256 MB and stop accepting new records when free disk space falls below 1 GB, while emitting a critical warning.
- Frozen builds store logs in the per-user `%LOCALAPPDATA%\Bytehound\SingleCellCycler\logs` directory instead of the protected Program Files directory.

---

## Execution Sequence

```text
Phase 1: Sprint 1 (Quick Wins - Pillar 1 & 4)
  ├── IMP-01: Interactive Crosshairs & Real-Time HUD
  ├── IMP-02: Quick-Zoom Toolbar Controls ([Fit All], [Current Step])
  ├── IMP-03: Cell Chemistry Presets & Voltage Guardrails
  └── IMP-11: One-Click Run Exporter (.zip bundle)

Phase 2: Sprint 2 (Integrity & Metrology - Pillar 2 & 3)
  ├── IMP-08: Power Loss / Crash Recovery (State Journaling)
  ├── IMP-09: Rate-of-Rise Thermal Trigger (dT/dt)
  └── IMP-05: Differential Capacity Analysis (dQ/dV Tab)

Phase 3: Sprint 3 (Certification & Automation - Pillar 4 & Advanced)
  ├── IMP-12: Automated PDF / HTML Test Certification Report
  ├── IMP-04: Visual Recipe Timeline Profile Preview
  ├── IMP-10: Pre-Flight Hardware Sanity Handshake
  ├── IMP-06: Standardized Pulse DCIR Mapping
  ├── IMP-07: Capacity Degradation Trend Modeling
  └── IMP-13: Remote Lab Notifications (Webhooks)
```
