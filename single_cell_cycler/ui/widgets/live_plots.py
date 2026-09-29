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
pg.setConfigOption("antialias", False)  # Fast rasterization for high-rate data

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


class VoltageAxisItem(pg.AxisItem):
    """Left Y-Axis explicitly formatted for Cell Voltage (0.0 to 6.0 V)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setPen(pg.mkPen(_C1_V, width=1.8))
        self.setTextPen(pg.mkPen(_C1_V))
        self.setTickPen(pg.mkPen("#334155", width=1))
        self.setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 9, pg.QtGui.QFont.Weight.Bold))
        self.sync_ticks()

    def sync_ticks(self) -> None:
        """Establish synchronized ticks aligned 1:1 with Current axis across 6.0 units span."""
        major = [(float(v), f"{v}.0 V") for v in range(7)]
        minor = [(float(v) + 0.5, f"{v}.5 V") for v in range(6)]
        self.setTicks([major, minor])

    def tickStrings(self, values, scale, spacing):
        return [f"{v:.1f} V" for v in values]


class CurrentAxisItem(pg.AxisItem):
    """Right Y-Axis explicitly formatted for Cell Current (-3.0 to +3.0 A).

    Both Left and Right axes share the exact same 6.0 units span and identical
    fractional tick heights, ensuring that both active grids align onto the exact
    same horizontal lines across the canvas without any conflicting dual lines.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setPen(pg.mkPen(_C1_I, width=1.8))
        self.setTextPen(pg.mkPen(_C1_I))
        self.setTickPen(pg.mkPen("#334155", width=1))
        self.setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 9, pg.QtGui.QFont.Weight.Bold))
        self.sync_ticks()

    def sync_ticks(self) -> None:
        """Establish synchronized ticks aligned 1:1 with Voltage axis across 6.0 units span."""
        major = [(float(i - 3), f"{i - 3:+.1f} A" if (i - 3) != 0 else "0.0 A") for i in range(7)]
        minor = [(float(i - 3) + 0.5, f"{i - 3 + 0.5:+.1f} A") for i in range(6)]
        self.setTicks([major, minor])

    def tickStrings(self, values, scale, spacing):
        return [f"{v:+.1f} A" if abs(v) > 0.01 else "0.0 A" for v in values]


class TemperatureAxisItem(pg.AxisItem):
    """Left Y-Axis explicitly formatted for Temperature (0 to 70 °C)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setPen(pg.mkPen("#fb923c", width=1.8))
        self.setTextPen(pg.mkPen("#fb923c"))
        self.setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 9, pg.QtGui.QFont.Weight.Bold))

    def tickStrings(self, values, scale, spacing):
        return [f"{v:.0f} °C" for v in values]


class LivePlotWidget(QWidget):
    """Multi-tab real-time telemetry chart suite optimized for high performance."""

    def __init__(self, max_buffer_points: int = 1_000_000, parent: QWidget | None = None):
        super().__init__(parent)
        self.max_points = max_buffer_points

        # ------------------------------------------------------------------ #
        # Time-series buffers (1,000,000 samples = >27 hours at 10 Hz)        #
        # ------------------------------------------------------------------ #
        self._t: collections.deque = collections.deque(maxlen=self.max_points)
        self._v: collections.deque = collections.deque(maxlen=self.max_points)
        self._i: collections.deque = collections.deque(maxlen=self.max_points)
        self._t_term: collections.deque = collections.deque(maxlen=self.max_points)
        self._t_body: collections.deque = collections.deque(maxlen=self.max_points)

        # V-Q
        self._vq_cap: collections.deque = collections.deque(maxlen=100_000)
        self._vq_volt: collections.deque = collections.deque(maxlen=100_000)

        self.start_epoch: float = time.time()

        # State
        self._relay_on: bool = False
        self._cell_num: int = 1
        self._dirty: bool = False
        self._last_pen_cell: int | None = None

        self._setup_ui()

    # ----------------------------------------------------------------------- #
    # Public API                                                               #
    # ----------------------------------------------------------------------- #

    def set_relay_state(self, relay_on: bool, cell_num: int) -> None:
        """Called by MainWindow during 10 Hz tick.

        A NaN break is inserted ONLY when the cell selection physically switches
        (Cell 1 <-> Cell 2), preventing artificial cutting of the graph during
        normal cycling, transitions, or rest periods.
        """
        cell_switched = (self._cell_num != cell_num) and (len(self._t) > 0)
        self._relay_on = relay_on
        self._cell_num = cell_num

        if cell_switched:
            self._insert_nan_break()

        if relay_on:
            self._dirty = True

    def add_telemetry(self, data: CellDataTelemetry, step_mah: float = 0.0) -> None:
        """Buffer a new sample. Points are only pushed when the relay is ON."""
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
        """Redraw only the active visible tab. Called at 10 Hz by MainWindow."""
        if not self._dirty or not self._t:
            return
        self._dirty = False
        self._render_tab(self.tabs.currentIndex(), force=False)

    def _on_tab_changed(self, index: int) -> None:
        """Instantly render the newly selected tab using buffered data."""
        self._sync_current_view()
        self._dirty = True
        self._render_tab(index, force=True)

    def _render_tab(self, tab_idx: int, force: bool = False) -> None:
        """Render a specific tab with minimal conversions and GPU/paint overhead."""
        if not self._t:
            return

        # Cache pen updates so mkPen is called only when the cell changes
        cell_changed = (self._cell_num != self._last_pen_cell)
        if cell_changed or force:
            v_col = _C1_V if self._cell_num == 1 else _C2_V
            i_col = _C1_I if self._cell_num == 1 else _C2_I
            self.curve_voltage.setPen(pg.mkPen(v_col, width=2.0))
            self.curve_current.setPen(pg.mkPen(i_col, width=1.8))
            self.curve_vq_current.setPen(pg.mkPen(v_col, width=2.2))
            self._update_axis_styling(v_col, i_col)
            self._last_pen_cell = self._cell_num

        if tab_idx == 0:
            # Tab 0 – Voltage & Current (convert only what is needed)
            t = np.array(self._t)
            v = np.array(self._v)
            i_arr = np.array(self._i)
            self.curve_voltage.setData(t, v)
            self.curve_current.setData(t, i_arr)
            # Fixed Y-ranges: 0-6V for voltage, -3 to 3A for current (aligned 6.0 unit spans)
            self.plot_vi.setYRange(0.0, 6.0, padding=0.0)
            self.view_current.setYRange(-3.0, 3.0, padding=0.0)
            # Auto-wrap / auto-expand X range smoothly to fit complete test dataset
            if len(t) > 0 and not np.isnan(t[-1]):
                max_t = max(10.0, float(t[-1]))
                self.plot_vi.setXRange(0.0, max_t, padding=0.01)

        elif tab_idx == 1:
            # Tab 1 – Temperature (convert only temperature buffers)
            t = np.array(self._t)
            self.curve_term_temp.setData(t, np.array(self._t_term))
            self.curve_body_temp.setData(t, np.array(self._t_body))
            # Fixed Y-range: 0-70°C for temperature
            self.plot_temp.setYRange(0.0, 70.0, padding=0.0)
            if len(t) > 0 and not np.isnan(t[-1]):
                max_t = max(10.0, float(t[-1]))
                self.plot_temp.setXRange(0.0, max_t, padding=0.01)

        elif tab_idx == 2:
            # Tab 2 – V-Q Curve
            if self._vq_cap:
                caps = np.array(self._vq_cap)
                volts = np.array(self._vq_volt)
                self.curve_vq_current.setData(caps, volts)
                self.plot_vq.setYRange(0.0, 6.0, padding=0.0)
                if len(caps) > 0:
                    max_cap = max(100.0, float(np.nanmax(caps)))
                    self.plot_vq.setXRange(0.0, max_cap, padding=0.02)

    # ----------------------------------------------------------------------- #
    # Step / Cycle Events                                                      #
    # ----------------------------------------------------------------------- #

    def reset_step_vq(self) -> None:
        """Archive current V-Q trace when a new step begins."""
        if len(self._vq_cap) > 10:
            caps = np.array(self._vq_cap)
            volts = np.array(self._vq_volt)
            color = _C1_V if self._cell_num == 1 else _C2_V
            p_hist = self.plot_vq.plot(
                caps,
                volts,
                pen=pg.mkPen(color, width=1.0, style=pg.QtCore.Qt.PenStyle.DashLine),
            )
            p_hist.setClipToView(True)
        self._vq_cap.clear()
        self._vq_volt.clear()

    def add_cycle_summary(
        self, cycle_idx: int, discharge_mah: float, coulombic_eff: float
    ) -> None:
        """No-op: Cycle Aging tab has been removed."""
        pass

    def reset_all(self) -> None:
        """Full reset for a new test run."""
        self._t.clear(); self._v.clear(); self._i.clear()
        self._t_term.clear(); self._t_body.clear()
        self._vq_cap.clear(); self._vq_volt.clear()
        self.plot_vq.clear()
        self.curve_vq_current = self.plot_vq.plot(
            pen=pg.mkPen(_C1_V, width=2.2)
        )
        self.curve_vq_current.setClipToView(True)
        self.start_epoch = time.time()
        self._relay_on = False
        self._dirty = False
        self._last_pen_cell = None
        self.curve_voltage.setData([], [])
        self.curve_current.setData([], [])
        self.curve_term_temp.setData([], [])
        self.curve_body_temp.setData([], [])
        self.plot_vi.setYRange(0.0, 6.0, padding=0.0)
        self.view_current.setYRange(-3.0, 3.0, padding=0.0)
        self.plot_temp.setYRange(0.0, 70.0, padding=0.0)

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
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs)
        self._build_vi_tab()
        self._build_temp_tab()
        self._build_vq_tab()

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

        self.ax_voltage = VoltageAxisItem(orientation="left")
        self.ax_current = CurrentAxisItem(orientation="right")
        self.plot_vi = pg.PlotWidget(axisItems={"left": self.ax_voltage, "right": self.ax_current})
        self.plot_vi.showGrid(x=True, y=True, alpha=0.20)
        self.plot_vi.plotItem.getAxis("bottom").setTickPen(pg.mkPen("#334155", width=1))
        self.ax_voltage.setTickPen(pg.mkPen("#334155", width=1))
        self.ax_current.setTickPen(pg.mkPen("#334155", width=1))
        self.plot_vi.setLabel("bottom", "<span style='color:#94a3b8; font-weight:600;'>Elapsed Time (s)</span>")

        # Fixed Y-axis: 0.0 to 6.0 V (aligned 1:1 with Current -3 to +3 A over 6.0 units)
        self.plot_vi.setYRange(0.0, 6.0, padding=0.0)
        self.plot_vi.plotItem.getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        self.plot_vi.plotItem.getViewBox().enableAutoRange(axis=pg.ViewBox.XAxis, enable=True)
        self.plot_vi.plotItem.getViewBox().setLimits(xMin=0.0, yMin=0.0, yMax=6.0)

        self.curve_voltage = self.plot_vi.plot(
            pen=pg.mkPen(_C1_V, width=2.0), connect="finite"
        )
        self.curve_voltage.setClipToView(True)

        self.view_current = pg.ViewBox()
        self.plot_vi.plotItem.scene().addItem(self.view_current)
        ax_r = self.plot_vi.plotItem.getAxis("right")
        ax_r.linkToView(self.view_current)
        self.plot_vi.plotItem.showAxis("right")
        self.view_current.setXLink(self.plot_vi.plotItem)

        # Fixed Y-axis: -3.0 to +3.0 A (current range -3 to 3 A)
        self.view_current.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        self.view_current.setYRange(-3.0, 3.0, padding=0.0)
        self.view_current.setLimits(yMin=-3.0, yMax=3.0)

        self.curve_current = pg.PlotDataItem(
            pen=pg.mkPen(_C1_I, width=1.8), connect="finite"
        )
        self.curve_current.setClipToView(True)
        self.view_current.addItem(self.curve_current)
        self.plot_vi.plotItem.getViewBox().sigResized.connect(self._sync_current_view)
        self._update_axis_styling(_C1_V, _C1_I)

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
        self.ax_temp = TemperatureAxisItem(orientation="left")
        self.plot_temp = pg.PlotWidget(axisItems={"left": self.ax_temp})
        self.plot_temp.showGrid(x=True, y=True, alpha=0.18)
        self.ax_temp.setTickPen(pg.mkPen("#334155", width=1))
        self.plot_temp.plotItem.getAxis("bottom").setTickPen(pg.mkPen("#334155", width=1))
        self.plot_temp.setLabel("left", "<span style='color:#fb923c; font-weight:bold; font-size:12px;'>🌡 Temperature (0 – 70 °C)</span>")
        self.plot_temp.setLabel("bottom", "<span style='color:#94a3b8; font-weight:600;'>Elapsed Time (s)</span>")

        # Share the exact same X-axis with the Voltage/Current plot
        self.plot_temp.setXLink(self.plot_vi)

        # Fixed Y-axis: 0.0 to 70.0 °C
        self.plot_temp.setYRange(0.0, 70.0, padding=0.0)
        self.plot_temp.plotItem.getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        self.plot_temp.plotItem.getViewBox().enableAutoRange(axis=pg.ViewBox.XAxis, enable=True)
        self.plot_temp.plotItem.getViewBox().setLimits(xMin=0.0, yMin=0.0, yMax=70.0)

        self.curve_term_temp = self.plot_temp.plot(
            pen=pg.mkPen(_TERM_COLOR, width=2.0), connect="finite"
        )
        self.curve_term_temp.setClipToView(True)

        self.curve_body_temp = self.plot_temp.plot(
            pen=pg.mkPen(_BODY_COLOR, width=2.0), connect="finite"
        )
        self.curve_body_temp.setClipToView(True)

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
        self.ax_vq = VoltageAxisItem(orientation="left")
        self.plot_vq = pg.PlotWidget(axisItems={"left": self.ax_vq})
        self.plot_vq.showGrid(x=True, y=True, alpha=0.18)
        self.ax_vq.setTickPen(pg.mkPen("#334155", width=1))
        self.plot_vq.plotItem.getAxis("bottom").setTickPen(pg.mkPen("#334155", width=1))
        self.plot_vq.setLabel("left", "<span style='color:#38bdf8; font-weight:bold; font-size:12px;'>⚡ Cell Voltage (0 – 5 V)</span>")
        self.plot_vq.setLabel("bottom", "<span style='color:#94a3b8; font-weight:600;'>Step Capacity (mAh)</span>")
        self.curve_vq_current = self.plot_vq.plot(pen=pg.mkPen(_C1_V, width=2.2))
        self.curve_vq_current.setClipToView(True)
        vlay.addWidget(self.plot_vq)
        self.tabs.addTab(tab, "📈 V-Q Curve")

    def _update_axis_styling(self, v_col: str, i_col: str) -> None:
        """Dynamically style axes lines, text, and titles to match active cell curve colors."""
        if hasattr(self, "ax_voltage"):
            self.ax_voltage.setPen(pg.mkPen(v_col, width=1.8))
            self.ax_voltage.setTextPen(pg.mkPen(v_col))
            self.ax_voltage.setTickPen(pg.mkPen("#334155", width=1))
            self.ax_voltage.sync_ticks()
            self.plot_vi.setLabel(
                "left",
                f"<span style='color:{v_col}; font-weight:bold; font-size:12px;'>⚡ Cell {self._cell_num} Voltage (0 – 6 V)</span>",
            )
        if hasattr(self, "ax_current"):
            self.ax_current.setPen(pg.mkPen(i_col, width=1.8))
            self.ax_current.setTextPen(pg.mkPen(i_col))
            self.ax_current.setTickPen(pg.mkPen("#334155", width=1))
            self.ax_current.sync_ticks()
            self.plot_vi.plotItem.getAxis("right").setLabel(
                f"<span style='color:{i_col}; font-weight:bold; font-size:12px;'>⚡ Cell {self._cell_num} Current (-3 – +3 A)</span>",
            )

    def update_font_size(self, pt: int) -> None:
        """Scale plot axis fonts dynamically when application font size changes."""
        tick_pt = max(8, pt - 2)
        font = pg.QtGui.QFont("Segoe UI", tick_pt, pg.QtGui.QFont.Weight.Bold)
        axes_to_scale = [
            getattr(self, "ax_voltage", None),
            getattr(self, "ax_current", None),
            getattr(self, "ax_temp", None),
            getattr(self, "ax_vq", None),
        ]
        for plot in [getattr(self, "plot_vi", None), getattr(self, "plot_temp", None), getattr(self, "plot_vq", None)]:
            if plot and hasattr(plot, "plotItem"):
                b_ax = plot.plotItem.getAxis("bottom")
                if b_ax:
                    axes_to_scale.append(b_ax)
        for ax in axes_to_scale:
            if ax is not None:
                ax.setStyle(tickFont=font)
                if hasattr(ax, "sync_ticks"):
                    ax.sync_ticks()

