"""Typed configuration objects for the Serial monitor app.

The app accepts the full instruction.md schema and still supports the early
flat ``frame_config.csv`` sample for compatibility.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ─── Enum classes for config-string fields ───────────────────────────────────
#
# These are ``(str, Enum)`` mixins (not ``StrEnum`` because we still support
# Python 3.10). Members compare equal to their string value, so existing code
# that stores strings on dataclasses (``SignalSpec.data_type: str`` etc.)
# keeps working unchanged. The benefit is one source of truth for the valid
# values, plus IDE-friendly member access (e.g. ``ByteOrder.BIG``).
#
# Validators living next to each enum (``parse(value, *, source)``) accept a
# raw string from a CSV cell and return either a normalised string or raise
# ``ValueError``. config_loader wraps those into ``ConfigError`` so the user
# sees the row context.


class ByteOrder(str, enum.Enum):
    BIG = "big"
    LITTLE = "little"

    @classmethod
    def parse(cls, value: str) -> "ByteOrder":
        normalised = (value or "").strip().lower()
        for member in cls:
            if member.value == normalised:
                return member
        raise ValueError(f"byte_order must be 'big' or 'little' (got {value!r})")


class ParserType(str, enum.Enum):
    FRAMED = "framed"
    MODBUS_RTU = "modbus_rtu"

    @classmethod
    def parse(cls, value: str) -> "ParserType":
        normalised = (value or "framed").strip().lower()
        for member in cls:
            if member.value == normalised:
                return member
        raise ValueError(
            f"parser_type must be 'framed' or 'modbus_rtu' (got {value!r})"
        )


class CrcType(str, enum.Enum):
    CRC16_MODBUS = "crc16_modbus"
    CRC16_CCITT = "crc16_ccitt"
    CRC32 = "crc32"
    NONE = "none"

    @classmethod
    def parse(cls, value: str) -> "CrcType":
        normalised = (value or "").strip().lower()
        for member in cls:
            if member.value == normalised:
                return member
        valid = sorted(m.value for m in cls)
        raise ValueError(f"crc_type must be one of {valid} (got {value!r})")


class DataType(str, enum.Enum):
    """Coarse data-type category used by the legacy ``frame_config`` schema."""

    INT = "int"
    UINT = "uint"
    FLOAT = "float"

    @classmethod
    def parse(cls, value: str) -> "DataType":
        normalised = (value or "").strip().lower()
        for member in cls:
            if member.value == normalised:
                return member
        valid = sorted(m.value for m in cls)
        raise ValueError(f"data_type must be one of {valid} (got {value!r})")


class FmtType(str, enum.Enum):
    """Concrete numeric format used by the modern ``variables`` schema.
    Width is derived from the format via :data:`FMT_SIZES`.
    """

    UINT8 = "uint8"
    INT8 = "int8"
    UINT16 = "uint16"
    INT16 = "int16"
    UINT32 = "uint32"
    INT32 = "int32"
    FLOAT32 = "float32"
    FLOAT64 = "float64"

    @classmethod
    def parse(cls, value: str) -> "FmtType":
        normalised = (value or "").strip().lower()
        for member in cls:
            if member.value == normalised:
                return member
        valid = sorted(m.value for m in cls)
        raise ValueError(f"data_type (fmt) must be one of {valid} (got {value!r})")


class ReadWrite(str, enum.Enum):
    R = "R"
    W = "W"
    RW = "RW"

    @classmethod
    def parse(cls, value: str) -> "ReadWrite":
        normalised = (value or "R").strip().upper()
        for member in cls:
            if member.value == normalised:
                return member
        raise ValueError(
            f"read_write must be one of 'R', 'W', 'RW' (got {value!r})"
        )


# Public sets kept as enum-derived aliases so any external code that imports
# them keeps working. Internally, prefer the Enum classes above.
SUPPORTED_CRC_TYPES = {m.value for m in CrcType}
SUPPORTED_DATA_TYPES = {m.value for m in DataType}

FMT_SIZES = {
    FmtType.UINT8.value: 1,
    FmtType.INT8.value: 1,
    FmtType.UINT16.value: 2,
    FmtType.INT16.value: 2,
    FmtType.UINT32.value: 4,
    FmtType.INT32.value: 4,
    FmtType.FLOAT32.value: 4,
    FmtType.FLOAT64.value: 8,
}
SUPPORTED_FMT_TYPES = {m.value for m in FmtType}


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
    #: Which span of the frame the CRC covers. Today only
    #: ``"header_to_payload"`` is implemented; the validator rejects anything
    #: else, and the framed parser branches on this value at
    #: ``packet_parser.py:_try_parse_one``. The field exists so future
    #: coverage variants can be added without changing the wire-format
    #: dataclass shape.
    crc_coverage: str
    footer: bytes
    #: Byte-escaping scheme. Today only ``"none"`` is supported (no byte
    #: stuffing). The field is reserved for protocols that escape header /
    #: footer bytes inside the payload; the validator enforces ``"none"``
    #: until that path lands.
    escape_mode: str
    enabled: bool
    parser_type: str = "framed"
    tx_pad_length: Optional[int] = None
    inter_frame_delay_ms: int = 10
    # Endianness of the payload-length field. Optional in the config — when
    # omitted (None) it falls back to ``frame_id_byte_order``. With
    # ``length_size=1`` (the common case) this field is irrelevant; it only
    # matters for protocols whose length is multi-byte.
    length_byte_order: Optional[str] = None
    #: Modbus RTU node address (slave ID). Only relevant when
    #: ``parser_type == "modbus_rtu"``. Defaults to 1.
    modbus_node_address: int = 1
    #: How the raw CSV logger formats the ``hex`` column.
    #: ``"hex"`` (default) writes space-separated bytes: ``AA 55 01 20``.
    #: ``"compact"`` writes contiguous bytes: ``AA550120``. Both are
    #: uppercase. Validated by the loader; the logger reads it via the
    #: ``hex_format`` constructor parameter.
    raw_log_format: str = "hex"


@dataclass(frozen=True)
class FrameDefinition:
    frame_id: int
    frame_name: str
    payload_length: Optional[int] = None
    enabled: bool = True
    #: Free-text note from the ``frames.csv`` ``description`` column. Not
    #: shown anywhere in the UI today — intended for documentation that
    #: lives next to the data, not for display.
    description: str = ""
    #: ``rx`` (receive only — hidden from TX Commands and Parameter Editor),
    #: ``tx`` (send only — never expected on the wire), or ``rxtx`` (default,
    #: both directions). Auto-created frames inherit the default ``rxtx`` so
    #: they remain available to every UI panel.
    direction: str = "rxtx"

    @property
    def is_tx_capable(self) -> bool:
        return self.direction in ("tx", "rxtx")

    @property
    def is_rx_capable(self) -> bool:
        return self.direction in ("rx", "rxtx")


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
    read_write: str = "R"
    min_value: Optional[float] = None
    max_value: Optional[float] = None

    @property
    def end_byte(self) -> int:
        return self.start_byte + self.byte_length


@dataclass(frozen=True)
class DecodeWarning:
    kind: str
    frame_id: int
    message: str
    offset: Optional[int] = None
    extra_hex: Optional[str] = None


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
    """Aggregate of every parsed config sheet.

    FrameConfig groups all parsed CSV/XLSX sheets into one container so the
    decoder, UI, and logging layers can pass a single value around. The
    sub-collections fall into four conceptual domains that are independent
    in the sheet schema:

    * **Wire framing** — :attr:`protocol`, :attr:`serial_defaults`.
    * **Decoding inputs** — :attr:`frames`, :attr:`signals_by_frame`,
      :attr:`frame_names`, :attr:`bitfields`, :attr:`enums`,
      :attr:`calc_groups`.
    * **Transmit** — :attr:`tx_commands`.
    * **Scheduling** — :attr:`polling_schedules`.

    A composition split (``Config.signals``, ``Config.commands``, …) is
    tempting and was considered, but every test today constructs a
    FrameConfig with only the dict/list fields it needs (the defaults
    handle the rest), so the "independently testable" benefit is already
    available without restructuring. The flat shape stays for now.
    """

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
