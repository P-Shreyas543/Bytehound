"""Sequence-counter gap detection (Plane.md F12)."""

from __future__ import annotations

import struct
import time
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from app.decoder.config_loader import ConfigError, load_config
from app.decoder.sequence import SequenceTracker
from app.decoder.types import SequenceCounterSpec
from app.protocol.packet_builder import build_packet
from app.protocol.packet_parser import ParsedPacket
from tools.hil import nucleo as hw


def _tracker(bits=8, step=1):
    return SequenceTracker({0x10: SequenceCounterSpec(0x10, "c", bits, step)})


def _kinds(tr, values, fid=0x10):
    return [(e.kind, e.missing) if (e := tr.observe(fid, v)) else None for v in values]


def test_in_order_values_and_wraparound_raise_nothing():
    tr = _tracker(bits=8)
    assert _kinds(tr, [250, 251, 252, 253, 254, 255, 0, 1, 2]) == [None] * 9
    assert tr.totals()["seq_missing"] == 0 and tr.stats[0x10].received == 9


def test_gap_counts_the_missing_frames_also_across_wrap():
    tr = _tracker(bits=8)
    assert _kinds(tr, [5, 9]) == [None, ("gap", 3)]
    # 9 -> 253 is more than half the 8-bit range back: a reset, not loss.
    # 253 -> 2 wraps forward: 254, 255, 0, 1 are missing.
    assert _kinds(tr, [253, 2]) == [("reset", 0), ("gap", 4)]
    assert tr.totals()["seq_missing"] == 3 + 4 and tr.totals()["seq_gaps"] == 2


def test_repeat_and_reset_are_not_counted_as_loss():
    tr = _tracker(bits=16)
    assert _kinds(tr, [100, 100, 3, 4]) == [None, ("repeat", 0), ("reset", 0), None]
    t = tr.totals()
    assert (t["seq_missing"], t["seq_repeats"], t["seq_resets"]) == (0, 1, 1)


def test_half_range_separates_gaps_from_resets():
    tr = _tracker(bits=8)                      # modulus 256, half = 128
    assert _kinds(tr, [0, 127]) == [None, ("gap", 126)]
    tr = _tracker(bits=8)
    assert _kinds(tr, [0, 128]) == [None, ("reset", 0)]


def test_step_and_32_bit_counters():
    tr = _tracker(bits=32, step=2)
    top = 0xFFFFFFFE
    assert _kinds(tr, [top - 2, top, 0, 6]) == [None, None, None, ("gap", 2)]
    assert tr.totals()["seq_missing_0x10"] == 2


def test_unknown_frame_is_ignored():
    assert _tracker().observe(0x99, 5) is None


# ------------------------------------------------------------------ loader

def _config_with(tmp_path, rows):
    folder = hw.hil_config_dir(tmp_path / "cfg")
    (folder / "sequence_counters.csv").write_text("id_or_address,signal_name,bits,step,enabled\n" + rows,
                                                   encoding="utf-8")
    return folder


def test_loader_reads_counters_with_defaults(tmp_path):
    cfg = load_config(_config_with(tmp_path, "0x4000,HIL Seq,,,TRUE\n"))
    spec = cfg.sequence_counters[0x4000]
    assert (spec.signal_name, spec.bits, spec.step) == ("HIL Seq", 32, 1)     # width from the uint32 signal


def test_config_without_the_table_has_no_counters():
    cfg = load_config(Path(__file__).resolve().parents[1] / "app" / "resources" / "config_template")
    assert cfg.sequence_counters == {}


@pytest.mark.parametrize("rows, message", [
    ("0x4000,Nope,,,TRUE\n", "has no signal"),
    ("0x4000,HIL Seq,,,TRUE\n0x4000,HIL Uptime,,,TRUE\n", "already has a counter"),
    ("0x4000,HIL Seq,65,,TRUE\n", "bits must be"),
    ("0x4000,HIL Seq,8,200,TRUE\n", "step must be"),
])
def test_loader_rejects_bad_counter_rows(tmp_path, rows, message):
    with pytest.raises(ConfigError, match=message):
        load_config(_config_with(tmp_path, rows))


def test_disabled_counter_row_is_ignored(tmp_path):
    assert load_config(_config_with(tmp_path, "0x4000,HIL Seq,,,FALSE\n")).sequence_counters == {}


# ------------------------------------------------------------------ worker + session

def test_worker_detects_gaps_reports_them_and_counts_them(tmp_path):
    from app.serial_io.serial_worker import PollingWorker, SerialSettings
    from app.serial_logging.session import SessionLog, SessionSettings, read_manifest

    cfg_dir = _config_with(tmp_path, "0x4000,HIL Seq,,,TRUE\n")
    config = load_config(cfg_dir)
    worker = PollingWorker(SerialSettings(port="x"), config.protocol, [], decode_config=config)
    warnings = []
    worker.warning_occurred.connect(warnings.append, Qt.ConnectionType.DirectConnection)
    session = SessionLog(tmp_path / "sess", config, SessionSettings(segment_seconds=3600), config_source=cfg_dir)
    session.start()
    worker.set_session_sink(session)
    seqs = [0, 1, 2, 5, 6, 6, 20, 2, 3]            # gap 3..4 (2), repeat 6, gap 7..19 (13), reset
    packets = []
    for s in seqs:
        raw = build_packet(config.protocol, 0x4000, struct.pack("<II", s, 0))
        packets.append(ParsedPacket(raw=raw, frame_id=0x4000, payload=raw[5:13], ok=True))
    worker._accumulate(packets, time.perf_counter())
    snap = worker.integrity_snapshot()
    assert (snap["seq_missing"], snap["seq_gaps"], snap["seq_repeats"], snap["seq_resets"]) == (15, 2, 1, 1)
    assert snap["seq_missing_0x4000"] == 15
    assert len(warnings) == 1 and "2 missing" in warnings[0]       # rate-limited to one per 10 s
    worker.set_session_sink(None)
    session.stop()
    assert session.await_finished(60)
    seg = read_manifest(tmp_path / "sess")["segments"][0]
    assert seg["sequence_events"] == 4
    rows = (tmp_path / "sess" / seg["files"]["sequence_csv"]).read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("time_utc,time_local,elapsed_ms,frame_id,kind,expected,received,missing")
    assert [r.split(",")[4:] for r in rows[1:]] == [
        ["gap", "3", "5", "2"], ["repeat", "7", "6", "0"], ["gap", "7", "20", "13"], ["reset", "21", "2", "0"]]
