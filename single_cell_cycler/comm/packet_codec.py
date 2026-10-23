"""High-performance binary codec for Single-Cell BMS framed packets."""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple, Union

from .protocol_defs import (
    BMSFaultFlags,
    FRAME_BOARD_PARAMS,
    FRAME_CELL_DATA,
    FRAME_CHARGE_CTRL,
    FRAME_CHARGE_SEL,
    FRAME_DISCHARGE_CTRL,
    FRAME_DISCHARGE_SEL,
    FRAME_FAULT_SOC,
    FRAME_RELAY_CTRL,
    HEADER_BYTES,
    HEADER_LEN,
    PAYLOAD_LEN_BOARD_PARAMS,
    PAYLOAD_LEN_CELL_DATA,
    PAYLOAD_LEN_CMD,
    PAYLOAD_LEN_FAULT_SOC,
    SCALE_BOARD_VOLTAGE,
    SCALE_CELL_CURRENT,
    SCALE_CELL_VOLTAGE,
    SCALE_SOC,
    SCALE_TEMPERATURE,
)


@dataclass(slots=True)
class CellDataTelemetry:
    """Frame 0x1000 - 8 bytes."""
    voltage: float           # Volts (0.000 .. 5.000)
    current: float           # Amperes (-50.000 .. +50.000, + = charge, - = discharge)
    terminal_temp: float     # °C (-40.0 .. 125.0)
    body_temp: float         # °C (-40.0 .. 125.0)
    timestamp: float = 0.0

    @classmethod
    def from_payload(cls, payload: bytes, timestamp: float | None = None) -> CellDataTelemetry:
        if len(payload) < PAYLOAD_LEN_CELL_DATA:
            raise ValueError(f"Payload too short for Cell Data: expected {PAYLOAD_LEN_CELL_DATA}, got {len(payload)}")
        raw_v, raw_i, raw_t_term, raw_t_body = struct.unpack("<HhHH", payload[:PAYLOAD_LEN_CELL_DATA])
        return cls(
            voltage=round(raw_v * SCALE_CELL_VOLTAGE, 4),
            current=round(raw_i * SCALE_CELL_CURRENT, 4),
            terminal_temp=round(raw_t_term * SCALE_TEMPERATURE, 1),
            body_temp=round(raw_t_body * SCALE_TEMPERATURE, 1),
            timestamp=timestamp if timestamp is not None else time.time(),
        )


@dataclass(slots=True)
class BoardParamsTelemetry:
    """Frame 0x2000 - 6 bytes."""
    ambient_temp: float      # °C (-40.0 .. 85.0)
    charge_voltage: float    # Volts (0.000 .. 60.000)
    load_voltage: float      # Volts (0.000 .. 60.000)
    timestamp: float = 0.0

    @classmethod
    def from_payload(cls, payload: bytes, timestamp: float | None = None) -> BoardParamsTelemetry:
        if len(payload) < PAYLOAD_LEN_BOARD_PARAMS:
            raise ValueError(f"Payload too short for Board Params: expected {PAYLOAD_LEN_BOARD_PARAMS}, got {len(payload)}")
        # Hardware frame 0x2000 transmits: ambient_temp, load_bus_voltage, charge_bus_voltage
        raw_amb, raw_vload, raw_vchg = struct.unpack("<HHH", payload[:PAYLOAD_LEN_BOARD_PARAMS])
        return cls(
            ambient_temp=round(raw_amb * SCALE_TEMPERATURE, 1),
            charge_voltage=round(raw_vchg * SCALE_BOARD_VOLTAGE, 4),
            load_voltage=round(raw_vload * SCALE_BOARD_VOLTAGE, 4),
            timestamp=timestamp if timestamp is not None else time.time(),
        )


@dataclass(slots=True)
class FaultSoCTelemetry:
    """Frame 0x3000 - 5 bytes."""
    fault_byte: int
    cov: bool               # Cell Over Voltage
    cuv: bool               # Cell Under Voltage
    occ: bool               # Over Current Charge
    ocd: bool               # Over Current Discharge
    cot: bool               # Cell Over Temperature
    cut: bool               # Cell Under Temperature
    soc_ocv: float          # State of Charge from OCV (%)
    soc_cc: float           # State of Charge from Coulomb Counting (%)
    timestamp: float = 0.0

    @property
    def has_any_fault(self) -> bool:
        return (self.fault_byte & 0x3F) != 0

    @classmethod
    def from_payload(cls, payload: bytes, timestamp: float | None = None) -> FaultSoCTelemetry:
        if len(payload) < PAYLOAD_LEN_FAULT_SOC:
            raise ValueError(f"Payload too short for Fault/SoC: expected {PAYLOAD_LEN_FAULT_SOC}, got {len(payload)}")
        raw_fault, raw_soc_ocv, raw_soc_cc = struct.unpack("<BHH", payload[:PAYLOAD_LEN_FAULT_SOC])
        return cls(
            fault_byte=raw_fault,
            cov=bool(raw_fault & BMSFaultFlags.COV),
            cuv=bool(raw_fault & BMSFaultFlags.CUV),
            occ=bool(raw_fault & BMSFaultFlags.OCC),
            ocd=bool(raw_fault & BMSFaultFlags.OCD),
            cot=bool(raw_fault & BMSFaultFlags.COT),
            cut=bool(raw_fault & BMSFaultFlags.CUT),
            soc_ocv=round(raw_soc_ocv * SCALE_SOC, 2),
            soc_cc=round(raw_soc_cc * SCALE_SOC, 2),
            timestamp=timestamp if timestamp is not None else time.time(),
        )


@dataclass(slots=True)
class CommandEchoTelemetry:
    """Echo/readback of 0x6000 - 0x6004 control states."""
    frame_id: int
    payload_byte: int
    timestamp: float = 0.0


DecodedPacket = Union[CellDataTelemetry, BoardParamsTelemetry, FaultSoCTelemetry, CommandEchoTelemetry]


def encode_command_packet(frame_id: int, payload_byte: int) -> bytes:
    """Build a framed transmit command: AA 55 | ID_LE (2) | LEN=1 (1) | PAYLOAD (1)."""
    return struct.pack("<BBHB B", 0xAA, 0x55, frame_id, 1, payload_byte & 0xFF)


def decode_stream(buffer: bytearray) -> Tuple[List[DecodedPacket], bytearray]:
    """Scan byte stream buffer for valid frames.
    
    Returns:
        (decoded_packets, remaining_buffer)
    """
    packets: List[DecodedPacket] = []
    idx = 0
    buf_len = len(buffer)
    now = time.time()

    while idx <= buf_len - 5:  # Minimum frame size is 5 bytes: 2 (header) + 2 (id) + 1 (len)
        # Search for AA 55 header
        if buffer[idx] != 0xAA or buffer[idx + 1] != 0x55:
            idx += 1
            continue

        frame_id = buffer[idx + 2] | (buffer[idx + 3] << 8)
        payload_len = buffer[idx + 4]
        total_frame_len = 5 + payload_len

        if idx + total_frame_len > buf_len:
            # Incomplete packet, wait for more bytes
            break

        payload = bytes(buffer[idx + 5 : idx + total_frame_len])

        try:
            if frame_id == FRAME_CELL_DATA and payload_len >= PAYLOAD_LEN_CELL_DATA:
                packets.append(CellDataTelemetry.from_payload(payload, now))
            elif frame_id == FRAME_BOARD_PARAMS and payload_len >= PAYLOAD_LEN_BOARD_PARAMS:
                packets.append(BoardParamsTelemetry.from_payload(payload, now))
            elif frame_id == FRAME_FAULT_SOC and payload_len >= PAYLOAD_LEN_FAULT_SOC:
                packets.append(FaultSoCTelemetry.from_payload(payload, now))
            elif frame_id in (
                FRAME_RELAY_CTRL,
                FRAME_CHARGE_SEL,
                FRAME_CHARGE_CTRL,
                FRAME_DISCHARGE_CTRL,
                FRAME_DISCHARGE_SEL,
            ) and payload_len >= PAYLOAD_LEN_CMD:
                packets.append(CommandEchoTelemetry(frame_id=frame_id, payload_byte=payload[0], timestamp=now))
        except Exception:
            # Skip malformed frame
            pass

        idx += total_frame_len

    # Return leftover unprocessed bytes
    return packets, buffer[idx:]
