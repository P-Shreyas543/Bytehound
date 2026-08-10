"""Tests for the live-plot history buffer (``TimeSeriesBuffer``).

The class lives in ``app.ui.plot_panel`` and replaces the old fixed-capacity
ring buffer with append-only chunked storage so long sessions retain every
sample. Tests cover: ordering, arrays_since() slicing, the optional soft
cap that drops oldest chunks, and the legacy ``_RingBuffer`` alias still
imports cleanly.
"""

from __future__ import annotations

import numpy as np

from app.ui.plot_panel import TimeSeriesBuffer, _RingBuffer


def test_alias_resolves_to_time_series_buffer():
    # External callers still importing ``_RingBuffer`` get TimeSeriesBuffer.
    assert _RingBuffer is TimeSeriesBuffer


def test_empty_buffer_has_no_first_or_last_x():
    buf = TimeSeriesBuffer()
    assert len(buf) == 0
    assert not buf
    assert buf.first_x() is None
    assert buf.last_x() is None
    xs, ys = buf.arrays()
    assert xs.size == 0
    assert ys.size == 0


def test_append_retains_all_samples_when_unbounded():
    buf = TimeSeriesBuffer()
    # Exceed one full chunk so the seal + new-chunk path runs.
    n = TimeSeriesBuffer.CHUNK_SIZE + 100
    for i in range(n):
        buf.append(float(i), float(i) * 2)
    assert len(buf) == n
    assert buf.first_x() == 0.0
    assert buf.last_x() == float(n - 1)
    xs, ys = buf.arrays()
    assert list(xs[:3]) == [0.0, 1.0, 2.0]
    assert list(xs[-3:]) == [float(n - 3), float(n - 2), float(n - 1)]
    # Y values stay paired with their X values across chunk boundaries.
    assert list(ys[:3]) == [0.0, 2.0, 4.0]
    assert list(ys[-3:]) == [float((n - 3) * 2), float((n - 2) * 2), float((n - 1) * 2)]


def test_partial_chunk_arrays_returns_zero_copy_view():
    """Pre-seal, arrays() returns a slice that shares storage."""
    buf = TimeSeriesBuffer()
    for i in range(5):
        buf.append(float(i), float(i))
    xs, ys = buf.arrays()
    assert list(xs) == [0.0, 1.0, 2.0, 3.0, 4.0]
    # Pure-partial path: numpy slice → has a base.
    assert xs.base is not None
    assert ys.base is not None


def test_clear_resets_state():
    buf = TimeSeriesBuffer()
    for i in range(10):
        buf.append(float(i), float(i))
    buf.clear()
    assert len(buf) == 0
    assert buf.first_x() is None
    assert buf.last_x() is None
    # Re-using after clear must work cleanly — no leftover samples.
    buf.append(100.0, 200.0)
    xs, ys = buf.arrays()
    assert list(xs) == [100.0]
    assert list(ys) == [200.0]


def test_arrays_since_returns_window_only():
    buf = TimeSeriesBuffer()
    for i in range(10):
        buf.append(float(i), float(i) * 10)
    xs, ys = buf.arrays_since(4.0)
    # Includes the preceding sample (3.0) to prevent visual gaps.
    assert list(xs) == [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
    assert list(ys) == [30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0]


def test_arrays_since_none_returns_full_series():
    buf = TimeSeriesBuffer()
    for i in range(5):
        buf.append(float(i), float(i))
    xs, _ = buf.arrays_since(None)
    assert list(xs) == [0.0, 1.0, 2.0, 3.0, 4.0]


def test_arrays_since_skips_old_chunks():
    """Window past every frozen chunk's last x → only touches partial chunk."""
    buf = TimeSeriesBuffer()
    # Two full chunks + a partial third.
    chunk = TimeSeriesBuffer.CHUNK_SIZE
    for i in range(2 * chunk + 50):
        buf.append(float(i), float(i))
    # Pick t_min inside the partial (third) chunk.
    t_min = float(2 * chunk + 10)
    xs, ys = buf.arrays_since(t_min)
    # Includes the preceding sample (t_min - 1) to prevent visual gaps.
    assert xs[0] == t_min - 1.0
    assert xs[-1] == float(2 * chunk + 49)
    assert len(xs) == 41


def test_arrays_since_inside_middle_chunk():
    """Window crosses chunk boundaries — must keep ordering oldest → newest."""
    buf = TimeSeriesBuffer()
    chunk = TimeSeriesBuffer.CHUNK_SIZE
    for i in range(2 * chunk + 5):
        buf.append(float(i), float(i))
    # t_min in the FIRST chunk → result spans first chunk tail + full second
    # chunk + partial third.
    t_min = float(chunk - 3)
    xs, _ = buf.arrays_since(t_min)
    # Includes the preceding sample (t_min - 1) to prevent visual gaps.
    assert xs[0] == t_min - 1.0
    assert xs[-1] == float(2 * chunk + 4)
    # Strictly increasing.
    assert np.all(np.diff(xs) == 1.0)


def test_soft_cap_drops_oldest_chunks():
    """A finite max_samples drops oldest chunks once frozen size exceeds cap."""
    # Cap of 1 chunk: as soon as the second chunk seals, the first is dropped.
    cap = TimeSeriesBuffer.CHUNK_SIZE
    buf = TimeSeriesBuffer(max_samples=cap)
    for i in range(2 * cap + 10):
        buf.append(float(i), float(i))
    # We expect to have at most CHUNK_SIZE frozen samples + the partial chunk.
    # i.e. samples 0..cap-1 dropped, samples cap..end retained.
    assert buf.first_x() is not None
    assert buf.first_x() >= float(cap)
    assert buf.last_x() == float(2 * cap + 9)


def test_searchsorted_works_on_returned_arrays():
    """Hover handler uses np.searchsorted; returned arrays must support it."""
    buf = TimeSeriesBuffer()
    for i in range(5):
        buf.append(float(i), float(i) * 2)
    xs, ys = buf.arrays()
    idx = int(np.searchsorted(xs, 2.5))
    assert idx == 3
    assert float(ys[idx]) == 6.0


def test_set_max_samples_applies_retroactively():
    buf = TimeSeriesBuffer()
    chunk = TimeSeriesBuffer.CHUNK_SIZE
    for i in range(3 * chunk + 5):
        buf.append(float(i), float(i))
    # No cap yet → everything retained.
    assert buf.first_x() == 0.0
    # Tighten the cap: should drop oldest frozen chunks.
    buf.set_max_samples(chunk)
    assert buf.first_x() is not None and buf.first_x() >= float(chunk)
    assert buf.last_x() == float(3 * chunk + 4)


def test_append_time_reset_clears_buffer():
    buf = TimeSeriesBuffer()
    for i in range(100):
        buf.append(float(i), float(i * 2))
    assert buf.last_x() == 99.0
    # Time resets to 0.0 (session restart / device reboot > 1s back)
    buf.append(0.0, 50.0)
    assert len(buf) == 1
    assert buf.first_x() == 0.0
    assert buf.last_x() == 0.0
    xs, ys = buf.arrays()
    assert list(xs) == [0.0]
    assert list(ys) == [50.0]


def test_append_minor_jitter_clamps_x():
    buf = TimeSeriesBuffer()
    buf.append(10.0, 100.0)
    # Slight out-of-order arrival (e.g. 9.8s <= 10.0s)
    buf.append(9.8, 105.0)
    xs, ys = buf.arrays()
    assert list(xs) == [10.0, 10.0]
    assert list(ys) == [100.0, 105.0]

