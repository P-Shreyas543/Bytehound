from __future__ import annotations

import pytest

from app.decoder.calculations import calculate_group_value
from app.decoder.types import CalcGroupSpec


@pytest.mark.parametrize(
    ("stat", "expected"),
    [
        ("min", 1.0),
        ("max", 4.0),
        ("diff", 3.0),
        ("sum", 8.0),
        ("avg", 2.0),
    ],
)
def test_calculate_group_value(stat, expected):
    calc = CalcGroupSpec(group="Cells", stat=stat, unit="V")
    assert calculate_group_value(calc, [1.0, 2.0, 1.0, 4.0]) == pytest.approx(expected)


def test_calculate_group_value_rejects_empty_values():
    calc = CalcGroupSpec(group="Cells", stat="avg", unit="V")
    with pytest.raises(ValueError, match="empty"):
        calculate_group_value(calc, [])


def test_calculate_groups_raw_value_and_units():
    from app.decoder.frame_decoder import _calculate_groups, DecodedSignal
    from app.decoder.types import CalcGroupSpec, FrameConfig, ProtocolConfig, SignalSpec

    # Mock configuration
    protocol = ProtocolConfig(
        profile_name="test", header=b"", frame_id_size=2, frame_id_byte_order="little",
        length_size=1, length_meaning="payload", crc_type="none", crc_size=0,
        crc_byte_order="little", crc_coverage="header_to_payload", footer=b"",
        escape_mode="none", enabled=True
    )

    sig_spec = SignalSpec(
        frame_id=0x0100, frame_name="FrameA", signal_name="Cell_V1",
        start_byte=0, byte_length=2, endianness="little", data_type="uint16",
        scale=0.001, offset=0.0, unit="V", group="Cells"
    )

    calc = CalcGroupSpec(group="Cells", stat="avg", unit="V", frame_id=0x0100)
    cfg = FrameConfig(
        protocol=protocol,
        frames={},
        signals_by_frame={0x0100: [sig_spec]},
        frame_names={0x0100: "FrameA"},
    )
    cfg.calc_groups = [calc]

    decoded_signals = [
        DecodedSignal(
            frame_id=0x0100, frame_name="FrameA", signal_name="Cell_V1",
            raw_value=4000, scaled_value=4.0, unit="V", status="ok", group="Cells"
        ),
        DecodedSignal(
            frame_id=0x0100, frame_name="FrameA", signal_name="Cell_V2",
            raw_value=4200, scaled_value=4.2, unit="V", status="ok", group="Cells"
        )
    ]

    state_dict = {}
    out = _calculate_groups(cfg, 0x0100, "FrameA", decoded_signals, state_dict)

    assert len(out) == 1
    calc_sig = out[0]
    assert calc_sig.signal_name == "Cells avg"
    assert calc_sig.scaled_value == pytest.approx(4.1)
    assert calc_sig.raw_value == pytest.approx(4100)
    assert calc_sig.unit == "V"
    assert calc_sig.display_value == "4.1 V"
    assert calc_sig.is_calculated is True


def test_calculate_groups_inherits_unit():
    from app.decoder.frame_decoder import _calculate_groups, DecodedSignal
    from app.decoder.types import CalcGroupSpec, FrameConfig, ProtocolConfig, SignalSpec

    protocol = ProtocolConfig(
        profile_name="test", header=b"", frame_id_size=2, frame_id_byte_order="little",
        length_size=1, length_meaning="payload", crc_type="none", crc_size=0,
        crc_byte_order="little", crc_coverage="header_to_payload", footer=b"",
        escape_mode="none", enabled=True
    )

    sig_spec = SignalSpec(
        frame_id=0x0100, frame_name="FrameA", signal_name="Cell_V1",
        start_byte=0, byte_length=2, endianness="little", data_type="uint16",
        scale=0.001, offset=0.0, unit="V", group="Cells"
    )

    calc = CalcGroupSpec(group="Cells", stat="avg", unit="", frame_id=0x0100)
    cfg = FrameConfig(
        protocol=protocol,
        frames={},
        signals_by_frame={0x0100: [sig_spec]},
        frame_names={0x0100: "FrameA"},
    )
    cfg.calc_groups = [calc]

    decoded_signals = [
        DecodedSignal(
            frame_id=0x0100, frame_name="FrameA", signal_name="Cell_V1",
            raw_value=4000, scaled_value=4.0, unit="V", status="ok", group="Cells"
        ),
        DecodedSignal(
            frame_id=0x0100, frame_name="FrameA", signal_name="Cell_V2",
            raw_value=4200, scaled_value=4.2, unit="V", status="ok", group="Cells"
        )
    ]

    state_dict = {}
    out = _calculate_groups(cfg, 0x0100, "FrameA", decoded_signals, state_dict)

    assert len(out) == 1
    calc_sig = out[0]
    assert calc_sig.unit == "V"
    assert calc_sig.display_value == "4.1 V"

