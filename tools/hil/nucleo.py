"""Host-side helper for the NUCLEO-G474RE HIL firmware
(firmware/nucleo_g474_bms_sim).

Frames are built and parsed with the application's own protocol code
(``build_packet`` / ``create_parser``) using the bundled config template, so
the tests exercise the real implementation, not a second one.

Two ways to talk to the board:

* :class:`Nucleo` — owns the serial port directly (setup, baud changes,
  board statistics) before / after the application uses the port;
* :func:`command` — the raw bytes of a command, to send through the app's
  worker (``worker.enqueue_priority_tx``) while the app owns the port.
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import serial
from serial.tools import list_ports

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "app" / "resources" / "config_template"

ID_COUNTER = 0x4000
ID_STREAM, ID_BAUD, ID_INJECT, ID_RESET_STATS = 0x7F01, 0x7F02, 0x7F03, 0x7F04
ID_STATS, ID_BURST, ID_PING = 0x7F05, 0x7F06, 0x7F07
ID_BAUD_ACK, ID_STATS_REPLY, ID_PING_REPLY = 0x7F82, 0x7F85, 0x7F87
LEGACY_STREAMING = 0x1005     # [0] = on, [1] = off
CYCLE_BYTES = {True: 68, False: 52}   # bytes per cycle with / without the 0x4000 frame

STATS_FIELDS = (
    "frames_1000", "frames_2000", "frames_3000", "frames_4000",
    "corrupted", "noise_bytes", "tx_bytes",
    "rx_frames_ok", "rx_crc_errors", "rx_overruns", "rx_ring_full", "rx_line_errors",
    "uptime_ms", "seq_next", "baud",
)


def _protocol():
    from app.decoder.config_loader import load_config
    return load_config(TEMPLATE).protocol


def command(frame_id: int, payload: bytes = b"") -> bytes:
    from app.protocol.packet_builder import build_packet
    return build_packet(_protocol(), frame_id, payload)


def stream_cmd(cycles_per_s: int, counter: bool = True) -> bytes:
    return command(ID_STREAM, struct.pack("<HB", cycles_per_s, 1 if counter else 0))


def inject_cmd(noise_every: int = 0, corrupt_every: int = 0) -> bytes:
    return command(ID_INJECT, struct.pack("<HH", noise_every, corrupt_every))


def burst_cmd(cycles: int) -> bytes:
    return command(ID_BURST, struct.pack("<I", cycles))


def parse_stats(payload: bytes) -> Dict[str, int]:
    return dict(zip(STATS_FIELDS, struct.unpack("<15I", payload), strict=True))


def find_port() -> Optional[str]:
    """The ST-LINK virtual COM port, if a NUCLEO is plugged in."""
    for p in list_ports.comports():
        if (p.vid == 0x0483 and "STLink" in (p.description or "")) or "STLink" in (p.description or ""):
            return p.device
    return None


@dataclass
class Nucleo:
    port: str
    baud: int = 115200

    def __post_init__(self) -> None:
        from app.protocol.packet_parser import create_parser
        self.ser = serial.Serial(self.port, self.baud, timeout=0.05)
        self.parser = create_parser(_protocol())

    def close(self) -> None:
        self.ser.close()

    def __enter__(self) -> "Nucleo":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def send(self, frame_id: int, payload: bytes = b"") -> None:
        self.ser.write(command(frame_id, payload))
        self.ser.flush()

    def request(self, frame_id: int, payload: bytes, reply_id: int, timeout: float = 2.0) -> bytes:
        """Send a command and return the payload of the first reply frame
        (other traffic is skipped)."""
        self.send(frame_id, payload)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            data = self.ser.read(4096)
            if data:
                self.parser.feed(data)
                for p in self.parser.extract_all():
                    if p.ok and p.frame_id == reply_id:
                        return p.payload
        raise TimeoutError(f"no reply 0x{reply_id:04X} to 0x{frame_id:04X}")

    def quiesce(self) -> None:
        """Stop every autonomous transmission and drain the line."""
        self.send(ID_STREAM, struct.pack("<HB", 0, 0))
        self.send(ID_INJECT, struct.pack("<HH", 0, 0))
        self.send(LEGACY_STREAMING, b"\x01")
        time.sleep(0.2)
        self.ser.reset_input_buffer()
        self.parser = type(self.parser)(self.parser.protocol)

    def ping(self) -> str:
        return self.request(ID_PING, b"", ID_PING_REPLY).decode("ascii")

    def stats(self) -> Dict[str, int]:
        return parse_stats(self.request(ID_STATS, b"", ID_STATS_REPLY))

    def reset_stats(self) -> None:
        self.send(ID_RESET_STATS)

    def set_baud(self, baud: int) -> None:
        ack = self.request(ID_BAUD, struct.pack("<I", baud), ID_BAUD_ACK)
        assert struct.unpack("<I", ack)[0] == baud
        time.sleep(0.05)
        self.ser.baudrate = baud
        self.baud = baud
        time.sleep(0.05)
        self.ser.reset_input_buffer()


def hil_config_dir(dest: Path) -> Path:
    """Copy of the bundled template plus frame 0x4000 (HIL Seq / HIL Uptime),
    so the sequence counter is decoded, logged and analysable like any
    other signal."""
    import shutil
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(TEMPLATE, dest)

    def append(name: str, row: str) -> None:
        p = dest / name
        text = p.read_text(encoding="utf-8")
        if not text.endswith("\n"):
            text += "\n"
        p.write_text(text + row + "\n", encoding="utf-8")

    append("frames.csv", "0x4000,HIL Counter,8,rx,TRUE,Sequence counter from the HIL firmware")
    append("variables.csv", "0x4000,HIL Seq,uint32,1,1,little,1,0,,,R,0,4294967295,Frame sequence number,TRUE")
    append("variables.csv", "0x4000,HIL Uptime,uint32,1,1,little,1,0,ms,,R,0,4294967295,Board uptime,TRUE")
    return dest


def programmer_cli() -> Optional[Path]:
    """STM32_Programmer_CLI bundled with STM32CubeIDE, if installed."""
    for base in (Path("C:/ST"), Path("C:/Program Files/STMicroelectronics")):
        hits = sorted(base.glob("**/STM32_Programmer_CLI.exe")) if base.exists() else []
        if hits:
            return hits[-1]
    return None


def open_any_baud(port: str, bauds=(115200, 921600, 2000000, 460800, 230400)) -> "Nucleo":
    """Find the board whatever baud a previous run left it at, return it
    quiesced at 115200."""
    for b in bauds:
        n = Nucleo(port, b)
        try:
            n.quiesce()
            n.ping()
        except TimeoutError:
            n.close()
            continue
        if b != 115200:
            n.set_baud(115200)
        return n
    raise TimeoutError(f"no HIL firmware answering on {port}")
