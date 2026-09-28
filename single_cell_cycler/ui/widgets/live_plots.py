"""High-performance real-time plotting widget using pyqtgraph.

Design:
- ``tick_update()`` is the sole redraw entry point, called by MainWindow at a
  deterministic 10 Hz rate (100 ms QTimer).  The widget is PASSIVE – it never
  owns its own redraw timer.
- ``set_relay_state(relay_on, cell_num)`` gates data ingestion:  when the
  relay is OFF a NaN break-point is inserted so the line shows a visible gap.
- Per-cell colour coding:  cyan = Cell 1, orange = Cell 2 (voltage);
  green = Cell 1, purple = Cell 2 (current).
- Inline colour-coded legends at the top of every tab.
"""

from __future__ import annotations

import collections
import time
from typing import List

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from ...comm.packet_codec import CellDataTelemetry
from ..theme import (
    BG_PANEL,
    COLOR_ACCENT,
    COLOR_CHARGE,
    TEXT_MUTED,
    TEXT_SECONDARY,
)

# --------------------------------------------------------------------------- #
# pyqtgraph global config                                                      #
# --------------------------------------------------------------------------- #
pg.setConfigOption("background", BG_PANEL)
pg.setConfigOption("foreground", TEXT_SECONDARY)
pg.setConfigOption("antialias", True)

# Segment colours per cell
_C1_V = COLOR_ACCENT    # cyan  – Cell 1 voltage
_C2_V = "#f97316"       # orange – Cell 2 voltage
_C1_I = COLOR_CHARGE    # green  – Cell 1 current
_C2_I = "#a855f7"       # purple – Cell 2 current
_TERM_COLOR = "#f97316"
_BODY_COLOR = "#ec4899"


def _legend_label(color: str, text: str) -> QLabel:
    lbl = QLabel(f"  ■  {text}")
    lbl.setStyleSheet(
        f"color: {color}; font-size: 11px; font-weight: 600; background: transparent;"
    )
    return lbl


def _legend_bar(*items) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setContentsMargins(8, 2, 8, 0)
    row.setSpacing(4)
    for item in items:
        row.addWidget(item)
    row.addStretch()
    return row


class LivePlotWidget(QWidget):
    """Multi-tab real-time telemetry chart suite."""

    def __init__(self, max_buffer_points: int = 10_000, parent: QWidget | None = None):
        super().__init__(parent)
        self.max_points = max_buffer_points

        # ------------------------------------------------------------------ #
        # Time-series buffers                                                  #
        # ------------------------------------------------------------------ #
        self._t: collections.deque = collections.deque(maxlen=self.max_points)
        self._v: collections.deque = collections.deque(maxlen=self.max_points)
        self._i: collections.deque = collections.deque(maxlen=self.max_points)
        self._t_term: collections.deque = collections.deque(maxlen=self.max_points)
        self._t_body: collections.deque = collections.deque(maxlen=self.max_points)

        # V-Q
        self._vq_cap: collections.deque = collections.deque(maxlen=3000)
        self._vq_volt: collections.deque = collections.deque(maxlen=3000)

        # Cycle aging
        self._cycle_idx: List[int] = []
        self._cycle_cap: List[float] = []

        self.start_epoch: float = time.time()

        # State
        self._relay_on: bool = False
        self._cell_num: int = 1
        self._dirty: bool = False

        self._setup_ui()

    # ----------------------------------------------------------------------- #
    # Public API                                                               #
    # ----------------------------------------------------------------------- #

    def set_relay_state(self, relay_on: bool, cell_num: int) -> None:
        """Called by MainWindow whenever the relay readback changes.

        relay_on=False → NaN gap is inserted so the live chart shows a break.
        """
        was_on = self._relay_on
        self._relay_on = relay_on
        self._cell_num = cell_num

        if was_on and not relay_on:
            self._insert_nan_break()
        if relay_on:
            self._dirty = True

    def add_telemetry(self, data: CellDataTelemetry, step_mah: float = 0.0) -> None:
        """Buffer a new sample.  Points are only pushed when the relay is ON."""
        if not self._relay_on:
            return

        elapsed = (
            data.timestamp - self.start_epoch
            if data.timestamp > 0
            else time.time() - self.start_epoch
        )
        self._t.append(elapsed)
        self._v.append(data.voltage)
        self._i.append(data.current)
        self._t_term.append(data.terminal_temp)
        self._t_body.append(data.body_temp)

        self._vq_cap.append(abs(step_mah))
        self._vq_volt.append(data.voltage)

        self._dirty = True

    def tick_update(self) -> None:
        """Redraw the visible tab.  Called at a fixed 10 Hz rate by MainWindow."""
        if not self._dirty or not self._t:
            return
        self._dirty = False

        t = np.array(self._t)
        v = np.array(self._v)
        i_arr = np.array(self._i)
        t_term = np.array(self._t_term)
        t_body = np.array(self._t_body)

        v_col = _C1_V if self._cell_num == 1 else _C2_V
        i_col = _C1_I if self._cell_num == 1 else _C2_I
        cur_tab = self.tabs.currentIndex()

        if cur_tab == 0:
            self.curve_voltage.setPen(pg.mkPen(v_col, width=2.0))
            self.curve_current.setPen(pg.mkPen(i_col, width=1.8))
            self.curve_voltage.setData(t, v)
            self.curve_current.setData(t, i_arr)
            fi = i_arr[np.isfinite(i_arr)]
            if len(fi) > 0:
                lo, hi = float(fi.min()), float(fi.max())
                pad = max(0.3, (hi - lo) * 0.12)
                self.view_current.setYRange(lo - pad, hi + pad, padding=0)

        elif cur_tab == 1:
            self.curve_term_temp.setData(t, t_term)
            self.curve_body_temp.setData(t, t_body)

        elif cur_tab == 2:
            if self._vq_cap:
                v_col_vq = _C1_V if self._cell_num == 1 else _C2_V
                self.curve_vq_current.setPen(pg.mkPen(v_col_vq, width=2.2))
                self.curve_vq_current.setData(
                    np.array(self._vq_cap), np.array(self._vq_volt)
                )

    # ----------------------------------------------------------------------- #
    # Step / Cycle Events                                                      #
    # ----------------------------------------------------------------------- #

    def reset_step_vq(self) -> None:
        """Archive current V-Q trace when a new step begins."""
        if len(self._vq_cap) > 10:
            caps = np.array(self._vq_cap)
            volts = np.array(self._vq_volt)
            color = _C1_V if self._cell_num == 1 else _C2_V
            self.plot_vq.plot(
                caps,
                volts,
                pen=pg.mkPen(color, width=1.0, style=pg.QtCore.Qt.PenStyle.DashLine),
            )
        self._vq_cap.clear()
        self._vq_volt.clear()

    def add_cycle_summary(
        self, cycle_idx: int, discharge_mah: float, coulombic_eff: float
    ) -> None:
        self._cycle_idx.append(cycle_idx)
        self._cycle_cap.append(discharge_mah)
        self.curve_aging_cap.setData(self._cycle_idx, self._cycle_cap)

    def reset_all(self) -> None:
        """Full reset for a new test run."""
        self._t.clear(); self._v.clear(); self._i.clear()
        self._t_term.clear(); self._t_body.clear()
        self._vq_cap.clear(); self._vq_volt.clear()
        self._cycle_idx.clear(); self._cycle_cap.clear()
        self.plot_vq.clear()
        self.curve_vq_current = self.plot_vq.plot(
            pen=pg.mkPen(_C1_V, width=2.2)
        )
        self.start_epoch = time.time()
        self._relay_on = False
        self._dirty = False
        self.curve_voltage.setData([], [])
        self.curve_current.setData([], [])
        self.curve_term_temp.setData([], [])
        self.curve_body_temp.setData([], [])
        self.curve_aging_cap.setData([], [])

    # ----------------------------------------------------------------------- #
    # Internal helpers                                                         #
    # ----------------------------------------------------------------------- #

    def _insert_nan_break(self) -> None:
        last_t = self._t[-1] if self._t else (time.time() - self.start_epoch)
        self._t.append(last_t + 0.001)
        self._v.append(float("nan"))
        self._i.append(float("nan"))
        self._t_term.append(float("nan"))
        self._t_body.append(float("nan"))
        self._dirty = True

    def _sync_current_view(self) -> None:
        self.view_current.setGeometry(
            self.plot_vi.plotItem.getViewBox().sceneBoundingRect()
        )
        self.view_current.linkedViewChanged(
            self.plot_vi.plotItem.getViewBox(), self.view_current.XAxis
        )

    # ----------------------------------------------------------------------- #
    # UI Setup                                                                 #
    # ----------------------------------------------------------------------- #

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self._build_vi_tab()
        self._build_temp_tab()
        self._build_vq_tab()
        self._build_aging_tab()

    def _build_vi_tab(self) -> None:
        tab = QWidget()
        vlay = QVBoxLayout(tab)
        vlay.setContentsMargins(4, 4, 4, 2)
        vlay.setSpacing(2)

        note = QLabel("  (gap = relay OFF / cell switching)")
        note.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;"
        )
        vlay.addLayout(
            _legend_bar(
                _legend_label(_C1_V, "Cell 1 Voltage (V)"),
                _legend_label(_C2_V, "Cell 2 Voltage (V)"),
                _legend_label(_C1_I, "Cell 1 Current (A)"),
                _legend_label(_C2_I, "Cell 2 Current (A)"),
                note,
            )
        )

        self.plot_vi = pg.PlotWidget()
        self.plot_vi.showGrid(x=True, y=True, alpha=0.20)
        self.plot_vi.setLabel("left", "Cell Voltage", units="V", color=_C1_V)
        self.plot_vi.setLabel("bottom", "Elapsed Time", units="s")

        self.curve_voltage = self.plot_vi.plot(
            pen=pg.mkPen(_C1_V, width=2.0), connect="finite"
        )

        self.view_current = pg.ViewBox()
        self.plot_vi.plotItem.scene().addItem(self.view_current)
        ax_r = self.plot_vi.plotItem.getAxis("right")
        ax_r.linkToView(self.view_current)
        self.plot_vi.plotItem.showAxis("right")
        ax_r.setLabel("Cell Current", units="A", color=_C1_I)
        self.view_current.setXLink(self.plot_vi.plotItem)

        self.curve_current = pg.PlotCurveItem(
            pen=pg.mkPen(_C1_I, width=1.8), connect="finite"
        )
        self.view_current.addItem(self.curve_current)
        self.plot_vi.plotItem.getViewBox().sigResized.connect(self._sync_current_view)

        vlay.addWidget(self.plot_vi)
        self.tabs.addTab(tab, "⚡ Voltage & Current")

    def _build_temp_tab(self) -> None:
        tab = QWidget()
        vlay = QVBoxLayout(tab)
        vlay.setContentsMargins(4, 4, 4, 2)
        vlay.setSpacing(2)
        vlay.addLayout(
            _legend_bar(
                _legend_label(_TERM_COLOR, "Terminal Temp (°C)"),
                _legend_label(_BODY_COLOR, "Body Temp (°C)"),
            )
        )
        self.plot_temp = pg.PlotWidget()
        self.plot_temp.showGrid(x=True, y=True, alpha=0.20)
        self.plot_temp.setLabel("left", "Temperature", units="°C")
        self.plot_temp.setLabel("bottom", "Elapsed Time", units="s")
        self.curve_term_temp = self.plot_temp.plot(
            pen=pg.mkPen(_TERM_COLOR, width=2.0), connect="finite"
        )
        self.curve_body_temp = self.plot_temp.plot(
            pen=pg.mkPen(_BODY_COLOR, width=2.0), connect="finite"
        )
        vlay.addWidget(self.plot_temp)
        self.tabs.addTab(tab, "🌡 Temperature")

    def _build_vq_tab(self) -> None:
        tab = QWidget()
        vlay = QVBoxLayout(tab)
        vlay.setContentsMargins(4, 4, 4, 2)
        vlay.setSpacing(2)
        vlay.addLayout(
            _legend_bar(
                _legend_label(_C1_V, "Cell 1 – Active Step"),
                _legend_label(_C2_V, "Cell 2 – Active Step"),
                _legend_label("#475569", "Historical Steps (dashed)"),
            )
        )
        self.plot_vq = pg.PlotWidget()
        self.plot_vq.showGrid(x=True, y=True, alpha=0.20)
        self.plot_vq.setLabel("left", "Voltage", units="V")
        self.plot_vq.setLabel("bottom", "Step Capacity", units="mAh")
        self.curve_vq_current = self.plot_vq.plot(pen=pg.mkPen(_C1_V, width=2.2))
        vlay.addWidget(self.plot_vq)
        self.tabs.addTab(tab, "📈 V-Q Curve")

    def _build_aging_tab(self) -> None:
        tab = QWidget()
        vlay = QVBoxLayout(tab)
        vlay.setContentsMargins(4, 4, 4, 2)
        vlay.setSpacing(2)
        vlay.addLayout(
            _legend_bar(_legend_label("#a855f7", "Discharge Capacity per Cycle (mAh)"))
        )
        self.plot_aging = pg.PlotWidget()
        self.plot_aging.showGrid(x=True, y=True, alpha=0.20)
        self.plot_aging.setLabel("left", "Discharge Capacity", units="mAh", color="#a855f7")
        self.plot_aging.setLabel("bottom", "Cycle Number")
        self.curve_aging_cap = self.plot_aging.plot(
            pen=pg.mkPen("#a855f7", width=2.0),
            symbol="o",
            symbolSize=6,
            symbolBrush="#a855f7",
            symbolPen=pg.mkPen("#c084fc", width=1),
        )
        vlay.addWidget(self.plot_aging)
        self.tabs.addTab(tab, "🔋 Cycle Aging")
