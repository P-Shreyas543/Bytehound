"""Synthetic packet generator derived from the loaded configuration."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Iterator, List

from ..decoder.types import FrameConfig, ProtocolConfig, SignalSpec
from ..protocol.packet_builder import build_packet


@dataclass
class FakeFrameTemplate:
    frame_id: int
    payloads: List[bytes]


def fake_packet_stream(
    protocol: ProtocolConfig, templates: List[FakeFrameTemplate]
) -> Iterator[bytes]:
    if not templates:
        return
    indices = [0] * len(templates)
    while True:
        for template_index, template in enumerate(templates):
            if not template.payloads:
                continue
            payload = template.payloads[indices[template_index] % len(template.payloads)]
            indices[template_index] += 1
            yield build_packet(protocol, template.frame_id, payload)


def templates_from_config(config: FrameConfig, variants: int = 3) -> List[FakeFrameTemplate]:
    """Create generic changing fake payloads from configured signal layout."""

    templates: List[FakeFrameTemplate] = []
    for frame_id, signals in config.signals_by_frame.items():
        frame = config.frames.get(frame_id)
        if frame and frame.direction not in {"rx", "both"}:
            continue
        payload_length = _payload_length(config, frame_id, signals)
        payloads = [
            _build_payload_variant(signals, payload_length, variant)
            for variant in range(max(1, variants))
        ]
        templates.append(FakeFrameTemplate(frame_id=frame_id, payloads=payloads))
    return templates


def _payload_length(
    config: FrameConfig, frame_id: int, signals: List[SignalSpec]
) -> int:
    frame = config.frames.get(frame_id)
    configured = frame.payload_length if frame else None
    signal_length = max((signal.end_byte for signal in signals), default=0)
    return max(configured or 0, signal_length)


def _build_payload_variant(
    signals: List[SignalSpec], payload_length: int, variant: int
) -> bytes:
    payload = bytearray(payload_length)
    for signal_index, signal in enumerate(signals):
        raw = _sample_raw_value(signal, signal_index, variant)
        encoded = _encode_raw(signal, raw)
        payload[signal.start_byte : signal.end_byte] = encoded
    return bytes(payload)


def _sample_raw_value(signal: SignalSpec, signal_index: int, variant: int) -> float:
    if signal.data_type == "float":
        return float(signal_index + 1) + variant * 0.1
    if signal.unit.lower() == "bitfield":
        return (variant + signal_index) & ((1 << (8 * signal.byte_length)) - 1)
    if signal.unit.lower() == "enum":
        return variant
    base = 1000 + signal_index * 100
    val = base + variant
    max_val = (1 << (8 * signal.byte_length)) - 1
    if signal.data_type == "int":
        max_val = (1 << (8 * signal.byte_length - 1)) - 1
        return min(val, max_val)
    return min(val, max_val)


def _encode_raw(signal: SignalSpec, raw: float) -> bytes:
    if signal.data_type == "float":
        endian = "<" if signal.endianness == "little" else ">"
        fmt = "f" if signal.byte_length == 4 else "d"
        return struct.pack(endian + fmt, float(raw))
    signed = signal.data_type == "int"
    return int(raw).to_bytes(signal.byte_length, signal.endianness, signed=signed)
