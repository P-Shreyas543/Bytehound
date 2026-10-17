"""Session analysis (Plane.md Part B): every result is checked against brute
force over the full-resolution CSV data."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.decoder.config_loader import load_config
from app.decoder.frame_decoder import decode_frame
from app.serial_logging import session_analysis as sa
from app.serial_logging.session import SessionLog, SessionSettings, read_manifest
from app.serial_logging.session_analysis import SessionSource, build_segment_cache

TEMPLATE = Path(__file__).resolve().parents[1] / "app" / "resources" / "config_template"


class Clock:
    def __init__(self) -> None:
        self.wall = 1_800_000_000.0
        self.perf = 1_000.0

    def advance(self, s: float) -> None:
        self.wall += s
        self.perf += s


class RawHooks:
    def start(self, path, metadata):
        path.write_bytes(b"")

    def stop(self):
        return None


@pytest.fixture(scope="module")
def session(tmp_path_factory):
    """~40 minutes of 2 Hz cycles over 8 five-minute segments, with a
    90-second disconnect gap and a few spikes."""
    config = load_config(TEMPLATE)
    folder = tmp_path_factory.mktemp("sa") / "sess"
    clock = Clock()
    s = SessionLog(folder, config, SessionSettings(segment_seconds=300, fixed_step_s=1.0),
                   raw_capture=RawHooks(), clock=lambda: clock.wall, perf=lambda: clock.perf,
                   disk_free=lambda p: 1 << 40)
    s.start()
    rng = np.random.default_rng(7)
    for i in range(4800):
        if i == 2400:
            s.connection_lost("unplugged")
            clock.advance(90.0)
            s.tick()
            s.connection_restored()
        for fid, f in config.frames.items():
            base = (i // 3 + fid) & 0xFF
            spike = 0xFF if i % 997 == 0 else base
            payload = bytes((spike if k == 0 else int(rng.integers(0, 256))) for k in range(f.payload_length))
            s.log_frame(decode_frame(config, fid, payload, {}), clock.perf)
        clock.advance(0.5)
        s.tick()
    s.stop()
    assert s.await_finished(120)
    src = SessionSource(folder)
    src.ensure_caches()
    return src


def _truth(src: SessionSource, param: str):
    """All rows of all event CSVs: (t, y) as the cache should hold them."""
    ts, ys = [], []
    for seg in src.segments:
        df = pd.read_csv(seg.csv, low_memory=False)
        t = (pd.to_datetime(df["time_utc"], utc=True, format="ISO8601").astype("int64") / 1e9
             - src.start_epoch).to_numpy()
        ts.append(t)
        ys.append(pd.to_numeric(df[param], errors="coerce").to_numpy(dtype=float))
    t = np.concatenate(ts)
    y = np.concatenate(ys)
    order = np.argsort(t, kind="stable")
    return t[order], y[order]


def _param(src):
    return next(p for p in src.signals() if p.startswith("0x1000."))


def test_caches_cover_every_segment_and_signal(session):
    src = session
    assert len(src.segments) >= 8
    assert not src.missing_caches()
    assert len(src.signals()) >= 5
    assert src.gaps and src.gaps[0][1] - src.gaps[0][0] == pytest.approx(90.0, abs=0.01)


def test_full_resolution_window_equals_the_csv_rows(session):
    src = session
    p = _param(src)
    t, y = _truth(src, p)
    w = src.window([p], 100.0, 400.0)
    assert w.level == 0
    ok = ~np.isnan(w.x)
    sel = (t >= 100.0) & (t <= 400.0)
    inside = (w.x[ok] >= 100.0) & (w.x[ok] <= 400.0)
    np.testing.assert_allclose(w.x[ok][inside], t[sel])
    np.testing.assert_allclose(w.y[p][ok][inside], y[sel], equal_nan=True)


def test_envelope_keeps_every_bucket_min_and_max(session):
    src = session
    p = _param(src)
    t, y = _truth(src, p)
    w = src.window([p], 0.0, src.duration, level=10)
    assert w.level == 10
    b = np.floor(t / 10).astype(int)
    env = w.y[p]
    xs = w.x
    for bucket in np.unique(b)[::7]:
        vals = y[b == bucket]
        vals = vals[~np.isnan(vals)]
        if not vals.size:
            continue
        i = int(np.nonzero(np.isclose(xs, bucket * 10 + 2.5))[0][0])
        assert env[i] == pytest.approx(vals.min())
        assert env[i + 1] == pytest.approx(vals.max())
    assert np.nanmax(env) == pytest.approx(np.nanmax(y))   # spikes are not averaged away


def test_gap_is_drawn_as_a_gap(session):
    src = session
    p = _param(src)
    g0, g1 = src.gaps[0]
    for level in (0, 10):
        w = src.window([p], g0 - 60, g1 + 60, level=level)
        inside = np.nonzero((w.x > g0 + 1) & (w.x < g1 - 1))[0]
        assert inside.size == 0                     # no samples inside the gap
        assert np.isnan(w.x).any()                  # and the line is broken there
    assert math.isnan(src.value_at(p, (g0 + g1) / 2))


@pytest.mark.parametrize("force_aggregates", [False, True])
def test_stats_match_brute_force(session, monkeypatch, force_aggregates):
    src = session
    if force_aggregates:
        monkeypatch.setattr(sa, "FULL_RES_LIMIT", 10)   # take the bucket-aggregate path
    p = _param(src)
    t, y = _truth(src, p)
    for t0, t1 in [(0.0, src.duration), (37.3, 1801.9), (205.0, 207.0)]:
        sel = (t >= t0) & (t <= t1) & ~np.isnan(y)
        v = y[sel]
        st = src.stats(p, t0, t1)
        assert st.n == v.size
        assert st.min == pytest.approx(v.min()) and st.max == pytest.approx(v.max())
        assert st.mean == pytest.approx(v.mean(), rel=1e-12)
        assert st.std == pytest.approx(v.std(), rel=1e-9)
        if st.approx_percentiles:
            spread = v.max() - v.min()
            assert abs(st.median - np.median(v)) <= 0.05 * spread
        else:
            assert st.median == pytest.approx(np.median(v))
            assert st.p5 == pytest.approx(np.percentile(v, 5))
        assert st.approx_percentiles == (force_aggregates and v.size > 10 and t1 - t0 > 20)


def test_value_at_is_full_resolution(session):
    src = session
    p = _param(src)
    t, y = _truth(src, p)
    ok = ~np.isnan(y)
    for q in (12.25, 777.7, 1500.0):
        assert src.value_at(p, q) == pytest.approx(np.interp(q, t[ok], y[ok]))
    assert math.isnan(src.value_at(p, -5.0))


def test_export_range_writes_every_row(session, tmp_path):
    src = session
    p = _param(src)
    t, y = _truth(src, p)
    out = tmp_path / "range.csv"
    n = src.export_range([p], 300.0, 900.0, out, xlsx=True)
    df = pd.read_csv(out)
    assert n == len(df) == int(((t >= 300.0) & (t <= 900.0)).sum())
    np.testing.assert_allclose(df[p].to_numpy(), y[(t >= 300.0) & (t <= 900.0)], equal_nan=True)
    assert out.with_suffix(".xlsx").exists()


def test_fixed_step_logs_are_readable_too(session):
    src = SessionSource(session.folder, kind="fixed")
    src.ensure_caches()
    p = next(x for x in src.signals() if x.startswith("0x1000."))
    w = src.window([p], 0, src.duration, level=0)
    ok = ~np.isnan(w.x)
    steps = np.diff(w.x[ok])
    assert np.allclose(steps[steps < 5], 1.0)      # the grid is exactly 1 s


def test_cache_build_is_atomic_and_repeatable(session, tmp_path):
    seg = session.segments[0]
    out = tmp_path / "again.npz"
    build_segment_cache(seg.csv, session.start_epoch, out)
    with np.load(out, allow_pickle=True) as a, np.load(seg.cache, allow_pickle=True) as b:
        assert sorted(a.files) == sorted(b.files)
        np.testing.assert_array_equal(a["t"], b["t"])
    assert not list(tmp_path.glob("*.partial"))
    assert read_manifest(session.folder)["status"] == "closed"


def test_summary_extends_incrementally_to_the_same_result(session, tmp_path):
    """A live session grows: extending the saved summary with new segments
    must give exactly what a full rebuild gives."""
    import shutil

    folder = tmp_path / "copy"
    shutil.copytree(session.folder, folder)
    (folder / "event_summary.npz").unlink(missing_ok=True)
    full = SessionSource(folder)
    full.ensure_summary()
    want = dict(full._summary)

    (folder / "event_summary.npz").unlink()
    part = SessionSource(folder)
    keep = part.segments[:3]
    part.segments, rest = keep, part.segments[3:]
    part.ensure_summary()                      # summary of the first 3 segments
    grown = SessionSource(folder)              # all segments: extends, not rebuilds
    grown.ensure_summary()
    assert [int(i) for i in grown._summary["segments"]] == [s.index for s in keep + rest]
    for key, arr in want.items():
        got = grown._summary[key]
        if arr.dtype == object:
            assert list(got) == list(arr), key
        else:
            np.testing.assert_allclose(got, arr, rtol=1e-12, atol=1e-12, equal_nan=True, err_msg=key)
