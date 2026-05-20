"""Reusable widget components for the Analysis Suite.

Holds the standalone Qt / pyqtgraph widget classes that the
``AnalysisSuiteWindow`` composes — pulled out of analysis_suite.py to
shrink the monolithic file and let each component be developed and
tested in isolation:

* :class:`TimeAxisItem` — custom x-axis that renders elapsed seconds as
  ``mm:ss`` (or wall-clock ``HH:MM:SS`` when an epoch offset is set).
* :class:`CursorReadoutPanel` — sidebar group-box that prints
  interpolated values at every active vertical cursor, with ΔX / ΔY
  comparisons when two cursors are placed.
* :class:`StatisticsPanel` — bottom-dock table of descriptive stats
  (min/median/max/std/percentiles/n) computed over the visible x-range
  of each curve.
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import TYPE_CHECKING

import numpy as np
import pyqtgraph as pg

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .analysis_theme import _parse_unit

if TYPE_CHECKING:
    from .log_io import LogEntry


# ─────────────────────────────────────────────────────────────────────
# Custom time-axis — renders ticks as mm:ss or H:MM:SS
# ─────────────────────────────────────────────────────────────────────
class TimeAxisItem(pg.AxisItem):
    """X-axis that renders elapsed seconds as mm:ss or H:MM:SS.

    Set *epoch_offset* to a POSIX timestamp to switch to wall-clock
    mode (HH:MM:SS).  Reset to ``None`` to return to elapsed mode.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._epoch_offset: float | None = None

    @property
    def epoch_offset(self) -> float | None:
        return self._epoch_offset

    @epoch_offset.setter
    def epoch_offset(self, value: float | None):
        self._epoch_offset = value
        # Force label refresh
        self.picture = None
        self.update()

    # -- formatting helpers --------------------------------------------------
    @staticmethod
    def _fmt_elapsed(seconds: float) -> str:
        """Format elapsed seconds as mm:ss or H:MM:SS."""
        neg = seconds < 0
        s = abs(seconds)
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sec = int(s % 60)
        if h > 0:
            txt = f"{h}:{m:02d}:{sec:02d}"
        else:
            txt = f"{m}:{sec:02d}"
        return f"-{txt}" if neg else txt

    @staticmethod
    def _fmt_wallclock(posix: float) -> str:
        """Format a POSIX timestamp as HH:MM:SS."""
        try:
            dt = _dt.datetime.fromtimestamp(posix)
            return dt.strftime("%H:%M:%S")
        except (OSError, OverflowError, ValueError):
            return "?"

    def tickStrings(self, values, scale, spacing):
        if self._epoch_offset is not None:
            return [self._fmt_wallclock(v + self._epoch_offset) for v in values]
        return [self._fmt_elapsed(v) for v in values]


# ═══════════════════════════════════════════════════════════════════════
# Cursor readout widget
# ═══════════════════════════════════════════════════════════════════════
class CursorReadoutPanel(QGroupBox):
    """Displays interpolated values at vertical cursor positions.

    Features:
    - Monospace numbers, right-aligned for scan-ability.
    - Colored swatch ● next to each log name.
    - ΔX / ΔY readouts when two cursors are active.
    """

    _MONO = QFont("Consolas", 9)
    _MONO_BOLD = QFont("Consolas", 9, QFont.Bold)
    _LABEL_FONT = QFont("PT Sans", 8, QFont.Bold)

    def __init__(self, parent=None):
        super().__init__("Cursor Readout", parent)
        self.setMinimumWidth(200)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)

        self._inner = QWidget()
        self._layout = QVBoxLayout(self._inner)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(1)
        self._scroll.setWidget(self._inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 12, 0, 0)
        outer.addWidget(self._scroll)

        self._delta_label = QLabel("")
        self._delta_label.setFont(self._MONO_BOLD)
        self._layout.addWidget(self._delta_label)
        self._info_label = QLabel("Add cursors with V / Shift+V / H keys.")
        self._info_label.setFont(QFont("PT Sans", 8))
        self._info_label.setWordWrap(True)
        self._layout.addWidget(self._info_label)
        self._layout.addStretch()

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _fmt_val(v: float) -> str:
        """Format a value with 3 significant figures."""
        if not np.isfinite(v):
            return "—"
        if v == 0:
            return "0"
        return f"{v:.4g}"

    def _make_row(self, left: str, right: str, *,
                  color: str = "", bold: bool = False) -> QWidget:
        """Build a compact horizontal row: left-aligned label + right-aligned value."""
        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(4)
        ll = QLabel(left)
        ll.setFont(self._MONO_BOLD if bold else self._MONO)
        if color:
            ll.setStyleSheet(f"color: {color};")
        rl = QLabel(right)
        rl.setFont(self._MONO)
        rl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        hl.addWidget(ll, 1)
        hl.addWidget(rl)
        return row

    def update_readout(self, cursors: list[dict],
                       logs: list['LogEntry'],
                       active_params: list[str]):
        vbar = self._scroll.verticalScrollBar()
        old_scroll = vbar.value()

        # Clear dynamic labels (keep delta + info + stretch)
        while self._layout.count() > 3:
            item = self._layout.takeAt(2)
            w = item.widget() if item else None
            if w:
                w.deleteLater()

        if not cursors:
            self._delta_label.setText("")
            self._info_label.setText("Add cursors with V / Shift+V / H keys.")
            vbar.setValue(min(old_scroll, vbar.maximum()))
            return

        self._info_label.setText("")

        # ΔX header when two cursors active
        if len(cursors) >= 2:
            dt_val = abs(cursors[1]['time'] - cursors[0]['time'])
            self._delta_label.setText(
                f"ΔX = {TimeAxisItem._fmt_elapsed(dt_val)}  ({dt_val:.3f} s)")
        else:
            t0 = cursors[0]['time']
            self._delta_label.setText(
                f"t = {TimeAxisItem._fmt_elapsed(t0)}  ({t0:.3f} s)")

        # Per-cursor readout
        # Collect values for ΔY computation (cursor_idx -> {(log_id,param): value})
        cursor_vals: list[dict[tuple[str, str], float]] = []

        for _ci, cursor in enumerate(cursors):
            t = cursor['time']
            label_num = cursor.get('label', 0)
            scope = cursor.get('scope', 'all')
            plot_param = cursor.get('plot_param')
            hdr_txt = f"C{label_num}  {TimeAxisItem._fmt_elapsed(t)}"
            if scope == 'plot' and plot_param:
                hdr_txt += f"  [{plot_param}]"
            hdr = QLabel(hdr_txt)
            hdr.setFont(self._LABEL_FONT)
            self._layout.insertWidget(self._layout.count() - 1, hdr)

            if scope == 'plot' and plot_param:
                params_for_cursor = [plot_param]
            else:
                params_for_cursor = active_params

            vals: dict[tuple[str, str], float] = {}
            for log in logs:
                if not log.visible or len(log.elapsed) == 0:
                    continue
                x = log.elapsed + log.time_offset
                # Swatch + log name
                row_w = self._make_row(f"● {log.name}", "",
                                       color=log.color, bold=True)
                self._layout.insertWidget(self._layout.count() - 1, row_w)
                for param in params_for_cursor:
                    if param not in log.columns:
                        continue
                    idx = int(np.clip(np.searchsorted(x, t), 0, len(x) - 1))
                    v = log.columns[param][idx]
                    short = re.sub(r'\s*[\[\(][^\]\)]*[\]\)]\s*$', '', param).strip()
                    unit = _parse_unit(param) or ""
                    if np.isfinite(v):
                        val_str = f"{self._fmt_val(v)} {unit}".strip()
                        vals[(log.id, param)] = v
                    else:
                        val_str = "—"
                    row_w = self._make_row(f"  {short}", val_str)
                    self._layout.insertWidget(self._layout.count() - 1, row_w)
            cursor_vals.append(vals)

        # ΔY readout between two cursors
        if len(cursor_vals) >= 2:
            sep = QLabel("── ΔY ──")
            sep.setFont(self._LABEL_FONT)
            self._layout.insertWidget(self._layout.count() - 1, sep)
            keys = set(cursor_vals[0].keys()) & set(cursor_vals[1].keys())
            for key in sorted(keys, key=lambda k: k[1]):
                v0 = cursor_vals[0][key]
                v1 = cursor_vals[1][key]
                delta = v1 - v0
                _, param = key
                short = re.sub(r'\s*[\[\(][^\]\)]*[\]\)]\s*$', '', param).strip()
                unit = _parse_unit(param) or ""
                row_w = self._make_row(
                    f"  {short}",
                    f"Δ {self._fmt_val(delta)} {unit}".strip())
                self._layout.insertWidget(self._layout.count() - 1, row_w)

        vbar.setValue(min(old_scroll, vbar.maximum()))


# ═══════════════════════════════════════════════════════════════════════
# Statistics panel — visible-range descriptive stats per curve
# ═══════════════════════════════════════════════════════════════════════
class StatisticsPanel(QWidget):
    """Per-curve descriptive statistics (min/max/mean/median/std/percentiles)
    computed over the currently visible x-range of each subplot.

    Updates are debounced so panning/zooming doesn't trigger continuous
    recomputation on large logs.
    """

    STATS_COLUMNS = ["Curve", "Min", "P5", "Mean", "Median", "P95", "Max", "Std", "n"]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(4)

        self._info = QLabel("Load logs and check parameters to see statistics.")
        self._info.setWordWrap(True)
        self._info.setStyleSheet("color: palette(mid); font-size: 11px; padding: 2px;")
        layout.addWidget(self._info)

        self._table = QTableWidget(0, len(self.STATS_COLUMNS))
        self._table.setHorizontalHeaderLabels(self.STATS_COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setFont(QFont("Consolas", 9))
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, len(self.STATS_COLUMNS)):
            hh.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        layout.addWidget(self._table, 1)

    @staticmethod
    def compute_stats(x: np.ndarray, y: np.ndarray,
                       x_range: tuple[float, float] | None
                       ) -> dict[str, float] | None:
        """Return a stats dict for the slice of y where x is within
        ``x_range`` (or the full series if x_range is None). NaNs are
        ignored. Returns None if there are no finite samples in range."""
        if x.size == 0 or y.size == 0:
            return None
        if x_range is not None:
            lo, hi = x_range
            mask = (x >= lo) & (x <= hi)
        else:
            mask = np.ones_like(x, dtype=bool)
        yv = y[mask]
        yv = yv[~np.isnan(yv)]
        if yv.size == 0:
            return None
        return {
            "min":    float(np.min(yv)),
            "p5":     float(np.percentile(yv, 5)),
            "max":    float(np.max(yv)),
            "mean":   float(np.mean(yv)),
            "median": float(np.median(yv)),
            "p95":    float(np.percentile(yv, 95)),
            "std":    float(np.std(yv)),
            "n":      int(yv.size),
        }

    @staticmethod
    def _fmt(v: float) -> str:
        """Format with 3 significant figures."""
        if not np.isfinite(v):
            return "—"
        if v == 0:
            return "0"
        return f"{v:.3g}"

    def update_stats(self, rows: list[dict]):
        """``rows`` is a list of {curve, log_id, param, color, x, y, x_range}.
        We compute stats and re-render the table."""
        self._table.setRowCount(0)
        if not rows:
            self._info.setText("No visible curves. Check parameters to populate.")
            return
        self._info.setText(f"Stats over visible x-range  ·  {len(rows)} curve(s)")
        self._table.setRowCount(len(rows))
        for r, info in enumerate(rows):
            stats = self.compute_stats(info["x"], info["y"], info.get("x_range"))
            label = info["curve"]
            color = info.get("color", "")

            name_item = QTableWidgetItem(label)
            if color:
                name_item.setForeground(QColor(color))
            self._table.setItem(r, 0, name_item)

            if stats is None:
                placeholders = ["—"] * (len(self.STATS_COLUMNS) - 2) + ["0"]
                for c, txt in enumerate(placeholders, start=1):
                    cell = QTableWidgetItem(txt)
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self._table.setItem(r, c, cell)
                continue

            for c, key in enumerate(["min", "p5", "mean", "median", "p95", "max", "std", "n"], start=1):
                if key == "n":
                    txt = str(stats[key])
                else:
                    txt = self._fmt(stats[key])
                cell = QTableWidgetItem(txt)
                cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._table.setItem(r, c, cell)
