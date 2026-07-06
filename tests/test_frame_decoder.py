"""Tests for `app.decoder.frame_decoder.decode_frame`."""

from __future__ import annotations

import struct

import pytest

from app.decoder.frame_decoder import decode_frame
from app.decoder.types import FrameConfig, ProtocolConfig, SignalSpec
from tests.conftest import CANONICAL_FRAME_ID, CANONICAL_PAYLOAD_HEX, hex_to_bytes


def test_decodes_canonical_payload(config):
    decoded = decode_frame(
        config, CANONICAL_FRAME_ID, hex_to_bytes(CANONICAL_PAYLOAD_HEX)
    )
    assert decoded.error is None
    assert len(decoded.signals) == 2

    s1, s2 = decoded.signals
    assert s1.signal_name == "Cell Voltage 1"
    assert s1.raw_value == 4000
    assert s1.scaled_value == pytest.approx(4.0)
    assert s1.unit == "V"
    assert s1.status == "ok"

    assert s2.signal_name == "Cell Voltage 2"
    assert s2.raw_value == 3000
    assert s2.scaled_value == pytest.approx(3.0)
    assert {c.signal_name: c.scaled_value for c in decoded.calculations} == {
        "Cells min": pytest.approx(3.0),
        "Cells max": pytest.approx(4.0),
        "Cells diff": pytest.approx(1.0),
        "Cells avg": pytest.approx(3.5),
    }


def test_decodes_enum_and_bitfields(config):
    decoded = decode_frame(config, 0x0030, bytes.fromhex("02030200"))
    assert decoded.error is None
    by_name = {signal.signal_name: signal for signal in decoded.signals}
    assert by_name["BMS State"].enum_label == "Charge"
    assert by_name["FET Status"].bit_values == {
        "Main FET Status": True,
        "Pre Charge FET Status": True,
    }
    assert by_name["Fault Status"].bit_values["Cell UV"] is True


def test_unknown_frame_id_returns_frame_level_error(config):
    decoded = decode_frame(config, 0x0999, b"\x00\x00")
    assert decoded.signals == []
    assert decoded.error is not None
    assert "0x0999" in decoded.error


def test_payload_too_short_marks_signal_error(config):
    decoded = decode_frame(config, CANONICAL_FRAME_ID, b"\x0F\xA0")  # only 2 of 4 bytes
    assert decoded.error is None  # frame-level still ok
    assert decoded.signals[0].status == "ok"
    assert decoded.signals[0].raw_value == 4000
    assert decoded.signals[1].status.startswith("Payload too short")
    assert decoded.signals[1].raw_value is None


def test_extra_payload_bytes_are_reported_as_warning(config):
    decoded = decode_frame(config, CANONICAL_FRAME_ID, bytes.fromhex("0FA00BB800"))
    assert decoded.error is None
    # decoded.warnings is List[DecodeWarning]; check the .message field.
    assert any("extra payload byte" in w.message for w in decoded.warnings)
    assert any(w.kind == "extra_bytes" for w in decoded.warnings)


# --- Synthetic configs to exercise int / float decoding paths ---------------


def _protocol() -> ProtocolConfig:
    return ProtocolConfig(
        profile_name="t", header=b"\xAA\x55", frame_id_size=2,
        frame_id_byte_order="big", length_size=1, length_meaning="payload_only",
        crc_type="crc16_modbus", crc_size=2, crc_byte_order="little",
        crc_coverage="header_to_payload", footer=b"", escape_mode="none",
        enabled=True,
    )


def _make_config(specs: list[SignalSpec]) -> FrameConfig:
    cfg = FrameConfig(protocol=_protocol())
    for s in specs:
        cfg.signals_by_frame.setdefault(s.frame_id, []).append(s)
        cfg.frame_names.setdefault(s.frame_id, s.frame_name)
    return cfg


def test_signed_int_decodes_negative():
    spec = SignalSpec(
        frame_id=0x1, frame_name="t", signal_name="Temp",
        start_byte=0, byte_length=2, endianness="little",
        data_type="int", scale=0.1, offset=0.0, unit="C",
    )
    cfg = _make_config([spec])
    # int16 little-endian 0xFF 0xFF == -1
    decoded = decode_frame(cfg, 0x1, b"\xFF\xFF")
    assert decoded.signals[0].raw_value == -1
    assert decoded.signals[0].scaled_value == pytest.approx(-0.1)


def test_decode_odd_byte_length_fallback():
    spec_3 = SignalSpec(
        frame_id=1, frame_name="F1", signal_name="S3", start_byte=0, byte_length=3,
        endianness="big", data_type="uint", scale=1.0, offset=0.0, unit=""
    )
    spec_5 = SignalSpec(
        frame_id=1, frame_name="F1", signal_name="S5", start_byte=3, byte_length=5,
        endianness="little", data_type="uint", scale=1.0, offset=0.0, unit=""
    )
    
    cfg = _make_config([spec_3, spec_5])
    
    # 3 bytes big-endian: \x01\x02\x03 -> 0x010203 (66051)
    # 5 bytes little-endian: \x04\x05\x06\x07\x08 -> 0x0807060504 (34477831428)
    data = b"\x01\x02\x03" + b"\x04\x05\x06\x07\x08"
    decoded = decode_frame(cfg, 1, data)
    
    assert decoded.signals[0].raw_value == 0x010203
    assert decoded.signals[1].raw_value == 0x0807060504


def test_float32_big_endian_decodes_ieee754():
    spec = SignalSpec(
        frame_id=0x2, frame_name="t", signal_name="V",
        start_byte=0, byte_length=4, endianness="big",
        data_type="float", scale=1.0, offset=0.0, unit="V",
    )
    cfg = _make_config([spec])
    payload = struct.pack(">f", 12.5)
    decoded = decode_frame(cfg, 0x2, payload)
    assert decoded.signals[0].raw_value == pytest.approx(12.5)
    assert decoded.signals[0].scaled_value == pytest.approx(12.5)


def test_offset_applied_after_scale():
    spec = SignalSpec(
        frame_id=0x3, frame_name="t", signal_name="Temp",
        start_byte=0, byte_length=1, endianness="little",
        data_type="uint", scale=1.0, offset=-40.0, unit="C",
    )
    cfg = _make_config([spec])
    decoded = decode_frame(cfg, 0x3, b"\x32")  # 50 - 40 = 10
    assert decoded.signals[0].scaled_value == pytest.approx(10.0)


def test_odd_byte_widths_decodes():
    # 3-byte unsigned little-endian
    spec_3u_le = SignalSpec(
        frame_id=0x4, frame_name="t", signal_name="3u_le",
        start_byte=0, byte_length=3, endianness="little",
        data_type="uint", scale=1.0, offset=0.0, unit="",
    )
    # 3-byte signed big-endian
    spec_3s_be = SignalSpec(
        frame_id=0x4, frame_name="t", signal_name="3s_be",
        start_byte=3, byte_length=3, endianness="big",
        data_type="int", scale=1.0, offset=0.0, unit="",
    )
    # 5-byte signed little-endian
    spec_5s_le = SignalSpec(
        frame_id=0x4, frame_name="t", signal_name="5s_le",
        start_byte=6, byte_length=5, endianness="little",
        data_type="int", scale=1.0, offset=0.0, unit="",
    )
    # 6-byte unsigned big-endian
    spec_6u_be = SignalSpec(
        frame_id=0x4, frame_name="t", signal_name="6u_be",
        start_byte=11, byte_length=6, endianness="big",
        data_type="uint", scale=1.0, offset=0.0, unit="",
    )
    # 7-byte signed big-endian near the edge (overshoots 8 bytes, so falls back to int.from_bytes)
    spec_7s_be_edge = SignalSpec(
        frame_id=0x4, frame_name="t", signal_name="7s_be_edge",
        start_byte=17, byte_length=7, endianness="big",
        data_type="int", scale=1.0, offset=0.0, unit="",
    )

    cfg = _make_config([spec_3u_le, spec_3s_be, spec_5s_le, spec_6u_be, spec_7s_be_edge])

    # 3u_le = 0x123456 -> 56 34 12
    # 3s_be = -1 -> FF FF FF
    # 5s_le = -2 -> FE FF FF FF FF
    # 6u_be = 0x112233445566 -> 11 22 33 44 55 66
    # 7s_be_edge = -3 -> FF FF FF FF FF FF FD
    payload = bytes.fromhex("563412" + "FFFFFF" + "FEFFFFFFFF" + "112233445566" + "FFFFFFFFFFFFFD")

    decoded = decode_frame(cfg, 0x4, payload)
    assert decoded.error is None

    signals = {sig.signal_name: sig.raw_value for sig in decoded.signals}
    assert signals["3u_le"] == 0x123456
    assert signals["3s_be"] == -1
    assert signals["5s_le"] == -2
    assert signals["6u_be"] == 0x112233445566
    assert signals["7s_be_edge"] == -3
