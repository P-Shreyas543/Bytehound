# Single-Cell BMS Control Register Map

Reference for the five host → BMS control registers (`0x6000`–`0x6004`) and the order the cycler writes them in.

---

## Conventions

- **Bit order:** binary is written **LSB first**, so the first column is **Bit 0**, then Bit 1, and so on.
- **Payload:** every control register is **1 byte**.
- **Wire frame (host → BMS):** `AA 55 | Frame ID (2 bytes, little-endian) | Length = 01 | Payload`
  - Example: `0x6000 = 3` goes out as `AA 55 00 60 01 03`.
- **Readback:** the BMS echoes all five registers about 10 times per second. The host treats a write as done **only when the readback shows the written value**.

---

## 0x6000: Relay Control

Two physical relays share this register:

| Bit | Relay | 0 | 1 |
|:---:|---|---|---|
| **Bit 0** | **Cell Enable** | Selected cell disconnected | Selected cell connected for charge or discharge |
| **Bit 1** | **Cell Select** | Cell 1 | Cell 2 |

- **Cell Select** chooses between the two cells. It also chooses which cell's voltage the BMS measures and reports.
- **Cell Enable** connects the selected cell so it can charge or discharge.

| Decimal | Binary, LSB first (Bit 0, Bit 1) | Cell Select | Cell Enable | Meaning |
|:---:|:---:|:---:|:---:|---|
| **0** | `0 0` | Cell 1 | Off | Cell 1 selected, not connected |
| **1** | `1 0` | Cell 1 | **On** | Cell 1 selected and connected |
| **2** | `0 1` | Cell 2 | Off | Cell 2 selected, not connected |
| **3** | `1 1` | Cell 2 | **On** | Cell 2 selected and connected |

**Rules:**
- Cell Select is set when the operator chooses the cell, and again when **START** is pressed if it has changed (for example `0` after a Stop). Cell Enable stays **off**.
- Cell Enable is switched **on only after a test has started**.
- Cell Select is **never changed while Cell Enable is on**. To change cells, Cell Enable is switched off first.
  - Example: `3 → 1` is never written directly. The host writes `3 → 2 → 0 → 1`.
  - Example: Stop from Cell 2 goes `3 → 2 → 0`, never `3 → 0` in one write.
- The pre-flight check **reads only**. It never writes this register.
- **Cell Select is locked from START until the test ends.** During the test (Pause included) only Cell Enable changes; the Cell dropdown and Manual Hardware Control are disabled.
- After **Stop / Safety Stop / test complete** this register is **0**, like all the others. **Pause** only switches Cell Enable off (`3 → 2`).

---

## 0x6001: Charge Select

| Bit | Parameter | 0 | 1 |
|:---:|---|---|---|
| **Bit 0** | Max charge voltage | 3.6 V CC/CV (LFP) | 4.2 V CC/CV (NMC/LCO) |
| **Bit 1** | Charge current 1 | +0.0 A | +0.5 A |
| **Bit 2** | Charge current 2 | +0.0 A | +1.0 A |

| Decimal | Binary, LSB first (Bit 0, 1, 2) | Max voltage | Charge current |
|:---:|:---:|:---:|:---:|
| **0** | `0 0 0` | 3.6 V | 0.0 A |
| **1** | `1 0 0` | 4.2 V | 0.0 A |
| **2** | `0 1 0` | 3.6 V | 0.5 A |
| **3** | `1 1 0` | 4.2 V | 0.5 A |
| **4** | `0 0 1` | 3.6 V | 1.0 A |
| **5** | `1 0 1` | 4.2 V | 1.0 A |
| **6** | `0 1 1` | 3.6 V | 1.5 A |
| **7** | `1 1 1` | 4.2 V | 1.5 A |

This register only sets the voltage and current. Charging starts only when `0x6002` Charge Enable = 1.

---

## 0x6002: Charge Control

| Bit | Parameter | 0 | 1 |
|:---:|---|---|---|
| **Bit 0** | Charge Enable | Charging off | Charging on |
| **Bit 1** | Charge Comparator Reset | Normal | Reset the charge protection comparator |

| Decimal | Binary, LSB first (Bit 0, Bit 1) | Charge Enable | Comparator Reset | Meaning |
|:---:|:---:|:---:|:---:|---|
| **0** | `0 0` | Off | Off | Charging off |
| **1** | `1 0` | **On** | Off | Charging |
| **2** | `0 1` | Off | **On** | Comparator reset pulse |
| **3** | `1 1` | On | On | **Not used**: the host never writes this |

> On COM15 hardware, the BMS clears the reset bit by itself about 140 ms after it is set, so the readback goes `2 → 0` without a host write. The host counts the reset as confirmed if `2` was seen in the readback at any point.

---

## 0x6003: Discharge Control

| Bit | Parameter | 0 | 1 |
|:---:|---|---|---|
| **Bit 0** | Discharge Enable | Discharging off | Discharging on |
| **Bit 1** | Discharge Comparator Reset | Normal | Reset the discharge protection comparator |

| Decimal | Binary, LSB first (Bit 0, Bit 1) | Discharge Enable | Comparator Reset | Meaning |
|:---:|:---:|:---:|:---:|---|
| **0** | `0 0` | Off | Off | Discharging off |
| **1** | `1 0` | **On** | Off | Discharging |
| **2** | `0 1` | Off | **On** | Comparator reset pulse |
| **3** | `1 1` | On | On | **Not used**: the host never writes this |

Charge Enable (`0x6002` Bit 0) and Discharge Enable (`0x6003` Bit 0) are **never on at the same time**.

---

## 0x6004: Discharge Load Bank Select

Four binary-weighted loads. Total current = decimal value × 0.2 A.

| Bit | Load | Current |
|:---:|:---:|:---:|
| **Bit 0** | L1 | 0.2 A |
| **Bit 1** | L2 | 0.4 A |
| **Bit 2** | L3 | 0.8 A |
| **Bit 3** | L4 | 1.6 A |

| Decimal | Binary, LSB first (L1 L2 L3 L4) | Loads on | Total current |
|:---:|:---:|:---:|:---:|
| **0** | `0 0 0 0` | 0 | 0.0 A |
| **1** | `1 0 0 0` | 1 | 0.2 A |
| **2** | `0 1 0 0` | 1 | 0.4 A |
| **3** | `1 1 0 0` | 2 | 0.6 A |
| **4** | `0 0 1 0` | 1 | 0.8 A |
| **5** | `1 0 1 0` | 2 | 1.0 A |
| **6** | `0 1 1 0` | 2 | 1.2 A |
| **7** | `1 1 1 0` | 3 | 1.4 A |
| **8** | `0 0 0 1` | 1 | 1.6 A |
| **9** | `1 0 0 1` | 2 | 1.8 A |
| **10** | `0 1 0 1` | 2 | 2.0 A |
| **11** | `1 1 0 1` | 3 | 2.2 A |
| **12** | `0 0 1 1` | 2 | 2.4 A |
| **13** | `1 0 1 1` | 3 | 2.6 A |
| **14** | `0 1 1 1` | 3 | 2.8 A |
| **15** | `1 1 1 1` | 4 | 3.0 A |

The loads draw current only while `0x6003` Discharge Enable = 1.

---

## Write sequences

Every write below waits for its readback before the next write is sent:

1. Wait **250 ms**, then compare the readback with the written value.
2. If it doesn't match, check again every **100 ms**, up to **3 times**.
3. If it still doesn't match, **send the write again**, up to **4 times**.
4. If it still doesn't match:
   - during step setup, the test goes to **Safety Stop**;
   - during shutdown, the error is reported and the remaining shutdown writes still go out.

### Selecting a cell (no test running)

| # | Write | Confirm |
|:---:|---|---|
| 1 | `0x6000 = 0` (Cell 1) or `2` (Cell 2) | Readback equals the written value. Cell Enable stays off. |

### Pressing START (example: Cell 2)

| # | Action | Confirm |
|:---:|---|---|
| 1 | If `0x6000` does not read `2`, write `0x6000 = 2`: Cell Select → Cell 2, Cell Enable off | readback `2` (START is blocked if it cannot be confirmed) |
| 2 | Wait 250 ms for the relay, then for 3 new voltage readings | Cell 2's voltage is now reported |
| 3 | Pre-flight check (read only) | must pass |
| 4 | Charge / discharge / rest step sequence below | |

### Charge step (example: Cell 2, 4.2 V, 1.5 A)

| # | Write | Confirm |
|:---:|---|---|
| 1 | `0x6002 = 0` | readback `0` |
| 2 | `0x6004 = 0`: load off first | readback `0`, then wait **0.5 s** if a load was on |
| 3 | `0x6003 = 0`: then Discharge Enable off | readback `0` |
| 4 | Check Cell Select. If `0x6000` does not read Cell 2, write `0x6000 = 2`. | readback `2` |
| 5 | `0x6000 = 3`: Cell Enable **on** | readback `3`, then wait **1.5 s** for the measurements to settle |
| 6 | `0x6001 = 1`: 4.2 V | readback `1` |
| 7 | `0x6001 = 7`: 4.2 V + 1.5 A | readback `7` |
| 8 | `0x6002 = 2`: comparator reset set | `2` seen in the readback |
| 9 | `0x6002 = 0`: comparator reset cleared | readback `0` |
| 10 | Check that `0x6000` still reads `3` | if not, restart from row 1 |
| 11 | `0x6002 = 1`: **Charge Enable** | readback `1` |
| 12 | Check that `0x6000` still reads `3` | if not, `0x6002 = 0` and restart from row 1 |
| 13 | Final check of all five readbacks: `0x6000=3`, `0x6001=7`, `0x6002=1`, `0x6003=0`, `0x6004=0` | then the test goes to **Running** |

### Discharge step (example: Cell 2, 1.0 A, load value 5)

| # | Write | Confirm |
|:---:|---|---|
| 1–5 | Same as charge rows 1–5 | |
| 6 | Check that `0x6000` still reads `3` | if not, restart from row 1 |
| 7 | `0x6003 = 1`: **Discharge Enable** | readback `1`, then wait **0.5 s** |
| 8 | `0x6003 = 3`: comparator reset set, Enable kept on | `3` seen in the readback |
| 9 | No write: wait for the board to clear the reset bit | readback returns to `1` (about 0.3 s; written as `1` if not seen within 3 s), then wait **0.5 s** |
| 10 | Check that `0x6000` still reads `3` | if not, `0x6003 = 0` and restart from row 1 |
| 11 | `0x6004 = 5`: loads L1 + L3 = 1.0 A | readback `5` |
| 12 | Final check of all readbacks | then the test goes to **Running** |

The reset must be pulsed **after** Discharge Enable. Bench result on the board: the earlier
order (`0x6003 = 2` → `0` → `1`) leaves the discharge comparator latched after a previous
discharge — `0x6003` reads `1` but the load bus stays at 0 V and no current flows. Pulsing the
reset with Enable already on (`1` → `3`) releases it; the load bus rises to the cell voltage.

### Rest step (example: Cell 2)

| # | Write | Confirm |
|:---:|---|---|
| 1–3 | `0x6002 = 0`, `0x6004 = 0` (wait 0.5 s if a load was on), `0x6003 = 0` | each reads back `0` |
| 4 | `0x6000 = 2`: Cell Enable **off**, Cell Select stays on Cell 2 | readback `2` |

### Pause and Resume (example: Cell 2)

| # | Write | Confirm |
|:---:|---|---|
| 1 | `0x6002 = 0`, `0x6004 = 0` (wait 0.5 s if a load was on), `0x6003 = 0`, `0x6001 = 0` | each reads back `0` |
| 2 | `0x6000 = 2`: Cell Enable **off**, Cell Select **stays on Cell 2** | readback `2` |

**Resume** runs the step sequence again. Cell Select already reads Cell 2, so only Cell Enable closes (`0x6000 = 3`, then the 1.5 s settle) before the step's own settings.

### Consecutive steps

- If the previous step already switched Cell Enable on and `0x6000` still reads `3`, charge rows 4–5 are skipped (no new relay write and no 1.5 s wait).
- After a Rest, Pause or Stop, Cell Enable is off again, so the next step switches it on and waits the 1.5 s.

### Stop / Safety Stop / test complete (example: Cell 2)

| # | Write | Confirm |
|:---:|---|---|
| 1 | `0x6002 = 0`: charging off | readback `0` |
| 2 | `0x6004 = 0`: all loads off first | readback `0`, then wait **0.5 s** if a load was on |
| 3 | `0x6003 = 0`: then discharging off | readback `0` |
| 4 | `0x6001 = 0` | readback `0` |
| 5 | `0x6000 = 2`: Cell Enable **off**, Cell Select stays on Cell 2 | readback `2` |
| 6 | `0x6000 = 0`: Cell Select back to Cell 1 | readback `0` |

End state: **every register is 0**. From Cell 1 connected (`0x6000 = 1`), row 5 is skipped and row 6 writes `0` directly, since only Cell Enable changes.

- **Emergency Stop** and the automatic safety trips (voltage, current, temperature, BMS fault, watchdog) first send `0x6002 = 0`, `0x6004 = 0`, `0x6003 = 0`, `0x6001 = 0` and `0x6000` with Cell Enable off and Cell Select unchanged, **at once, without waiting**. The confirmed sequence above then runs and brings `0x6000` to `0`.
- The automatic safety trips send these writes **only while a test is Running**. When the app is Idle, Paused, Aborted or Completed, the registers are already zero and nothing is sent. **Emergency Stop always sends them.**
- If the BMS stops answering during a Stop, the remaining shutdown writes (except the Cell Select move in row 6) are sent immediately; each is still confirmed afterwards.
- **Disconnect** and **closing the app** wait up to 4 s for this sequence to finish before the serial port closes.

---

## Fault handling (BMS `0x3000` fault bits and software limits)

| Fault | While a step is Running | While Idle / Paused / Aborted / Completed |
|---|---|---|
| **COT, CUT**, temperature limit, temperature rise (dT/dt) | **Safety Stop**: all registers to 0, alarm, webhook | Logged only (hardware already 0) |
| **OCC, OCD**, current limits | **Safety Stop**: all registers to 0, alarm, webhook | Logged only |
| **COV, CUV**, voltage limits | **Step ends like a cut-off** ("FAULT: …" in the tracker), warning alarm and event; the test continues with the next step (or completes if it was the last) | Logged only |
| No telemetry for 8 s (watchdog) | **Safety Stop** | — |
| **E-STOP** | **Safety Stop**, always | Always sends the zeros |

- If several fault bits are set together, the most severe wins: temperature > current > voltage.
- Faults ignored because they are expected in that situation: CUV while charging, COV while discharging, OCC/OCD and (above the minimum voltage) CUV while resting, and COV/CUV/OCC/OCD during the step setup (only COT/CUT count there).

