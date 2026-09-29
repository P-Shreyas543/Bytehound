"""Real-time test step execution tracker and completed step history table."""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
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
    BG_PANEL,
    BORDER_COLOR,
    COLOR_ACCENT,
    COLOR_CHARGE,
    COLOR_DANGER,
    COLOR_DISCHARGE,
    COLOR_REST,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

# Row background tints per step type
_ROW_COLORS = {
    "charge":    "#0f2d1a",   # dark green tint
    "discharge": "#2d1f08",   # dark amber tint
    "rest":      "#1a1f2c",   # neutral dark panel
}
_CYCLE_SEP_BG = "#1e293b"  # slate – cycle boundary rows

# Column indices (keep in sync with _HEADERS)
_COL_CYCLE   = 0
_COL_STEP    = 1
_COL_NAME    = 2
_COL_TYPE    = 3
_COL_DUR     = 4
_COL_START_V = 5
_COL_END_V   = 6
_COL_PEAK_I  = 7
_COL_CAP     = 8
_COL_ENERGY  = 9
_COL_DCIR    = 10
_COL_CUTOFF  = 11

_HEADERS = [
    "Cycle", "Step", "Name", "Type",
    "Duration", "Start V", "End V",
    "Peak I (A)", "Capacity (mAh)", "Energy (mWh)",
    "DCIR (mOhm)", "Cut-off Reason",
]
_NUM_COLS = len(_HEADERS)


def _fmt_duration(seconds: float) -> str:
    """Convert seconds to H:MM:SS or MM:SS string."""
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _type_color(step_type_lower: str) -> str:
    if step_type_lower == "charge":
        return COLOR_CHARGE
    if step_type_lower == "discharge":
        return COLOR_DISCHARGE
    return COLOR_REST


class StepTrackerTableWidget(QWidget):
    """Tracks running step progress and historical sequence of completed steps."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.step_start_time: Optional[float] = None
        self.test_start_time: Optional[float] = None
        self._last_cycle_shown: int = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # ------------------------------------------------------------------ #
        # Live Progress Banner                                                 #
        # ------------------------------------------------------------------ #
        self.banner = QFrame()
        self.banner.setStyleSheet(
            f"QFrame {{ background-color: {BG_CARD}; border: 1px solid {BORDER_COLOR}; border-radius: 8px; }}"
        )
        b_layout = QHBoxLayout(self.banner)
        b_layout.setContentsMargins(14, 8, 14, 8)
        b_layout.setSpacing(12)

        self.lbl_step_badge = QLabel("\u25cf")
        self.lbl_step_badge.setFixedWidth(14)
        self.lbl_step_badge.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 16px;")
        b_layout.addWidget(self.lbl_step_badge)

        self.lbl_active_step = QLabel("STATUS: IDLE")
        self.lbl_active_step.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {TEXT_MUTED};"
        )
        b_layout.addWidget(self.lbl_active_step, stretch=1)

        def _vsep():
            s = QFrame()
            s.setFrameShape(QFrame.Shape.VLine)
            s.setStyleSheet(f"color: {BORDER_COLOR};")
            return s

        b_layout.addWidget(_vsep())

        self.lbl_step_timer = QLabel("Step  00:00")
        self.lbl_step_timer.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {COLOR_ACCENT}; font-family: Consolas, monospace;"
        )
        b_layout.addWidget(self.lbl_step_timer)

        b_layout.addWidget(_vsep())

        self.lbl_tot_timer = QLabel("Total  00:00")
        self.lbl_tot_timer.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {TEXT_SECONDARY}; font-family: Consolas, monospace;"
        )
        b_layout.addWidget(self.lbl_tot_timer)

        layout.addWidget(self.banner)

        # ------------------------------------------------------------------ #
        # History Table                                                        #
        # ------------------------------------------------------------------ #
        self.table = QTableWidget(0, _NUM_COLS)
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)

        hdr = self.table.horizontalHeader()
        for col in range(_NUM_COLS):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_NAME,   QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_CUTOFF, QHeaderView.ResizeMode.Stretch)

        self.table.setColumnWidth(_COL_CYCLE,   52)
        self.table.setColumnWidth(_COL_STEP,    48)
        self.table.setColumnWidth(_COL_TYPE,    82)
        self.table.setColumnWidth(_COL_DUR,     80)
        self.table.setColumnWidth(_COL_START_V, 74)
        self.table.setColumnWidth(_COL_END_V,   74)
        self.table.setColumnWidth(_COL_PEAK_I,  80)
        self.table.setColumnWidth(_COL_CAP,    102)
        self.table.setColumnWidth(_COL_ENERGY,  92)
        self.table.setColumnWidth(_COL_DCIR,    80)

        layout.addWidget(self.table)

        # ------------------------------------------------------------------ #
        # Clock update timer (500ms is optimal for 1-second resolution clocks) #
        # ------------------------------------------------------------------ #
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._update_clocks)
        self._timer.start()

    # ----------------------------------------------------------------------- #
    # Public API                                                               #
    # ----------------------------------------------------------------------- #

    def set_active_step(
        self, cycle_idx: int, step_idx: int, step_name: str, step_type: str
    ) -> None:
        """Update banner when a new step starts executing."""
        t_lower = step_type.lower()
        color = _type_color(t_lower)
        self.lbl_step_badge.setStyleSheet(f"color: {color}; font-size: 16px;")
        self.lbl_active_step.setText(
            f"Cycle {cycle_idx}  \u203a  Step {step_idx}: {step_name}  [{step_type.upper()}]"
        )
        self.lbl_active_step.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {color};"
        )
        self.step_start_time = time.time()
        if self.test_start_time is None:
            self.test_start_time = self.step_start_time

    def add_completed_step(self, metrics: StepMetrics) -> None:
        """Append a completed step row, with a cycle separator if needed."""
        if metrics.cycle_index > self._last_cycle_shown and self._last_cycle_shown > 0:
            self._insert_cycle_separator(metrics.cycle_index)
        self._last_cycle_shown = metrics.cycle_index

        t_lower = metrics.step_type.value.lower()
        row_bg  = _ROW_COLORS.get(t_lower, _ROW_COLORS["rest"])
        text_col = _type_color(t_lower)

        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 26)

        dcir_str = f"{metrics.dcir_mohm:.1f}" if metrics.dcir_mohm is not None else "--"

        values = [
            str(metrics.cycle_index),
            str(metrics.step_index),
            metrics.step_name,
            metrics.step_type.value.upper(),
            _fmt_duration(metrics.duration_s),
            f"{metrics.start_voltage:.3f} V",
            f"{metrics.end_voltage:.3f} V",
            f"{metrics.peak_current:.3f}",
            f"{abs(metrics.capacity_mah):.2f}",
            f"{abs(metrics.energy_mwh):.2f}",
            dcir_str,
            metrics.cutoff_reason or "--",
        ]

        center_cols = {
            _COL_CYCLE, _COL_STEP, _COL_TYPE, _COL_DUR,
            _COL_START_V, _COL_END_V, _COL_PEAK_I,
            _COL_CAP, _COL_ENERGY, _COL_DCIR,
        }

        for col, text in enumerate(values):
            item = QTableWidgetItem(text)
            item.setBackground(QColor(row_bg))
            if col == _COL_TYPE:
                item.setForeground(QColor(text_col))
                pt = self.font().pointSize()
                item.setFont(QFont("Segoe UI", max(9, pt if pt > 0 else 10), QFont.Weight.Bold))
            elif col in (_COL_CAP, _COL_ENERGY):
                item.setForeground(QColor(text_col))
            elif col == _COL_CUTOFF and "FAULT" in text:
                item.setForeground(QColor(COLOR_DANGER))
                pt = self.font().pointSize()
                item.setFont(QFont("Segoe UI", max(9, pt if pt > 0 else 10), QFont.Weight.Bold))
            else:
                item.setForeground(QColor(TEXT_PRIMARY))
            if col in center_cols:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, col, item)

        self.table.scrollToBottom()

    def set_idle(self, msg: str = "STATUS: IDLE") -> None:
        """Called when a test finishes or is stopped."""
        self.lbl_step_badge.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 16px;")
        self.lbl_active_step.setText(msg)
        self.lbl_active_step.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {TEXT_MUTED};"
        )
        self.step_start_time = None
        # test_start_time intentionally kept so final elapsed stays frozen

    def reset_all(self) -> None:
        """Full reset for a new test run."""
        self.table.setRowCount(0)
        self.step_start_time = None
        self.test_start_time = None
        self._last_cycle_shown = 0
        self.lbl_step_badge.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 16px;")
        self.lbl_active_step.setText("STATUS: IDLE")
        self.lbl_active_step.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {TEXT_MUTED};"
        )
        self.lbl_step_timer.setText("Step  00:00")
        self.lbl_tot_timer.setText("Total  00:00")

    # ----------------------------------------------------------------------- #
    # Internal helpers                                                         #
    # ----------------------------------------------------------------------- #

    def _insert_cycle_separator(self, next_cycle: int) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 20)
        sep_item = QTableWidgetItem(f"  \u2500\u2500  Cycle {next_cycle}  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
        sep_item.setBackground(QColor(_CYCLE_SEP_BG))
        sep_item.setForeground(QColor(COLOR_ACCENT))
        pt = self.font().pointSize()
        sep_item.setFont(QFont("Segoe UI", max(9, pt if pt > 0 else 10), QFont.Weight.Bold))
        sep_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.table.setItem(row, 0, sep_item)
        self.table.setSpan(row, 0, 1, _NUM_COLS)

    def _update_clocks(self) -> None:
        now = time.time()
        s_text = f"Step  {_fmt_duration(now - self.step_start_time)}" if self.step_start_time is not None else "Step  00:00"
        if s_text != self.lbl_step_timer.text():
            self.lbl_step_timer.setText(s_text)

        t_text = f"Total  {_fmt_duration(now - self.test_start_time)}" if self.test_start_time is not None else "Total  00:00"
        if t_text != self.lbl_tot_timer.text():
            self.lbl_tot_timer.setText(t_text)
