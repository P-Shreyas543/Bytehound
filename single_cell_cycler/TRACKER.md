# Single-Cell BMS Cell Cycler — Project & Verification Tracker

## 1. Overview & Objective
A dedicated, industrial-grade **Single-Cell Battery Cycler & Test Automation Suite** interfacing with single-cell Battery Management Systems conforming to `Experiment_6_SC_Configuration.xlsx`.

Key Objectives:
- High-efficiency, multi-threaded architecture (I/O, state machine, logging, and UI strictly decoupled).
- Comprehensive test recipes (Charge, Discharge, Rest, Loop) with programmable cut-off conditions (Voltage, Current Taper, Duration, Ah Capacity, Temperature).
- Real-time battery metrology (Coulomb Counting $\int I dt$, Energy $\int V \cdot I dt$, Coulombic Efficiency, DCIR).
- Hardware protection and safety interlocks (COV, CUV, OCC, OCD, COT, CUT, Watchdog, Emergency Stop).
- Ultra-smooth 25-30 FPS live visualization using PyQtGraph.
- Dedicated physical serial hardware interface with auto COM port detection.

---

## 2. Feature Checklist & Implementation Status

| Module | Feature / Component | Status | Notes |
|---|---|---|---|
| **Protocol & Comm** | Binary packet parser (`0xAA 0x55`, 0x1000, 0x2000, 0x3000) | `COMPLETED` | Fast `struct.unpack`, zero heap alloc in hot path |
| | TX command builder (0x6000, 0x6001, 0x6002, 0x6003, 0x6004) | `COMPLETED` | Bitwise bitfield packing matching firmware |
| | Serial transceiver thread | `COMPLETED` | Non-blocking QThread with thread-safe priority TX queue |
| **Core Engine** | Profile / Recipe data models | `COMPLETED` | Dataclasses, JSON schema import/export |
| | Deterministic Cut-off Detector | `COMPLETED` | Voltage max/min, Current taper, Duration, Capacity, Temp |
| | Metrology & Coulomb Counter | `COMPLETED` | Trapezoidal integration for Ah, Wh, $\eta_C$, $\eta_E$, DCIR |
| | Safety Interlock Monitor | `COMPLETED` | Scans BMS fault bits + software guardrails + e-stop |
| | Cycler State Machine Engine | `COMPLETED` | Multi-step sequencing, looping, transitions, pause/resume |
| **Data & Logging** | Asynchronous CSV Logger | `COMPLETED` | Background queue flush, zero UI thread blocking |
| | Cycle & Step Summary Writer | `COMPLETED` | Step-by-step and cycle-by-cycle metrics recorder |
| **User Interface** | Main Window & Docking Layout | `COMPLETED` | Modern industrial dark theme (QDarkTheme) |
| | Real-Time KPI Cards | `COMPLETED` | Large numeric readouts for V, I, T, SoC, Ah, Wh, Bus V |
| | Interactive Profile Editor | `COMPLETED` | Step table, cut-off builder, recipe preset loader |
| | Live Multi-Plot Dashboard | `COMPLETED` | V-I-t, T-t, V-Q curve overlay, Capacity vs Cycle |
| | Step Tracker Table | `COMPLETED` | History of executed steps with start/end V, Ah, cutoff reason |
| | Manual Control Panel | `COMPLETED` | Direct manual toggling of relays, charge rates, loads |
| | BMS Safety & Fault Panel | `COMPLETED` | 6 LED indicators for COV, CUV, OCC, OCD, COT, CUT |
| **Verification** | Unit tests for Protocol & Codec | `COMPLETED` | Pytest suite |
| | Unit tests for Cut-off Detector | `COMPLETED` | Pytest suite |
| | Unit tests for Metrology (Ah/Wh) | `COMPLETED` | Pytest suite |
| | Unit tests for Safety & Interlocks | `COMPLETED` | Pytest suite |
| | End-to-end Cycler Engine test | `COMPLETED` | Pytest suite with mock command callbacks |
| | Headless GUI smoke test | `COMPLETED` | Automated verification of UI & plots |

---

## 3. Communication & Register Map Reference

### Telemetry Frames (BMS -> Host)
- `0x1000` (8 bytes): `CellVoltage` (mV), `CellCurrent` (mA signed), `CellTerminalTemperature` (0.1 °C), `CellBodyTemperature` (0.1 °C)
- `0x2000` (6 bytes): `AmbientTemperature` (0.1 °C), `ChargeVoltage` (mV), `LoadVoltage` (mV)
- `0x3000` (5 bytes): `Fault` (uint8 bitfield), `SoC (OCV)` (0.01%), `SoC (CC)` (0.01%)
  - Bit 0: Cell Over Voltage (COV)
  - Bit 1: Cell Under Voltage (CUV)
  - Bit 2: Over Current Charge (OCC)
  - Bit 3: Over Current Discharge (OCD)
  - Bit 4: Cell Over Temperature (COT)
  - Bit 5: Cell Under Temperature (CUT)

### Hardware Commands (Host -> BMS, 1 byte each)
> For detailed firmware upgrade recommendations, autonomous safety watchdog, and automated comparator reset implementation, see [FirmwareUpdate_required.md](../FirmwareUpdate_required.md).

#### 0x6000: Cell Relay Control
| Bit | Parameter | Value | Function |
|---|---|---|---|
| Bit 0 | Cell Enable | `0` | Disconnected from test circuit |
| | | `1` | Connected to relay for charge/discharge |
| Bit 1 | Cell Select | `0` | Cell 1 selected |
| | | `1` | Cell 2 selected |

#### 0x6001: Cell Charge Select
| Bit | Parameter | Value | Function |
|---|---|---|---|
| Bit 0 | Max Charge Voltage | `0` | 3.6 V CCCV (LFP) |
| | | `1` | 4.2 V CCCV (NMC/LCO) |
| Bit 1 | Charge Current 1 | `0` | +0.0 A |
| | | `1` | +0.5 A contribution |
| Bit 2 | Charge Current 2 | `0` | +0.0 A |
| | | `1` | +1.0 A contribution |
| Bits 1+2 | Total Current | `1+1` | **1.5 A total charge current** |

#### 0x6002: Cell Charge Control
- Bit 0: Charge Enable (`1` = Enables charging operation)
- Bit 1: Charge Comparator Reset (`1` = Resets charge protection comparator)

#### 0x6003: Cell Discharge Control
- Bit 0: Discharge Enable (`1` = Enables discharging operation)
- Bit 1: Discharge Comparator Reset (`1` = Resets discharge protection comparator)

#### 0x6004: Discharge Load Bank Select (16 Discrete States)
| Decimal | L1 (0.2A) | L2 (0.4A) | L3 (0.8A) | L4 (1.6A) | Switches ON | Total Current (A) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **0** | OFF | OFF | OFF | OFF | 0 | **0.0 A** |
| **1** | **ON** | OFF | OFF | OFF | 1 | **0.2 A** |
| **2** | OFF | **ON** | OFF | OFF | 1 | **0.4 A** |
| **3** | **ON** | **ON** | OFF | OFF | 2 | **0.6 A** |
| **4** | OFF | OFF | **ON** | OFF | 1 | **0.8 A** |
| **5** | **ON** | OFF | **ON** | OFF | 2 | **1.0 A** |
| **6** | OFF | **ON** | **ON** | OFF | 2 | **1.2 A** |
| **7** | **ON** | **ON** | **ON** | OFF | 3 | **1.4 A** |
| **8** | OFF | OFF | OFF | **ON** | 1 | **1.6 A** |
| **9** | **ON** | OFF | OFF | **ON** | 2 | **1.8 A** |
| **10** | OFF | **ON** | OFF | **ON** | 2 | **2.0 A** |
| **11** | **ON** | **ON** | OFF | **ON** | 3 | **2.2 A** |
| **12** | OFF | OFF | **ON** | **ON** | 2 | **2.4 A** |
| **13** | **ON** | OFF | **ON** | **ON** | 3 | **2.6 A** |
| **14** | OFF | **ON** | **ON** | **ON** | 3 | **2.8 A** |
| **15** | **ON** | **ON** | **ON** | **ON** | 4 | **3.0 A** |

---

## 4. Test Runs & Verification Log

| Date | Test Case / Suite | Expected Result | Actual Result | Status |
|---|---|---|---|---|
| Initial | `test_packet_codec.py` | Encode/decode match spec byte-for-byte | All passed | `PASS` |
| Initial | `test_cutoff_detector.py` | Voltage, current taper, and time limits trigger correctly | All passed | `PASS` |
| Initial | `test_metrics_tracker.py` | Coulomb counting and Wh accurate within <0.1% | All passed | `PASS` |
| Initial | `test_safety_monitor.py` | Hardware fault bits and e-stop trigger safe shutdown | All passed | `PASS` |
| Initial | `test_cycler_engine.py` | Full multi-step cycle sequence executes deterministically | All passed | `PASS` |
| Initial | `test_hardware_table.py` | 16-state discharge load bank, charge specs, relay bits | All 4 passed | `PASS` |
| Initial | `smoke_cycler_gui.py` | Headless GUI initialization, live telemetry rendering, clean stop | All passed | `PASS` |
