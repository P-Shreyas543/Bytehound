"""Simulated single-cell BMS board on a POSIX pseudo-terminal.

Encodes the Experiment-6 frames independently of ``comm.packet_codec``:
``AA 55 | frame id (LE u16) | len (u8) | payload``. Streams 0x1000 / 0x2000 /
0x3000 telemetry at 10 Hz, echoes every 0x6000-0x6004 command back (as the
MCU does, and as the step-transition handshake waits for), and models cell
current from the register state so a recipe can actually run.
"""

from __future__ import annotations

import os
import struct
import threading
import time
import tty

RELAY, CHG_SEL, CHG_CTRL, DIS_CTRL, DIS_SEL = 0x6000, 0x6001, 0x6002, 0x6003, 0x6004
CONTROL_FRAMES = (RELAY, CHG_SEL, CHG_CTRL, DIS_CTRL, DIS_SEL)


def frame(frame_id: int, payload: bytes) -> bytes:
    return b"\xAA\x55" + struct.pack("<HB", frame_id, len(payload)) + payload


class SimulatedCell:
    def __init__(self, voltage: float = 3.70, temp_c: float = 25.0, period: float = 0.1) -> None:
        self.voltage = voltage
        self.temp_c = temp_c
        self.ambient_c = temp_c
        self.fault_byte = 0
        self.period = period
        self.registers = {fid: 0 for fid in CONTROL_FRAMES}
        self.command_log: list[tuple[int, int]] = []   # every (frame_id, value) received, in order
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._master, self._slave = os.openpty()
        tty.setraw(self._slave)
        os.set_blocking(self._master, False)
        self.port = os.ttyname(self._slave)
        self._thread = threading.Thread(target=self._run, name="SimulatedCell", daemon=True)

    # ---- model -------------------------------------------------------------
    @property
    def current(self) -> float:
        r = self.registers
        if not r[RELAY] & 0x01:                       # CELL_ENABLE open: no current path
            return 0.0
        if r[CHG_CTRL] & 0x01:                        # CHARGE_ENABLE
            return 1.0
        if r[DIS_CTRL] & 0x01:                        # DISCHARGE_ENABLE, 0.2 A per load step
            return -0.2 * (r[DIS_SEL] & 0x0F)
        return 0.0

    def energized(self) -> list[str]:
        """Registers the board is left driving (anything but a safe idle)."""
        r = self.registers
        live = []
        if r[CHG_CTRL] & 0x01:
            live.append("charge enabled")
        if r[DIS_CTRL] & 0x01:
            live.append("discharge enabled")
        if r[RELAY] & 0x01:
            live.append("cell relay closed")
        return live

    def telemetry(self) -> bytes:
        i = self.current
        self.voltage += i * 0.002                     # crude: charging raises V
        cell = struct.pack("<HhHH", round(self.voltage * 1000), round(i * 1000),
                           round(self.temp_c * 10), round(self.temp_c * 10))
        board = struct.pack("<HHH", round(self.ambient_c * 10), 0, 5000)
        fault = struct.pack("<BHH", self.fault_byte, 5000, 5000)
        return frame(0x1000, cell) + frame(0x2000, board) + frame(0x3000, fault)

    # ---- I/O ---------------------------------------------------------------
    def start(self) -> "SimulatedCell":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)
        os.close(self._master)
        os.close(self._slave)

    def _handle_rx(self, buf: bytearray) -> bytearray:
        while len(buf) >= 6:
            if buf[0] != 0xAA or buf[1] != 0x55:
                del buf[0]
                continue
            fid, length = struct.unpack_from("<HB", buf, 2)
            if len(buf) < 5 + length:
                break
            payload = bytes(buf[5:5 + length])
            del buf[:5 + length]
            if fid in self.registers and length == 1:
                with self._lock:
                    self.registers[fid] = payload[0]
                    self.command_log.append((fid, payload[0]))
                os.write(self._master, frame(fid, payload))   # echo / readback
        return buf

    def _run(self) -> None:
        rx = bytearray()
        next_tx = time.monotonic()
        while not self._stop.is_set():
            try:
                chunk = os.read(self._master, 4096)
                if chunk:
                    rx = self._handle_rx(rx + chunk)
            except (BlockingIOError, OSError):
                pass
            if time.monotonic() >= next_tx:
                try:
                    os.write(self._master, self.telemetry())
                except OSError:
                    pass
                next_tx += self.period
            time.sleep(0.002)
