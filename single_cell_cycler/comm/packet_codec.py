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
    PAYLOAD_LEN_FAULT_SOC_EXT,
    SCALE_BOARD_VOLTAGE,
    SCALE_CELL_CURRENT,
    SCALE_CELL_VOLTAGE,
    SCALE_EKF_SOC,
    SCALE_P_DIAG,
    SCALE_SOC,
    SCALE_TEMPERATURE,
    SCALE_VR,
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


def _decode_soc_pct(raw: int) -> float:
    """Decode raw SoC uint16 into percentage (0.0 - 100.0%).

    The MCU sends SoC as a fraction (0.0 - 1.05) scaled by 1000 (i.e. tenths of
    percent / 0.1% resolution, e.g. 994 -> 99.4%, 1000 -> 100.0%).
    If raw is scaled by 100 (> 1050, e.g. 8250 for 82.5%), fallback to / 100.0.
    """
    frac = raw / 1000.0
    if frac <= 1.05:
        return round(frac * 100.0, 2)
    return round(raw * 0.01, 2)


@dataclass(slots=True)
class FaultSoCTelemetry:
    """Frame 0x3000 - 5 bytes (legacy) or 17 bytes (EKF extended)."""
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
    soc_ekf: float = 0.0    # EKF / Main SoC (%)
    vr1: float = 0.0        # Polarization overpotential VR1 (V)
    vr2: float = 0.0        # Polarization overpotential VR2 (V)
    p_diag: tuple[float, float, float] = (0.0, 0.0, 0.0) # Covariance matrix diagonal P_diag
    extended: bool = False  # True when decoded from the 17-byte frame (EKF fields were sent)

    @property
    def has_any_fault(self) -> bool:
        return (self.fault_byte & 0x3F) != 0

    @property
    def has_ekf(self) -> bool:
        """True when the firmware actually sent the EKF fields (SoC EKF, VR1/VR2, P_diag)."""
        return self.extended or self.soc_ekf > 0.0 or self.vr1 != 0.0 or self.vr2 != 0.0

    @property
    def soc_main(self) -> float:
        """Return primary SoC (EKF if available and > 0, otherwise CC, otherwise OCV)."""
        if self.soc_ekf > 0.0:
            return self.soc_ekf
        if self.soc_cc > 0.0:
            return self.soc_cc
        return self.soc_ocv

    @classmethod
    def from_payload(cls, payload: bytes, timestamp: float | None = None) -> FaultSoCTelemetry:
        if len(payload) < PAYLOAD_LEN_FAULT_SOC:
            raise ValueError(f"Payload too short for Fault/SoC: expected at least {PAYLOAD_LEN_FAULT_SOC}, got {len(payload)}")

        now = timestamp if timestamp is not None else time.time()

        if len(payload) >= PAYLOAD_LEN_FAULT_SOC_EXT:
            # 17-byte Extended Frame: 1-byte faults + 8 x 16-bit words.
            # VR1 / VR2 are signed (int16, 0.001 V): the polarization voltages go negative on
            # discharge, and read as unsigned they showed up as ~65.5 V. The rest are uint16.
            raw_fault, raw_ekf, raw_vr1, raw_vr2, raw_p0, raw_p1, raw_p2, raw_soc_cc, raw_soc_ocv = struct.unpack(
                "<BHhh5H", payload[:PAYLOAD_LEN_FAULT_SOC_EXT]
            )

            return cls(
                fault_byte=raw_fault,
                cov=bool(raw_fault & BMSFaultFlags.COV),
                cuv=bool(raw_fault & BMSFaultFlags.CUV),
                occ=bool(raw_fault & BMSFaultFlags.OCC),
                ocd=bool(raw_fault & BMSFaultFlags.OCD),
                cot=bool(raw_fault & BMSFaultFlags.COT),
                cut=bool(raw_fault & BMSFaultFlags.CUT),
                soc_ocv=_decode_soc_pct(raw_soc_ocv),
                soc_cc=_decode_soc_pct(raw_soc_cc),
                timestamp=now,
                soc_ekf=_decode_soc_pct(raw_ekf),
                vr1=round(raw_vr1 * SCALE_VR, 4),
                vr2=round(raw_vr2 * SCALE_VR, 4),
                p_diag=(
                    round(raw_p0 * SCALE_P_DIAG, 4),
                    round(raw_p1 * SCALE_P_DIAG, 4),
                    round(raw_p2 * SCALE_P_DIAG, 4),
                ),
                extended=True,
            )
        else:
            raw_fault, raw_soc_ocv, raw_soc_cc = struct.unpack("<BHH", payload[:PAYLOAD_LEN_FAULT_SOC])
            soc_ocv = _decode_soc_pct(raw_soc_ocv)
            soc_cc = _decode_soc_pct(raw_soc_cc)
            return cls(
                fault_byte=raw_fault,
                cov=bool(raw_fault & BMSFaultFlags.COV),
                cuv=bool(raw_fault & BMSFaultFlags.CUV),
                occ=bool(raw_fault & BMSFaultFlags.OCC),
                ocd=bool(raw_fault & BMSFaultFlags.OCD),
                cot=bool(raw_fault & BMSFaultFlags.COT),
                cut=bool(raw_fault & BMSFaultFlags.CUT),
                soc_ocv=soc_ocv,
                soc_cc=soc_cc,
                timestamp=now,
                # The 5-byte frame carries no EKF data: those fields stay unset. Values are
                # reported as the firmware sent them, never filled in from another source.
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
