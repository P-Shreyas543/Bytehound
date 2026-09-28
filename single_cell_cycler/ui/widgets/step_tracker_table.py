"""Real-time test step execution tracker and completed step history table."""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.metrics_tracker import StepMetrics
from ..theme import (
    BG_CARD,
    BORDER_COLOR,
    COLOR_ACCENT,
    COLOR_CHARGE,
    COLOR_DISCHARGE,
    COLOR_REST,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class StepTrackerTableWidget(QWidget):
    """Tracks running step progress and historical sequence of completed steps."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.step_start_time: Optional[float] = None
        self.test_start_time: Optional[float] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 1. Live Progress Banner
        self.banner = QFrame()
        self.banner.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER_COLOR};
                border-radius: 8px;
                padding: 8px;
            }}
        """)
        b_layout = QHBoxLayout(self.banner)
        b_layout.setContentsMargins(12, 6, 12, 6)

        self.lbl_active_step = QLabel("STATUS: IDLE")
        self.lbl_active_step.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {TEXT_PRIMARY};")
        b_layout.addWidget(self.lbl_active_step)
        b_layout.addStretch()

        self.lbl_step_timer = QLabel("Step Time: 00:00:00")
        self.lbl_step_timer.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {COLOR_ACCENT}; font-family: 'Consolas', monospace;")
        b_layout.addWidget(self.lbl_step_timer)

        self.lbl_tot_timer = QLabel("Total Time: 00:00:00")
        self.lbl_tot_timer.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {TEXT_SECONDARY}; font-family: 'Consolas', monospace; margin-left: 16px;")
        b_layout.addWidget(self.lbl_tot_timer)

        layout.addWidget(self.banner)

        # 2. History Table
        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels([
            "Cycle",
            "Step",
            "Name",
            "Type",
            "Duration (s)",
            "Start V",
            "End V",
            "Peak I (A)",
            "Capacity (mAh)",
            "Energy (mWh)",
            "Cut-off Trigger Reason",
        ])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        # Timer to update live execution clocks
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._update_clocks)
        self._timer.start()

    def set_active_step(self, cycle_idx: int, step_idx: int, step_name: str, step_type: str) -> None:
        self.lbl_active_step.setText(f"CYCLE {cycle_idx} | STEP {step_idx}: {step_name.upper()} ({step_type.upper()})")
        color = COLOR_CHARGE if step_type.lower() == "charge" else (COLOR_DISCHARGE if step_type.lower() == "discharge" else COLOR_REST)
        self.lbl_active_step.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {color};")
        self.step_start_time = time.time()
        if self.test_start_time is None:
            self.test_start_time = self.step_start_time

    def add_completed_step(self, metrics: StepMetrics) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        items = [
            str(metrics.cycle_index),
            str(metrics.step_index),
            metrics.step_name,
            metrics.step_type.value,
            f"{metrics.duration_s:.1f}",
            f"{metrics.start_voltage:.3f}",
            f"{metrics.end_voltage:.3f}",
            f"{metrics.peak_current:.3f}",
            f"{abs(metrics.capacity_mah):.1f}",
            f"{abs(metrics.energy_mwh):.1f}",
            metrics.cutoff_reason,
        ]

        for col, text in enumerate(items):
            item = QTableWidgetItem(text)
            if col in (0, 1, 4, 5, 6, 7, 8, 9):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, col, item)

        self.table.scrollToBottom()

    def set_idle(self, msg: str = "STATUS: IDLE") -> None:
        self.lbl_active_step.setText(msg)
        self.lbl_active_step.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {TEXT_MUTED};")
        self.step_start_time = None

    def reset_all(self) -> None:
        self.table.setRowCount(0)
        self.step_start_time = None
        self.test_start_time = None
        self.lbl_active_step.setText("STATUS: IDLE")
        self.lbl_step_timer.setText("Step Time: 00:00:00")
        self.lbl_tot_timer.setText("Total Time: 00:00:00")

    def _update_clocks(self) -> None:
        now = time.time()
        if self.step_start_time is not None:
            el_s = int(now - self.step_start_time)
            m, s = divmod(el_s, 60)
            h, m = divmod(m, 60)
            self.lbl_step_timer.setText(f"Step Time: {h:02d}:{m:02d}:{s:02d}")

        if self.test_start_time is not None:
            el_tot = int(now - self.test_start_time)
            m, s = divmod(el_tot, 60)
            h, m = divmod(m, 60)
            self.lbl_tot_timer.setText(f"Total Time: {h:02d}:{m:02d}:{s:02d}")
