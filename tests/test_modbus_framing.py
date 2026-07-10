from tests.conftest import dummy_protocol_config
from app.protocol.packet_parser import ModbusRtuParser

def test_modbus_read_holding_registers_response():
    pc = dummy_protocol_config(parser_type="modbus_rtu")
    parser = ModbusRtuParser(pc)

    # 0x01 (Node), 0x03 (FC), 0x04 (Bytes), [0x01, 0x02, 0x03, 0x04] (Data), CRC
    frame = bytes([0x01, 0x03, 0x04, 0x01, 0x02, 0x03, 0x04])
    import app.protocol.crc as crc_mod
    crc = crc_mod.compute("crc16_modbus", frame)
    frame += crc.to_bytes(2, "little")

    parser.feed(frame)
    packets = parser.extract_all()
    assert len(packets) == 1
    p = packets[0]
    assert p.ok
    assert p.frame_id == 0x01
    assert p.payload == bytes([0x01, 0x02, 0x03, 0x04])

def test_modbus_write_single_register_response():
    pc = dummy_protocol_config(parser_type="modbus_rtu")
    parser = ModbusRtuParser(pc)

    # 0x01, 0x06, 0x00, 0x0A (Addr), 0x00, 0x01 (Val), CRC
    frame = bytes([0x01, 0x06, 0x00, 0x0A, 0x00, 0x01])
    import app.protocol.crc as crc_mod
    crc = crc_mod.compute("crc16_modbus", frame)
    frame += crc.to_bytes(2, "little")

    parser.feed(frame)
    packets = parser.extract_all()
    assert len(packets) == 1
    p = packets[0]
    assert p.ok
    assert p.frame_id == 0x01
    assert p.payload == bytes([0x00, 0x01]) # Our parser returns the whole payload after FC and before CRC, wait.
    # Actually our parser for FC 6 returns frame[4:6] which is just the value
    # Let's check what it returns
    assert p.payload == bytes([0x00, 0x01])

def test_modbus_error_response():
    pc = dummy_protocol_config(parser_type="modbus_rtu")
    parser = ModbusRtuParser(pc)

    # 0x01, 0x83, 0x02 (Error code), CRC
    frame = bytes([0x01, 0x83, 0x02])
    import app.protocol.crc as crc_mod
    crc = crc_mod.compute("crc16_modbus", frame)
    frame += crc.to_bytes(2, "little")

    parser.feed(frame)
    packets = parser.extract_all()
    assert len(packets) == 1
    p = packets[0]
    assert p.ok
    assert p.frame_id == 0x01
    assert p.payload == b""
