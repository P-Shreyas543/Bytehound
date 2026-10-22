"""Decode frame payloads into scaled variables, enums, bitfields, and stats."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

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
    t: Optional[float] = None,
) -> DecodedFrame:
    """Decode one frame. ``state_dict`` carries values between frames (calc
    groups, derived inputs, running integrals); ``t`` is the frame's receive
    time in seconds (``time.perf_counter()``), needed only for integrals."""
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
    if config.derived:
        calculations += _evaluate_derived(config, frame_id, frame_name, decoded, state_dict, t)
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
    if spec.clamp_negative and spec.min_value is not None and spec.min_value >= 0 and -0.5 <= scaled < 0:
        scaled = 0.0

    rules = config.value_rules
    if rules:
        rule = rules.get((spec.frame_id, spec.signal_name))
        if rule is not None and rule.source_byte < len(payload):
            scaled = rule.value_if_match if payload[rule.source_byte] in rule.match_values else rule.value_otherwise
            raw = int(scaled)

    enum_label = _lookup_enum(config, spec, raw)
    # raw is already an int here (the isinstance branch); int(raw) was a
    # redundant no-op call that just added per-signal overhead.
    bit_values = _decode_bitfield(config, spec, raw) if isinstance(raw, int) else {}
    display = _display_text(scaled, enum_label, bit_values, spec)
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

    Boolean signals are decoded via bit masking (bit_offset or LSB).
    Numeric signals use ``struct.unpack_from`` which reads directly from
    the payload bytes object; avoiding the per-signal ``payload[start:end]``
    slice eliminates one bytes allocation per int/float signal and is
    faster than ``int.from_bytes`` for every fixed-width type benchmarked
    (microbench: ~1.9× faster for uint16). Odd-byte-length ints
    (3 / 5 / 6 / 7) have no native struct format code and are unpacked
    using a wider struct.unpack_from (4 or 8 bytes) combined with bitwise
    shifting and masking, or fallback to ``int.from_bytes``.
    """
    if spec.bit_length is not None and spec.bit_length > 1:
        shift = spec.bit_offset if spec.bit_offset is not None else 0
        total_int = int.from_bytes(payload[spec.start_byte : spec.end_byte], byteorder=spec.endianness, signed=False)
        raw = (total_int >> shift) & ((1 << spec.bit_length) - 1)
        signed = spec.data_type == "int" or (spec.data_type.startswith("int") and not spec.data_type.startswith("uint"))
        if signed and (raw & (1 << (spec.bit_length - 1))):
            raw -= (1 << spec.bit_length)
        return raw
    if spec.bit_offset is not None:
        return (payload[spec.start_byte] >> spec.bit_offset) & 1
    if spec.is_boolean:
        return payload[spec.start_byte] & 1
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
    signed = spec.data_type == "int" or (spec.data_type.startswith("int") and not spec.data_type.startswith("uint"))

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
    if spec.data_type == "float" or spec.data_type.startswith("float"):
        return struct.Struct(endian + ("f" if spec.byte_length == 4 else "d"))
    signed = spec.data_type == "int" or (spec.data_type.startswith("int") and not spec.data_type.startswith("uint"))
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
    scaled: Optional[float], enum_label: Optional[str], bit_values: Dict[str, bool], spec: Optional[SignalSpec] = None
) -> str:
    if enum_label:
        return enum_label
    if bit_values:
        active = [name for name, enabled in bit_values.items() if enabled]
        return ", ".join(active) if active else "None"
    if scaled is None:
        return "-"
    if spec is not None and spec.is_boolean:
        return "1" if scaled != 0 else "0"
    return f"{scaled:.6g}"


def _calculate_groups(
    config: FrameConfig,
    frame_id: int,
    frame_name: str,
    decoded: List[DecodedSignal],
    state_dict: Dict[str, Dict[str, Any]],
) -> List[DecodedSignal]:
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

        # Resolve unit: use calc.unit if specified, otherwise try to inherit from signals in the group
        unit = calc.unit
        if not unit:
            for sig in decoded:
                if sig.group == calc.group and sig.unit:
                    unit = sig.unit
                    break
            if not unit:
                for sig_spec in config.all_signals:
                    if sig_spec.group == calc.group and sig_spec.unit:
                        unit = sig_spec.unit
                        break

        display_val = f"{value:.6g} {unit}".strip() if unit else f"{value:.6g}"
        signal_name = f"{calc.group} {calc.stat}"

        # Do not emit one log record per calculated signal/frame.  At normal
        # telemetry rates this can produce thousands of records per minute and
        # make both the file handler and the UI feel sluggish when DEBUG is
        # enabled.  Calculation details are already available in the decoded
        # frame and can be inspected from the live table/log.

        out.append(
            DecodedSignal(
                frame_id=frame_id,
                frame_name=frame_name,
                signal_name=signal_name,
                raw_value=raw_value,
                scaled_value=value,
                unit=unit,
                status="ok",
                group=calc.group,
                display_value=display_val,
                is_calculated=True,
            )
        )
    return out


_DERIVED_LATEST = "__derived_latest__"
_DERIVED_INTEGRALS = "__derived_integrals__"
# An integral interval much longer than usual is a gap (unplug, silent
# device): it is not integrated, never bridged by a straight line.
_INTEGRAL_GAP_FACTOR = 5.0
_INTEGRAL_GAP_MIN_S = 2.0


def reset_integrals(state_dict: Dict) -> None:
    """Start every running integral (Ah, Wh …) again from 0 — at the start
    of a logging session."""
    state_dict.pop(_DERIVED_INTEGRALS, None)


def _evaluate_derived(config: FrameConfig, frame_id: int, frame_name: str, decoded: List[DecodedSignal],
                      state_dict: Dict, t: Optional[float]) -> List[DecodedSignal]:
    latest = state_dict.setdefault(_DERIVED_LATEST, {})
    for s in decoded:
        if s.status == "ok" and s.scaled_value is not None:
            latest[(frame_id, s.signal_name)] = float(s.scaled_value)
    integrals = state_dict.setdefault(_DERIVED_INTEGRALS, {})
    out: List[DecodedSignal] = []
    for d in config.derived:
        if d.frame_id != frame_id:
            continue
        expr = _compiled(d.expression)
        values = {}
        for ref, key in zip(expr.refs, d.inputs, strict=True):
            v = latest.get(key)
            if v is None:
                break
            values[ref] = v
        else:
            try:
                value = float(expr.evaluate(values))
            except (ArithmeticError, ValueError, TypeError):
                continue
            if not math.isfinite(value):
                continue
            if d.kind != "value":
                st = integrals.get(d.name)          # [last_t, last_value, total, typical_dt]
                if t is None:
                    if st is None:
                        continue
                elif st is None:
                    st = integrals[d.name] = [t, value, 0.0, None]
                else:
                    dt = t - st[0]
                    if dt > 0:
                        typical = st[3]
                        gap = typical is not None and dt > max(_INTEGRAL_GAP_MIN_S, _INTEGRAL_GAP_FACTOR * typical)
                        if not gap:
                            area = 0.5 * (value + st[1]) * dt
                            st[2] += area / 3600.0 if d.kind == "integral_hours" else area
                            st[3] = dt if typical is None else typical + 0.1 * (dt - typical)
                        st[0] = t
                    st[1] = value
                value = st[2]
            latest[("derived", d.name)] = value
            display = f"{value:.6g} {d.unit}".strip() if d.unit else f"{value:.6g}"
            out.append(DecodedSignal(
                frame_id=frame_id, frame_name=frame_name, signal_name=d.name, raw_value=None,
                scaled_value=value, unit=d.unit, status="ok", group="Derived",
                display_value=display, is_calculated=True,
            ))
    return out


_COMPILED: Dict[str, object] = {}


def _compiled(text: str):
    expr = _COMPILED.get(text)
    if expr is None:
        from .expressions import compile_expression
        expr = _COMPILED[text] = compile_expression(text)
    return expr


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
    expected_length = (
        frame.payload_length
        if (frame and frame.payload_length is not None)
        else expected_from_signals
    )
    if len(payload) > expected_length:
        tail = payload[expected_length : expected_length + 32]
        warnings.append(
            DecodeWarning(
                kind="extra_bytes",
                frame_id=frame_id,
                message=(
                    f"Frame 0x{frame_id:04X} has {len(payload) - expected_length} "
                    "extra payload byte(s)"
                ),
                offset=expected_length,
                extra_hex=tail.hex(" ").upper(),
            )
        )
    return warnings
