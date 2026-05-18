"""Tests for the live-plot history ring buffer.

Lives in ``app.ui.main_window`` because it's tightly coupled to the plot
pipeline (and importing it does pull in PySide6 transitively). The class
itself is pure Python + numpy and has no Qt dependency, so we can
exercise it directly without a ``QApplication``.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.ui.main_window import _RingBuffer


def test_empty_buffer_has_no_first_or_last_x():
    rb = _RingBuffer(8)
    assert len(rb) == 0
    assert not rb
    assert rb.first_x() is None
    assert rb.last_x() is None
    xs, ys = rb.arrays()
    assert xs.size == 0
    assert ys.size == 0


def test_partial_fill_returns_zero_copy_view():
    """Before wrap, arrays() returns a view into the underlying storage."""
    rb = _RingBuffer(8)
    for i in range(3):
        rb.append(float(i), float(i) * 10)

    assert len(rb) == 3
    assert bool(rb)
    assert rb.first_x() == 0.0
    assert rb.last_x() == 2.0

    xs, ys = rb.arrays()
    assert list(xs) == [0.0, 1.0, 2.0]
    assert list(ys) == [0.0, 10.0, 20.0]
    # arrays() must be a view (not a copy) on the not-yet-wrapped path so
    # the redraw path avoids the per-tick allocation. base != None means
    # the slice shares storage with the original numpy array.
    assert xs.base is not None
    assert ys.base is not None


def test_filling_to_capacity_keeps_order_no_wrap_yet():
    rb = _RingBuffer(4)
    for i in range(4):
        rb.append(float(i), float(i))
    assert len(rb) == 4
    assert rb.first_x() == 0.0
    assert rb.last_x() == 3.0
    xs, ys = rb.arrays()
    assert list(xs) == [0.0, 1.0, 2.0, 3.0]
    assert list(ys) == [0.0, 1.0, 2.0, 3.0]


def test_wrap_around_returns_oldest_to_newest_order():
    """Once the buffer wraps, the oldest sample is at the next-write slot."""
    rb = _RingBuffer(4)
    # Append 6 samples into a capacity-4 buffer: last 4 win in order.
    for i in range(6):
        rb.append(float(i), float(i) * 100)

    assert len(rb) == 4
    assert rb.first_x() == 2.0  # oldest surviving sample
    assert rb.last_x() == 5.0

    xs, ys = rb.arrays()
    assert list(xs) == [2.0, 3.0, 4.0, 5.0]
    assert list(ys) == [200.0, 300.0, 400.0, 500.0]
    # Post-wrap arrays() must be a fresh copy (concat result), not a view
    # into storage that could be overwritten by the next append. base is
    # None for owned numpy arrays.
    assert xs.base is None
    assert ys.base is None


def test_clear_resets_count_and_pointer():
    rb = _RingBuffer(4)
    for i in range(10):
        rb.append(float(i), float(i))
    rb.clear()
    assert len(rb) == 0
    assert rb.first_x() is None
    assert rb.last_x() is None
    # Re-using after clear must work cleanly — no stale samples leaking.
    rb.append(100.0, 200.0)
    xs, ys = rb.arrays()
    assert list(xs) == [100.0]
    assert list(ys) == [200.0]


def test_wrap_exactly_at_capacity_boundary():
    """Edge case: writing exactly capacity*N samples lands at write==0."""
    rb = _RingBuffer(3)
    for i in range(6):  # exactly two full wraps
        rb.append(float(i), float(i))
    assert len(rb) == 3
    assert rb.first_x() == 3.0
    assert rb.last_x() == 5.0
    xs, _ = rb.arrays()
    assert list(xs) == [3.0, 4.0, 5.0]


def test_searchsorted_works_on_returned_arrays():
    """Hover handler uses np.searchsorted; the returned arrays must support it."""
    rb = _RingBuffer(8)
    for i in range(5):
        rb.append(float(i), float(i) * 2)
    xs, ys = rb.arrays()
    # Bisect via numpy on a view (pre-wrap path).
    idx = int(np.searchsorted(xs, 2.5))
    assert idx == 3
    assert float(ys[idx]) == 6.0


def test_capacity_one():
    rb = _RingBuffer(1)
    rb.append(1.0, 10.0)
    assert rb.first_x() == 1.0
    assert rb.last_x() == 1.0
    rb.append(2.0, 20.0)
    assert rb.first_x() == 2.0  # the only surviving sample
    assert rb.last_x() == 2.0
    xs, ys = rb.arrays()
    assert list(xs) == [2.0]
    assert list(ys) == [20.0]
