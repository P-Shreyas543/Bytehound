"""Decode frame payloads into scaled variables, enums, bitfields, and stats."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

from .calculations import calculate_group_value
from .types import BitfieldSpec, DecodeWarning, FrameConfig, SignalSpec


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


def decode_frame(
    config: FrameConfig,
    frame_id: int,
    payload: bytes,
    state_dict: Optional[Dict[str, Dict[str, float]]] = None,
) -> DecodedFrame:
    if state_dict is None:
        state_dict = {}

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
    calculations = _calculate_groups(config, frame_id, frame_name, decoded, state_dict)
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

    try:
        raw = _decode_raw_at(payload, spec)
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


# Cache from (endianness, byte_length, data_type) → compiled struct.Struct.
# Lazily populated on first decode of each unique signal shape. Lookups
# are a single dict.get with a 3-tuple key; collapsing what used to be
# two dict.gets (one for the format char, one for the Struct) into a
# single hot-path call. A None entry caches the "no native struct code"
# verdict (odd byte counts) so the fallback path still avoids re-deciding
# per call.
#
# Bounded by construction: keys come from a tiny finite product —
# 2 endiannesses × 8 byte lengths (1..8) × 3 data_types ("int", "uint",
# "float") = 48 entries max for the lifetime of the process. Not an
# unbounded cache; no eviction needed.
_DECODE_STRUCT_CACHE: Dict[tuple, Optional[struct.Struct]] = {}

# Fixed-width integer struct format chars. Power-of-two byte counts
# only — 3 / 5 / 6 / 7 byte ints have no native struct code and fall
# back to int.from_bytes on a sliced chunk.
_INT_FMT_CHAR = {
    (1, False): "B",
    (1, True):  "b",
    (2, False): "H",
    (2, True):  "h",
    (4, False): "I",
    (4, True):  "i",
    (8, False): "Q",
    (8, True):  "q",
}


def _decode_raw_at(payload: bytes, spec: SignalSpec) -> Union[int, float]:
    """Decode a single raw value at ``spec.start_byte`` without slicing.

    ``struct.unpack_from`` reads directly from the payload bytes object;
    avoiding the per-signal ``payload[start:end]`` slice eliminates one
    bytes allocation per int/float signal and is faster than
    ``int.from_bytes`` for every fixed-width type benchmarked
    (microbench: ~1.9× faster for uint16). Odd-byte-length ints
    (3 / 5 / 6 / 7) have no native struct format code. To avoid slicing
    and allocation, they are unpacked using a wider struct.unpack_from
    (4 or 8 bytes) combined with bitwise shifting and masking, provided
    there are enough remaining bytes in the payload. Otherwise, they
    fallback to the slice + ``int.from_bytes`` path.
    """
    cache_key = (spec.endianness, spec.byte_length, spec.data_type)
    s = _DECODE_STRUCT_CACHE.get(cache_key, _UNCACHED)
    if s is _UNCACHED:
        s = _build_struct_for(spec)
        _DECODE_STRUCT_CACHE[cache_key] = s
    if s is not None:
        return s.unpack_from(payload, spec.start_byte)[0]

    # Cached "no native struct code" — odd byte length int.
    W = spec.byte_length
    start = spec.start_byte
    signed = spec.data_type == "int"

    if W == 3 and start + 4 <= len(payload):
        if spec.endianness == "little":
            val = struct.unpack_from("<I", payload, start)[0] & 0xFFFFFF
        else:
            val = struct.unpack_from(">I", payload, start)[0] >> 8
        if signed and (val & 0x800000):
            val -= 0x1000000
        return val
    elif W in (5, 6, 7) and start + 8 <= len(payload):
        if spec.endianness == "little":
            val = struct.unpack_from("<Q", payload, start)[0]
            mask = (1 << (8 * W)) - 1
            val = val & mask
        else:
            val = struct.unpack_from(">Q", payload, start)[0]
            shift = 8 * (8 - W)
            val = val >> shift
        if signed:
            sign_bit = 1 << (8 * W - 1)
            if val & sign_bit:
                val -= 1 << (8 * W)
        return val

    chunk = payload[start : spec.end_byte]
    return int.from_bytes(chunk, byteorder=spec.endianness, signed=signed)


# Sentinel that distinguishes "not yet seen this spec" from "seen and
# concluded no native struct code applies" (cache value: None). Keeps
# the hot path branch-free for the common case.
_UNCACHED: object = object()


def _build_struct_for(spec: SignalSpec) -> Optional[struct.Struct]:
    endian = "<" if spec.endianness == "little" else ">"
    if spec.data_type == "float":
        return struct.Struct(endian + ("f" if spec.byte_length == 4 else "d"))
    signed = spec.data_type == "int"
    fmt_char = _INT_FMT_CHAR.get((spec.byte_length, signed))
    if fmt_char is None:
        return None
    return struct.Struct(endian + fmt_char)


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
    state_dict: Dict[str, Dict[str, Any]],
) -> List[DecodedSignal]:
    import logging
    logger = logging.getLogger("bytehound.decoder.calculations")
    out: List[DecodedSignal] = []

    # Update state_dict with the current frame's valid signals
    for sig in decoded:
        if sig.status == "ok" and sig.group and sig.scaled_value is not None:
            group_state = state_dict.setdefault(sig.group, {})
            group_state[sig.signal_name] = sig.scaled_value
            if sig.raw_value is not None:
                raw_group_state = state_dict.setdefault(f"__raw__{sig.group}", {})
                raw_group_state[sig.signal_name] = sig.raw_value

    for calc in config.calc_groups:
        if calc.frame_id is not None and calc.frame_id != frame_id:
            continue

        raw_group_state = state_dict.get(f"__raw__{calc.group}")
        group_state = state_dict.get(calc.group)

        if not raw_group_state and not group_state:
            continue

        # Calculate raw value from raw values
        raw_values = [v for v in raw_group_state.values() if v is not None] if raw_group_state else []
        if raw_values:
            raw_val_calc = calculate_group_value(calc, raw_values)
            raw_value = int(round(raw_val_calc))
        else:
            raw_value = None

        # Calculate scaled value from scaled values
        values = list(group_state.values()) if group_state else []
        if not values:
            continue
        value = calculate_group_value(calc, values)

        display_val = f"{value:.6g} {calc.unit}".strip() if calc.unit else f"{value:.6g}"
        signal_name = f"{calc.group} {calc.stat}"

        raw_val_str = f"{raw_value:.6g}" if isinstance(raw_value, float) else str(raw_value)
        logger.info("Calculated %s: scaled = %s (raw = %s)", signal_name, display_val, raw_val_str)

        out.append(
            DecodedSignal(
                frame_id=frame_id,
                frame_name=frame_name,
                signal_name=signal_name,
                raw_value=raw_value,
                scaled_value=value,
                unit=calc.unit,
                status="ok",
                group=calc.group,
                display_value=display_val,
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
