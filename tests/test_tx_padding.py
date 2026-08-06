from tests.conftest import dummy_protocol_config
from app.protocol.packet_builder import build_packet, build_modbus_packet

def test_tx_padding_framed():
    pc = dummy_protocol_config(parser_type="framed", header=b"\xAA", footer=b"\x55", tx_pad_length=10)
    # 1 byte header, 2 byte frame id, 1 byte len, 2 byte crc, 1 byte footer -> 7 bytes fixed
    # If payload is 1 byte, total = 8. Padding needed = 2 bytes.
    packet = build_packet(pc, 0x0001, b"\xFF")
    assert len(packet) == 10

    # Check that padding is \x00
    # format: header(1) + frame_id(2) + len(1) + payload(1) + padding(2) + crc(2) + footer(1)
    # The padding should be after payload.
    # packet[:-3] is everything up to padding. packet[-3] is crc byte 1.
    assert packet[5:7] == b"\x00\x00"

def test_tx_padding_modbus():
    # Modbus packet builder doesn't currently implement tx_pad_length in our code
    # We should probably test that it just builds normal modbus frames
    pc = dummy_protocol_config(parser_type="modbus_rtu")
    packet = build_modbus_packet(pc, 0x1000, b"")
    # Read holding register 0x1000
    assert packet == b"\x01\x03\x10\x00\x00\x01\x80\xCA"


def test_tx_pad_length_zero_normalized():
    pc = dummy_protocol_config(parser_type="framed", header=b"\xAA", footer=b"\x55", tx_pad_length=0)
    assert pc.tx_pad_length is None
    # 7-byte frame (header 1, fid 2, len 1, crc 2, footer 1, payload 0)
    packet = build_packet(pc, 0x6000, b"")
    assert len(packet) == 7



def test_experiment1_excel_loading():
    from app.decoder.config_loader import load_config
    cfg = load_config("Experiment1_frame_config.xlsx")
    assert cfg.protocol.tx_pad_length is None
    pkt = build_packet(cfg.protocol, 0x6000, b"\x01")
    assert isinstance(pkt, bytes)

