# Implementation Plan: Dynamic Configurable BMS Protocol & Telemetry Engine

## 1. Executive Summary & Objectives
The goal of this architectural enhancement is to transition the Bytehound Single-Cell BMS Cycler from a hardcoded binary framing structure to an **extensible, configuration-driven communication engine**. 

This allows:
1. **Dynamic Frame & Field Configuration:** Changing Header sync bytes (`0xAA 0x55`), Frame IDs, payload lengths, byte offsets, and scale factors via `config/bms_protocol.json` without recompiling the codebase.
2. **Extensible Fault Flags:** Arbitrary fault definitions (e.g., adding **Short Circuit Fault `SCD`**, external interlocks, watchdog trips) with automatic dynamic LED generation on the Safety Panel.
3. **Multi-Channel SoC State Estimation:** Seamless support for **EKF SoC (Extended Kalman Filter)** alongside OCV and Coulomb-Counting (CC), dynamically displayed on the KPI Dashboard.
4. **Visual Protocol Editor & Live Hex Simulator:** An interactive GUI dialog to configure frames, inspect registers, and paste raw hardware hex packets to simulate and test decoding before running hardware.
5. **Robust Build Cleanliness:** Resolving Windows `[WinError 5] Access is denied` file lock issues during `build.py` artifact cleaning.

---

## 2. Architecture & Data Flow

```mermaid
graph TD
    A[BMS Hardware / Serial Stream] -->|Raw Bytes| B[ConfigurablePacketCodec]
    C[config/bms_protocol.json] -->|Loads / Hot-Reloads| D[ProtocolConfigManager]
    D -->|Provides Active Schema| B
    
    B -->|Decodes| E[CellDataTelemetry]
    B -->|Decodes| F[BoardParamsTelemetry]
    B -->|Decodes (Dynamic Faults + EKF)| G[FaultSoCTelemetry]
    B -->|Echoes| H[CommandEchoTelemetry]
    
    G -->|Dynamic Fault Flags| I[SafetyPanelWidget: Dynamic LED Grid]
    G -->|Dynamic Trip Detection| J[SafetyMonitor]
    G -->|EKF / CC / OCV SoC| K[KPIDashboard: Multi-SoC Card]
    
    L[Visual Protocol Dialog] -->|Live Test Raw Hex| D
    L -->|Save & Hot-Apply| C
```

---

## 3. Detailed Phase Breakdown

### Phase 1: Declarative Schema & Manager (`comm/protocol_config.py` & `config/bms_protocol.json`)
- **JSON Schema (`config/bms_protocol.json`):**
  - Defines `framing`: Header sync hex (`"AA55"`), endianness (`"little"`), checksum mode (`"none"`, `"xor8"`, `"crc16"`).
  - Defines `frames`:
    - `cell_data` (0x1000): Offsets and scales for voltage, current, terminal temp, body temp.
    - `board_params` (0x2000): Ambient temp, load bus voltage, charge bus voltage.
    - `fault_soc` (0x3000): 
      - Dynamic fault bitmask list: `[{"bit": 0, "code": "COV", "name": "Cell Over Voltage"}, ..., {"bit": 6, "code": "SCD", "name": "Short Circuit Fault"}]`.
      - Multi-channel SoC specifications: `[{"id": "soc_ocv", "name": "OCV", "offset": 1}, {"id": "soc_cc", "name": "CC", "offset": 3}, {"id": "soc_ekf", "name": "EKF", "offset": 5}]`.
    - `actuation_commands`: Frame IDs for 0x6000–0x6004.
- **`ProtocolConfigManager` Class:**
  - Manages active configuration.
  - Implements robust error handling and fallback to factory defaults if the JSON file is missing or corrupted.
  - Provides thread-safe hot-reload notifications when settings change.

### Phase 2: Upgraded Binary Packet Codec (`comm/packet_codec.py`)
- Enhance `FaultSoCTelemetry`:
  - Add `fault_flags_active: list[str]` storing all tripped fault codes (e.g. `["SCD", "COT"]`).
  - Add `soc_ekf: float | None` and `soc_channels: dict[str, float]` for arbitrary state estimation sources.
  - Update `has_any_fault` to check dynamic bitmasks across all configured faults.
- Enhance `decode_stream`:
  - Utilize active `ProtocolConfigManager` for frame ID routing, payload length checking, and dynamic field extraction.
  - Maintain 100% backward compatibility for all existing property lookups (`voltage`, `current`, `cov`, `cuv`, etc.).

### Phase 3: Dynamic Safety Panel (`ui/widgets/safety_panel.py`)
- Replace the hardcoded 6-LED grid (`led_cov` through `led_cut`) with a **dynamic LED registry**:
  - `rebuild_fault_grid(fault_definitions)` constructs `LEDIndicator` instances dynamically for any number of fault flags.
  - Automatically handles Short Circuit Fault (`SCD`), external trips, etc.
- In `update_fault_status`, iterate through active fault flags to update LED states and display the exact fault names in the trip banner.

### Phase 4: Dynamic KPI Dashboard (`ui/widgets/kpi_dashboard.py`)
- Update `KPIDashboard.card_soc`:
  - Primary value: displays the configured primary SoC (defaulting to EKF if present, otherwise CC/OCV).
  - Dynamic subtitle: formats all available channels in real-time:
    `"EKF: 78.4% | CC: 78.1% | OCV: 79.0%"`
  - Tooltip: explains the active state estimation algorithm.

### Phase 5: Visual Protocol Editor & Live Hex Simulator (`ui/widgets/protocol_dialog.py`)
- **Tabs/Sections:**
  1. **Framing & Headers:** Set sync header hex (`AA 55`), baud rates, and endianness.
  2. **Frame IDs & Scales:** Adjust engineering scale multipliers (mV vs V, mA vs A).
  3. **Fault Flags Manager:** Add/edit/remove fault bits (e.g. adding Bit 6: `SCD - Short Circuit Fault`).
  4. **SoC Channels:** Configure EKF, CC, and OCV offsets and primary priority.
  5. **Live Hex Simulator:**
     - Hex input box (e.g. `AA 55 00 30 07 40 1E 20 1E 20 1F 20`).
     - "Test Parse" button displaying decoded telemetry in a clean preview table.
     - "Save & Apply": Persists to disk and hot-reloads the active cycler without restart.
- Hook dialog into `ui/main_window.py` under the `More...` toolbar menu.

### Phase 6: Build Script Lock Resiliency (`build.py`)
- Improve `clean_artifacts()` in `build.py`:
  - Add retry logic with exponential backoff on `[WinError 5] Access is denied`.
  - Ensure any zombie or preview processes are gracefully terminated before directory removal.

### Phase 7: Verification & Testing
- Unit tests for dynamic schema serialization and parsing.
- Unit tests for dynamic fault flag detection (including `SCD` Short Circuit).
- Unit tests for EKF SoC extraction and KPI dashboard rendering.
- Full regression run across all existing 98 tests to ensure 100% pass rate.
