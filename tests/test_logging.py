from __future__ import annotations

from datetime import datetime

from app.decoder.frame_decoder import decode_frame
from app.decoder.template_io import snapshot_config
from app.serial_logging.decoded_logger import DecodedLogger
from app.serial_logging.raw_logger import RawLogger
from tests.conftest import CANONICAL_FRAME_ID, CANONICAL_PAYLOAD_HEX, hex_to_bytes


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


def test_decoded_logger_writes_signal_and_calculation_rows(config, tmp_path):
    decoded = decode_frame(config, CANONICAL_FRAME_ID, hex_to_bytes(CANONICAL_PAYLOAD_HEX))
    path = tmp_path / "decoded.csv"
    with DecodedLogger(path) as logger:
        logger.log_frame(1, decoded, datetime(2026, 5, 4, 12, 37, 37, 125000))
    text = path.read_text(encoding="utf-8")
    assert "Cell Voltage 1" in text
    assert "Cells avg" in text


def test_snapshot_config_copies_csv_templates(resources_dir, tmp_path):
    snapshot = snapshot_config(resources_dir / "config_template", tmp_path)
    assert snapshot.is_dir()
    assert (snapshot / "variables.csv").exists()
