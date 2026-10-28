# NUCLEO-G474RE BMS simulator (HIL firmware)

Bare-metal firmware that turns a NUCLEO-G474RE into a BMS for testing
ByteHound on real hardware. It speaks the protocol of the bundled config
template (`app/resources/config_template`) over the ST-LINK virtual COM port,
behaves like `MCU_BMS_Simulator/MCU_BMS_Simulator.ino`, and adds commands for
loss testing: a sequence counter, line-rate streaming at any baud, noise and
CRC-error injection, and counters of everything it sent and received.

`tools/hil/run_hil.py` compares those counters with what the application saw.

## Hardware

Only the board and a USB cable. The ST-LINK VCP is wired to LPUART1
(PA2 TX / PA3 RX). The core runs at 150 MHz; LPUART1 is clocked from HSI16,
which gives an exact divider at 115200, 921600 and 2000000 baud. The green LED
(PA5) blinks fast while streaming and slowly when idle.

## Build, flash, debug

The project uses the GCC, make, ST-LINK GDB server and STM32CubeProgrammer that
ship with STM32CubeIDE (2.2.0 in `C:/ST/STM32CubeIDE_2.2.0`). Nothing else is
installed.

**VS Code**: open this folder (`firmware/nucleo_g474_bms_sim`) as the workspace.
Install the recommended extensions (C/C++, Cortex-Debug). Then:

| Action | How |
|---|---|
| Build | `Ctrl+Shift+B` (task *Build firmware*) |
| Flash | task *Flash firmware (SWD)* |
| Debug | F5, *Debug NUCLEO-G474RE (ST-LINK)*: builds, flashes, stops at `main`, with peripheral registers from the SVD |
| Attach | *Attach to running NUCLEO-G474RE* (no reset) |
| Check the board | task *Ping board* |

If CubeIDE is installed elsewhere or is a different version, change the four
paths in `.vscode/settings.json` and `CUBEIDE_PLUGINS` in the `Makefile` (or
pass `make CUBEIDE_PLUGINS=...`).

**Command line**:

```
make            # build/bh_sim.elf, .bin, .hex, .map
make flash      # program over SWD, verify, reset
make size
make clean
```

Use CubeIDE's `make.exe`: its path is the `bhfw.make` setting in `.vscode/settings.json`.

## Protocol

Frames are `AA 55 | id (u16 LE) | len (u8) | payload | CRC16-Modbus (LE) | EE`.
The CRC covers header through payload.

### Simulator behaviour (as MCU_BMS_Simulator.ino)

| ID | Direction | Meaning |
|---|---|---|
| 0x1000 | board → PC | BMS Status, 8 bytes (100 ms when streaming). Empty-payload request = poll. `FF FF` = Reset Faults |
| 0x2000 | board → PC | 8 cell voltages + voltage limit, 18 bytes (500 ms). `u16` payload = Set Voltage Limit |
| 0x3000 | board → PC | Fault Flags bitfield + state, 2 bytes (200 ms) |
| 0x1002–0x1005 | PC → board | test hooks (1-byte payload): 0x1002 stress rates on/off, 0x1003 corrupt the next N CRCs, 0x1004 go silent for N seconds, 0x1005 streaming on [00] / off [01] |

Autonomous streaming is **off** at power-up (the HIL tests start from a silent
line). Send `0x1005 [00]` or Reset Faults to turn it on.

### HIL commands

| ID | Payload | Effect |
|---|---|---|
| 0x4000 | (board → PC) `u32 seq, u32 uptime_ms` | sequence counter, one per cycle when enabled |
| 0x7F01 STREAM | `u16 cycles_per_s, u8 flags` | send 0x1000+0x2000+0x3000 (+0x4000 if `flags` bit 0) cycles at that rate; 0 stops |
| 0x7F02 SET_BAUD | `u32 baud` | acknowledges with 0x7F82 at the old baud, then switches |
| 0x7F03 INJECT | `u16 noise_every, u16 corrupt_every` | after every Nth frame send noise `00 AA 13 77`; send every Mth frame with a wrong CRC; 0 = off |
| 0x7F04 RESET_STATS | — | zero the counters and the sequence number |
| 0x7F05 GET_STATS | — | reply 0x7F85: 15 × `u32` (below) |
| 0x7F06 BURST | `u32 cycles` | that many cycles (with 0x4000) back to back at full line rate |
| 0x7F07 PING | — | reply 0x7F87: firmware version string |
| 0x7F08 SET_SEQ | `u32 seq` | next 0x4000 sequence number (wraparound tests) |

GET_STATS fields, in order: frames sent for 0x1000, 0x2000, 0x3000 and 0x4000
(good CRC only), frames sent corrupted, noise bytes injected, total bytes sent;
frames received OK, received with bad CRC, UART overruns, RX ring full, line
errors (framing/noise); uptime ms, next sequence number, current baud.
Control replies (0x7F8x) are not counted, so the counters describe only the
telemetry under test.

## Running the hardware tests

From the repository root, with the board plugged in (the port is found
automatically, or pass `--port COMx`):

```
python tools/hil/run_hil.py                  # all tests, about 5 minutes
python tools/hil/run_hil.py --ping
python tools/hil/run_hil.py --only stream_2000000 gui_end_to_end
python tools/hil/run_hil.py --soak-minutes 120
```

Each test prints its checks. A JSON report goes to `artifacts/hil/`. The exit
status is the number of failed tests. What each test covers is listed in
`Documentation/hardware_validation_plan.md` (HIL section).
