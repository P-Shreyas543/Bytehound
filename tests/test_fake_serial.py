from __future__ import annotations

from app.protocol.packet_parser import create_parser, FramedParser
from app.serial_io.fake_serial import fake_packet_stream, templates_from_config


def test_fake_templates_are_derived_from_config(config):
    templates = templates_from_config(config)
    frame_ids = {template.frame_id for template in templates}
    assert 0x0010 in frame_ids
    assert 0x0030 in frame_ids

    stream = fake_packet_stream(config.protocol, templates)
    parser = create_parser(config.protocol)
    parser.feed(next(stream))
    packets = parser.extract_all()
    assert len(packets) == 1
    assert packets[0].ok
    assert packets[0].frame_id in frame_ids
