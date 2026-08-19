"""Verification test confirming bidirectional RX and TX boolean handling."""

import sys
from pathlib import Path

# Ensure project root is in sys.path when executed directly as python test_xxx.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from app.decoder.types import (
    FrameConfig, ProtocolConfig, FrameDefinition, SignalSpec,
    BitfieldSpec, TxCommandSpec, TxCommandFieldSpec
)
from app.decoder.frame_decoder import decode_frame
from app.commands.tx_command_builder import build_tx_command


def _create_protocol():
    return ProtocolConfig(
        profile_name="Test",
        header=b"\xaa\x55",
        frame_id_size=2,
        frame_id_byte_order="little",
        length_size=1,
        length_meaning="payload_only",
        crc_type="none",
        crc_size=0,
        crc_byte_order="little",
        crc_coverage="header_to_payload",
        footer=b"",
        escape_mode="none",
        enabled=True,
        parser_type="framed"
    )


def test_boolean_rx_and_tx_direct():
    """Verify direct boolean signal in Variables and TxCommandFields."""
    protocol = _create_protocol()
    frames = {0x1000: FrameDefinition(frame_id=0x1000, frame_name="Control", payload_length=1, direction="rxtx")}
    signals_by_frame = {
        0x1000: [
            SignalSpec(
                frame_id=0x1000,
                frame_name="Control",
                signal_name="Relay_State",
                start_byte=0,
                byte_length=1,
                endianness="little",
                data_type="boolean",
                scale=1.0,
                offset=0.0,
                unit="",
                group="Main"
            )
        ]
    }
    tx_commands = {
        "Set_Relay": TxCommandSpec(
            command_name="Set_Relay",
            frame_id=0x1000,
            payload_hex="",
            description="Toggle relay",
            fields=[
                TxCommandFieldSpec(
                    command_name="Set_Relay",
                    field_name="Relay_State",
                    fmt="boolean",
                    default=0.0
                )
            ]
        )
    }
    config = FrameConfig(protocol=protocol, frames=frames, signals_by_frame=signals_by_frame, tx_commands=tx_commands)

    # 1. RX Ingress: Hardware sends 0x01 (ON)
    decoded_on = decode_frame(config, 0x1000, b"\x01")
    assert decoded_on.signals[0].scaled_value == 1.0
    assert decoded_on.signals[0].display_value == "1"

    # 2. RX Ingress: Hardware sends 0x00 (OFF)
    decoded_off = decode_frame(config, 0x1000, b"\x00")
    assert decoded_off.signals[0].scaled_value == 0.0
    assert decoded_off.signals[0].display_value == "0"

    # 3. TX Egress: User transmits Relay_State = 1
    packet_on = build_tx_command(config, "Set_Relay", {"Relay_State": 1.0})
    # Header: AA 55, FrameID: 00 10 (little-endian 0x1000), Length: 01, Payload: 01
    assert packet_on == b"\xaa\x55\x00\x10\x01\x01"

    # 4. TX Egress: User transmits Relay_State = 0
    packet_off = build_tx_command(config, "Set_Relay", {"Relay_State": 0.0})
    assert packet_off == b"\xaa\x55\x00\x10\x01\x00"


def test_boolean_rx_bitfields_and_enums():
    """Verify bitfields and enums decoding for boolean status words."""
    protocol = _create_protocol()
    frames = {0x1000: FrameDefinition(frame_id=0x1000, frame_name="Status", payload_length=1, direction="rx")}
    signals_by_frame = {
        0x1000: [
            SignalSpec(frame_id=0x1000, frame_name="Status", signal_name="Relay_Enum", start_byte=0, byte_length=1, endianness="little", data_type="uint8", scale=1.0, offset=0.0, unit="", group="Main"),
            SignalSpec(frame_id=0x1000, frame_name="Status", signal_name="Status_Word", start_byte=0, byte_length=1, endianness="little", data_type="uint8", scale=1.0, offset=0.0, unit="", group="Main")
        ]
    }
    bitfields = {
        (0x1000, "Status_Word"): [
            BitfieldSpec(frame_id=0x1000, variable_name="Status_Word", bit_index=0, bit_name="Relay_Active", active_text="ON", inactive_text="OFF")
        ]
    }
    enums = {
        (0x1000, "Relay_Enum"): {0: "OFF", 1: "ON"}
    }
    config = FrameConfig(protocol=protocol, frames=frames, signals_by_frame=signals_by_frame, bitfields=bitfields, enums=enums)

    # Frame with 0x01 (Bit 0 is high)
    dec = decode_frame(config, 0x1000, b"\x01")
    assert dec.signals[0].enum_label == "ON"
    assert dec.signals[0].display_value == "ON"
    assert dec.signals[1].bit_values["Relay_Active"] is True
    assert dec.signals[1].display_value == "Relay_Active"

    # Frame with 0x00 (Bit 0 is low)
    dec_zero = decode_frame(config, 0x1000, b"\x00")
    assert dec_zero.signals[0].enum_label == "OFF"
    assert dec_zero.signals[0].display_value == "OFF"
    assert dec_zero.signals[1].bit_values["Relay_Active"] is False
    assert dec_zero.signals[1].display_value == "None"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
