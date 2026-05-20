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
    QGroupBox, QHeaderView, QLabel,
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
    _TABLE_COLUMNS = ["Cursor", "Log", "Parameter", "Value", "Unit", "Delta"]

    def __init__(self, parent=None):
        super().__init__("Cursor Readout", parent)
        self.setMinimumWidth(200)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 12, 8, 8)
        outer.setSpacing(6)

        self._delta_label = QLabel("")
        self._delta_label.setFont(self._MONO_BOLD)
        outer.addWidget(self._delta_label)

        self._info_label = QLabel("Add cursors with V / Shift+V / H keys.")
        self._info_label.setFont(QFont("PT Sans", 8))
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet("color: palette(mid);")
        outer.addWidget(self._info_label)

        self._table = QTableWidget(0, len(self._TABLE_COLUMNS))
        self._table.setHorizontalHeaderLabels(self._TABLE_COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setFont(self._MONO)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        for col in range(3, len(self._TABLE_COLUMNS)):
            hh.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        outer.addWidget(self._table, 1)

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _fmt_val(v: float) -> str:
        """Format a value with 3 significant figures."""
        if not np.isfinite(v):
            return "—"
        if v == 0:
            return "0"
        return f"{v:.4g}"

    @staticmethod
    def _strip_param_label(param: str) -> str:
        return re.sub(r"\s*[\[\(][^\]\)]*[\]\)]\s*$", "", param).strip()

    def _set_cell(self, row: int, col: int, text: str,
                  *, color: str | None = None, align_right: bool = False) -> None:
        item = QTableWidgetItem(text)
        if color:
            item.setForeground(QColor(color))
        if align_right:
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._table.setItem(row, col, item)

    def update_readout(self, cursors: list[dict],
                       logs: list['LogEntry'],
                       active_params: list[str],
                       h_cursors: list[dict] | None = None):
        """Refresh the readout with the current cursors.

        ``cursors`` are vertical cursors (each has ``time``, ``label``,
        ``scope`` ∈ {"all", "plot"}, ``plot_param``, ``color``).
        ``h_cursors`` (added later) are horizontal cursors with a fixed Y
        value (``value``, ``color``, optional ``plot_widget``). Both
        lists are rendered into the same scroll area so the analyst sees
        all active cursor measurements in one place.
        """
        h_cursors = h_cursors or []
        self._table.setRowCount(0)

        if not cursors and not h_cursors:
            self._delta_label.setText("")
            self._info_label.setText("Add cursors with V / Shift+V / H keys.")
            return

        self._info_label.setText("")

        # ΔX header when two vertical cursors active; otherwise show the
        # single cursor's time. With no vertical cursors but H-cursors
        # present, clear the header so it doesn't show a stale time.
        if len(cursors) >= 2:
            dt_val = abs(cursors[1]['time'] - cursors[0]['time'])
            self._delta_label.setText(
                f"ΔX = {TimeAxisItem._fmt_elapsed(dt_val)}  ({dt_val:.3f} s)")
        elif cursors:
            t0 = cursors[0]['time']
            self._delta_label.setText(
                f"t = {TimeAxisItem._fmt_elapsed(t0)}  ({t0:.3f} s)")
        else:
            self._delta_label.setText("")

        def params_for_cursor(cursor: dict) -> list[str]:
            if cursor.get('scope') == 'plot' and cursor.get('plot_param'):
                return [cursor.get('plot_param')]
            return active_params

        def collect_values(cursor: dict) -> dict[tuple[str, str], float]:
            vals: dict[tuple[str, str], float] = {}
            t = cursor.get('time', 0.0)
            for log in logs:
                if len(log.elapsed) == 0:
                    continue
                x = log.elapsed + log.time_offset
                for param in params_for_cursor(cursor):
                    if param not in log.columns:
                        continue
                    idx = int(np.clip(np.searchsorted(x, t), 0, len(x) - 1))
                    v = log.columns[param][idx]
                    if np.isfinite(v):
                        vals[(log.id, param)] = float(v)
            return vals

        delta_map: dict[tuple[str, str], float] = {}
        if len(cursors) == 2:
            v0 = collect_values(cursors[0])
            v1 = collect_values(cursors[1])
            for key in v0.keys() & v1.keys():
                delta_map[key] = v1[key] - v0[key]

        row = 0
        for ci, cursor in enumerate(cursors):
            t = cursor.get('time', 0.0)
            label_num = cursor.get('label', ci + 1)
            cursor_color = cursor.get('color', '')
            cursor_text = f"C{label_num} @ {TimeAxisItem._fmt_elapsed(t)}"
            for log in logs:
                if len(log.elapsed) == 0:
                    continue
                x = log.elapsed + log.time_offset
                for param in params_for_cursor(cursor):
                    if param not in log.columns:
                        continue
                    idx = int(np.clip(np.searchsorted(x, t), 0, len(x) - 1))
                    v = log.columns[param][idx]
                    value_text = self._fmt_val(v)
                    unit = _parse_unit(param) or ""
                    short = self._strip_param_label(param)
                    delta_text = ""
                    if len(cursors) == 2 and ci == 1:
                        delta = delta_map.get((log.id, param))
                        if delta is not None:
                            delta_text = self._fmt_val(delta)

                    self._table.insertRow(row)
                    self._set_cell(row, 0, cursor_text, color=cursor_color)
                    self._set_cell(row, 1, log.name, color=log.color)
                    self._set_cell(row, 2, short)
                    self._set_cell(row, 3, value_text, align_right=True)
                    self._set_cell(row, 4, unit)
                    self._set_cell(row, 5, delta_text, align_right=True)
                    row += 1

        h_delta_map: dict[tuple[int, int], float] = {}
        by_plot: dict[int, list[dict]] = {}
        for hc in h_cursors:
            by_plot.setdefault(hc.get('plot_widget_id'), []).append(hc)
        for plot_id, items in by_plot.items():
            items_sorted = sorted(items, key=lambda h: h.get('label', 0))
            if len(items_sorted) < 2:
                continue
            base = items_sorted[0].get('value', float('nan'))
            if not np.isfinite(base):
                continue
            for hc in items_sorted[1:]:
                val = hc.get('value', float('nan'))
                if np.isfinite(val):
                    h_delta_map[(plot_id, hc.get('label', 0))] = val - base

        for hi, hc in enumerate(h_cursors, start=1):
            value = hc.get('value', float('nan'))
            cursor_color = hc.get('color', '')
            label_num = hc.get('label', hi)
            cursor_text = f"H{label_num} @ {self._fmt_val(value)}"
            group: list[str] = hc.get('plot_group') or []
            plot_id = hc.get('plot_widget_id')
            for log in logs:
                if len(log.elapsed) == 0:
                    continue
                log_params = [p for p in group if p in log.columns]
                if not log_params:
                    continue
                for param in log_params:
                    unit = _parse_unit(param) or ""
                    short = self._strip_param_label(param)
                    delta_text = ""
                    delta = h_delta_map.get((plot_id, label_num))
                    if delta is not None:
                        delta_text = self._fmt_val(delta)
                    self._table.insertRow(row)
                    self._set_cell(row, 0, cursor_text, color=cursor_color)
                    self._set_cell(row, 1, log.name, color=log.color)
                    self._set_cell(row, 2, short)
                    self._set_cell(row, 3, self._fmt_val(value), align_right=True)
                    self._set_cell(row, 4, unit)
                    self._set_cell(row, 5, delta_text, align_right=True)
                    row += 1

        if row == 0:
            self._info_label.setText("No cursor values for the selected parameters.")


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
