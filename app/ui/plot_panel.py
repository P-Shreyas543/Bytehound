"""Live-plot building blocks carved out of main_window.py.

PlotPanel, _RingBuffer, _TimeAxisItem and their direct helpers
(_format_elapsed_time, _EMPTY_F64) live here so the live-plot data path
can be reviewed and tested without dragging in the full MainWindow.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import pyqtgraph as pg
except ImportError:  # pragma: no cover - exercised only when optional dep missing
    pg = None


# Live Plot grid layouts — display label → (rows, cols).
GRID_LAYOUTS: Dict[str, Tuple[int, int]] = {
    "1×1": (1, 1),
    "1×2": (1, 2),
    "2×1": (2, 1),
    "1×3": (1, 3),
    "3×1": (3, 1),
    "2×2": (2, 2),
    "2×4": (2, 4),
    "4×2": (4, 2),
}


@dataclass
class PlotPanel:
    """State for one subplot cell in the multi-grid live plot.

    ``plot_item``     – the pyqtgraph PlotItem for this cell.
    ``assigned_keys`` – ordered list of (frame_id, signal_name) signals to draw.
    ``curves``        – mapping from key → PlotDataItem (the live curve object).
    ``auto_fit_y``    – when True, pyqtgraph rescales the y-axis automatically
                        so growing signals stay in view without manual zoom.
    """
    plot_item: object                                     # pg.PlotItem
    assigned_keys: List[Tuple[int, str]] = field(default_factory=list)
    curves:        Dict[Tuple[int, str], object] = field(default_factory=dict)
    auto_fit_y:    bool = True
    legend:        Optional[object] = None
    time_axis:     Optional[object] = None
    index:         int = 0


# Width of the live plot's X view before any data has arrived AND the minimum
# width once data exists. Keeps the curve from looking glued to the left edge
# in the first ~10 s of a session.
_PLOT_INITIAL_WINDOW_S = 10.0


def _configure_live_curve(curve) -> None:
    """Apply per-curve perf flags so paint time stays sublinear in buffer length.

    Why: profiling at 100 Hz showed QPainter.drawPath dominating CPU (>25% of
    runtime) because every live-plot redraw painted every sample in the ring
    buffer, even when many samples collapsed onto the same pixel. Mirrors the
    flags the Analysis Suite already uses on its plots.
    """
    if pg is None:
        return
    try:
        curve.setClipToView(True)
        curve.setDownsampling(auto=True, method='peak')
        # Antialiasing dominates QPainter.drawPath cost at high refresh rates;
        # disable it per-curve on the live plot only (Analysis Suite keeps AA).
        curve.opts['antialias'] = False
    except Exception:  # pragma: no cover - older pyqtgraph fallbacks
        pass


# Reused for empty-buffer reads so we don't allocate a fresh np.array on
# every redraw when a curve has no samples yet.
_EMPTY_F64 = np.array([], dtype=float)


class _RingBuffer:
    """Fixed-capacity ring buffer over two parallel float arrays.

    Replaces the previous ``(deque, deque)`` pair that backed each entry of
    ``_plot_history``. The deque version required ``np.fromiter`` over the
    deque on every redraw — a Python-level loop whose cost grew with the
    buffer length. The ring buffer stores samples in pre-allocated numpy
    arrays and exposes ordered numpy slices via :meth:`arrays` so the
    redraw path can hand them straight to ``setData`` with zero per-tick
    allocation while the buffer is still filling, and a single
    ``np.concatenate`` once it wraps.

    Interface kept narrow on purpose — only the surface the live-plot
    pipeline actually needs (append, clear, len, first/last x, arrays).
    """

    __slots__ = ("_xs", "_ys", "_capacity", "_write", "_count")

    def __init__(self, capacity: int) -> None:
        self._xs = np.empty(capacity, dtype=float)
        self._ys = np.empty(capacity, dtype=float)
        self._capacity = capacity
        self._write = 0
        self._count = 0

    def __len__(self) -> int:
        return self._count

    def __bool__(self) -> bool:
        return self._count > 0

    def append(self, x: float, y: float) -> None:
        w = self._write
        self._xs[w] = x
        self._ys[w] = y
        w += 1
        if w >= self._capacity:
            w = 0
        self._write = w
        if self._count < self._capacity:
            self._count += 1

    def clear(self) -> None:
        self._write = 0
        self._count = 0

    def first_x(self) -> Optional[float]:
        """Oldest x sample, or ``None`` when empty."""
        if self._count == 0:
            return None
        if self._count < self._capacity:
            return float(self._xs[0])
        return float(self._xs[self._write])  # next-write slot == oldest

    def last_x(self) -> Optional[float]:
        """Most recently appended x sample, or ``None`` when empty."""
        if self._count == 0:
            return None
        idx = self._write - 1
        if idx < 0:
            idx = self._capacity - 1
        return float(self._xs[idx])

    def arrays(self) -> Tuple[np.ndarray, np.ndarray]:
        """Return (xs, ys) ordered oldest → newest.

        Zero-copy slice when the buffer has not yet wrapped, single
        ``np.concatenate`` once it has. Callers MUST NOT mutate the
        returned arrays — slicing returns a view into the underlying
        storage.
        """
        if self._count == 0:
            return _EMPTY_F64, _EMPTY_F64
        if self._count < self._capacity:
            return self._xs[: self._count], self._ys[: self._count]
        w = self._write
        return (
            np.concatenate((self._xs[w:], self._xs[:w])),
            np.concatenate((self._ys[w:], self._ys[:w])),
        )


def _format_elapsed_time(seconds: float, spacing: Optional[float] = None) -> str:
    if not math.isfinite(seconds):
        return ""
    spacing = spacing if spacing is not None else 1.0
    abs_s = abs(seconds)
    if abs_s >= 60 or spacing >= 10:
        sign = "-" if seconds < 0 else ""
        minutes, secs = divmod(abs_s, 60)
        return f"{sign}{int(minutes)}:{int(secs):02d}"
    if spacing < 1:
        return f"{seconds:.1f}s"
    return f"{seconds:.0f}s"


if pg is not None:
    class _TimeAxisItem(pg.AxisItem):
        def __init__(
            self,
            *,
            mode: str = "elapsed",
            session_start: Optional[datetime] = None,
            min_label_px: int = 80,
        ) -> None:
            super().__init__(orientation="bottom")
            self._mode = mode
            self._session_start = session_start or datetime.now()
            self._min_label_px = min_label_px

        def set_mode(self, mode: str) -> None:
            self._mode = mode

        def set_session_start(self, session_start: datetime) -> None:
            self._session_start = session_start

        @staticmethod
        def _nice_step(span: float, target_ticks: int) -> float:
            raw = span / max(target_ticks, 1)
            if raw <= 0 or not math.isfinite(raw):
                return 1.0
            power = 10 ** math.floor(math.log10(raw))
            for mult in (1, 2, 5, 10):
                step = mult * power
                if step >= raw:
                    return step
            return 10 * power

        def tickValues(self, minVal: float, maxVal: float, size: float):  # noqa: N802
            if not (math.isfinite(minVal) and math.isfinite(maxVal)):
                return []
            span = maxVal - minVal
            if span <= 0 or size <= 0:
                return []
            target = max(2, int(size / self._min_label_px))
            step = self._nice_step(span, target)
            first = math.floor(minVal / step) * step
            count = int(math.ceil((maxVal - first) / step)) + 1
            ticks = [first + i * step for i in range(count)]
            return [(step, ticks)]

        def tickStrings(self, values, scale, spacing):  # noqa: N802
            if self._mode == "clock":
                base = self._session_start
                return [
                    (base + timedelta(seconds=float(v))).strftime("%H:%M:%S")
                    if math.isfinite(float(v)) else ""
                    for v in values
                ]
            return [_format_elapsed_time(float(v), spacing) for v in values]
else:
    _TimeAxisItem = object  # type: ignore[misc,assignment]
