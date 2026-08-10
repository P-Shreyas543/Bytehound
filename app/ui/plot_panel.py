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


# Reused for empty-buffer reads so we don't allocate a fresh np.array on
# every redraw when a curve has no samples yet.
_EMPTY_F64 = np.array([], dtype=float)


class TimeSeriesBuffer:
    """Append-only chunked store for (x, y) float samples.

    Replaces the fixed-capacity ring buffer that dropped early samples on
    long sessions. Storage grows in fixed-size chunks (``CHUNK_SIZE``);
    arrays_since() lets the redraw path read just the visible time
    window so paint cost stays bounded as history grows.

    A soft cap ``max_samples`` is honoured by dropping whole oldest chunks
    when exceeded — set to ``None`` (default) to keep every sample for
    the entire session. The cap is a safety valve for marathon runs
    on memory-constrained hosts; it intentionally drops in chunk-sized
    steps so the bookkeeping cost stays O(1) per append.

    Interface mirrors the old ``_RingBuffer`` so existing call sites
    (``__len__``, ``__bool__``, ``arrays``, ``first_x``, ``last_x``,
    ``clear``, ``append``) keep working. ``arrays_since(t_min)`` is the
    one new method.
    """

    CHUNK_SIZE = 16_384

    __slots__ = (
        "_chunks_x", "_chunks_y", "_chunks_last_x",
        "_cur_x", "_cur_y", "_cur_fill",
        "_max_samples", "_first_x",
        "_frozen_xs", "_frozen_ys", "_frozen_dirty",
    )

    def __init__(self, max_samples: Optional[int] = None) -> None:
        self._chunks_x: list = []        # list[np.ndarray] of full chunks (oldest → newest)
        self._chunks_y: list = []
        self._chunks_last_x: list = []   # parallel: last x in each frozen chunk (for bisect)
        self._cur_x = np.empty(self.CHUNK_SIZE, dtype=float)
        self._cur_y = np.empty(self.CHUNK_SIZE, dtype=float)
        self._cur_fill = 0
        self._max_samples = max_samples
        self._first_x: Optional[float] = None
        # Cache for arrays() of frozen chunks — invalidated when a chunk
        # is sealed or oldest chunk is dropped. The current partial chunk
        # is concatenated on top per-call (small, cheap).
        self._frozen_xs: Optional[np.ndarray] = None
        self._frozen_ys: Optional[np.ndarray] = None
        self._frozen_dirty = True

    def __len__(self) -> int:
        return len(self._chunks_x) * self.CHUNK_SIZE + self._cur_fill

    def __bool__(self) -> bool:
        return self._cur_fill > 0 or bool(self._chunks_x)

    def set_max_samples(self, max_samples: Optional[int]) -> None:
        """Update the soft cap. ``None`` removes any cap."""
        self._max_samples = max_samples
        self._maybe_drop()

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

        if self._cur_fill >= self.CHUNK_SIZE:
            # Seal the current chunk and start a fresh one.
            self._chunks_x.append(self._cur_x)
            self._chunks_y.append(self._cur_y)
            self._chunks_last_x.append(float(self._cur_x[-1]))
            self._cur_x = np.empty(self.CHUNK_SIZE, dtype=float)
            self._cur_y = np.empty(self.CHUNK_SIZE, dtype=float)
            self._cur_fill = 0
            self._frozen_dirty = True
            self._maybe_drop()
        self._cur_x[self._cur_fill] = x
        self._cur_y[self._cur_fill] = y
        self._cur_fill += 1
        if self._first_x is None and not self._chunks_x:
            self._first_x = float(x)

    def _maybe_drop(self) -> None:
        cap = self._max_samples
        if cap is None:
            return
        # Drop whole oldest chunks while the frozen sample count would
        # exceed the cap. The current (partial) chunk is never dropped.
        while len(self._chunks_x) * self.CHUNK_SIZE > cap and self._chunks_x:
            self._chunks_x.pop(0)
            self._chunks_y.pop(0)
            self._chunks_last_x.pop(0)
            self._frozen_dirty = True
            # _first_x will be recomputed lazily on next first_x() call
            self._first_x = None

    def clear(self) -> None:
        self._chunks_x.clear()
        self._chunks_y.clear()
        self._chunks_last_x.clear()
        self._cur_fill = 0
        self._first_x = None
        self._frozen_xs = None
        self._frozen_ys = None
        self._frozen_dirty = True

    def first_x(self) -> Optional[float]:
        if self._first_x is not None:
            return self._first_x
        if self._chunks_x:
            self._first_x = float(self._chunks_x[0][0])
            return self._first_x
        if self._cur_fill:
            self._first_x = float(self._cur_x[0])
            return self._first_x
        return None

    def last_x(self) -> Optional[float]:
        if self._cur_fill:
            return float(self._cur_x[self._cur_fill - 1])
        if self._chunks_x:
            return self._chunks_last_x[-1]
        return None

    def _frozen_arrays(self) -> Tuple[np.ndarray, np.ndarray]:
        if self._frozen_dirty or self._frozen_xs is None:
            if self._chunks_x:
                self._frozen_xs = np.concatenate(self._chunks_x)
                self._frozen_ys = np.concatenate(self._chunks_y)
            else:
                self._frozen_xs = _EMPTY_F64
                self._frozen_ys = _EMPTY_F64
            self._frozen_dirty = False
        return self._frozen_xs, self._frozen_ys

    def arrays(self) -> Tuple[np.ndarray, np.ndarray]:
        """Return all (xs, ys) ordered oldest → newest.

        For very long sessions, prefer :meth:`arrays_since` to avoid
        materialising the whole series on every redraw.
        """
        if not self._chunks_x and self._cur_fill == 0:
            return _EMPTY_F64, _EMPTY_F64
        if not self._chunks_x:
            # Pure partial-chunk case: return zero-copy views.
            return (
                self._cur_x[: self._cur_fill],
                self._cur_y[: self._cur_fill],
            )
        frozen_xs, frozen_ys = self._frozen_arrays()
        if self._cur_fill == 0:
            return frozen_xs, frozen_ys
        return (
            np.concatenate((frozen_xs, self._cur_x[: self._cur_fill])),
            np.concatenate((frozen_ys, self._cur_y[: self._cur_fill])),
        )

    def arrays_since(self, t_min: Optional[float]) -> Tuple[np.ndarray, np.ndarray]:
        """Return (xs, ys) for samples with x >= t_min, oldest → newest.

        To prevent visual gaps at the left edge of the plot window, the single
        sample immediately preceding ``t_min`` (if one exists) is also included.
        ``t_min=None`` (or non-finite) returns the full series.
        """
        if t_min is None or not math.isfinite(t_min):
            return self.arrays()
        # Fast path: window starts after every frozen chunk → only current.
        if self._chunks_last_x and self._chunks_last_x[-1] < t_min and self._cur_fill:
            xs = self._cur_x[: self._cur_fill]
            ys = self._cur_y[: self._cur_fill]
            start = int(np.searchsorted(xs, t_min, side="left"))
            if start > 0:
                return xs[start - 1 :], ys[start - 1 :]
            last_frozen_x = self._chunks_x[-1][-1:]
            last_frozen_y = self._chunks_y[-1][-1:]
            return np.concatenate((last_frozen_x, xs)), np.concatenate((last_frozen_y, ys))
        if not self._chunks_x:
            if self._cur_fill == 0:
                return _EMPTY_F64, _EMPTY_F64
            xs = self._cur_x[: self._cur_fill]
            ys = self._cur_y[: self._cur_fill]
            start = int(np.searchsorted(xs, t_min, side="left"))
            start = max(0, start - 1)
            return xs[start:], ys[start:]
        # Find first chunk whose last_x >= t_min via bisection.
        last_x_arr = np.asarray(self._chunks_last_x)
        chunk_idx = int(np.searchsorted(last_x_arr, t_min, side="left"))
        if chunk_idx >= len(self._chunks_x):
            # All frozen chunks are before t_min; only partial chunk matters.
            if self._cur_fill == 0:
                return _EMPTY_F64, _EMPTY_F64
            xs = self._cur_x[: self._cur_fill]
            ys = self._cur_y[: self._cur_fill]
            start = int(np.searchsorted(xs, t_min, side="left"))
            if start > 0:
                return xs[start - 1 :], ys[start - 1 :]
            last_frozen_x = self._chunks_x[-1][-1:]
            last_frozen_y = self._chunks_y[-1][-1:]
            return np.concatenate((last_frozen_x, xs)), np.concatenate((last_frozen_y, ys))
        head_x = self._chunks_x[chunk_idx]
        head_y = self._chunks_y[chunk_idx]
        start_in_head = int(np.searchsorted(head_x, t_min, side="left"))
        if start_in_head > 0:
            parts_x = [head_x[start_in_head - 1 :]]
            parts_y = [head_y[start_in_head - 1 :]]
        else:
            if chunk_idx > 0:
                prev_x = self._chunks_x[chunk_idx - 1][-1:]
                prev_y = self._chunks_y[chunk_idx - 1][-1:]
                parts_x = [prev_x, head_x]
                parts_y = [prev_y, head_y]
            else:
                parts_x = [head_x]
                parts_y = [head_y]
        for i in range(chunk_idx + 1, len(self._chunks_x)):
            parts_x.append(self._chunks_x[i])
            parts_y.append(self._chunks_y[i])
        if self._cur_fill:
            parts_x.append(self._cur_x[: self._cur_fill])
            parts_y.append(self._cur_y[: self._cur_fill])
        if len(parts_x) == 1:
            return parts_x[0], parts_y[0]
        return np.concatenate(parts_x), np.concatenate(parts_y)


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
