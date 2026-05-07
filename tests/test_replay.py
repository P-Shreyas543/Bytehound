"""Tests for `app.serial_io.replay_source` and end-to-end replay decoding."""

from __future__ import annotations

from app.decoder.frame_decoder import decode_frame
from app.protocol.packet_parser import create_parser, FramedParser
from app.serial_io.replay_source import parse_log_file, replay_bytes
from tests.conftest import (
    CANONICAL_FRAME_HEX,
    CANONICAL_FRAME_ID,
    hex_to_bytes,
)


def test_parse_bundled_sample_log(resources_dir):
    rows, errors = parse_log_file(resources_dir / "sample_raw_log.txt")
    assert errors == []
    assert len(rows) == 1
    row = rows[0]
    assert row.direction == "RX"
    assert row.raw_bytes == hex_to_bytes(CANONICAL_FRAME_HEX)


def test_replay_filters_by_direction():
    # Inline log content with both RX and TX rows.
    rows, errors = _parse_inline(
        "2026-05-04 10:00:00.000, RX, AA 55 00 10 04 0F A0 0B B8 BE 70\n"
        "2026-05-04 10:00:01.000, TX, AA 55 00 50 00 12 34\n"
    )
    assert errors == []
    rx_only = list(replay_bytes(rows))
    assert len(rx_only) == 1
    both = list(replay_bytes(rows, directions=("RX", "TX")))
    assert len(both) == 2


def test_offline_replay_full_pipeline(resources_dir, config):
    rows, errors = parse_log_file(resources_dir / "sample_raw_log.txt")
    assert errors == []
    parser = create_parser(config.protocol)
    for chunk in replay_bytes(rows):
        parser.feed(chunk)
    packets = parser.extract_all()
    assert len(packets) == 1 and packets[0].ok

    decoded = decode_frame(config, packets[0].frame_id, packets[0].payload)
    assert decoded.error is None
    assert {s.signal_name for s in decoded.signals} == {
        "Cell Voltage 1", "Cell Voltage 2"
    }
    s_by_name = {s.signal_name: s for s in decoded.signals}
    assert s_by_name["Cell Voltage 1"].scaled_value == 4.0
    assert s_by_name["Cell Voltage 2"].scaled_value == 3.0


def test_parse_csv_format_with_header(tmp_path):
    log = tmp_path / "session.csv"
    log.write_text(
        "timestamp,direction,hex\n"
        "2026-05-04 10:00:00.000,RX,AA 55 00 10 04 0F A0 0B B8 BE 70\n"
        "2026-05-04 10:00:01.000,TX,AA 55 00 50 00 12 34\n",
        encoding="utf-8",
    )
    rows, errors = parse_log_file(log)
    assert errors == []
    assert len(rows) == 2
    assert rows[0].direction == "RX"
    assert rows[1].direction == "TX"


def test_skipped_lines_are_reported(tmp_path):
    log = tmp_path / "broken.log"
    log.write_text(
        "2026-05-04 10:00:00.000, RX, GG GG\n"          # invalid hex
        "this is not a valid line\n"                     # not 3 commas
        "2026-05-04 10:00:01.000, RX, AA 55\n",          # ok
        encoding="utf-8",
    )
    rows, errors = parse_log_file(log)
    assert len(rows) == 1
    assert len(errors) == 2


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _parse_inline(content: str):
    """Round-trip the inline content through parse_log_file via tmp file.

    Implemented inline (not a fixture) to keep the test single-purpose.
    """
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".log", delete=False
    ) as fp:
        fp.write(content)
        path = Path(fp.name)
    try:
        return parse_log_file(path)
    finally:
        path.unlink(missing_ok=True)
