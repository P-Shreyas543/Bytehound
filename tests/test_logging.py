from __future__ import annotations

import csv
from datetime import datetime

import pytest

from app.decoder.frame_decoder import DecodedFrame, DecodedSignal
from app.decoder.template_io import snapshot_config
from app.decoder.types import CalcGroupSpec, FrameConfig, FrameDefinition, SignalSpec
from app.serial_logging.decoded_logger import DecodedLogger
from app.serial_logging.raw_logger import RawLogger
from tests.conftest import dummy_protocol_config


def test_raw_logger_writes_csv_with_header(tmp_path):
    path = tmp_path / "raw.csv"
    with RawLogger(path) as logger:
        logger.log(
            "RX",
            bytes.fromhex("AA550010040FA00BB8BE70"),
            datetime(2026, 5, 4, 12, 37, 37, 125000),
        )
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "timestamp,direction,hex,delta_t_ms"
    assert lines[1] == "2026-05-04 12:37:37.125,RX,AA 55 00 10 04 0F A0 0B B8 BE 70,0.0"


def test_raw_logger_appends_without_duplicating_header(tmp_path):
    path = tmp_path / "raw.csv"
    ts = datetime(2026, 5, 4, 12, 37, 37, 125000)
    with RawLogger(path) as logger:
        logger.log("RX", bytes.fromhex("AA55"), ts)
    with RawLogger(path) as logger:
        logger.log("TX", bytes.fromhex("BBCC"), ts)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "timestamp,direction,hex,delta_t_ms"
    assert sum(1 for line in lines if line.startswith("timestamp,")) == 1
    assert len(lines) == 3


def _make_test_config(signal_b_name: str = "Pack_V") -> FrameConfig:
    protocol = dummy_protocol_config()
    frame_a = FrameDefinition(frame_id=0x0100, frame_name="FrameA")
    frame_b = FrameDefinition(frame_id=0x0200, frame_name="FrameB")

    signals_a = [
        SignalSpec(
            frame_id=0x0100,
            frame_name="FrameA",
            signal_name="Cell_V1",
            start_byte=0,
            byte_length=2,
            endianness="little",
            data_type="uint16",
            scale=0.001,
            offset=0.0,
            unit="V",
            group="Cells",
        ),
        SignalSpec(
            frame_id=0x0100,
            frame_name="FrameA",
            signal_name="Pack_I",
            start_byte=2,
            byte_length=2,
            endianness="little",
            data_type="int16",
            scale=0.1,
            offset=0.0,
            unit="",
        ),
    ]
    signals_b = [
        SignalSpec(
            frame_id=0x0200,
            frame_name="FrameB",
            signal_name=signal_b_name,
            start_byte=0,
            byte_length=2,
            endianness="little",
            data_type="uint16",
            scale=0.1,
            offset=0.0,
            unit="V",
        )
    ]

    return FrameConfig(
        protocol=protocol,
        frames={0x0100: frame_a, 0x0200: frame_b},
        signals_by_frame={0x0100: signals_a, 0x0200: signals_b},
        frame_names={0x0100: "FrameA", 0x0200: "FrameB"},
        calc_groups=[
            CalcGroupSpec(group="Cells", stat="avg", unit="V", frame_id=0x0100)
        ],
    )


def test_decoded_logger_writes_wide_rows(tmp_path):
    config = _make_test_config()
    path = tmp_path / "decoded.csv"

    frame_a = DecodedFrame(
        frame_id=0x0100,
        frame_name="FrameA",
        signals=[
            DecodedSignal(
                frame_id=0x0100,
                frame_name="FrameA",
                signal_name="Cell_V1",
                raw_value=3850,
                scaled_value=3.85,
                unit="V",
                status="ok",
                group="Cells",
            ),
            DecodedSignal(
                frame_id=0x0100,
                frame_name="FrameA",
                signal_name="Pack_I",
                raw_value=121,
                scaled_value=12.1,
                unit="",
                status="ok",
            ),
        ],
        calculations=[
            DecodedSignal(
                frame_id=0x0100,
                frame_name="FrameA",
                signal_name="Cells avg",
                raw_value=None,
                scaled_value=3.9,
                unit="V",
                status="ok",
                group="Cells",
                display_value="3.9",
                is_calculated=True,
            )
        ],
    )

    frame_b = DecodedFrame(
        frame_id=0x0200,
        frame_name="FrameB",
        signals=[
            DecodedSignal(
                frame_id=0x0200,
                frame_name="FrameB",
                signal_name="Pack_V",
                raw_value=482,
                scaled_value=48.2,
                unit="V",
                status="ok",
            )
        ],
    )

    with DecodedLogger(path, config) as logger:
        logger.log_frame(frame_a, 1000, datetime(2026, 5, 4, 12, 37, 37, 125000))
        logger.log_frame(frame_b, 1100, datetime(2026, 5, 4, 12, 37, 38, 125000))

    with path.open("r", encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        rows = list(reader)

    expected_header = [
        "timestamp",
        "elapsed_ms",
        "Cell_V1 (V)",
        "Pack_I",
        "Pack_V (V)",
        "Cells avg (V)",
    ]
    assert reader.fieldnames == expected_header

    row1 = rows[0]
    assert row1["elapsed_ms"] == "1000"
    assert row1["Cell_V1 (V)"] == "3.85"
    assert row1["Pack_I"] == "12.1"
    assert row1["Pack_V (V)"] == ""
    assert row1["Cells avg (V)"] == "3.9"

    row2 = rows[1]
    assert row2["elapsed_ms"] == "1100"
    assert row2["Cell_V1 (V)"] == ""
    assert row2["Pack_I"] == ""
    assert row2["Pack_V (V)"] == "48.2"
    assert row2["Cells avg (V)"] == ""


def test_decoded_logger_append_and_mismatch(tmp_path):
    config = _make_test_config()
    path = tmp_path / "decoded.csv"

    frame = DecodedFrame(
        frame_id=0x0100,
        frame_name="FrameA",
        signals=[
            DecodedSignal(
                frame_id=0x0100,
                frame_name="FrameA",
                signal_name="Cell_V1",
                raw_value=3850,
                scaled_value=3.85,
                unit="V",
                status="ok",
                group="Cells",
            )
        ],
    )

    with DecodedLogger(path, config) as logger:
        logger.log_frame(frame, 1000, datetime(2026, 5, 4, 12, 37, 37, 125000))
    with DecodedLogger(path, config) as logger:
        logger.log_frame(frame, 1100, datetime(2026, 5, 4, 12, 37, 38, 125000))

    lines = path.read_text(encoding="utf-8").splitlines()
    assert sum(1 for line in lines if line.startswith("timestamp,")) == 1

    mismatched = _make_test_config(signal_b_name="Pack_V2")
    with pytest.raises(ValueError):
        with DecodedLogger(path, mismatched) as logger:
            logger.open()


def test_snapshot_config_copies_csv_templates(resources_dir, tmp_path):
    snapshot = snapshot_config(resources_dir / "config_template", tmp_path)
    assert snapshot.is_dir()
    assert (snapshot / "variables.csv").exists()
