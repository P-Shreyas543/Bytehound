"""Long-duration logging sessions: segments, manifest, fixed-step grid,
gaps, disk guard and crash recovery (Plane.md Part A, Part H, F9–F11)."""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from openpyxl import load_workbook

from app.decoder.config_loader import load_config
from app.decoder.frame_decoder import DecodedFrame, DecodedSignal, decode_frame
from app.serial_logging import decoded_logger as dl_mod
from app.serial_logging import session as session_mod
from app.serial_logging.session import (
    FixedStepSampler,
    SessionLog,
    SessionSettings,
    find_unfinished_sessions,
    read_manifest,
    recover_session,
)

TEMPLATE = Path(__file__).resolve().parents[1] / "app" / "resources" / "config_template"


@pytest.fixture(scope="module")
def config():
    return load_config(TEMPLATE)


class Clock:
    """Controllable wall + monotonic clocks."""

    def __init__(self) -> None:
        self.wall = 1_800_000_000.0
        self.perf = 5_000.0

    def advance(self, s: float) -> None:
        self.wall += s
        self.perf += s


class RawHooks:
    def __init__(self) -> None:
        self.started: List[Path] = []
        self.stopped = 0

    def start(self, path: Path, metadata: Dict[str, Any]) -> None:
        self.started.append(path)
        path.write_bytes(b"")  # the real worker creates the .bhraw file

    def stop(self) -> Optional[str]:
        self.stopped += 1
        return None


def _frames(config) -> List[DecodedFrame]:
    out = []
    for fid, f in config.frames.items():
        payload = bytes((i * 7 + fid) & 0xFF for i in range(f.payload_length))
        out.append(decode_frame(config, fid, payload, {}))
    return out


def _session(tmp_path, config, clock, **settings_kw) -> tuple[SessionLog, RawHooks]:
    hooks = RawHooks()
    s = SessionLog(
        tmp_path / "sess", config, SessionSettings(**settings_kw),
        config_source=TEMPLATE, metadata={"app": "test"}, app_version="9.9.9",
        raw_capture=hooks, clock=lambda: clock.wall, perf=lambda: clock.perf,
        disk_free=lambda p: 500 * 1024 ** 3,
    )
    return s, hooks


def _csv_rows(path: Path) -> List[List[str]]:
    with path.open(newline="", encoding="utf-8") as fp:
        return list(csv.reader(fp))


# ---------------------------------------------------------------------------
# Fixed-step sampler
# ---------------------------------------------------------------------------

def _sig(fid: int, name: str, value: float) -> DecodedFrame:
    return DecodedFrame(fid, "F", [DecodedSignal(fid, "F", name, value, value, "V", "ok")])


def _sampler(step=0.1, hold=True):
    cols = [((1, "a"), "a (V)"), ((2, "b"), "b (V)")]
    return FixedStepSampler(cols, step, 100.0, stale_steps=3, hold_stale=hold, wall_of=lambda t: 1e9 + t)


def test_sampler_rows_hold_newest_value_at_or_before_each_tick():
    s = _sampler()
    rows = s.feed(_sig(1, "a", 1.0), 100.05)       # tick 0 complete; a not seen yet
    assert [r[0] for r in rows] == [0] and rows[0][4:8] == ["", "", "", ""] and rows[0][-1] == 2
    rows = s.feed(_sig(1, "a", 2.0), 100.20)                         # completes 0.1 (and not 0.2)
    assert [r[0] for r in rows] == [1]
    assert rows[0][4:6] == [1.0, 50]                                  # a=1.0, 50 ms old at t=0.1
    rows = s.feed(_sig(2, "b", 7.0), 100.31)
    assert [r[0] for r in rows] == [2, 3]
    assert rows[0][4:6] == [2.0, 0]                                   # frame exactly at the tick counts
    assert rows[1][6:8] == ["", ""] and rows[1][-1] == 1             # b not yet seen → stale


def test_sampler_marks_and_optionally_blanks_stale_values():
    for hold, expect in ((True, 1.0), (False, "")):
        s = _sampler(hold=hold)
        s.feed(_sig(1, "a", 1.0), 100.0)
        rows = s.advance(100.5)                    # a is 500 ms old at t=0.5 > 3 steps
        last = rows[-1]
        assert last[0] == 5 and last[5] == 500
        assert last[4] == expect
        assert last[-1] == 2                       # a stale + b never seen


def test_sampler_catches_up_after_a_stall_without_skipping():
    s = _sampler()
    s.feed(_sig(1, "a", 1.0), 100.0)
    rows = s.feed(_sig(1, "a", 2.0), 160.0)        # GUI stalled for a minute
    assert [r[0] for r in rows] == list(range(0, 600))
    assert all(r[4] == 1.0 for r in rows)          # every row holds the value valid at its tick


def test_sampler_grid_does_not_drift_over_a_week():
    s = _sampler(step=0.1)
    n = 7 * 24 * 3600 * 10                          # one week of 0.1 s ticks
    assert abs(s.grid_time(n) - (100.0 + 604_800.0)) < 1e-6


# ---------------------------------------------------------------------------
# Session folder, segments and manifest
# ---------------------------------------------------------------------------

def test_session_rotates_segments_and_records_everything(tmp_path, config):
    clock = Clock()
    s, hooks = _session(tmp_path, config, clock, segment_seconds=60, fixed_step_s=1.0)
    s.start()
    frames = _frames(config)
    for _seg in range(3):
        for _ in range(30):                          # 30 s per loop, 2 loops per segment
            for f in frames:
                s.log_frame(f, clock.perf)
            clock.advance(1.0)
            s.tick()
        s.log_rejected(b"\xAA\x55\x01", 0x1000, "CRC mismatch", clock.perf)
        clock.advance(30.0)
        s.tick()
    s.stop()
    assert s.await_finished(30)

    m = read_manifest(tmp_path / "sess")
    assert m["status"] == "closed" and m["app_version"] == "9.9.9"
    assert m["config"]["files_sha256"] and (tmp_path / "sess" / "config" / "frames.csv").exists()
    segs = m["segments"]
    assert [x["index"] for x in segs] == list(range(1, len(segs) + 1)) and len(segs) >= 3
    assert all(x["status"] == "closed" for x in segs), segs
    assert [p.name for p in hooks.started] == [f"seg_{i:04d}.bhraw" for i in range(1, len(segs) + 1)]
    assert hooks.stopped == len(segs)
    folder = tmp_path / "sess"
    for x in segs:
        for name in ("event_csv", "event_xlsx", "fixed_csv", "fixed_xlsx"):
            assert (folder / x["files"][name]).exists()
        assert all(len(d) == 64 for d in x["sha256"].values())
    total_event = sum(x["rows"]["event"] for x in segs)
    assert total_event > 0
    assert sum(x.get("rejected_frames", 0) for x in segs) == 3
    first = _csv_rows(folder / segs[0]["files"]["event_csv"])
    assert first[0][:2] == ["time_utc", "time_local"]
    assert first[1][0].endswith("+00:00") and "T" in first[1][0]
    wb = load_workbook(folder / segs[0]["files"]["event_xlsx"], read_only=True)
    assert wb.sheetnames == ["Metadata", "Data"]
    wb.close()


def test_fixed_step_grid_is_continuous_across_segments(tmp_path, config):
    clock = Clock()
    s, _ = _session(tmp_path, config, clock, segment_seconds=10, fixed_step_s=0.5, event_log=False)
    s.start()
    frames = _frames(config)
    for _ in range(100):                             # 25 s of data at 4 Hz
        s.log_frame(frames[0], clock.perf)
        clock.advance(0.25)
        s.tick()
    clock.advance(2.0)
    s.tick()
    s.stop()
    assert s.await_finished(30)
    m = read_manifest(tmp_path / "sess")
    ticks: List[int] = []
    for x in m["segments"]:
        rows = _csv_rows(tmp_path / "sess" / x["files"]["fixed_csv"])
        ticks += [int(r[0]) for r in rows[1:]]
    assert len(m["segments"]) >= 3
    assert ticks == list(range(len(ticks)))          # no gaps, no repeats across rotations
    assert len(ticks) >= 50


def test_segments_rotate_before_the_xlsx_row_limit(tmp_path, config):
    clock = Clock()
    s, _ = _session(tmp_path, config, clock, segment_seconds=10_000, max_segment_rows=40)
    s.start()
    frames = _frames(config)
    for _ in range(100):
        for f in frames:
            s.log_frame(f, clock.perf)
        clock.advance(0.1)
        time.sleep(0.002)  # let the writer thread count the rows it wrote
        s.tick()
    s.stop()
    assert s.await_finished(30)
    segs = read_manifest(tmp_path / "sess")["segments"]
    assert len(segs) >= 2
    assert all(x["rows"]["event"] <= 40 + 10 for x in segs)  # rotation granularity: one tick


def test_connection_gap_closes_segment_and_session_continues(tmp_path, config):
    clock = Clock()
    s, hooks = _session(tmp_path, config, clock, fixed_step_s=1.0)
    s.start()
    f = _frames(config)[0]
    s.log_frame(f, clock.perf)
    clock.advance(5)
    s.tick()
    s.connection_lost("USB device disconnected")
    clock.advance(42)
    s.tick()                                          # no segment open: nothing written, no error
    s.connection_restored()
    s.log_frame(f, clock.perf)
    clock.advance(3)
    s.tick()
    s.stop()
    assert s.await_finished(30)
    m = read_manifest(tmp_path / "sess")
    assert len(m["segments"]) == 2
    assert m["gaps"][0]["reason"] == "USB device disconnected"
    assert m["gaps"][0]["seconds"] == 42.0
    rows = _csv_rows(tmp_path / "sess" / m["segments"][1]["files"]["fixed_csv"])
    stale_counts = [int(r[-1]) for r in rows[1:]]
    assert len(rows) - 1 >= 40                        # gap ticks are written, not skipped
    assert max(stale_counts) > 0                      # and marked stale


def test_disk_guard_warns_then_stops(tmp_path, config):
    clock = Clock()
    warnings: List[str] = []
    errors: List[str] = []
    free = {"bytes": 50 * 1024 ** 3}
    s = SessionLog(
        tmp_path / "sess", config, SessionSettings(), raw_capture=RawHooks(),
        on_warning=warnings.append, on_error=errors.append,
        clock=lambda: clock.wall, perf=lambda: clock.perf, disk_free=lambda p: free["bytes"],
    )
    s.start()
    s.tick()
    assert not warnings and not errors
    free["bytes"] = 5 * 1024 ** 3
    clock.advance(31)
    s.tick()
    assert len(warnings) == 1 and "getting full" in warnings[0]
    clock.advance(31)
    s.tick()
    assert len(warnings) == 1                          # warned once, not every check
    free["bytes"] = 1 * 1024 ** 3
    clock.advance(31)
    s.tick()
    assert s.stopped_for_disk and "Logging stopped" in errors[0]
    s.stop()
    assert s.await_finished(30)
    texts = [e["text"] for e in read_manifest(tmp_path / "sess")["events"]]
    assert any("low" in t for t in texts) and any("stopped" in t for t in texts)


def test_existing_session_is_never_overwritten(tmp_path, config):
    clock = Clock()
    s, _ = _session(tmp_path, config, clock)
    s.start()
    s.stop()
    assert s.await_finished(30)
    again, _ = _session(tmp_path, config, clock)
    with pytest.raises(FileExistsError):
        again.start()


def test_recovery_after_a_crash_keeps_all_rows(tmp_path, config, monkeypatch):
    clock = Clock()
    s, _ = _session(tmp_path, config, clock, fixed_step_s=1.0)
    s.start()
    frames = _frames(config)
    for _ in range(20):
        for f in frames:
            s.log_frame(f, clock.perf)
        clock.advance(1.0)
        s.tick()
    # Simulate the process dying: writers flush their temp CSVs but nothing
    # is compiled and the manifest still says "recording".
    monkeypatch.setattr(dl_mod, "finalize_temp_log", lambda *a, **k: None)
    monkeypatch.setattr(session_mod, "finalize_temp_log", lambda *a, **k: None)
    seg = s._segment
    seg.event.close(timeout=30)
    seg.fixed.close()
    seg.fixed.join(30)
    event_rows = seg.event.rows_written
    fixed_rows = seg.fixed.rows_written
    monkeypatch.undo()

    folder = tmp_path / "sess"
    assert read_manifest(folder)["status"] == "recording"
    assert find_unfinished_sessions(tmp_path) == [folder]
    assert recover_session(folder)
    m = read_manifest(folder)
    assert m["status"] == "recovered" and m["segments"][0]["status"] == "recovered"
    assert len(_csv_rows(folder / "seg_0001_event.csv")) - 1 == event_rows
    assert len(_csv_rows(folder / "seg_0001_fixed.csv")) - 1 == fixed_rows
    assert (folder / "seg_0001_event.xlsx").exists() and (folder / "seg_0001_fixed.xlsx").exists()
    assert not list(folder.glob("*.tmp_data"))
    assert find_unfinished_sessions(tmp_path) == []
    assert recover_session(folder) is False            # idempotent
    json.loads((folder / "session.json").read_text(encoding="utf-8"))
