"""Typed configuration objects for the Serial monitor app.

The app accepts the full instruction.md schema and still supports the early
flat ``frame_config.csv`` sample for compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


SUPPORTED_CRC_TYPES = {"crc16_modbus", "crc16_ccitt", "crc32", "none"}

# Legacy flat CSV data types.
SUPPORTED_DATA_TYPES = {"int", "uint", "float"}

FMT_SIZES = {
    "uint8": 1,
    "int8": 1,
    "uint16": 2,
    "int16": 2,
    "uint32": 4,
    "int32": 4,
    "float32": 4,
    "float64": 8,
}
SUPPORTED_FMT_TYPES = set(FMT_SIZES)


@dataclass(frozen=True)
class ProtocolConfig:
    profile_name: str
    header: bytes
    frame_id_size: int
    frame_id_byte_order: str
    length_size: int
    length_meaning: str
    crc_type: str
    crc_size: int
    crc_byte_order: str
    crc_coverage: str
    footer: bytes
    escape_mode: str
    raw_log_format: str
    enabled: bool
    parser_type: str = "framed"
    tx_pad_length: Optional[int] = None
    inter_frame_delay_ms: int = 10
    # Endianness of the payload-length field. Optional in the config — when
    # omitted (None) it falls back to ``frame_id_byte_order``. With
    # ``length_size=1`` (the common case) this field is irrelevant; it only
    # matters for protocols whose length is multi-byte.
    length_byte_order: Optional[str] = None


@dataclass(frozen=True)
class FrameDefinition:
    frame_id: int
    frame_name: str
    payload_length: Optional[int] = None
    direction: str = "rx"
    enabled: bool = True
    description: str = ""


@dataclass(frozen=True)
class SignalSpec:
    """One decoded signal extracted from a frame payload.

    Counted variables from the full schema are expanded into one SignalSpec per
    element so the rest of the app can operate on simple table rows.
    """

    frame_id: int
    frame_name: str
    signal_name: str
    start_byte: int
    byte_length: int
    endianness: str
    data_type: str
    scale: float
    offset: float
    unit: str
    group: str = ""
    index: Optional[int] = None
    source_name: str = ""
    enabled: bool = True
    description: str = ""
    register_type: str = ""
    read_write: str = "R"
    min_value: Optional[float] = None
    max_value: Optional[float] = None

    @property
    def end_byte(self) -> int:
        return self.start_byte + self.byte_length


@dataclass(frozen=True)
class BitfieldSpec:
    frame_id: int
    variable_name: str
    bit_index: int
    bit_name: str
    active_text: str = "ON"
    inactive_text: str = "OFF"


@dataclass(frozen=True)
class EnumSpec:
    frame_id: int
    variable_name: str
    value: int
    label: str


@dataclass(frozen=True)
class CalcGroupSpec:
    group: str
    stat: str
    unit: str = ""
    frame_id: Optional[int] = None
    enabled: bool = True


@dataclass(frozen=True)
class TxCommandFieldSpec:
    command_name: str
    field_name: str
    fmt: str
    unit: str = ""
    factor: float = 1.0
    offset: float = 0.0
    byte_order: str = "little"
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    default: Optional[float] = None


@dataclass(frozen=True)
class TxCommandSpec:
    command_name: str
    frame_id: int
    payload_hex: str = ""
    description: str = ""
    enabled: bool = True
    fields: List[TxCommandFieldSpec] = field(default_factory=list)


@dataclass(frozen=True)
class SerialDefaults:
    baud_rate: int = 115200
    data_bits: int = 8
    stop_bits: float = 1.0
    parity: str = "N"
    timeout_ms: int = 100


@dataclass(frozen=True)
class PollingScheduleSpec:
    target_id: int
    interval_ms: int
    timeout_ms: int
    enabled: bool = True


@dataclass
class FrameConfig:
    protocol: ProtocolConfig
    frames: Dict[int, FrameDefinition] = field(default_factory=dict)
    signals_by_frame: Dict[int, List[SignalSpec]] = field(default_factory=dict)
    frame_names: Dict[int, str] = field(default_factory=dict)
    bitfields: Dict[tuple[int, str], List[BitfieldSpec]] = field(default_factory=dict)
    enums: Dict[tuple[int, str], Dict[int, str]] = field(default_factory=dict)
    calc_groups: List[CalcGroupSpec] = field(default_factory=list)
    tx_commands: Dict[str, TxCommandSpec] = field(default_factory=dict)
    serial_defaults: SerialDefaults = field(default_factory=SerialDefaults)
    polling_schedules: List[PollingScheduleSpec] = field(default_factory=list)

    @property
    def all_signals(self) -> List[SignalSpec]:
        return [signal for signals in self.signals_by_frame.values() for signal in signals]
