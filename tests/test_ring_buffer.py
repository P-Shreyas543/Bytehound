"""Tests for the live-plot history buffer (``TimeSeriesBuffer``).

The class lives in ``app.ui.plot_panel``: contiguous, append-only storage
so long sessions retain every sample and reads are zero-copy. Tests cover:
ordering, arrays_since() slicing, the optional soft cap, views staying valid
across growth/trim/clear, and the legacy ``_RingBuffer`` alias.
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
    # Enough samples to force several capacity growths.
    n = 50_000
    for i in range(n):
        buf.append(float(i), float(i) * 2)
    assert len(buf) == n
    assert buf.first_x() == 0.0
    assert buf.last_x() == float(n - 1)
    xs, ys = buf.arrays()
    assert list(xs[:3]) == [0.0, 1.0, 2.0]
    assert list(xs[-3:]) == [float(n - 3), float(n - 2), float(n - 1)]
    # Y values stay paired with their X values across growths.
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


def test_arrays_since_window_at_the_end():
    buf = TimeSeriesBuffer()
    for i in range(50_000):
        buf.append(float(i), float(i))
    xs, ys = buf.arrays_since(49_990.0)
    # Includes the preceding sample (t_min - 1) to prevent visual gaps.
    assert xs[0] == 49_989.0
    assert xs[-1] == 49_999.0
    assert len(xs) == 11
    assert np.array_equal(xs, ys)


def test_arrays_since_from_the_middle():
    buf = TimeSeriesBuffer()
    for i in range(50_000):
        buf.append(float(i), float(i))
    xs, _ = buf.arrays_since(10_000.0)
    assert xs[0] == 9_999.0
    assert xs[-1] == 49_999.0
    # Strictly increasing.
    assert np.all(np.diff(xs) == 1.0)


def test_soft_cap_keeps_newest_samples():
    cap = 1_000
    buf = TimeSeriesBuffer(max_samples=cap)
    for i in range(5_000):
        buf.append(float(i), float(i))
    # Holds between cap and cap + slack samples, always the newest ones.
    assert cap <= len(buf) <= cap + TimeSeriesBuffer._slack(cap)
    assert buf.last_x() == 4_999.0
    xs, _ = buf.arrays()
    assert np.all(np.diff(xs) == 1.0)
    assert xs[0] == 4_999.0 - (len(buf) - 1)
    assert buf.nbytes <= TimeSeriesBuffer.bytes_for(cap)


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
    for i in range(5_000):
        buf.append(float(i), float(i))
    assert buf.first_x() == 0.0
    # Tightening the cap trims to it immediately, keeping the newest.
    buf.set_max_samples(1_000)
    assert len(buf) == 1_000
    assert buf.first_x() == 4_000.0
    assert buf.last_x() == 4_999.0
    # Loosening it keeps what is there.
    buf.set_max_samples(None)
    assert len(buf) == 1_000


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


def test_empty_buffer_allocates_nothing():
    """Signals that never receive data must not cost memory."""
    assert TimeSeriesBuffer().nbytes == 0
    assert TimeSeriesBuffer(max_samples=100_000).nbytes == 0


def test_views_stay_valid_after_growth_trim_and_clear():
    """pyqtgraph keeps the arrays it was given until the next setData();
    later appends, trims and clears must never rewrite them."""
    buf = TimeSeriesBuffer(max_samples=1_000)
    for i in range(900):
        buf.append(float(i), float(i))
    xs, ys = buf.arrays()
    snapshot = (xs.copy(), ys.copy())
    for i in range(900, 3_000):          # forces growth and several trims
        buf.append(float(i), -1.0)
    assert np.array_equal(xs, snapshot[0]) and np.array_equal(ys, snapshot[1])
    xs2, _ = buf.arrays()
    snap2 = xs2.copy()
    buf.clear()
    buf.append(0.0, 0.0)
    assert np.array_equal(xs2, snap2)
