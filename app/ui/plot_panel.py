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
    ``y_scale_mode`` – how the y-axis tracks data on each redraw:
                        "fit"    = tight auto-fit (5% padding)
                        "loose"  = auto-fit + 25% headroom (less twitchy)
                        "expand" = grow-only; axis never shrinks, so noisy
                                   signals don't make it breathe
                        "manual" = locked at user-chosen range
    """
    plot_item: object                                     # pg.PlotItem
    assigned_keys: List[Tuple[int, str]] = field(default_factory=list)
    curves:        Dict[Tuple[int, str], object] = field(default_factory=dict)
    y_scale_mode:  str = "fit"
    legend:        Optional[object] = None
    time_axis:     Optional[object] = None
    index:         int = 0
    right_vb:      Optional[object] = None
    right_axis:    Optional[object] = None
    left_unit:     Optional[str] = None
    right_unit:    Optional[str] = None


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


# Gap detection (live plot P1): a sample arriving more than GAP_FACTOR times
# the signal's usual interval after the previous one, and at least GAP_MIN_S
# later, starts a new line piece. A NaN break point is stored between the
# two; curves are drawn with connect="finite", so nothing joins across it.
GAP_FACTOR = 5.0
GAP_MIN_S = 0.5

# Reused for empty-buffer reads so we don't allocate a fresh np.array on
# every redraw when a curve has no samples yet.
_EMPTY_F64 = np.array([], dtype=float)


class TimeSeriesBuffer:
    """Append-only store for (x, y) float64 samples, oldest → newest.

    Storage is one contiguous array pair that grows on demand (x1.5), so a
    signal costs nothing until it has data and reads are zero-copy views.
    The live window (:meth:`arrays_since`) and the "All session" view
    (:meth:`arrays`) both slice the same arrays; nothing is cached or
    duplicated.

    Views handed out stay valid: samples a view covers are never
    overwritten. Appends only write past the current end, and dropping old
    samples or growing always moves the data into a *new* array.

    ``max_samples`` is a soft cap (``None`` keeps every sample). Once
    reached, the oldest samples are dropped in batches of
    ``_slack(max_samples)`` so the copy is amortised; the buffer holds between
    ``max_samples`` and ``max_samples + _slack(max_samples)`` samples.
    Tightening the cap with :meth:`set_max_samples` trims to it immediately.
    """

    INITIAL_CAPACITY = 256
    BYTES_PER_SAMPLE = 16  # float64 x + float64 y

    __slots__ = ("_x", "_y", "_start", "_end", "_max_samples", "_dt", "_break_next")

    def __init__(self, max_samples: Optional[int] = None) -> None:
        self._x = _EMPTY_F64
        self._y = _EMPTY_F64
        self._start = 0
        self._end = 0
        self._max_samples = max_samples
        self._dt: Optional[float] = None      # usual interval between samples (EMA)
        self._break_next = False

    @staticmethod
    def _slack(cap: int) -> int:
        return max(256, cap // 8)

    @classmethod
    def bytes_for(cls, max_samples: int) -> int:
        """Worst-case bytes one capped buffer holds (cap + slack samples)."""
        return (max_samples + cls._slack(max_samples)) * cls.BYTES_PER_SAMPLE

    def __len__(self) -> int:
        return self._end - self._start

    def __bool__(self) -> bool:
        return self._end > self._start

    @property
    def nbytes(self) -> int:
        """Bytes currently allocated for this buffer's arrays."""
        return self._x.nbytes + self._y.nbytes

    def set_max_samples(self, max_samples: Optional[int]) -> None:
        """Update the soft cap. ``None`` removes any cap."""
        self._max_samples = max_samples
        if max_samples is not None and len(self) > max_samples:
            self._relocate(self._end - max_samples, max_samples + self._slack(max_samples))

    def _relocate(self, keep_from: int, capacity: int) -> None:
        """Copy samples [keep_from, end) into fresh arrays of ``capacity``."""
        n = self._end - keep_from
        x = np.empty(capacity, dtype=float)
        y = np.empty(capacity, dtype=float)
        x[:n] = self._x[keep_from:self._end]
        y[:n] = self._y[keep_from:self._end]
        self._x, self._y = x, y
        self._start, self._end = 0, n

    def _make_room(self) -> None:
        n = len(self)
        cap = self._max_samples
        if cap is not None and n >= cap:
            # At the cap: keep the newest `cap` samples and leave `slack` free
            # slots, so the next copy is `slack` appends away.
            self._relocate(self._end - cap, cap + self._slack(cap))
            return
        capacity = max(self.INITIAL_CAPACITY, int(n * 1.5) + 1)
        if cap is not None:
            capacity = min(capacity, cap + self._slack(cap))
        self._relocate(self._start, capacity)

    def append(self, x: float, y: float) -> None:
        last = self.last_x()
        if last is not None and x < last:
            if (last - x) > 1.0:
                # Time reset to zero or jumped back significantly (e.g. device reboot/reconnect).
                # Auto-clear buffer to prevent drawing backward horizontal lines across the plot.
                self.clear()
            else:
                # Minor jitter or out-of-order packet: clamp x to last_x to enforce monotonicity.
                x = last
        if self._end > self._start:
            prev = float(self._x[self._end - 1])
            dt = x - prev
            typical = self._dt
            gap = typical is not None and dt > max(GAP_MIN_S, GAP_FACTOR * typical)
            if self._break_next or gap:
                # Break point immediately after the last sample: a step curve
                # holds each value until the next point, so a later break
                # would draw the old state into the gap. x stays sorted, so
                # the window lookups (searchsorted) are unaffected.
                self._put(float(np.nextafter(prev, x)), math.nan)
            if dt > 0 and not gap:
                self._dt = dt if typical is None else typical + 0.1 * (dt - typical)
        self._break_next = False
        self._put(x, y)

    def mark_break(self) -> None:
        """Start a new line piece at the next sample: samples in between were
        not plotted (display skipped them under load, P4)."""
        if self._end > self._start:
            self._break_next = True

    def _put(self, x: float, y: float) -> None:
        if self._end >= self._x.shape[0]:
            self._make_room()
        self._x[self._end] = x
        self._y[self._end] = y
        self._end += 1

    def clear(self) -> None:
        # Drop the arrays rather than rewinding: views handed out earlier
        # must not see their samples overwritten by new appends.
        self._x = _EMPTY_F64
        self._y = _EMPTY_F64
        self._start = 0
        self._end = 0
        self._dt = None
        self._break_next = False

    def first_x(self) -> Optional[float]:
        return float(self._x[self._start]) if self._end > self._start else None

    def last_x(self) -> Optional[float]:
        return float(self._x[self._end - 1]) if self._end > self._start else None

    def arrays(self) -> Tuple[np.ndarray, np.ndarray]:
        """Return all (xs, ys) ordered oldest → newest, as zero-copy views."""
        if self._end == self._start:
            return _EMPTY_F64, _EMPTY_F64
        return self._x[self._start:self._end], self._y[self._start:self._end]

    def arrays_since(self, t_min: Optional[float]) -> Tuple[np.ndarray, np.ndarray]:
        """Return (xs, ys) for samples with x >= t_min, oldest → newest.

        To prevent visual gaps at the left edge of the plot window, the single
        sample immediately preceding ``t_min`` (if one exists) is also included.
        ``t_min=None`` (or non-finite) returns the full series.
        """
        xs, ys = self.arrays()
        if t_min is None or not math.isfinite(t_min) or xs.size == 0:
            return xs, ys
        i = max(0, int(np.searchsorted(xs, t_min, side="left")) - 1)
        return xs[i:], ys[i:]


# Backwards-compatible alias for any code still importing the old name.
_RingBuffer = TimeSeriesBuffer


def _format_elapsed_time(seconds: float, spacing: Optional[float] = None) -> str:
    if not math.isfinite(seconds):
        return ""
    spacing = spacing if spacing is not None else 1.0
    abs_s = abs(seconds)
    if abs_s >= 60 or spacing >= 10:
        sign = "-" if seconds < 0 else ""
        minutes, secs = divmod(abs_s, 60)
        return f"{sign}{int(minutes)}:{int(secs):02d}"
    # Adaptive precision: pick one decimal finer than the tick spacing so
    # adjacent ticks render as distinct values when the user zooms in.
    # Previously hard-coded to .1f, which made ticks at e.g. 1.123 and
    # 1.127 both print as "1.1s" — the "two same labels" the user saw.
    # Capped at 3 decimals to keep labels short.
    if spacing >= 1:
        decimals = 0
    elif spacing >= 0.1:
        decimals = 1
    elif spacing >= 0.01:
        decimals = 2
    else:
        decimals = 3
    return f"{seconds:.{decimals}f}s"


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
