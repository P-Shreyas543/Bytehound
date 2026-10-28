"""Expected frame rate (next version, owner request 2026-10-23): Frames
``expected_period_ms`` — one Activity Log line when a frame stops or slows
down and one when it is back, and sharper stale marking in the live plot."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.decoder import canonical
from app.decoder.config_loader import ConfigError, load_config, read_source_tables
from app.decoder.rate_monitor import FrameRateMonitor

TEMPLATE = Path(__file__).resolve().parents[1] / "app" / "resources" / "config_template"


def _doc(period):
    tables, _ = read_source_tables(TEMPLATE)
    doc = canonical.tables_to_canonical(tables)
    for row in doc["tables"]["frames"]:
        row["expected_period_ms"] = period if str(row["frame_id"]).lower() == "0x1000" else ""
    return doc


def _feed(m, start, stop, period, fid=0x1000):
    t = start
    while t < stop - 1e-9:
        m.note(fid, t)
        t += period
    return t - period


def test_the_column_loads_and_round_trips(tmp_path):
    cfg = load_config(_doc(200))
    assert cfg.frames[0x1000].expected_period_ms == 200.0
    assert all(f.expected_period_ms is None for fid, f in cfg.frames.items() if fid != 0x1000)
    for target in (tmp_path / "c.json", tmp_path / "c.xlsx", tmp_path / "csv"):
        canonical.export(_doc(200), target)
        assert load_config(target).frames[0x1000].expected_period_ms == 200.0, target
    assert all(f.expected_period_ms is None for f in load_config(TEMPLATE).frames.values())
    with pytest.raises(ConfigError, match="not a number"):
        load_config(_doc("fast"))
    with pytest.raises(ConfigError, match="1..3600000"):
        load_config(_doc(0))


def test_a_frame_on_time_is_never_reported():
    m = FrameRateMonitor({0x1000: 0.2}, {0x1000: "BMS"})
    t = 0.0
    while t < 60:
        m.note(0x1000, t)
        assert m.check(t + 0.05) == []
        t += 0.2


def test_a_stopped_frame_is_reported_once_and_again_when_back():
    m = FrameRateMonitor({0x1000: 0.2}, {0x1000: "BMS"})
    last = _feed(m, 0, 20, 0.2)
    assert m.check(last + 0.5) == []                               # 2.5 periods: not yet
    (fid, state, msg), = m.check(last + 0.7)
    assert (fid, state) == (0x1000, "late") and msg.startswith("0x1000 BMS: no frame for 0.7 s")
    assert "expected every 200 ms" in msg
    for k in range(1, 100):                                        # a long outage: no repeats
        assert m.check(last + 0.7 + k) == []
    m.note(0x1000, last + 120)
    assert m.check(last + 120.05) == [(0x1000, "ok", "0x1000 BMS: arriving again")]


def test_a_slow_frame_is_reported_and_its_recovery():
    m = FrameRateMonitor({0x1000: 0.2})
    last = _feed(m, 0, 15, 0.2)
    last = _feed(m, last + 0.5, last + 15, 0.5)                    # now every 500 ms
    (_, state, msg), = m.check(last + 0.1)
    assert state == "slow" and "arriving every 500 ms (expected every 200 ms)" in msg
    last = _feed(m, last + 0.2, last + 15, 0.2)
    (_, state, msg), = m.check(last + 0.1)
    assert state == "ok" and "back to the expected rate (200 ms)" in msg


def test_frames_without_a_period_or_never_seen_are_not_watched():
    m = FrameRateMonitor({0x1000: 0.2, 0x2000: 0.1})
    m.note(0x3000, 0.0)                                            # no expected period
    assert m.check(100.0) == []                                    # 0x2000 never arrived
    m.note(0x1000, 0.0)
    m.reset()                                                      # disconnect
    assert m.check(100.0) == []
    assert not FrameRateMonitor({}) and FrameRateMonitor.from_config(load_config(_doc(100)))


def test_the_plot_marks_stale_after_three_expected_periods():
    from app.ui.plot_orchestration import PlotOrchestrationMixin

    class Buf:
        _dt = 0.2

        def __len__(self):
            return 1

        def last_x(self):
            return 10.0

    stale = PlotOrchestrationMixin._signal_staleness
    assert stale(Buf(), 10.7)[0] is False                          # usual rule: 5 x 0.2 = 1 s
    m = FrameRateMonitor({0x1000: 0.2})
    assert stale(Buf(), 10.7, m.late_after_s(0x1000))[0] is True   # expected: 3 x 0.2 = 0.6 s
