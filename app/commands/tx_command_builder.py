"""Build configured TX command packets."""

from __future__ import annotations

import struct
from typing import Dict

from ..decoder.types import FMT_SIZES, FrameConfig, TxCommandFieldSpec, TxCommandSpec
from ..protocol.packet_builder import build_packet


class CommandBuildError(ValueError):
    """Raised when a TX command cannot be built from user input."""


def build_tx_command(
    config: FrameConfig, command_name: str, values: Dict[str, float] | None = None
) -> bytes:
    command = config.tx_commands.get(command_name)
    if command is None:
        raise CommandBuildError(f"Unknown TX command: {command_name!r}")
    payload = build_payload(command, values or {})
    return build_packet(config.protocol, command.frame_id, payload)


def build_payload(command: TxCommandSpec, values: Dict[str, float]) -> bytes:
    payload = bytearray(_hex_to_bytes(command.payload_hex))
    for field in command.fields:
        value = values.get(field.field_name, field.default)
        if value is None:
            raise CommandBuildError(
                f"Missing value for TX field {field.field_name!r}"
            )
        payload.extend(_encode_field(field, float(value)))
    return bytes(payload)


def _encode_field(field: TxCommandFieldSpec, user_value: float) -> bytes:
    if field.min_value is not None and user_value < field.min_value:
        raise CommandBuildError(
            f"{field.field_name}={user_value:g} is below minimum {field.min_value:g}"
        )
    if field.max_value is not None and user_value > field.max_value:
        raise CommandBuildError(
            f"{field.field_name}={user_value:g} is above maximum {field.max_value:g}"
        )

    if field.factor == 0:
        raise CommandBuildError(f"{field.field_name}: factor must not be zero")

    if field.fmt.startswith("float"):
        raw_float = (user_value - field.offset) / field.factor
        endian = "<" if field.byte_order == "little" else ">"
        fmt = "f" if field.fmt == "float32" else "d"
        return struct.pack(endian + fmt, raw_float)

    raw = round((user_value - field.offset) / field.factor)
    signed = field.fmt.startswith("int")
    size = FMT_SIZES[field.fmt]
    try:
        return int(raw).to_bytes(size, field.byte_order, signed=signed)
    except OverflowError as exc:
        raise CommandBuildError(
            f"{field.field_name}: raw value {raw} does not fit in {field.fmt}"
        ) from exc


def _hex_to_bytes(value: str) -> bytes:
    cleaned = value.replace(" ", "").replace("0x", "").replace("0X", "")
    if not cleaned:
        return b""
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise CommandBuildError(f"Invalid static payload hex: {value!r}") from exc
