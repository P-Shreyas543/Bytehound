"""High-performance real-time plotting widget using pyqtgraph."""

from __future__ import annotations

import collections
import time
from typing import List, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from ...comm.packet_codec import CellDataTelemetry
from ..theme import (
    BG_DARK,
    BG_PANEL,
    COLOR_ACCENT,
    COLOR_CHARGE,
    COLOR_DISCHARGE,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

# Configure pyqtgraph global options for dark theme
pg.setConfigOption("background", BG_PANEL)
pg.setConfigOption("foreground", TEXT_SECONDARY)
pg.setConfigOption("antialias", True)


class LivePlotWidget(QWidget):
    """Multi-tab high-speed telemetry chart suite with decimated rendering."""

    def __init__(self, max_buffer_points: int = 5000, parent: QWidget | None = None):
        super().__init__(parent)
        self.max_points = max_buffer_points

        # Data buffers
        self.times = collections.deque(maxlen=self.max_points)
        self.voltages = collections.deque(maxlen=self.max_points)
        self.currents = collections.deque(maxlen=self.max_points)
        self.term_temps = collections.deque(maxlen=self.max_points)
        self.body_temps = collections.deque(maxlen=self.max_points)

        # V-Q curves data: list of (cycle_idx, step_type, list_of_caps, list_of_volts)
        self.vq_cycles: List[tuple] = []
        self._current_vq_cap = collections.deque(maxlen=2000)
        self._current_vq_volts = collections.deque(maxlen=2000)

        # Cycle Aging metrics
        self.cycle_indices: List[int] = []
        self.cycle_capacities: List[float] = []
        self.cycle_efficiencies: List[float] = []

        self.start_epoch = time.time()
        self._dirty = False

        self._setup_ui()

        # Decimated fixed-rate 25 FPS redraw timer
        self._redraw_timer = QTimer(self)
        self._redraw_timer.setInterval(40)  # 40ms = 25 FPS
        self._redraw_timer.timeout.connect(self._on_redraw_tick)
        self._redraw_timer.start()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tab 1: Voltage & Current vs Time (Dual Axis)
        self.tab_vi = QWidget()
        vi_layout = QVBoxLayout(self.tab_vi)
        vi_layout.setContentsMargins(4, 4, 4, 4)

        self.plot_vi = pg.PlotWidget()
        self.plot_vi.showGrid(x=True, y=True, alpha=0.25)
        self.plot_vi.setLabel("left", "Cell Voltage", units="V", color=COLOR_ACCENT)
        self.plot_vi.setLabel("bottom", "Elapsed Time", units="s")

        # Create secondary ViewBox for Current on the right
        self.curve_voltage = self.plot_vi.plot(pen=pg.mkPen(COLOR_ACCENT, width=2.0), name="Voltage (V)")

        self.view_current = pg.ViewBox()
        self.plot_vi.plotItem.scene().addItem(self.view_current)
        self.plot_vi.plotItem.getAxis("right").linkToView(self.view_current)
        self.plot_vi.plotItem.showAxis("right")
        self.plot_vi.plotItem.getAxis("right").setLabel("Cell Current", units="A", color=COLOR_CHARGE)
        self.view_current.setXLink(self.plot_vi.plotItem)

        self.curve_current = pg.PlotCurveItem(pen=pg.mkPen(COLOR_CHARGE, width=1.8), name="Current (A)")
        self.view_current.addItem(self.curve_current)

        # Connect view resize
        self.plot_vi.plotItem.getViewBox().sigResized.connect(self._update_views)

        vi_layout.addWidget(self.plot_vi)
        self.tabs.addTab(self.tab_vi, "Voltage & Current vs Time")

        # Tab 2: Temperatures vs Time
        self.tab_temp = QWidget()
        t_layout = QVBoxLayout(self.tab_temp)
        t_layout.setContentsMargins(4, 4, 4, 4)
        self.plot_temp = pg.PlotWidget()
        self.plot_temp.showGrid(x=True, y=True, alpha=0.25)
        self.plot_temp.setLabel("left", "Temperature", units="°C")
        self.plot_temp.setLabel("bottom", "Elapsed Time", units="s")
        self.curve_term_temp = self.plot_temp.plot(pen=pg.mkPen("#f97316", width=2.0), name="Terminal Temp")
        self.curve_body_temp = self.plot_temp.plot(pen=pg.mkPen("#ec4899", width=2.0), name="Body Temp")
        t_layout.addWidget(self.plot_temp)
        self.tabs.addTab(self.tab_temp, "Temperature vs Time")

        # Tab 3: Voltage vs Capacity (V-Q Curves)
        self.tab_vq = QWidget()
        vq_layout = QVBoxLayout(self.tab_vq)
        vq_layout.setContentsMargins(4, 4, 4, 4)
        self.plot_vq = pg.PlotWidget()
        self.plot_vq.showGrid(x=True, y=True, alpha=0.25)
        self.plot_vq.setLabel("left", "Voltage", units="V")
        self.plot_vq.setLabel("bottom", "Step Capacity", units="mAh")
        self.curve_vq_current = self.plot_vq.plot(pen=pg.mkPen("#38bdf8", width=2.2))
        vq_layout.addWidget(self.plot_vq)
        self.tabs.addTab(self.tab_vq, "Voltage vs Capacity (V-Q)")

        # Tab 4: Cycle Aging & Efficiency
        self.tab_aging = QWidget()
        aging_layout = QVBoxLayout(self.tab_aging)
        aging_layout.setContentsMargins(4, 4, 4, 4)
        self.plot_aging = pg.PlotWidget()
        self.plot_aging.showGrid(x=True, y=True, alpha=0.25)
        self.plot_aging.setLabel("left", "Discharge Capacity", units="mAh", color="#a855f7")
        self.plot_aging.setLabel("bottom", "Cycle Number")
        self.curve_aging_cap = self.plot_aging.plot(
            pen=pg.mkPen("#a855f7", width=2.0),
            symbol="o",
            symbolSize=7,
            symbolBrush="#a855f7",
        )
        aging_layout.addWidget(self.plot_aging)
        self.tabs.addTab(self.tab_aging, "Cycle Capacity Degradation")

    def _update_views(self) -> None:
        self.view_current.setGeometry(self.plot_vi.plotItem.getViewBox().sceneBoundingRect())
        self.view_current.linkedViewChanged(self.plot_vi.plotItem.getViewBox(), self.view_current.XAxis)

    def add_telemetry(self, data: CellDataTelemetry, step_mah: float = 0.0) -> None:
        """Push point into deques."""
        elapsed = data.timestamp - self.start_epoch if data.timestamp > 0 else time.time() - self.start_epoch
        self.times.append(elapsed)
        self.voltages.append(data.voltage)
        self.currents.append(data.current)
        self.term_temps.append(data.terminal_temp)
        self.body_temps.append(data.body_temp)

        # V-Q
        self._current_vq_cap.append(abs(step_mah))
        self._current_vq_volts.append(data.voltage)

        self._dirty = True

    def reset_step_vq(self) -> None:
        """Called when a step starts to reset active V-Q trace."""
        if len(self._current_vq_cap) > 10:
            # Store completed curve
            caps = np.array(self._current_vq_cap)
            volts = np.array(self._current_vq_volts)
            # Add static background curve to plot
            self.plot_vq.plot(caps, volts, pen=pg.mkPen("#475569", width=1.0, style=pg.QtCore.Qt.PenStyle.DashLine))
        self._current_vq_cap.clear()
        self._current_vq_volts.clear()

    def add_cycle_summary(self, cycle_idx: int, discharge_mah: float, coulombic_eff: float) -> None:
        self.cycle_indices.append(cycle_idx)
        self.cycle_capacities.append(discharge_mah)
        self.cycle_efficiencies.append(coulombic_eff)
        self.curve_aging_cap.setData(self.cycle_indices, self.cycle_capacities)

    def reset_all(self) -> None:
        self.times.clear()
        self.voltages.clear()
        self.currents.clear()
        self.term_temps.clear()
        self.body_temps.clear()
        self.vq_cycles.clear()
        self._current_vq_cap.clear()
        self._current_vq_volts.clear()
        self.cycle_indices.clear()
        self.cycle_capacities.clear()
        self.cycle_efficiencies.clear()
        self.plot_vq.clear()
        self.curve_vq_current = self.plot_vq.plot(pen=pg.mkPen("#38bdf8", width=2.2))
        self.start_epoch = time.time()
        self._dirty = True

    def _on_redraw_tick(self) -> None:
        """Batched redraw triggered at fixed 25 FPS rate."""
        if not self._dirty or not self.times:
            return
        self._dirty = False

        t = np.array(self.times)
        v = np.array(self.voltages)
        i = np.array(self.currents)
        t_term = np.array(self.term_temps)
        t_body = np.array(self.body_temps)

        # Update Tab 1 (V & I)
        current_tab = self.tabs.currentIndex()
        if current_tab == 0:
            self.curve_voltage.setData(t, v)
            self.curve_current.setData(t, i)
            # Auto-range right axis smoothly
            if len(i) > 0:
                i_min, i_max = float(np.min(i)), float(np.max(i))
                pad = max(0.5, (i_max - i_min) * 0.1)
                self.view_current.setYRange(i_min - pad, i_max + pad)

        # Update Tab 2 (Temps)
        elif current_tab == 1:
            self.curve_term_temp.setData(t, t_term)
            self.curve_body_temp.setData(t, t_body)

        # Update Tab 3 (V-Q)
        elif current_tab == 2:
            if self._current_vq_cap:
                self.curve_vq_current.setData(np.array(self._current_vq_cap), np.array(self._current_vq_volts))
