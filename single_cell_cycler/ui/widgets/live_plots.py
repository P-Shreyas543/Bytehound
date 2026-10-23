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
from enum import Enum, auto
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...comm.packet_codec import CellDataTelemetry
from ...core.aging_analysis import (
    DegradationForecast,
    fit_capacity_degradation,
)
from ...core.dqv_analysis import (
    DQVPeak,
    DQVProfile,
    compute_dq_dv,
    find_dqv_peaks,
)
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

# Differential Capacity (dQ/dV) and multi-cycle palette (IMP-05)
CYCLE_PALETTE = [
    "#38bdf8",  # Sky blue
    "#22c55e",  # Emerald green
    "#a855f7",  # Purple
    "#f59e0b",  # Amber
    "#ec4899",  # Pink
    "#06b6d4",  # Cyan
    "#eab308",  # Yellow
    "#10b981",  # Teal
    "#6366f1",  # Indigo
    "#f43f5e",  # Rose
]
_DQV_CHARGE_COLOR = "#38bdf8"
_DQV_DISCHARGE_COLOR = "#ec4899"
_PEAK_MARKER_COLOR = "#facc15"

# Aging & Health Metrology palette (IMP-07)
_AGING_Q_DIS_COLOR = "#38bdf8"    # Sky blue
_AGING_Q_CHG_COLOR = "#22c55e"    # Emerald green
_AGING_PROJ_COLOR = "#facc15"     # Yellow / Gold
_AGING_EOL_LINE_COLOR = "#f43f5e" # Rose / Red
_AGING_CE_COLOR = "#10b981"       # Teal / Emerald
_AGING_EE_COLOR = "#a855f7"       # Purple
_AGING_DCIR_COLOR = "#f59e0b"     # Amber


class ZoomMode(Enum):
    """Active time-series framing and auto-ranging mode."""
    FIT_ALL = auto()        # 0.0 to latest elapsed time (Continuous Auto-Wrap)
    CURRENT_STEP = auto()   # Start of active profile step to latest
    CURRENT_CYCLE = auto()  # Start of active cycle loop to latest
    LAST_10M = auto()       # Sliding 10-minute trailing window
    LAST_1M = auto()        # Sliding 1-minute trailing window
    MANUAL = auto()         # Freeform user mouse pan / zoom (do not override)


_ZOOM_BTN_STYLE_DEFAULT = """
QPushButton {
    background-color: #1e293b;
    color: #94a3b8;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 2px 7px;
    font-size: 11px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #334155;
    color: #f8fafc;
    border-color: #475569;
}
"""

_ZOOM_BTN_STYLE_ACTIVE = """
QPushButton {
    background-color: #0284c7;
    color: #ffffff;
    border: 1px solid #38bdf8;
    border-radius: 4px;
    padding: 2px 7px;
    font-size: 11px;
    font-weight: 700;
}
QPushButton:hover {
    background-color: #0369a1;
}
"""

_HUD_STYLE = """
QLabel {
    background-color: #0f172a;
    border: 1px solid #334155;
    border-radius: 5px;
    padding: 2px 8px;
    font-family: Consolas, monospace;
    font-size: 11px;
    color: #94a3b8;
}
"""


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
        self._vq_history_curves: List[Tuple[str, pg.PlotDataItem]] = []

        self.start_epoch: float = time.time()

        # State
        self._relay_on: bool = False
        self._cell_num: int = 1
        self._dirty: bool = False
        self._last_pen_cell: int | None = None
        self._event_markers: collections.deque[str] = collections.deque(maxlen=6)

        # Quick-Zoom and Framing State (IMP-02)
        self._zoom_mode: ZoomMode = ZoomMode.FIT_ALL
        self._current_step_start_t: float = 0.0
        self._current_cycle_start_t: float = 0.0
        self._current_cycle_idx: int = 1
        self._zoom_buttons: Dict[str, List[QPushButton]] = {
            "fit": [],
            "step": [],
            "cycle": [],
            "10m": [],
            "1m": [],
        }

        # Differential Capacity dQ/dV buffers & profiles (IMP-05)
        self._dqv_v_buf: collections.deque = collections.deque(maxlen=100_000)
        self._dqv_q_buf: collections.deque = collections.deque(maxlen=100_000)
        self._dqv_profiles: List[DQVProfile] = []
        self._dqv_history_curves: List[Tuple[DQVProfile, pg.PlotDataItem]] = []
        self._current_step_idx: int = 1
        self._current_step_type: str = "charge"
        self._dqv_dv: float = 0.005  # 5 mV uniform grid
        self._dqv_window: int = 15   # 15-point Savitzky-Golay window
        self._dqv_butterfly: bool = True  # True: charge +, discharge -; False: absolute |dQ/dV|
        self._dqv_mode_buttons: Dict[str, QPushButton] = {}
        self._dqv_smooth_buttons: Dict[str, QPushButton] = {}
        self._latest_dqv_peaks: List[DQVPeak] = []

        # Aging, Efficiency & Health tracking buffers (IMP-07)
        self._cycle_indices: List[int] = []
        self._cycle_q_dis: List[float] = []
        self._cycle_q_chg: List[float] = []
        self._cycle_ce: List[float] = []
        self._cycle_ee: List[float] = []
        self._cycle_dcir_cycles: List[int] = []
        self._cycle_dcir: List[float] = []
        self._aging_model: str = "linear"
        self._aging_model_buttons: Dict[str, QPushButton] = {}

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
        self._update_vq_identity_labels()

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

        # V-Q curve (IMP-02/IMP-07: exclude REST steps to eliminate vertical zero-capacity artifacts)
        if "rest" not in self._current_step_type.lower():
            self._vq_cap.append(abs(step_mah))
            self._vq_volt.append(data.voltage)

        # Differential Capacity Q-V trace (IMP-05)
        if "rest" not in self._current_step_type.lower():
            self._dqv_v_buf.append(data.voltage)
            self._dqv_q_buf.append(abs(step_mah))

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
        if self._zoom_mode == ZoomMode.MANUAL:
            if index == 1 and hasattr(self, "plot_vi") and hasattr(self, "plot_temp"):
                self.plot_temp.setXRange(*self.plot_vi.viewRange()[0], padding=0.0)
            elif index == 0 and hasattr(self, "plot_vi") and hasattr(self, "plot_temp"):
                self.plot_vi.setXRange(*self.plot_temp.viewRange()[0], padding=0.0)
        else:
            self._apply_zoom_framing()

        if index == 2 and hasattr(self, "plot_vq"):
            self.fit_vq_view()
        elif index == 3 and hasattr(self, "plot_dqv"):
            self._render_dqv_active()
            self.fit_dqv_view()
        elif index == 4 and hasattr(self, "plot_aging_cap"):
            self._render_aging_tab()
            self.fit_aging_view()

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
            if self._zoom_mode != ZoomMode.MANUAL:
                self._apply_zoom_framing()

        elif tab_idx == 1:
            # Tab 1 – Temperature (convert only temperature buffers)
            t = np.array(self._t)
            self.curve_term_temp.setData(t, np.array(self._t_term))
            self.curve_body_temp.setData(t, np.array(self._t_body))
            # Fixed Y-range: 0-70°C for temperature
            self.plot_temp.setYRange(0.0, 70.0, padding=0.0)
            if self._zoom_mode != ZoomMode.MANUAL:
                self._apply_zoom_framing()

        elif tab_idx == 2:
            # Tab 2 – V-Q Curve
            if self._vq_cap:
                caps = np.array(self._vq_cap)
                volts = np.array(self._vq_volt)
                is_charge = "charge" in self._current_step_type.lower()
                pen_color = _AGING_Q_CHG_COLOR if is_charge else _AGING_Q_DIS_COLOR
                self.curve_vq_current.setPen(pg.mkPen(pen_color, width=2.2))
                self.curve_vq_current.setData(caps, volts)
                self.curve_vq_current.setVisible(True)
                if self._zoom_mode != ZoomMode.MANUAL and len(caps) > 10:
                    max_cap = float(np.nanmax(caps))
                    v_min = float(np.nanmin(volts))
                    v_max = float(np.nanmax(volts))
                    self.plot_vq.setXRange(0.0, max(100.0, max_cap * 1.05), padding=0.02)
                    self.plot_vq.setYRange(max(0.0, v_min - 0.15), min(6.0, v_max + 0.15), padding=0.02)
            else:
                self.curve_vq_current.setData([], [])

        elif tab_idx == 3:
            # Tab 3 – Differential Capacity Analysis dQ/dV (IMP-05)
            self._render_dqv_active()

        elif tab_idx == 4:
            # Tab 4 – Cycle Aging & Health (IMP-07)
            self._render_aging_tab()

    # ----------------------------------------------------------------------- #
    # Quick-Zoom & Plot Framing (IMP-02)                                       #
    # ----------------------------------------------------------------------- #

    def notify_step_started(self, cycle_idx: int, step_idx: int, step_type: str = "charge") -> None:
        """Called by MainWindow on every step transition to track step/cycle boundaries."""
        # Safety auto-flush: If previous step buffers still hold unarchived data, archive them first
        if (len(self._dqv_v_buf) >= 15 or len(self._vq_cap) >= 15) and "rest" not in self._current_step_type.lower():
            self.reset_step_vq()

        latest_t = float(self._t[-1]) if self._t and not np.isnan(self._t[-1]) else 0.0
        self._current_step_start_t = latest_t
        self._current_step_idx = step_idx
        self._current_step_type = step_type
        if cycle_idx != self._current_cycle_idx:
            self._current_cycle_idx = cycle_idx
            self._current_cycle_start_t = latest_t
        self.add_event_marker(f"S{step_idx} {step_type.title()}")

    def add_event_marker(self, label: str) -> None:
        """Record a bounded event trail for long-running chart sessions."""
        self._event_markers.append(label)
        if hasattr(self, "lbl_event_strip"):
            self.lbl_event_strip.setText("Events: " + "  ·  ".join(self._event_markers))

    def set_zoom_mode(self, mode: ZoomMode) -> None:
        """Update zoom framing mode and synchronize UI button active states."""
        self._zoom_mode = mode

        # Update button styles across all toolbars
        for btn_key, btn_list in self._zoom_buttons.items():
            is_active = (
                (btn_key == "fit" and mode == ZoomMode.FIT_ALL)
                or (btn_key == "step" and mode == ZoomMode.CURRENT_STEP)
                or (btn_key == "cycle" and mode == ZoomMode.CURRENT_CYCLE)
                or (btn_key == "10m" and mode == ZoomMode.LAST_10M)
                or (btn_key == "1m" and mode == ZoomMode.LAST_1M)
            )
            style = _ZOOM_BTN_STYLE_ACTIVE if is_active else _ZOOM_BTN_STYLE_DEFAULT
            for btn in btn_list:
                btn.setStyleSheet(style)

        # Immediately execute view framing
        self._apply_zoom_framing()

    def _apply_zoom_framing(self) -> None:
        """Apply active zoom range to plot viewboxes."""
        if not hasattr(self, "plot_vi") or not hasattr(self, "plot_temp"):
            return
        t_arr = np.array(self._t) if self._t else np.array([])
        latest_t = float(t_arr[-1]) if len(t_arr) > 0 and not np.isnan(t_arr[-1]) else 10.0

        if self._zoom_mode == ZoomMode.FIT_ALL:
            self.plot_vi.setXRange(0.0, max(10.0, latest_t), padding=0.01)
            self.plot_temp.setXRange(0.0, max(10.0, latest_t), padding=0.01)
            self.plot_vi.setYRange(0.0, 6.0, padding=0.0)
            self.view_current.setYRange(-3.0, 3.0, padding=0.0)
            self.plot_temp.setYRange(0.0, 70.0, padding=0.0)
        elif self._zoom_mode == ZoomMode.CURRENT_STEP:
            s_t = max(0.0, self._current_step_start_t)
            self.plot_vi.setXRange(s_t, max(s_t + 5.0, latest_t), padding=0.02)
            self.plot_temp.setXRange(s_t, max(s_t + 5.0, latest_t), padding=0.02)
        elif self._zoom_mode == ZoomMode.CURRENT_CYCLE:
            c_t = max(0.0, self._current_cycle_start_t)
            self.plot_vi.setXRange(c_t, max(c_t + 10.0, latest_t), padding=0.02)
            self.plot_temp.setXRange(c_t, max(c_t + 10.0, latest_t), padding=0.02)
        elif self._zoom_mode == ZoomMode.LAST_10M:
            s_t = max(0.0, latest_t - 600.0)
            self.plot_vi.setXRange(s_t, max(s_t + 10.0, latest_t), padding=0.01)
            self.plot_temp.setXRange(s_t, max(s_t + 10.0, latest_t), padding=0.01)
        elif self._zoom_mode == ZoomMode.LAST_1M:
            s_t = max(0.0, latest_t - 60.0)
            self.plot_vi.setXRange(s_t, max(s_t + 5.0, latest_t), padding=0.01)
            self.plot_temp.setXRange(s_t, max(s_t + 5.0, latest_t), padding=0.01)

    def _on_manual_view_changed(self, *args) -> None:
        """Called when user manually pans or zooms using mouse drag."""
        if self._zoom_mode != ZoomMode.MANUAL:
            self._zoom_mode = ZoomMode.MANUAL
            for btn_list in self._zoom_buttons.values():
                for btn in btn_list:
                    btn.setStyleSheet(_ZOOM_BTN_STYLE_DEFAULT)

    def _create_quick_zoom_toolbar(self) -> QHBoxLayout:
        """Create a compact Quick-Zoom button bar for tab header."""
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(4)

        lbl = QLabel("Zoom:")
        lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600;")
        bar.addWidget(lbl)

        btn_fit = QPushButton("⤢ Fit All")
        btn_fit.setToolTip("Fit entire elapsed test timeline (0 to max time)")
        btn_fit.setStyleSheet(_ZOOM_BTN_STYLE_ACTIVE)
        btn_fit.clicked.connect(lambda: self.set_zoom_mode(ZoomMode.FIT_ALL))
        self._zoom_buttons["fit"].append(btn_fit)
        bar.addWidget(btn_fit)

        btn_step = QPushButton("⏱ Step")
        btn_step.setToolTip("Zoom to active profile step start")
        btn_step.setStyleSheet(_ZOOM_BTN_STYLE_DEFAULT)
        btn_step.clicked.connect(lambda: self.set_zoom_mode(ZoomMode.CURRENT_STEP))
        self._zoom_buttons["step"].append(btn_step)
        bar.addWidget(btn_step)

        btn_cycle = QPushButton("🔄 Cycle")
        btn_cycle.setToolTip("Zoom to active cycle loop start")
        btn_cycle.setStyleSheet(_ZOOM_BTN_STYLE_DEFAULT)
        btn_cycle.clicked.connect(lambda: self.set_zoom_mode(ZoomMode.CURRENT_CYCLE))
        self._zoom_buttons["cycle"].append(btn_cycle)
        bar.addWidget(btn_cycle)

        btn_10m = QPushButton("⏪ 10m")
        btn_10m.setToolTip("Follow sliding 10-minute window")
        btn_10m.setStyleSheet(_ZOOM_BTN_STYLE_DEFAULT)
        btn_10m.clicked.connect(lambda: self.set_zoom_mode(ZoomMode.LAST_10M))
        self._zoom_buttons["10m"].append(btn_10m)
        bar.addWidget(btn_10m)

        btn_1m = QPushButton("⏪ 1m")
        btn_1m.setToolTip("Follow sliding 1-minute window")
        btn_1m.setStyleSheet(_ZOOM_BTN_STYLE_DEFAULT)
        btn_1m.clicked.connect(lambda: self.set_zoom_mode(ZoomMode.LAST_1M))
        self._zoom_buttons["1m"].append(btn_1m)
        bar.addWidget(btn_1m)

        btn_clear = QPushButton("Clear History")
        btn_clear.setToolTip("Clear historical step traces while keeping live telemetry and aging summaries")
        btn_clear.setStyleSheet(_ZOOM_BTN_STYLE_DEFAULT)
        btn_clear.clicked.connect(self.clear_chart_history)
        bar.addWidget(btn_clear)

        return bar

    def clear_chart_history(self) -> None:
        """Remove dense historical chart overlays without deleting recorded telemetry."""
        if hasattr(self, "plot_vq"):
            for _, item in self._vq_history_curves:
                self.plot_vq.removeItem(item)
            self._vq_history_curves.clear()
            self._vq_cap.clear()
            self._vq_volt.clear()
            if hasattr(self, "curve_vq_current"):
                self.curve_vq_current.setData([], [])
            self.fit_vq_view()
        if hasattr(self, "plot_dqv"):
            for _, item in self._dqv_history_curves:
                self.plot_dqv.removeItem(item)
            self._dqv_history_curves.clear()
        self.add_event_marker("Chart history cleared")

    # ----------------------------------------------------------------------- #
    # Interactive Crosshair & Real-Time HUD (IMP-01)                           #
    # ----------------------------------------------------------------------- #

    def _on_mouse_moved_vi(self, pos) -> None:
        if not self._t or len(self._t) == 0:
            return
        vb = self.plot_vi.plotItem.vb
        if self.plot_vi.plotItem.sceneBoundingRect().contains(pos):
            mouse_pt = vb.mapSceneToView(pos)
            x_time = mouse_pt.x()
            t_arr = np.array(self._t)
            if len(t_arr) == 0:
                return
            idx = int(np.clip(np.searchsorted(t_arr, x_time), 0, len(t_arr) - 1))
            if idx > 0 and abs(t_arr[idx - 1] - x_time) < abs(t_arr[idx] - x_time):
                idx -= 1
            t_s = t_arr[idx]
            v_s = self._v[idx]
            i_s = self._i[idx]

            self.crosshair_v_vi.setPos(t_s)
            self.crosshair_v_vi.setVisible(True)
            if hasattr(self, "crosshair_v_temp"):
                self.crosshair_v_temp.setPos(t_s)
                self.crosshair_v_temp.setVisible(True)

            v_txt = f"{v_s:.3f} V" if not np.isnan(v_s) else "---"
            i_txt = f"{i_s:+.3f} A" if not np.isnan(i_s) else "---"
            v_col = _C1_V if self._cell_num == 1 else _C2_V
            i_col = _C1_I if self._cell_num == 1 else _C2_I
            self.lbl_hud_vi.setText(
                f"<span style='color:#94a3b8;'>⏱</span> <b style='color:#f8fafc;'>{t_s:.1f}s</b>  "
                f"<span style='color:{v_col};'>●</span> <b style='color:{v_col};'>V: {v_txt}</b>  "
                f"<span style='color:{i_col};'>●</span> <b style='color:{i_col};'>I: {i_txt}</b>"
            )
        else:
            self.crosshair_v_vi.setVisible(False)
            if hasattr(self, "crosshair_v_temp"):
                self.crosshair_v_temp.setVisible(False)
            self.lbl_hud_vi.setText("<span style='color:#64748b; font-style:italic;'>Hover over chart to inspect</span>")

    def _on_mouse_moved_temp(self, pos) -> None:
        if not self._t or len(self._t) == 0:
            return
        vb = self.plot_temp.plotItem.vb
        if self.plot_temp.plotItem.sceneBoundingRect().contains(pos):
            mouse_pt = vb.mapSceneToView(pos)
            x_time = mouse_pt.x()
            t_arr = np.array(self._t)
            if len(t_arr) == 0:
                return
            idx = int(np.clip(np.searchsorted(t_arr, x_time), 0, len(t_arr) - 1))
            if idx > 0 and abs(t_arr[idx - 1] - x_time) < abs(t_arr[idx] - x_time):
                idx -= 1
            t_s = t_arr[idx]
            term_s = self._t_term[idx]
            body_s = self._t_body[idx]

            self.crosshair_v_temp.setPos(t_s)
            self.crosshair_v_temp.setVisible(True)
            if hasattr(self, "crosshair_v_vi"):
                self.crosshair_v_vi.setPos(t_s)
                self.crosshair_v_vi.setVisible(True)

            term_txt = f"{term_s:.1f} °C" if not np.isnan(term_s) else "---"
            body_txt = f"{body_s:.1f} °C" if not np.isnan(body_s) else "---"
            self.lbl_hud_temp.setText(
                f"<span style='color:#94a3b8;'>⏱</span> <b style='color:#f8fafc;'>{t_s:.1f}s</b>  "
                f"<span style='color:{_TERM_COLOR};'>●</span> <b style='color:{_TERM_COLOR};'>Term: {term_txt}</b>  "
                f"<span style='color:{_BODY_COLOR};'>●</span> <b style='color:{_BODY_COLOR};'>Body: {body_txt}</b>"
            )
        else:
            self.crosshair_v_temp.setVisible(False)
            if hasattr(self, "crosshair_v_vi"):
                self.crosshair_v_vi.setVisible(False)
            self.lbl_hud_temp.setText("<span style='color:#64748b; font-style:italic;'>Hover over chart to inspect</span>")

    # ----------------------------------------------------------------------- #
    # Step / Cycle Events                                                      #
    # ----------------------------------------------------------------------- #

    def reset_step_vq(
        self,
        step_type: Optional[str] = None,
        cycle_idx: Optional[int] = None,
        step_idx: Optional[int] = None,
    ) -> None:
        """Archive current V-Q trace and completed dQ/dV profile when a step finishes."""
        target_stype = (step_type or self._current_step_type).lower()
        target_cycle = cycle_idx or self._current_cycle_idx
        target_step = step_idx or self._current_step_idx
        is_rest = "rest" in target_stype

        # 1. Archive V-Q Trace
        if len(self._vq_cap) >= 15 and not is_rest:
            caps = np.array(self._vq_cap)
            volts = np.array(self._vq_volt)
            if np.nanmax(caps) - np.nanmin(caps) >= 1.0:
                is_charge = "charge" in target_stype
                hist_color = "#16a34a" if is_charge else "#0284c7"
                p_hist = self.plot_vq.plot(
                    caps,
                    volts,
                    pen=pg.mkPen(hist_color, width=1.3, style=Qt.PenStyle.DashLine),
                )
                p_hist.setClipToView(True)
                self._vq_history_curves.append((target_stype, p_hist))

                while len(self._vq_history_curves) > 20:
                    _, old_item = self._vq_history_curves.pop(0)
                    self.plot_vq.removeItem(old_item)

        self._vq_cap.clear()
        self._vq_volt.clear()
        if hasattr(self, "curve_vq_current"):
            self.curve_vq_current.setData([], [])

        # 2. Archive completed step dQ/dV profile (IMP-05)
        if len(self._dqv_v_buf) >= 15 and not is_rest:
            v_arr = np.array(self._dqv_v_buf)
            q_arr = np.array(self._dqv_q_buf)
            v_grid, dqdv = compute_dq_dv(
                v_arr,
                q_arr,
                step_type=target_stype,
                dv_grid=self._dqv_dv,
                smooth_window=self._dqv_window,
            )
            if len(v_grid) > 0:
                pks = find_dqv_peaks(v_grid, dqdv)
                prof = DQVProfile(
                    cycle_index=target_cycle,
                    step_index=target_step,
                    step_type=target_stype,
                    voltages=v_grid,
                    dq_dv=dqdv,
                    peaks=pks,
                )
                self._dqv_profiles.append(prof)
                self._plot_historical_dqv(prof)
                if pks:
                    self._latest_dqv_peaks = list(pks)
                    self._update_dqv_peak_scatter(pks)
                self.fit_dqv_view()

        self._dqv_v_buf.clear()
        self._dqv_q_buf.clear()
        if hasattr(self, "curve_dqv_active"):
            self.curve_dqv_active.setData([], [])

    def add_cycle_summary(
        self,
        cycle_idx: int,
        discharge_mah: float,
        coulombic_eff: float,
        charge_mah: float = 0.0,
        energy_eff: float = 0.0,
        dcir_mohm: Optional[float] = None,
    ) -> None:
        """Cycle summary hook for Aging & Health tracker (IMP-07)."""
        self._cycle_indices.append(cycle_idx)
        self._cycle_q_dis.append(discharge_mah)
        self._cycle_q_chg.append(charge_mah)
        self._cycle_ce.append(coulombic_eff)
        self._cycle_ee.append(energy_eff)
        if dcir_mohm is not None and dcir_mohm > 0.0:
            self._cycle_dcir_cycles.append(cycle_idx)
            self._cycle_dcir.append(dcir_mohm)

        self._render_aging_tab()
        # Keep newly completed cycles in view even when the tab was already open.
        self.fit_aging_view()

    def reset_all(self) -> None:
        """Full reset for a new test run."""
        self._t.clear(); self._v.clear(); self._i.clear()
        self._t_term.clear(); self._t_body.clear()
        self._vq_cap.clear(); self._vq_volt.clear()
        self._dqv_v_buf.clear(); self._dqv_q_buf.clear()
        self._dqv_profiles.clear()
        self._latest_dqv_peaks.clear()
        self._event_markers.clear()
        if hasattr(self, "lbl_event_strip"):
            self.lbl_event_strip.setText("Events: waiting for step transitions")
        self.plot_vq.clear()
        self._vq_history_curves.clear()
        self.curve_vq_current = self.plot_vq.plot(
            pen=pg.mkPen(_AGING_Q_CHG_COLOR, width=2.2)
        )
        self.curve_vq_current.setClipToView(True)
        self.fit_vq_view()
        if hasattr(self, "plot_dqv"):
            for _, p_item in self._dqv_history_curves:
                self.plot_dqv.removeItem(p_item)
            self._dqv_history_curves.clear()
            if hasattr(self, "curve_dqv_active"):
                self.curve_dqv_active.setData([], [])
            if hasattr(self, "scatter_dqv_peaks"):
                self.scatter_dqv_peaks.setData([])
            if hasattr(self, "crosshair_v_dqv"):
                self.crosshair_v_dqv.setVisible(False)
            if hasattr(self, "lbl_hud_dqv"):
                self.lbl_hud_dqv.setText("<span style='color:#64748b; font-style:italic;'>Hover over chart to inspect</span>")
            if hasattr(self, "lbl_dqv_peaks_badge"):
                self.lbl_dqv_peaks_badge.setText("⚡ Peaks: Monitoring...")
            self.fit_dqv_view()

        # Aging and Health Tab reset (IMP-07)
        self._cycle_indices.clear()
        self._cycle_q_dis.clear()
        self._cycle_q_chg.clear()
        self._cycle_ce.clear()
        self._cycle_ee.clear()
        self._cycle_dcir_cycles.clear()
        self._cycle_dcir.clear()
        if hasattr(self, "curve_aging_q_dis"):
            self.curve_aging_q_dis.setData([], [])
            self.curve_aging_q_chg.setData([], [])
            self.curve_aging_q_proj.setData([], [])
            self.curve_aging_ce.setData([], [])
            self.curve_aging_ee.setData([], [])
            self.curve_aging_dcir.setData([], [])
            self.line_aging_eol.setVisible(False)
            self.crosshair_v_aging_cap.setVisible(False)
            self.crosshair_v_aging_eff.setVisible(False)
            self.lbl_hud_aging.setText("<span style='color:#64748b; font-style:italic;'>Hover over chart to inspect</span>")
            self.lbl_aging_health_badge.setText("● Retention: 100.0% | EOL: Calculating...")
            self.lbl_aging_health_badge.setStyleSheet(
                "background-color: #064e3b; color: #6ee7b7; border: 1px solid #059669; "
                "border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: bold;"
            )
            self.lbl_aging_fade_badge.setText("Fade: 0.00 mAh/cyc")
            if hasattr(self, "lbl_aging_data_state"):
                self.lbl_aging_data_state.setText("Waiting for first completed cycle")
                self.lbl_aging_data_state.setStyleSheet("color: #fbbf24; font-size: 11px; font-weight: 600;")
            self.fit_aging_view()

        self.start_epoch = time.time()
        self._relay_on = False
        self._dirty = False
        self._last_pen_cell = None
        self._current_step_start_t = 0.0
        self._current_cycle_start_t = 0.0
        self._current_cycle_idx = 1
        if hasattr(self, "crosshair_v_vi"):
            self.crosshair_v_vi.setVisible(False)
        if hasattr(self, "crosshair_v_temp"):
            self.crosshair_v_temp.setVisible(False)
        if hasattr(self, "lbl_hud_vi"):
            self.lbl_hud_vi.setText("<span style='color:#64748b; font-style:italic;'>Hover over chart to inspect</span>")
        if hasattr(self, "lbl_hud_temp"):
            self.lbl_hud_temp.setText("<span style='color:#64748b; font-style:italic;'>Hover over chart to inspect</span>")
        self.curve_voltage.setData([], [])
        self.curve_current.setData([], [])
        self.curve_term_temp.setData([], [])
        self.curve_body_temp.setData([], [])
        self.plot_vi.setYRange(0.0, 6.0, padding=0.0)
        self.view_current.setYRange(-3.0, 3.0, padding=0.0)
        self.plot_temp.setYRange(0.0, 70.0, padding=0.0)
        self.set_zoom_mode(ZoomMode.FIT_ALL)

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
        self._build_dqv_tab()
        self._build_aging_tab()
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _build_vi_tab(self) -> None:
        tab = QWidget()
        vlay = QVBoxLayout(tab)
        vlay.setContentsMargins(4, 4, 4, 2)
        vlay.setSpacing(2)

        # Header bar with Legends, HUD readout, and Quick-Zoom controls
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(4, 2, 4, 2)
        top_bar.setSpacing(8)

        legend_row = QHBoxLayout()
        legend_row.setContentsMargins(0, 0, 0, 0)
        legend_row.setSpacing(4)
        legend_row.addWidget(_legend_label(_C1_V, "Cell 1 V"))
        legend_row.addWidget(_legend_label(_C2_V, "Cell 2 V"))
        legend_row.addWidget(_legend_label(_C1_I, "Cell 1 I"))
        legend_row.addWidget(_legend_label(_C2_I, "Cell 2 I"))
        note = QLabel("(gap = relay OFF)")
        note.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;")
        legend_row.addWidget(note)
        top_bar.addLayout(legend_row)

        self.lbl_event_strip = QLabel("Events: waiting for step transitions")
        self.lbl_event_strip.setStyleSheet("color:#64748b; font-size:10px; font-family:Consolas, monospace;")
        top_bar.addWidget(self.lbl_event_strip)

        top_bar.addStretch(1)

        self.lbl_hud_vi = QLabel("<span style='color:#64748b; font-style:italic;'>Hover over chart to inspect</span>")
        self.lbl_hud_vi.setStyleSheet(_HUD_STYLE)
        top_bar.addWidget(self.lbl_hud_vi)

        top_bar.addStretch(1)

        top_bar.addLayout(self._create_quick_zoom_toolbar())
        vlay.addLayout(top_bar)

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
        self.plot_vi.plotItem.getViewBox().enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
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

        # Crosshair vertical marker (IMP-01)
        self.crosshair_v_vi = pg.InfiniteLine(
            angle=90, movable=False, pen=pg.mkPen("#cbd5e1", width=1.2, style=Qt.PenStyle.DashLine)
        )
        self.crosshair_v_vi.setVisible(False)
        self.plot_vi.addItem(self.crosshair_v_vi, ignoreBounds=True)

        # Signals for Hover HUD and Manual Zoom Tracking
        self.plot_vi.scene().sigMouseMoved.connect(self._on_mouse_moved_vi)
        self.plot_vi.plotItem.vb.sigRangeChangedManually.connect(self._on_manual_view_changed)

        vlay.addWidget(self.plot_vi)
        self.tabs.addTab(tab, "⚡ Voltage & Current")

    def _build_temp_tab(self) -> None:
        tab = QWidget()
        vlay = QVBoxLayout(tab)
        vlay.setContentsMargins(4, 4, 4, 2)
        vlay.setSpacing(2)

        # Header bar with Legends, HUD readout, and Quick-Zoom controls
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(4, 2, 4, 2)
        top_bar.setSpacing(8)

        legend_row = QHBoxLayout()
        legend_row.setContentsMargins(0, 0, 0, 0)
        legend_row.setSpacing(4)
        legend_row.addWidget(_legend_label(_TERM_COLOR, "Terminal Temp (°C)"))
        legend_row.addWidget(_legend_label(_BODY_COLOR, "Body Temp (°C)"))
        top_bar.addLayout(legend_row)

        top_bar.addStretch(1)

        self.lbl_hud_temp = QLabel("<span style='color:#64748b; font-style:italic;'>Hover over chart to inspect</span>")
        self.lbl_hud_temp.setStyleSheet(_HUD_STYLE)
        top_bar.addWidget(self.lbl_hud_temp)

        top_bar.addStretch(1)

        top_bar.addLayout(self._create_quick_zoom_toolbar())
        vlay.addLayout(top_bar)

        self.ax_temp = TemperatureAxisItem(orientation="left")
        self.plot_temp = pg.PlotWidget(axisItems={"left": self.ax_temp})
        self.plot_temp.showGrid(x=True, y=True, alpha=0.18)
        self.ax_temp.setTickPen(pg.mkPen("#334155", width=1))
        self.plot_temp.plotItem.getAxis("bottom").setTickPen(pg.mkPen("#334155", width=1))
        self.plot_temp.setLabel("left", "<span style='color:#fb923c; font-weight:bold; font-size:12px;'>🌡 Temperature (0 – 70 °C)</span>")
        self.plot_temp.setLabel("bottom", "<span style='color:#94a3b8; font-weight:600;'>Elapsed Time (s)</span>")

        # Fixed Y-axis: 0.0 to 70.0 °C
        self.plot_temp.setYRange(0.0, 70.0, padding=0.0)
        self.plot_temp.plotItem.getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        self.plot_temp.plotItem.getViewBox().enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
        self.plot_temp.plotItem.getViewBox().setLimits(xMin=0.0, yMin=0.0, yMax=70.0)

        self.curve_term_temp = self.plot_temp.plot(
            pen=pg.mkPen(_TERM_COLOR, width=2.0), connect="finite"
        )
        self.curve_term_temp.setClipToView(True)

        self.curve_body_temp = self.plot_temp.plot(
            pen=pg.mkPen(_BODY_COLOR, width=2.0), connect="finite"
        )
        self.curve_body_temp.setClipToView(True)

        # Crosshair vertical marker (IMP-01)
        self.crosshair_v_temp = pg.InfiniteLine(
            angle=90, movable=False, pen=pg.mkPen("#cbd5e1", width=1.2, style=Qt.PenStyle.DashLine)
        )
        self.crosshair_v_temp.setVisible(False)
        self.plot_temp.addItem(self.crosshair_v_temp, ignoreBounds=True)

        # Signals for Hover HUD and Manual Zoom Tracking
        self.plot_temp.scene().sigMouseMoved.connect(self._on_mouse_moved_temp)
        self.plot_temp.plotItem.vb.sigRangeChangedManually.connect(self._on_manual_view_changed)

        vlay.addWidget(self.plot_temp)
        self.tabs.addTab(tab, "🌡 Temperature")

    def _build_vq_tab(self) -> None:
        tab = QWidget()
        vlay = QVBoxLayout(tab)
        vlay.setContentsMargins(4, 4, 4, 2)
        vlay.setSpacing(2)

        # Header bar
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(4, 2, 4, 2)
        top_bar.setSpacing(8)

        legend_row = QHBoxLayout()
        legend_row.setContentsMargins(0, 0, 0, 0)
        legend_row.setSpacing(6)
        legend_row.addWidget(_legend_label(_AGING_Q_CHG_COLOR, "Charge"))
        legend_row.addWidget(_legend_label(_AGING_Q_DIS_COLOR, "Discharge"))
        legend_row.addWidget(_legend_label("#64748b", "History (dashed)"))
        top_bar.addLayout(legend_row)

        top_bar.addStretch(1)

        self.lbl_vq_context = QLabel("⚡ Cell 1 · V vs Q Envelope")
        self.lbl_vq_context.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        top_bar.addWidget(self.lbl_vq_context)

        top_bar.addStretch(1)

        ctrls = QHBoxLayout()
        ctrls.setContentsMargins(0, 0, 0, 0)
        ctrls.setSpacing(4)

        btn_fit = QPushButton("⤢ Fit")
        btn_fit.setToolTip("Auto-fit V-Q curve view")
        btn_fit.setStyleSheet(_ZOOM_BTN_STYLE_DEFAULT)
        btn_fit.clicked.connect(self.fit_vq_view)
        ctrls.addWidget(btn_fit)

        btn_clear = QPushButton("Clear History")
        btn_clear.setToolTip("Clear completed cycle traces from V-Q view")
        btn_clear.setStyleSheet(_ZOOM_BTN_STYLE_DEFAULT)
        btn_clear.clicked.connect(self.clear_chart_history)
        ctrls.addWidget(btn_clear)

        top_bar.addLayout(ctrls)
        vlay.addLayout(top_bar)

        self.ax_vq = VoltageAxisItem(orientation="left")
        self.plot_vq = pg.PlotWidget(axisItems={"left": self.ax_vq})
        self.plot_vq.showGrid(x=True, y=True, alpha=0.18)
        self.ax_vq.setTickPen(pg.mkPen("#334155", width=1))
        self.plot_vq.plotItem.getAxis("bottom").setTickPen(pg.mkPen("#334155", width=1))
        self.plot_vq.setLabel("left", "<span style='color:#38bdf8; font-weight:bold; font-size:12px;'>⚡ Cell 1 Voltage (V)</span>")
        self.plot_vq.setLabel("bottom", "<span style='color:#94a3b8; font-weight:600;'>Delivered / Stored Capacity (mAh)</span>")
        self.curve_vq_current = self.plot_vq.plot(pen=pg.mkPen(_AGING_Q_CHG_COLOR, width=2.2))
        self.curve_vq_current.setClipToView(True)
        vlay.addWidget(self.plot_vq)
        self.tabs.addTab(tab, "📈 V-Q Curve")

    def _update_vq_identity_labels(self) -> None:
        """Keep V-Q axis identity aligned with the selected cell."""
        cell = int(self._cell_num)
        color = _C1_V if cell == 1 else _C2_V
        if hasattr(self, "lbl_vq_context"):
            self.lbl_vq_context.setText(f"⚡ Cell {cell} · V vs Q Envelope")
        if hasattr(self, "plot_vq"):
            self.plot_vq.setLabel(
                "left",
                f"<span style='color:{color}; font-weight:bold; font-size:12px;'>⚡ Cell {cell} Voltage (V)</span>",
            )

    def _build_dqv_tab(self) -> None:
        tab = QWidget()
        vlay = QVBoxLayout(tab)
        vlay.setContentsMargins(4, 4, 4, 2)
        vlay.setSpacing(2)

        # Header bar
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(4, 2, 4, 2)
        top_bar.setSpacing(8)

        legend_row = QHBoxLayout()
        legend_row.setContentsMargins(0, 0, 0, 0)
        legend_row.setSpacing(4)
        legend_row.addWidget(_legend_label(_DQV_CHARGE_COLOR, "Charge dQ/dV"))
        legend_row.addWidget(_legend_label(_DQV_DISCHARGE_COLOR, "Discharge dQ/dV"))
        legend_row.addWidget(_legend_label(_PEAK_MARKER_COLOR, "Phase Peaks (◆)"))
        legend_row.addWidget(_legend_label("#64748b", "History (dashed)"))
        top_bar.addLayout(legend_row)

        top_bar.addStretch(1)

        # Peak badge
        self.lbl_dqv_peaks_badge = QLabel("Peaks: Monitoring...")
        self.lbl_dqv_peaks_badge.setStyleSheet(
            "background-color: #1e293b; color: #facc15; border: 1px solid #475569; "
            "border-radius: 4px; padding: 2px 7px; font-size: 11px; font-weight: 600;"
        )
        top_bar.addWidget(self.lbl_dqv_peaks_badge)

        btn_peaks = QPushButton("Peak Table")
        btn_peaks.setToolTip("Open the detected dQ/dV phase-transition peak table")
        btn_peaks.clicked.connect(self._show_dqv_peak_table)
        top_bar.addWidget(btn_peaks)

        self.lbl_dqv_context = QLabel("Cell 1 · Cycle 1 · Charge · 5 mV grid · ± sign")
        self.lbl_dqv_context.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 600;")
        top_bar.addWidget(self.lbl_dqv_context)

        # HUD readout
        self.lbl_hud_dqv = QLabel("<span style='color:#64748b; font-style:italic;'>Hover over chart to inspect</span>")
        self.lbl_hud_dqv.setStyleSheet(_HUD_STYLE)
        top_bar.addWidget(self.lbl_hud_dqv)

        top_bar.addStretch(1)

        # Controls bar: Mode (Butterfly vs Absolute) + Smoothing (5, 10, 15 mV) + Fit
        ctrls = QHBoxLayout()
        ctrls.setContentsMargins(0, 0, 0, 0)
        ctrls.setSpacing(3)

        lbl_mode = QLabel("Mode:")
        lbl_mode.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600;")
        ctrls.addWidget(lbl_mode)

        btn_bf = QPushButton("± Butterfly")
        btn_bf.setToolTip("Plot Charge (+dQ/dV) and Discharge (-dQ/dV) in dual-lobe butterfly view")
        btn_bf.setStyleSheet(_ZOOM_BTN_STYLE_ACTIVE)
        btn_bf.clicked.connect(lambda: self.set_dqv_mode(True))
        self._dqv_mode_buttons["butterfly"] = btn_bf
        ctrls.addWidget(btn_bf)

        btn_abs = QPushButton("|dQ/dV|")
        btn_abs.setToolTip("Plot Absolute Differential Capacity (|dQ/dV|) overlaid")
        btn_abs.setStyleSheet(_ZOOM_BTN_STYLE_DEFAULT)
        btn_abs.clicked.connect(lambda: self.set_dqv_mode(False))
        self._dqv_mode_buttons["abs"] = btn_abs
        ctrls.addWidget(btn_abs)

        ctrls.addSpacing(6)
        lbl_sm = QLabel("Grid:")
        lbl_sm.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600;")
        ctrls.addWidget(lbl_sm)

        for label, dv, win in [("5 mV", 0.005, 15), ("10 mV", 0.010, 17), ("15 mV", 0.015, 21)]:
            btn = QPushButton(label)
            btn.setToolTip(f"Savitzky-Golay differentiation with {label} grid spacing")
            btn.setStyleSheet(_ZOOM_BTN_STYLE_ACTIVE if dv == self._dqv_dv else _ZOOM_BTN_STYLE_DEFAULT)
            btn.clicked.connect(lambda checked=False, d=dv, w=win: self.set_dqv_smoothing(d, w))
            self._dqv_smooth_buttons[f"{int(dv*1000)}mv"] = btn
            ctrls.addWidget(btn)

        ctrls.addSpacing(6)
        btn_fit = QPushButton("⤢ Fit")
        btn_fit.setToolTip("Auto-fit differential capacity plot view")
        btn_fit.setStyleSheet(_ZOOM_BTN_STYLE_DEFAULT)
        btn_fit.clicked.connect(self.fit_dqv_view)
        ctrls.addWidget(btn_fit)

        top_bar.addLayout(ctrls)
        vlay.addLayout(top_bar)

        # Plot Widget
        self.plot_dqv = pg.PlotWidget()
        self.plot_dqv.showGrid(x=True, y=True, alpha=0.18)
        self.plot_dqv.plotItem.getAxis("bottom").setTickPen(pg.mkPen("#334155", width=1))
        self.plot_dqv.plotItem.getAxis("left").setTickPen(pg.mkPen("#334155", width=1))
        self.plot_dqv.setLabel("left", "<span style='color:#38bdf8; font-weight:bold; font-size:12px;'>dQ/dV (mAh / V)</span>")
        self.plot_dqv.setLabel("bottom", "<span style='color:#94a3b8; font-weight:600;'>Cell Voltage (V)</span>")

        # Zero reference line
        self.line_dqv_zero = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen("#475569", width=1.0, style=Qt.PenStyle.DashLine))
        self.plot_dqv.addItem(self.line_dqv_zero)

        # Crosshair vertical line
        self.crosshair_v_dqv = pg.InfiniteLine(
            angle=90, movable=False, pen=pg.mkPen("#cbd5e1", width=1.2, style=Qt.PenStyle.DashLine)
        )
        self.crosshair_v_dqv.setVisible(False)
        self.plot_dqv.addItem(self.crosshair_v_dqv, ignoreBounds=True)

        # Active curve
        self.curve_dqv_active = self.plot_dqv.plot(pen=pg.mkPen(_DQV_CHARGE_COLOR, width=2.4))
        self.curve_dqv_active.setClipToView(True)

        # Peak markers scatter
        self.scatter_dqv_peaks = pg.ScatterPlotItem()
        self.plot_dqv.addItem(self.scatter_dqv_peaks)

        # Initial view bounds
        self.plot_dqv.setXRange(2.0, 4.6, padding=0.02)

        # Signals
        self.plot_dqv.scene().sigMouseMoved.connect(self._on_mouse_moved_dqv)

        vlay.addWidget(self.plot_dqv)
        self.tabs.addTab(tab, "dQ/dV Capacity Analysis")

    def _render_dqv_active(self) -> None:
        """Render live dQ/dV curve for the currently running charge/discharge step."""
        if not hasattr(self, "curve_dqv_active"):
            return
        if len(self._dqv_v_buf) >= 15 and "rest" not in self._current_step_type.lower():
            v_arr = np.array(self._dqv_v_buf)
            q_arr = np.array(self._dqv_q_buf)
            v_grid, dqdv = compute_dq_dv(
                v_arr,
                q_arr,
                step_type=self._current_step_type,
                dv_grid=self._dqv_dv,
                smooth_window=self._dqv_window,
            )
            if len(v_grid) > 0:
                self.lbl_dqv_context.setText(
                    f"Cell {self._cell_num} · Cycle {self._current_cycle_idx} · "
                    f"{self._current_step_type.title()} · {int(self._dqv_dv * 1000)} mV grid · "
                    f"{'±' if self._dqv_butterfly else '| |'} sign"
                )
                is_dis = "discharge" in self._current_step_type.lower()
                pen_col = _DQV_DISCHARGE_COLOR if is_dis else _DQV_CHARGE_COLOR
                self.curve_dqv_active.setPen(pg.mkPen(pen_col, width=2.4))
                y_data = dqdv if self._dqv_butterfly else np.abs(dqdv)
                self.curve_dqv_active.setData(v_grid, y_data)

                # Peak detection
                pks = find_dqv_peaks(v_grid, dqdv)
                self._latest_dqv_peaks = list(pks)
                self._update_dqv_peak_scatter(pks)
                return

        # Active step is idle, resting, or buffering (<15 samples)
        self.curve_dqv_active.setData([], [])
        if self._dqv_profiles:
            last_prof = self._dqv_profiles[-1]
            if last_prof.peaks:
                self._latest_dqv_peaks = list(last_prof.peaks)
                self._update_dqv_peak_scatter(last_prof.peaks)
            self.lbl_dqv_context.setText(
                f"Cell {self._cell_num} · {len(self._dqv_profiles)} historical profile{'s' if len(self._dqv_profiles) != 1 else ''} · "
                f"{self._current_step_type.title()} active"
            )
        else:
            self.scatter_dqv_peaks.setData([])
            self._latest_dqv_peaks = []
            self.lbl_dqv_peaks_badge.setText("Peaks: Monitoring...")
            self.lbl_dqv_context.setText(
                f"Cell {self._cell_num} · Cycle {self._current_cycle_idx} · "
                f"{self._current_step_type.title()} · Insufficient samples (need 15+)"
            )

    def _update_dqv_peak_scatter(self, pks: List[DQVPeak]) -> None:
        """Render peak diamond markers on the dQ/dV plot."""
        if not hasattr(self, "scatter_dqv_peaks"):
            return
        if pks:
            spots = [
                {
                    "pos": (p.voltage, p.dq_dv if self._dqv_butterfly else abs(p.dq_dv)),
                    "data": p.label,
                    "brush": pg.mkBrush(_PEAK_MARKER_COLOR),
                    "pen": pg.mkPen("#0f172a", width=1),
                    "size": 11,
                    "symbol": "d",
                }
                for p in pks
            ]
            self.scatter_dqv_peaks.setData(spots)
            p_str = ", ".join([f"{p.voltage:.2f}V ({abs(p.dq_dv):.0f})" for p in pks[:3]])
            self.lbl_dqv_peaks_badge.setText(f"Peaks: {p_str}")
        else:
            self.scatter_dqv_peaks.setData([])
            self.lbl_dqv_peaks_badge.setText("Peaks: None detected")

    def _show_dqv_peak_table(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("dQ/dV Phase Transition Peaks")
        dialog.resize(620, 320)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["Voltage (V)", "dQ/dV (mAh/V)", "Prominence", "Cycle", "Direction"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        all_peaks_data: List[Tuple[DQVPeak, int, str]] = []
        for prof in self._dqv_profiles:
            for pk in prof.peaks:
                all_peaks_data.append((pk, prof.cycle_index, prof.step_type.title()))

        if not all_peaks_data and self._latest_dqv_peaks:
            for pk in self._latest_dqv_peaks:
                all_peaks_data.append((pk, self._current_cycle_idx, self._current_step_type.title()))

        for pk, cyc, direction in all_peaks_data:
            row = table.rowCount()
            table.insertRow(row)
            values = [
                f"{pk.voltage:.4f}",
                f"{pk.dq_dv:+.2f}",
                f"{pk.prominence:.2f}",
                f"Cycle {cyc}",
                direction,
            ]
            for col, val in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(val))

        table.cellDoubleClicked.connect(
            lambda row, _col: self._center_dqv_peak(all_peaks_data[row][0])
            if 0 <= row < len(all_peaks_data) else None
        )

        if not all_peaks_data:
            table.setRowCount(1)
            table.setItem(0, 0, QTableWidgetItem("No peaks detected or insufficient samples"))
            table.setSpan(0, 0, 1, 5)

        layout.addWidget(table)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        dialog.exec()

    def _center_dqv_peak(self, peak: DQVPeak) -> None:
        """Center the dQ/dV chart on a selected phase-transition peak."""
        if not hasattr(self, "plot_dqv"):
            return
        half_span = 0.12
        self.plot_dqv.setXRange(max(0.0, peak.voltage - half_span), peak.voltage + half_span, padding=0.0)
        y_value = abs(peak.dq_dv) if self._dqv_butterfly else abs(peak.dq_dv)
        self.plot_dqv.setYRange(min(-1.0, y_value * -0.25), max(1.0, y_value * 1.15), padding=0.0)
        self.crosshair_v_dqv.setPos(peak.voltage)
        self.crosshair_v_dqv.setVisible(True)
        self.lbl_hud_dqv.setText(
            f"<b>Peak</b> · V: {peak.voltage:.4f} V · dQ/dV: {peak.dq_dv:.2f} mAh/V · {peak.label}"
        )

    def _plot_historical_dqv(self, prof: DQVProfile) -> None:
        """Render completed step dQ/dV curve with cycle gradient styling."""
        if not hasattr(self, "plot_dqv"):
            return
        is_dis = "discharge" in prof.step_type.lower()
        if prof.cycle_index == 1:
            color = _DQV_DISCHARGE_COLOR if is_dis else _DQV_CHARGE_COLOR
        else:
            c_idx = (prof.cycle_index - 1) % len(CYCLE_PALETTE)
            color = CYCLE_PALETTE[c_idx]

        pen = pg.mkPen(
            color,
            width=1.5,
            style=pg.QtCore.Qt.PenStyle.DashLine if is_dis else pg.QtCore.Qt.PenStyle.SolidLine,
        )
        y_data = prof.dq_dv if self._dqv_butterfly else np.abs(prof.dq_dv)
        p_item = self.plot_dqv.plot(prof.voltages, y_data, pen=pen)
        p_item.setClipToView(True)
        self._dqv_history_curves.append((prof, p_item))

    def _on_mouse_moved_dqv(self, pos) -> None:
        """Interactive tracking crosshair and HUD readout for dQ/dV."""
        if not hasattr(self, "plot_dqv"):
            return
        vb = self.plot_dqv.plotItem.vb
        if self.plot_dqv.plotItem.sceneBoundingRect().contains(pos):
            mouse_pt = vb.mapSceneToView(pos)
            v_mouse = mouse_pt.x()
            self.crosshair_v_dqv.setPos(v_mouse)
            self.crosshair_v_dqv.setVisible(True)

            v_act, y_act = self.curve_dqv_active.getData()
            if v_act is not None and len(v_act) > 0:
                idx = int(np.clip(np.searchsorted(v_act, v_mouse), 0, len(v_act) - 1))
                if idx > 0 and abs(v_act[idx - 1] - v_mouse) < abs(v_act[idx] - v_mouse):
                    idx -= 1
                v_pt = v_act[idx]
                dq_pt = y_act[idx]
                col = _DQV_DISCHARGE_COLOR if "discharge" in self._current_step_type.lower() else _DQV_CHARGE_COLOR
                self.lbl_hud_dqv.setText(
                    f"<span style='color:#94a3b8;'>V:</span> <b style='color:#f8fafc;'>{v_pt:.3f} V</b>  "
                    f"<span style='color:{col};'>●</span> <b style='color:{col};'>dQ/dV: {dq_pt:+.1f} mAh/V</b>  "
                    f"<span style='color:#64748b;'>| {self._current_step_type.title()} (C{self._current_cycle_idx})</span>"
                )
            else:
                self.lbl_hud_dqv.setText(
                    f"<span style='color:#94a3b8;'>V:</span> <b style='color:#f8fafc;'>{v_mouse:.3f} V</b>"
                )
        else:
            self.crosshair_v_dqv.setVisible(False)
            self.lbl_hud_dqv.setText("<span style='color:#64748b; font-style:italic;'>Hover over chart to inspect</span>")

    def set_dqv_mode(self, butterfly: bool) -> None:
        """Toggle between Butterfly (+/-) mode and Overlay Absolute (|dQ/dV|) mode."""
        self._dqv_butterfly = butterfly
        btn_bf = self._dqv_mode_buttons.get("butterfly")
        btn_abs = self._dqv_mode_buttons.get("abs")
        if btn_bf:
            btn_bf.setStyleSheet(_ZOOM_BTN_STYLE_ACTIVE if butterfly else _ZOOM_BTN_STYLE_DEFAULT)
        if btn_abs:
            btn_abs.setStyleSheet(_ZOOM_BTN_STYLE_ACTIVE if not butterfly else _ZOOM_BTN_STYLE_DEFAULT)
        for prof, p_item in self._dqv_history_curves:
            y_data = prof.dq_dv if butterfly else np.abs(prof.dq_dv)
            p_item.setData(prof.voltages, y_data)
        self._render_dqv_active()
        self.fit_dqv_view()

    def set_dqv_smoothing(self, dv: float, window: int) -> None:
        """Update Savitzky-Golay grid spacing and window length."""
        self._dqv_dv = dv
        self._dqv_window = window
        for k, btn in self._dqv_smooth_buttons.items():
            is_active = (k == f"{int(dv*1000)}mv")
            btn.setStyleSheet(_ZOOM_BTN_STYLE_ACTIVE if is_active else _ZOOM_BTN_STYLE_DEFAULT)
        self._render_dqv_active()

    def fit_dqv_view(self) -> None:
        """Auto-frame dQ/dV view to encompass all active and historical data."""
        if not hasattr(self, "plot_dqv"):
            return
        y_vals: List[float] = []
        if hasattr(self, "curve_dqv_active"):
            act_x, act_y = self.curve_dqv_active.getData()
            if act_y is not None and len(act_y) > 0:
                y_vals.extend(act_y[::5])
        for prof, _ in self._dqv_history_curves:
            y_data = prof.dq_dv if self._dqv_butterfly else np.abs(prof.dq_dv)
            if len(y_data) > 0:
                y_vals.extend(y_data[::5])

        valid_y = [y for y in y_vals if np.isfinite(y)]
        if valid_y:
            y_min = min(valid_y)
            y_max = max(valid_y)
            pad = max(50.0, (y_max - y_min) * 0.1)
            self.plot_dqv.setYRange(y_min - pad, y_max + pad, padding=0.02)
        else:
            self.plot_dqv.setYRange(-500.0, 1500.0, padding=0.02)

        self.plot_dqv.setXRange(2.5, 4.35, padding=0.02)

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
        plots_to_scale = [
            getattr(self, "plot_vi", None),
            getattr(self, "plot_temp", None),
            getattr(self, "plot_vq", None),
            getattr(self, "plot_dqv", None),
            getattr(self, "plot_aging_cap", None),
            getattr(self, "plot_aging_eff", None),
        ]
        for plot in plots_to_scale:
            if plot and hasattr(plot, "plotItem"):
                b_ax = plot.plotItem.getAxis("bottom")
                l_ax = plot.plotItem.getAxis("left")
                if b_ax:
                    axes_to_scale.append(b_ax)
                if l_ax:
                    axes_to_scale.append(l_ax)
        if hasattr(self, "plot_aging_eff") and hasattr(self.plot_aging_eff, "plotItem"):
            r_ax = self.plot_aging_eff.plotItem.getAxis("right")
            if r_ax:
                axes_to_scale.append(r_ax)
        for ax in axes_to_scale:
            if ax is not None:
                ax.setStyle(tickFont=font)
                if hasattr(ax, "sync_ticks"):
                    ax.sync_ticks()

    def _build_aging_tab(self) -> None:
        """Tab 5: Cycle Aging, Capacity Fade, Health Degradation & EOL Forecasting (IMP-07)."""
        tab = QWidget()
        vlay = QVBoxLayout(tab)
        vlay.setContentsMargins(4, 4, 4, 2)
        vlay.setSpacing(2)

        # Header bar with Legends, Status Badges, and Degradation Model Controls
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(4, 2, 4, 2)
        top_bar.setSpacing(8)

        legend_row = QHBoxLayout()
        legend_row.setContentsMargins(0, 0, 0, 0)
        legend_row.setSpacing(6)
        legend_row.addWidget(_legend_label(_AGING_Q_DIS_COLOR, "Q_dis (mAh)"))
        legend_row.addWidget(_legend_label(_AGING_Q_CHG_COLOR, "Q_chg (mAh)"))
        legend_row.addWidget(_legend_label(_AGING_PROJ_COLOR, "Forecast"))
        legend_row.addWidget(_legend_label(_AGING_EOL_LINE_COLOR, "80% EOL"))
        legend_row.addWidget(_legend_label(_AGING_CE_COLOR, "CE (%)"))
        legend_row.addWidget(_legend_label(_AGING_EE_COLOR, "EE (%)"))
        legend_row.addWidget(_legend_label(_AGING_DCIR_COLOR, "DCIR (mΩ)"))
        top_bar.addLayout(legend_row)

        top_bar.addStretch(1)

        self.lbl_aging_health_badge = QLabel("● Retention: 100.0% | EOL: Calculating...")
        self.lbl_aging_health_badge.setStyleSheet(
            "background-color: #064e3b; color: #6ee7b7; border: 1px solid #059669; "
            "border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        top_bar.addWidget(self.lbl_aging_health_badge)

        self.lbl_aging_fade_badge = QLabel("Fade: 0.00 mAh/cyc")
        self.lbl_aging_fade_badge.setStyleSheet(
            "background-color: #1e293b; color: #94a3b8; border: 1px solid #334155; "
            "border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        top_bar.addWidget(self.lbl_aging_fade_badge)

        self.lbl_aging_data_state = QLabel("Waiting for first completed cycle")
        self.lbl_aging_data_state.setStyleSheet("color: #fbbf24; font-size: 11px; font-weight: 600;")
        top_bar.addWidget(self.lbl_aging_data_state)

        self.lbl_hud_aging = QLabel("<span style='color:#64748b; font-style:italic;'>Hover over chart to inspect</span>")
        self.lbl_hud_aging.setStyleSheet(_HUD_STYLE)
        top_bar.addWidget(self.lbl_hud_aging)

        top_bar.addStretch(1)

        # Model controls
        ctrls = QHBoxLayout()
        ctrls.setContentsMargins(0, 0, 0, 0)
        ctrls.setSpacing(4)
        lbl_mod = QLabel("Model:")
        lbl_mod.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600;")
        ctrls.addWidget(lbl_mod)

        btn_lin = QPushButton("Linear")
        btn_lin.setToolTip("Linear capacity fade model: Q(n) = a*n + b")
        btn_lin.setStyleSheet(_ZOOM_BTN_STYLE_ACTIVE)
        btn_lin.clicked.connect(lambda: self.set_aging_model("linear"))
        self._aging_model_buttons["linear"] = btn_lin
        ctrls.addWidget(btn_lin)

        btn_exp = QPushButton("Exp")
        btn_exp.setToolTip("Exponential capacity degradation model: Q(n) = Q₀ * exp(-k*n)")
        btn_exp.setStyleSheet(_ZOOM_BTN_STYLE_DEFAULT)
        btn_exp.clicked.connect(lambda: self.set_aging_model("exponential"))
        self._aging_model_buttons["exponential"] = btn_exp
        ctrls.addWidget(btn_exp)

        ctrls.addSpacing(6)
        btn_fit = QPushButton("Fit")
        btn_fit.setToolTip("Auto-fit cycle aging and efficiency plot views")
        btn_fit.setStyleSheet(_ZOOM_BTN_STYLE_DEFAULT)
        btn_fit.clicked.connect(self.fit_aging_view)
        ctrls.addWidget(btn_fit)

        top_bar.addLayout(ctrls)
        vlay.addLayout(top_bar)

        # Vertical Splitter for Dual Charts (Top: Capacity & Forecast, Bottom: Efficiency & DCIR)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setStyleSheet("QSplitter::handle { background-color: #334155; height: 3px; }")

        # Top Plot: Capacity Fade
        self.plot_aging_cap = pg.PlotWidget()
        self.plot_aging_cap.showGrid(x=True, y=True, alpha=0.18)
        self.plot_aging_cap.plotItem.getAxis("bottom").setTickPen(pg.mkPen("#334155", width=1))
        self.plot_aging_cap.plotItem.getAxis("left").setTickPen(pg.mkPen("#334155", width=1))
        self.plot_aging_cap.setLabel("left", "<span style='color:#38bdf8; font-weight:bold; font-size:12px;'>Capacity (mAh)</span>")
        self.plot_aging_cap.setLabel("bottom", "<span style='color:#94a3b8; font-weight:600;'>Cycle Number</span>")

        # Curves
        self.curve_aging_q_dis = self.plot_aging_cap.plot(
            pen=pg.mkPen(_AGING_Q_DIS_COLOR, width=2.0),
            symbol="o",
            symbolSize=7,
            symbolBrush=pg.mkBrush(_AGING_Q_DIS_COLOR),
            symbolPen=pg.mkPen("#0f172a", width=1),
        )

        self.curve_aging_q_chg = self.plot_aging_cap.plot(
            pen=pg.mkPen(_AGING_Q_CHG_COLOR, width=1.5, style=Qt.PenStyle.DashLine),
            symbol="s",
            symbolSize=6,
            symbolBrush=pg.mkBrush(_AGING_Q_CHG_COLOR),
            symbolPen=pg.mkPen("#0f172a", width=1),
        )

        self.curve_aging_q_proj = self.plot_aging_cap.plot(
            pen=pg.mkPen(_AGING_PROJ_COLOR, width=2.0, style=Qt.PenStyle.DashLine)
        )

        # 80% EOL target line
        self.line_aging_eol = pg.InfiniteLine(
            angle=0,
            movable=False,
            pen=pg.mkPen(_AGING_EOL_LINE_COLOR, width=1.6, style=Qt.PenStyle.DashLine),
            label="80% EOL Cutoff",
            labelOpts={"color": _AGING_EOL_LINE_COLOR, "position": 0.85},
        )
        self.line_aging_eol.setVisible(False)
        self.plot_aging_cap.addItem(self.line_aging_eol)

        # Crosshair line top
        self.crosshair_v_aging_cap = pg.InfiniteLine(
            angle=90, movable=False, pen=pg.mkPen("#cbd5e1", width=1.2, style=Qt.PenStyle.DashLine)
        )
        self.crosshair_v_aging_cap.setVisible(False)
        self.plot_aging_cap.addItem(self.crosshair_v_aging_cap, ignoreBounds=True)

        # Bottom Plot: Efficiency & DCIR
        self.plot_aging_eff = pg.PlotWidget()
        self.plot_aging_eff.showGrid(x=True, y=True, alpha=0.18)
        self.plot_aging_eff.plotItem.getAxis("bottom").setTickPen(pg.mkPen("#334155", width=1))
        self.plot_aging_eff.plotItem.getAxis("left").setTickPen(pg.mkPen("#334155", width=1))
        self.plot_aging_eff.setLabel("left", "<span style='color:#10b981; font-weight:bold; font-size:12px;'>Efficiency (%)</span>")
        self.plot_aging_eff.setLabel("bottom", "<span style='color:#94a3b8; font-weight:600;'>Cycle Number</span>")
        self.plot_aging_eff.setYRange(80.0, 102.0, padding=0.0)

        # 100% reference line
        line_100 = pg.InfiniteLine(angle=0, pos=100.0, movable=False, pen=pg.mkPen("#475569", width=1.0, style=Qt.PenStyle.DashLine))
        self.plot_aging_eff.addItem(line_100)

        self.curve_aging_ce = self.plot_aging_eff.plot(
            pen=pg.mkPen(_AGING_CE_COLOR, width=2.0),
            symbol="o",
            symbolSize=6,
            symbolBrush=pg.mkBrush(_AGING_CE_COLOR),
            symbolPen=pg.mkPen("#0f172a", width=1),
        )

        self.curve_aging_ee = self.plot_aging_eff.plot(
            pen=pg.mkPen(_AGING_EE_COLOR, width=1.8),
            symbol="t",
            symbolSize=6,
            symbolBrush=pg.mkBrush(_AGING_EE_COLOR),
            symbolPen=pg.mkPen("#0f172a", width=1),
        )

        # Right Y-Axis ViewBox for DCIR
        self.view_aging_dcir = pg.ViewBox()
        self.plot_aging_eff.plotItem.scene().addItem(self.view_aging_dcir)
        ax_dcir = self.plot_aging_eff.plotItem.getAxis("right")
        ax_dcir.linkToView(self.view_aging_dcir)
        self.plot_aging_eff.plotItem.showAxis("right")
        ax_dcir.setLabel("<span style='color:#f59e0b; font-weight:bold; font-size:12px;'>DCIR R₁₀ₛ (mΩ)</span>")
        ax_dcir.setPen(pg.mkPen(_AGING_DCIR_COLOR, width=1.8))
        ax_dcir.setTextPen(pg.mkPen(_AGING_DCIR_COLOR))
        ax_dcir.setTickPen(pg.mkPen("#334155", width=1))
        self.view_aging_dcir.setXLink(self.plot_aging_eff.plotItem)

        self.curve_aging_dcir = pg.PlotDataItem(
            pen=pg.mkPen(_AGING_DCIR_COLOR, width=1.8),
            symbol="d",
            symbolSize=6,
            symbolBrush=pg.mkBrush(_AGING_DCIR_COLOR),
            symbolPen=pg.mkPen("#0f172a", width=1),
        )
        self.view_aging_dcir.addItem(self.curve_aging_dcir)

        # Crosshair line bottom
        self.crosshair_v_aging_eff = pg.InfiniteLine(
            angle=90, movable=False, pen=pg.mkPen("#cbd5e1", width=1.2, style=Qt.PenStyle.DashLine)
        )
        self.crosshair_v_aging_eff.setVisible(False)
        self.plot_aging_eff.addItem(self.crosshair_v_aging_eff, ignoreBounds=True)

        # Link X axes of top and bottom plots
        self.plot_aging_eff.setXLink(self.plot_aging_cap)
        self.plot_aging_eff.plotItem.vb.sigResized.connect(self._sync_aging_dcir_view)

        # Mouse tracking
        self.plot_aging_cap.scene().sigMouseMoved.connect(self._on_mouse_moved_aging)
        self.plot_aging_eff.scene().sigMouseMoved.connect(self._on_mouse_moved_aging)

        splitter.addWidget(self.plot_aging_cap)
        splitter.addWidget(self.plot_aging_eff)
        splitter.setSizes([320, 220])

        vlay.addWidget(splitter)
        self.tabs.addTab(tab, "Cycle Aging && Health")

    def _sync_aging_dcir_view(self) -> None:
        """Keep right DCIR ViewBox geometrically synced with Efficiency ViewBox."""
        if hasattr(self, "view_aging_dcir") and hasattr(self, "plot_aging_eff"):
            self.view_aging_dcir.setGeometry(
                self.plot_aging_eff.plotItem.getViewBox().sceneBoundingRect()
            )
            self.view_aging_dcir.linkedViewChanged(
                self.plot_aging_eff.plotItem.getViewBox(), self.view_aging_dcir.XAxis
            )

    def _render_aging_tab(self) -> None:
        """Render cycle capacity history, EOL regression forecast, efficiency, and DCIR."""
        if not hasattr(self, "curve_aging_q_dis") or not self._cycle_indices:
            if hasattr(self, "lbl_aging_data_state"):
                self.lbl_aging_data_state.setText("Waiting for first completed cycle")
                self.lbl_aging_data_state.setStyleSheet("color: #fbbf24; font-size: 11px; font-weight: 600;")
            return

        if hasattr(self, "lbl_aging_data_state"):
            model_name = "Linear" if self._aging_model == "linear" else "Exponential"
            self.lbl_aging_data_state.setText(
                f"{len(self._cycle_indices)} completed cycle{'s' if len(self._cycle_indices) != 1 else ''} · {model_name} model"
            )
            self.lbl_aging_data_state.setStyleSheet("color: #86efac; font-size: 11px; font-weight: 600;")

        c_arr = np.array(self._cycle_indices, dtype=float)
        q_dis_arr = np.array(self._cycle_q_dis, dtype=float)
        q_chg_arr = np.array(self._cycle_q_chg, dtype=float)
        ce_arr = np.array(self._cycle_ce, dtype=float)
        ee_arr = np.array(self._cycle_ee, dtype=float)

        self.curve_aging_q_dis.setData(c_arr, q_dis_arr)
        self.curve_aging_q_chg.setData(c_arr, q_chg_arr)
        self.curve_aging_ce.setData(c_arr, ce_arr)
        self.curve_aging_ee.setData(c_arr, ee_arr)

        if self._cycle_dcir_cycles and self._cycle_dcir:
            c_dcir = np.array(self._cycle_dcir_cycles, dtype=float)
            r_dcir = np.array(self._cycle_dcir, dtype=float)
            self.curve_aging_dcir.setData(c_dcir, r_dcir)
            self.view_aging_dcir.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)

        self._sync_aging_dcir_view()

        # Run Degradation Modeling & EOL Projection
        forecast = fit_capacity_degradation(
            c_arr,
            q_dis_arr,
            eol_fraction=0.80,
            model=self._aging_model,
        )

        if forecast.q_initial_mah > 0:
            self.line_aging_eol.setPos(forecast.q_eol_mah)
            self.line_aging_eol.setVisible(True)

        if len(forecast.proj_cycles) > 0:
            self.curve_aging_q_proj.setData(forecast.proj_cycles, forecast.proj_capacities)
            self.curve_aging_q_proj.setVisible(True)
        else:
            self.curve_aging_q_proj.setData([], [])

        # Update Status Badges
        ret = forecast.current_retention_pct
        if ret >= 90.0:
            b_bg, b_col, b_border = "#064e3b", "#6ee7b7", "#059669"
        elif ret >= 80.0:
            b_bg, b_col, b_border = "#78350f", "#fde68a", "#d97706"
        else:
            b_bg, b_col, b_border = "#7f1d1d", "#fca5a5", "#dc2626"

        eol_txt = f"Cycle {forecast.projected_eol_cycle}" if forecast.projected_eol_cycle else (
            "> 3,000 cyc" if len(c_arr) >= 2 else "Calculating..."
        )
        self.lbl_aging_health_badge.setText(f"● Retention: {ret:.1f}% | EOL (80%): {eol_txt}")
        self.lbl_aging_health_badge.setStyleSheet(
            f"background-color: {b_bg}; color: {b_col}; border: 1px solid {b_border}; "
            f"border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )

        r2_txt = f" (R²: {forecast.r_squared:.3f})" if len(c_arr) >= 2 else ""
        self.lbl_aging_fade_badge.setText(
            f"Fade: {forecast.slope_mah_per_cycle:+.2f} mAh/cyc ({forecast.decay_pct_per_cycle:.3f}%/cyc){r2_txt}"
        )

    def fit_aging_view(self) -> None:
        """Auto-frame capacity and efficiency views with proper scaling and clipping protection."""
        if not hasattr(self, "plot_aging_cap") or not hasattr(self, "plot_aging_eff"):
            return

        # 1. Capacity Fade View
        if self._cycle_indices:
            max_c = max(self._cycle_indices)
            self.plot_aging_cap.setXRange(0.5, max(max_c + 1.0, 5.0), padding=0.03)

            # Capacity retention is fundamentally measured by delivered discharge capacity
            dis_caps = [q for q in self._cycle_q_dis if q > 0 and np.isfinite(q)]
            all_caps = [q for q in (self._cycle_q_dis + self._cycle_q_chg) if q > 0 and np.isfinite(q)]
            ref_caps = dis_caps if dis_caps else all_caps
            if ref_caps:
                q_min = min(ref_caps)
                q_max = max(all_caps) if all_caps else max(ref_caps)
                q_init = ref_caps[0]
                eol_q = q_init * 0.80
                y_low = max(0.0, min(q_min * 0.96, eol_q * 0.95))
                y_high = max(q_max * 1.04, y_low + 10.0)
                self.plot_aging_cap.setYRange(y_low, y_high, padding=0.03)
            else:
                self.plot_aging_cap.setYRange(0.0, 3000.0, padding=0.03)
        else:
            self.plot_aging_cap.setXRange(0.5, 10.0, padding=0.03)
            self.plot_aging_cap.setYRange(0.0, 3000.0, padding=0.03)

        # 2. Efficiency View (Coulombic & Energy Efficiency)
        eff_vals = [e for e in (self._cycle_ce + self._cycle_ee) if e > 0 and np.isfinite(e)]
        if eff_vals:
            e_min = min(eff_vals)
            e_max = max(eff_vals)
            # Default window is 80% to 102%. Dynamically expand if unconditioned Cycle 1 (e.g. 260%) or low efficiency
            y_eff_low = min(80.0, max(0.0, e_min - 5.0))
            y_eff_high = max(102.0, e_max + 5.0)
            self.plot_aging_eff.setYRange(y_eff_low, y_eff_high, padding=0.02)
        else:
            self.plot_aging_eff.setYRange(80.0, 102.0, padding=0.02)

        # 3. DCIR Right-Axis View (protect against zero-width range when 1 cycle has DCIR)
        if hasattr(self, "view_aging_dcir"):
            r_vals = [r for r in self._cycle_dcir if r > 0 and np.isfinite(r)]
            if len(r_vals) == 1:
                val = r_vals[0]
                self.view_aging_dcir.setYRange(max(0.0, val * 0.5), val * 1.5, padding=0.05)
            elif len(r_vals) > 1:
                r_min = min(r_vals)
                r_max = max(r_vals)
                span = max(2.0, (r_max - r_min) * 0.25)
                self.view_aging_dcir.setYRange(max(0.0, r_min - span), r_max + span, padding=0.03)
            else:
                self.view_aging_dcir.setYRange(0.0, 100.0, padding=0.05)

        self._sync_aging_dcir_view()

    def fit_vq_view(self) -> None:
        """Auto-frame V-Q curve view with proper battery operating window."""
        if not hasattr(self, "plot_vq"):
            return
        v_points: List[float] = list(self._vq_volt)
        q_points: List[float] = list(self._vq_cap)
        for _, p_item in self._vq_history_curves:
            x_data, y_data = p_item.getData()
            if x_data is not None and len(x_data) > 0:
                q_points.extend(x_data[::10])
            if y_data is not None and len(y_data) > 0:
                v_points.extend(y_data[::10])

        valid_v = [v for v in v_points if np.isfinite(v)]
        valid_q = [q for q in q_points if np.isfinite(q)]
        if valid_v and valid_q:
            v_min = min(valid_v)
            v_max = max(valid_v)
            q_max = max(valid_q)
            y_low = max(0.0, v_min - 0.15)
            y_high = min(6.0, v_max + 0.15)
            self.plot_vq.setYRange(y_low, y_high, padding=0.03)
            self.plot_vq.setXRange(0.0, max(50.0, q_max * 1.05), padding=0.03)
        else:
            self.plot_vq.setYRange(2.5, 4.35, padding=0.03)
            self.plot_vq.setXRange(0.0, 100.0, padding=0.03)

    def set_aging_model(self, model: str) -> None:
        """Switch between linear and exponential degradation regression models."""
        self._aging_model = model
        btn_lin = self._aging_model_buttons.get("linear")
        btn_exp = self._aging_model_buttons.get("exponential")
        if btn_lin:
            btn_lin.setStyleSheet(_ZOOM_BTN_STYLE_ACTIVE if model == "linear" else _ZOOM_BTN_STYLE_DEFAULT)
        if btn_exp:
            btn_exp.setStyleSheet(_ZOOM_BTN_STYLE_ACTIVE if model == "exponential" else _ZOOM_BTN_STYLE_DEFAULT)
        self._render_aging_tab()

    def _on_mouse_moved_aging(self, pos) -> None:
        """Interactive inspection crosshair and HUD for cycle aging."""
        if not hasattr(self, "plot_aging_cap") or not self._cycle_indices:
            return
        vb_cap = self.plot_aging_cap.plotItem.vb
        vb_eff = self.plot_aging_eff.plotItem.vb

        in_cap = self.plot_aging_cap.plotItem.sceneBoundingRect().contains(pos)
        in_eff = self.plot_aging_eff.plotItem.sceneBoundingRect().contains(pos)

        if in_cap or in_eff:
            vb = vb_cap if in_cap else vb_eff
            mouse_pt = vb.mapSceneToView(pos)
            c_mouse = mouse_pt.x()

            self.crosshair_v_aging_cap.setPos(c_mouse)
            self.crosshair_v_aging_eff.setPos(c_mouse)
            self.crosshair_v_aging_cap.setVisible(True)
            self.crosshair_v_aging_eff.setVisible(True)

            c_arr = np.array(self._cycle_indices)
            idx = int(np.clip(np.searchsorted(c_arr, c_mouse), 0, len(c_arr) - 1))
            if idx > 0 and abs(c_arr[idx - 1] - c_mouse) < abs(c_arr[idx] - c_mouse):
                idx -= 1

            cyc = self._cycle_indices[idx]
            q_dis = self._cycle_q_dis[idx] if idx < len(self._cycle_q_dis) else 0.0
            q_chg = self._cycle_q_chg[idx] if idx < len(self._cycle_q_chg) else 0.0
            ce = self._cycle_ce[idx] if idx < len(self._cycle_ce) else 0.0
            ee = self._cycle_ee[idx] if idx < len(self._cycle_ee) else 0.0

            dcir_val = "N/A"
            if cyc in self._cycle_dcir_cycles:
                d_idx = self._cycle_dcir_cycles.index(cyc)
                dcir_val = f"{self._cycle_dcir[d_idx]:.2f} mΩ"

            self.lbl_hud_aging.setText(
                f"<b style='color:#f8fafc;'>Cycle {cyc}</b>:  "
                f"<span style='color:{_AGING_Q_DIS_COLOR};'>●</span> <b>Q_dis: {q_dis:.1f} mAh</b>  "
                f"<span style='color:{_AGING_Q_CHG_COLOR};'>■</span> <b>Q_chg: {q_chg:.1f} mAh</b>  "
                f"<span style='color:{_AGING_CE_COLOR};'>●</span> <b>CE: {ce:.1f}%</b>  "
                f"<span style='color:{_AGING_EE_COLOR};'>▲</span> <b>EE: {ee:.1f}%</b>  "
                f"<span style='color:{_AGING_DCIR_COLOR};'>♦</span> <b>DCIR: {dcir_val}</b>"
            )
        else:
            self.crosshair_v_aging_cap.setVisible(False)
            self.crosshair_v_aging_eff.setVisible(False)
            self.lbl_hud_aging.setText("<span style='color:#64748b; font-style:italic;'>Hover over chart to inspect</span>")

