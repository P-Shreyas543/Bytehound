"""X-Y scatter plot window — secondary tool for cross-parameter analysis.

Launched from Tools → X-Y Plotter in the Analysis Suite. Lets the user
pick any two loaded parameters and render a scatter plot of one against
the other, with optional linear regression overlay. Extracted from
analysis_suite.py to keep the main window's responsibilities focused on
the time-series view.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QVBoxLayout,
)

from .analysis_theme import APP_NAME, THEME
from .log_io import LogEntry


# Symbol name → pyqtgraph symbol string
_XY_SYMBOLS = [
    ('Circle (outline)', 'o'),
    ('Circle (filled)', 'o'),
    ('Square', 's'),
    ('Triangle', 't'),
    ('Diamond', 'd'),
    ('Cross', '+'),
]


class XYPlotWindow(QDialog):
    """Scatter / X-Y plot window for cross-parameter analysis."""

    def __init__(self, logs: dict[str, LogEntry], parent=None):
        super().__init__(parent)
        # Qt.Window: independent z-order (not an owned always-on-top window)
        self.setWindowFlag(Qt.Window)
        self.setWindowTitle(f"X-Y Plotter — {APP_NAME}")
        self.resize(900, 700)
        self.setMinimumSize(600, 400)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        self._logs = logs
        self._curves: list = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        # ── Row 1: axis selectors ─────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("X-Axis:"))
        self._x_combo = QComboBox()
        self._x_combo.setMinimumWidth(160)
        ctrl.addWidget(self._x_combo)
        ctrl.addWidget(QLabel("Y-Axis:"))
        self._y_combo = QComboBox()
        self._y_combo.setMinimumWidth(160)
        ctrl.addWidget(self._y_combo)
        ctrl.addSpacing(12)

        # ── Symbol style ─────────────────────────────────────────
        ctrl.addWidget(QLabel("Symbol:"))
        self._sym_combo = QComboBox()
        for name, _ in _XY_SYMBOLS:
            self._sym_combo.addItem(name)
        self._sym_combo.setCurrentIndex(1)  # filled circle default
        ctrl.addWidget(self._sym_combo)
        ctrl.addSpacing(8)

        # ── Symbol size ──────────────────────────────────────────
        ctrl.addWidget(QLabel("Size:"))
        self._size_spin = QSpinBox()
        self._size_spin.setRange(2, 30)
        self._size_spin.setValue(6)
        self._size_spin.setFixedWidth(55)
        ctrl.addWidget(self._size_spin)
        ctrl.addSpacing(12)

        # ── Regression checkbox ──────────────────────────────────
        self._regress_cb = QCheckBox("Regression")
        self._regress_cb.setToolTip("Show linear regression line with R²")
        ctrl.addWidget(self._regress_cb)
        ctrl.addSpacing(8)

        btn_plot = QPushButton("Plot")
        btn_plot.clicked.connect(self._do_plot)
        ctrl.addWidget(btn_plot)

        btn_swap = QPushButton("⇄ Swap")
        btn_swap.setToolTip("Swap X and Y axis parameters")
        btn_swap.clicked.connect(self._swap_axes)
        ctrl.addWidget(btn_swap)

        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self._clear_plot)
        ctrl.addWidget(btn_clear)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        # ── Populate combos ───────────────────────────────────────
        all_params: list[str] = []
        seen = set()
        for entry in self._logs.values():
            for p in entry.available_params():
                if p not in seen:
                    seen.add(p)
                    all_params.append(p)
        self._x_combo.addItems(all_params)
        self._y_combo.addItems(all_params)
        if len(all_params) >= 2:
            self._x_combo.setCurrentIndex(0)
            self._y_combo.setCurrentIndex(1)

        # ── Plot widget ───────────────────────────────────────────
        self._plot = pg.PlotWidget()
        bg = THEME.c('plot_bg')
        fg = THEME.c('plot_fg')
        self._plot.setBackground(bg)
        self._plot.showGrid(x=True, y=True, alpha=THEME.plot_grid_alpha())
        for ax_name in ('left', 'bottom'):
            ax = self._plot.getAxis(ax_name)
            pen = pg.mkPen(fg)
            ax.setPen(pen)
            ax.setTextPen(pen)
        self._legend = self._plot.addLegend(offset=(10, 10))
        layout.addWidget(self._plot)

    def _do_plot(self):
        x_param = self._x_combo.currentText()
        y_param = self._y_combo.currentText()
        if not x_param or not y_param:
            return
        self._plot.setLabel('bottom', x_param)
        self._plot.setLabel('left', y_param)

        sym_idx = self._sym_combo.currentIndex()
        sym_str = _XY_SYMBOLS[sym_idx][1]
        size = self._size_spin.value()
        # Outline vs filled: outline uses mkPen with color, filled uses no pen
        filled = (self._sym_combo.currentText().lower().find('filled') >= 0
                  or self._sym_combo.currentIndex() == 1)

        for entry in self._logs.values():
            if not entry.visible:
                continue
            if x_param not in entry.columns or y_param not in entry.columns:
                continue
            x = entry.columns[x_param]
            y = entry.columns[y_param]
            mask = ~(np.isnan(x) | np.isnan(y))
            pen = pg.mkPen(None) if filled else pg.mkPen(entry.color, width=1)
            brush = pg.mkBrush(entry.color) if filled else pg.mkBrush(None)
            scatter = pg.ScatterPlotItem(
                x=x[mask], y=y[mask],
                pen=pen, brush=brush,
                symbol=sym_str, size=size,
                name=entry.name)
            self._plot.addItem(scatter)
            self._curves.append(scatter)

            if self._regress_cb.isChecked() and len(x[mask]) > 1:
                # Linear regression
                xm, ym = x[mask], y[mask]
                poly = np.polyfit(xm, ym, 1)
                y_fit = np.polyval(poly, xm)
                
                # Calculate R-squared
                y_mean = np.mean(ym)
                ss_tot = np.sum((ym - y_mean)**2)
                ss_res = np.sum((ym - y_fit)**2)
                r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
                
                # Sort X for plotting a continuous line
                sort_idx = np.argsort(xm)
                reg_pen = pg.mkPen(entry.color, width=2, style=Qt.PenStyle.DashLine)
                
                reg_name = f"{entry.name} fit (R²={r_squared:.3f})"
                reg_line = pg.PlotDataItem(xm[sort_idx], y_fit[sort_idx], pen=reg_pen, name=reg_name)
                self._plot.addItem(reg_line)
                self._curves.append(reg_line)

    def _swap_axes(self):
        """Swap the X and Y axis parameter selections and re-render.

        Previously wired to a button that referenced an undefined method —
        clicking ⇄ Swap crashed the X-Y Plotter dialog. The fix simply
        exchanges the two combo indices and re-runs the plot.
        """
        xi = self._x_combo.currentIndex()
        yi = self._y_combo.currentIndex()
        if xi < 0 or yi < 0:
            return
        # Block signals during the swap so any future currentIndexChanged
        # connections do not fire twice on a swap.
        self._x_combo.blockSignals(True)
        self._y_combo.blockSignals(True)
        try:
            self._x_combo.setCurrentIndex(yi)
            self._y_combo.setCurrentIndex(xi)
        finally:
            self._x_combo.blockSignals(False)
            self._y_combo.blockSignals(False)
        self._clear_plot()
        self._do_plot()

    def _clear_plot(self):
        for c in self._curves:
            self._plot.removeItem(c)
        self._curves.clear()
