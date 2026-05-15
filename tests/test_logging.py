from __future__ import annotations

from datetime import datetime

from openpyxl import load_workbook

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
    path = tmp_path / "decoded.xlsx"

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

    # Cycle 1: both frames arrive (FrameB is the trigger as the last in config).
    # Cycle 2: only FrameA arrives → trigger never fires → no row emitted.
    # Cycle 3: both frames again → second row emitted.
    with DecodedLogger(path, config) as logger:
        logger.log_frame(frame_a, 1000)
        logger.log_frame(frame_b, 1100)
        logger.log_frame(frame_a, 2000)
        logger.log_frame(frame_a, 3000)
        logger.log_frame(frame_b, 3100)

    wb = load_workbook(path, read_only=True)
    assert wb.sheetnames == [DecodedLogger.METADATA_SHEET, DecodedLogger.DATA_SHEET]
    data_rows = list(wb[DecodedLogger.DATA_SHEET].iter_rows(values_only=True))
    wb.close()

    expected_header = (
        "FrameA.elapsed_ms",
        "FrameA.frame_id",
        "FrameA.Cell_V1 (V)",
        "FrameA.Pack_I",
        "FrameA.Cells avg (V)",
        "FrameB.elapsed_ms",
        "FrameB.frame_id",
        "FrameB.Pack_V (V)",
    )
    assert data_rows[0] == expected_header
    # Only two complete cycles → two data rows.
    assert len(data_rows) == 3

    header = list(expected_header)
    row1 = dict(zip(header, data_rows[1]))
    assert row1["FrameA.elapsed_ms"] == 1000
    assert row1["FrameA.frame_id"] == "0x0100"
    assert row1["FrameA.Cell_V1 (V)"] == 3.85
    assert row1["FrameA.Pack_I"] == 12.1
    assert row1["FrameA.Cells avg (V)"] == 3.9
    assert row1["FrameB.elapsed_ms"] == 1100
    assert row1["FrameB.frame_id"] == "0x0200"
    assert row1["FrameB.Pack_V (V)"] == 48.2

    # Second cycle uses the LATEST FrameA seen before the trigger (elapsed=3000),
    # not the orphaned A at elapsed=2000 — buffer always keeps the freshest values.
    row2 = dict(zip(header, data_rows[2]))
    assert row2["FrameA.elapsed_ms"] == 3000
    assert row2["FrameB.elapsed_ms"] == 3100


def test_decoded_logger_writes_metadata_sheet(tmp_path):
    config = _make_test_config()
    path = tmp_path / "decoded.xlsx"
    metadata = {
        "app": "Bytehound",
        "app_version": "0.2.0",
        "baud_rate": "115200",
        "serial_port": "COM9",
        "logging_mode": "Raw + Decoded",
        "session_started": "2026-05-15 11:23:52",
    }

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

    with DecodedLogger(path, config, metadata=metadata) as logger:
        logger.log_frame(frame, 1000, datetime(2026, 5, 4, 12, 37, 37, 125000))

    wb = load_workbook(path, read_only=True)
    meta_rows = list(wb[DecodedLogger.METADATA_SHEET].iter_rows(values_only=True))
    wb.close()

    assert meta_rows[0] == ("Key", "Value")
    meta_pairs = dict(meta_rows[1:])
    for key, value in metadata.items():
        assert meta_pairs[key] == value


def test_decoded_logger_drops_incomplete_cycles(tmp_path):
    """Only FrameA arrives, never FrameB (the trigger). No data rows."""
    config = _make_test_config()
    path = tmp_path / "decoded.xlsx"

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
            )
        ],
    )

    with DecodedLogger(path, config) as logger:
        logger.log_frame(frame_a, 1000)
        logger.log_frame(frame_a, 2000)
        logger.log_frame(frame_a, 3000)

    wb = load_workbook(path, read_only=True)
    data_rows = list(wb[DecodedLogger.DATA_SHEET].iter_rows(values_only=True))
    wb.close()

    # Only the header row — no completed cycles.
    assert len(data_rows) == 1


def test_snapshot_config_copies_csv_templates(resources_dir, tmp_path):
    snapshot = snapshot_config(resources_dir / "config_template", tmp_path)
    assert snapshot.is_dir()
    assert (snapshot / "variables.csv").exists()
