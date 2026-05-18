"""Decode frame payloads into scaled variables, enums, bitfields, and stats."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

from .calculations import calculate_group_value
from .types import BitfieldSpec, CalcGroupSpec, DecodeWarning, FrameConfig, SignalSpec


@dataclass(slots=True)
class DecodedSignal:
    frame_id: int
    frame_name: str
    signal_name: str
    raw_value: Optional[Union[int, float]]
    scaled_value: Optional[float]
    unit: str
    status: str
    group: str = ""
    index: Optional[int] = None
    enum_label: Optional[str] = None
    bit_values: Dict[str, bool] = field(default_factory=dict)
    display_value: str = ""
    is_calculated: bool = False


@dataclass(slots=True)
class DecodedFrame:
    frame_id: int
    frame_name: str
    signals: List[DecodedSignal]
    calculations: List[DecodedSignal] = field(default_factory=list)
    warnings: List[DecodeWarning] = field(default_factory=list)
    error: Optional[str] = None


def decode_frame(config: FrameConfig, frame_id: int, payload: bytes) -> DecodedFrame:
    specs = config.signals_by_frame.get(frame_id)
    if specs is None:
        return DecodedFrame(
            frame_id=frame_id,
            frame_name=f"Unknown 0x{frame_id:04X}",
            signals=[],
            error=f"No signals configured for frame_id 0x{frame_id:04X}",
        )

    frame_name = config.frame_names.get(frame_id, "")
    decoded = [_decode_signal(config, spec, payload) for spec in specs]
    calculations = _calculate_groups(config, frame_id, frame_name, decoded)
    warnings = _payload_warnings(config, frame_id, payload, specs)
    return DecodedFrame(
        frame_id=frame_id,
        frame_name=frame_name,
        signals=decoded,
        calculations=calculations,
        warnings=warnings,
    )


def _decode_signal(config: FrameConfig, spec: SignalSpec, payload: bytes) -> DecodedSignal:
    if spec.end_byte > len(payload):
        return DecodedSignal(
            frame_id=spec.frame_id,
            frame_name=spec.frame_name,
            signal_name=spec.signal_name,
            raw_value=None,
            scaled_value=None,
            unit=spec.unit,
            group=spec.group,
            index=spec.index,
            status=(
                f"Payload too short: needs bytes {spec.start_byte}..{spec.end_byte} "
                f"but payload is {len(payload)} bytes"
            ),
            display_value="-",
        )

    chunk = payload[spec.start_byte : spec.end_byte]
    try:
        raw = _decode_raw(chunk, spec)
    except (struct.error, ValueError) as exc:
        return DecodedSignal(
            frame_id=spec.frame_id,
            frame_name=spec.frame_name,
            signal_name=spec.signal_name,
            raw_value=None,
            scaled_value=None,
            unit=spec.unit,
            group=spec.group,
            index=spec.index,
            status=f"Decode error: {exc}",
            display_value="-",
        )

    scaled = raw * spec.scale + spec.offset
    enum_label = _lookup_enum(config, spec, raw)
    # raw is already an int here (the isinstance branch); int(raw) was a
    # redundant no-op call that just added per-signal overhead.
    bit_values = _decode_bitfield(config, spec, raw) if isinstance(raw, int) else {}
    display = _display_text(scaled, enum_label, bit_values)
    return DecodedSignal(
        frame_id=spec.frame_id,
        frame_name=spec.frame_name,
        signal_name=spec.signal_name,
        raw_value=raw,
        scaled_value=scaled,
        unit=spec.unit,
        status="ok",
        group=spec.group,
        index=spec.index,
        enum_label=enum_label,
        bit_values=bit_values,
        display_value=display,
    )


def _decode_raw(chunk: bytes, spec: SignalSpec) -> Union[int, float]:
    if spec.data_type == "float":
        endian_prefix = "<" if spec.endianness == "little" else ">"
        fmt_char = "f" if spec.byte_length == 4 else "d"
        return struct.unpack(endian_prefix + fmt_char, chunk)[0]
    signed = spec.data_type == "int"
    return int.from_bytes(chunk, byteorder=spec.endianness, signed=signed)


def _lookup_enum(config: FrameConfig, spec: SignalSpec, raw: Union[int, float]) -> Optional[str]:
    if not isinstance(raw, int):
        return None
    # Fast path: most signals are not enums. Skip the keys-list allocation by
    # trying source_name first (when distinct from signal_name) and falling
    # through to signal_name only on miss.
    enums = config.enums
    if not enums:
        return None
    frame_id = spec.frame_id
    source = spec.source_name
    name = spec.signal_name
    if source and source != name:
        labels = enums.get((frame_id, source))
        if labels:
            label = labels.get(raw)
            if label is not None:
                return label
    labels = enums.get((frame_id, name))
    if labels is not None:
        return labels.get(raw)
    return None


def _decode_bitfield(config: FrameConfig, spec: SignalSpec, raw: int) -> Dict[str, bool]:
    # Fast path: most signals are not bitfields. Skip the keys-list build
    # entirely when the config has no bitfields, or neither key matches.
    bitfields = config.bitfields
    if not bitfields:
        return {}
    frame_id = spec.frame_id
    source = spec.source_name
    name = spec.signal_name
    specs: List[BitfieldSpec] = []
    if source and source != name:
        specs = bitfields.get((frame_id, source), ())  # type: ignore[assignment]
    if not specs:
        specs = bitfields.get((frame_id, name), ())  # type: ignore[assignment]
    if not specs:
        return {}
    return {bit.bit_name: bool(raw & (1 << bit.bit_index)) for bit in specs}


def _display_text(
    scaled: Optional[float], enum_label: Optional[str], bit_values: Dict[str, bool]
) -> str:
    if enum_label:
        return enum_label
    if bit_values:
        active = [name for name, enabled in bit_values.items() if enabled]
        return ", ".join(active) if active else "None"
    if scaled is None:
        return "-"
    return f"{scaled:.6g}"


def _calculate_groups(
    config: FrameConfig,
    frame_id: int,
    frame_name: str,
    decoded: List[DecodedSignal],
) -> List[DecodedSignal]:
    out: List[DecodedSignal] = []
    for calc in config.calc_groups:
        if calc.frame_id is not None and calc.frame_id != frame_id:
            continue
        values = [
            sig.scaled_value
            for sig in decoded
            if sig.status == "ok" and sig.group == calc.group and sig.scaled_value is not None
        ]
        if not values:
            continue
        value = calculate_group_value(calc, values)
        out.append(
            DecodedSignal(
                frame_id=frame_id,
                frame_name=frame_name,
                signal_name=f"{calc.group} {calc.stat}",
                raw_value=None,
                scaled_value=value,
                unit=calc.unit,
                status="ok",
                group=calc.group,
                display_value=f"{value:.6g}",
                is_calculated=True,
            )
        )
    return out


def _payload_warnings(
    config: FrameConfig, frame_id: int, payload: bytes, specs: List[SignalSpec]
) -> List[DecodeWarning]:
    warnings: List[DecodeWarning] = []
    frame = config.frames.get(frame_id)
    if frame and frame.payload_length is not None and len(payload) != frame.payload_length:
        warnings.append(
            DecodeWarning(
                kind="length_mismatch",
                frame_id=frame_id,
                message=(
                    f"Frame 0x{frame_id:04X} payload length is {len(payload)} bytes, "
                    f"expected {frame.payload_length}"
                ),
            )
        )
    expected_from_signals = max((spec.end_byte for spec in specs), default=0)
    if len(payload) > expected_from_signals:
        tail = payload[expected_from_signals : expected_from_signals + 32]
        warnings.append(
            DecodeWarning(
                kind="extra_bytes",
                frame_id=frame_id,
                message=(
                    f"Frame 0x{frame_id:04X} has {len(payload) - expected_from_signals} "
                    "extra payload byte(s)"
                ),
                offset=expected_from_signals,
                extra_hex=tail.hex(" ").upper(),
            )
        )
    return warnings
