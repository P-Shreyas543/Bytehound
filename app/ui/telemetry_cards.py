"""Subsystem Telemetry Card & Grid View for Bytehound."""

from __future__ import annotations

from typing import Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QGridLayout, QScrollArea, QGroupBox
)

from ..decoder.types import SignalSpec, FrameConfig


class SignalCardWidget(QFrame):
    """Visual card displaying a single signal's real-time state and quick plot button."""

    quick_plot_requested = Signal(str)  # signal_name

    def __init__(self, spec: SignalSpec, parent=None):
        super().__init__(parent)
        self.signal_name = spec.signal_name
        self.unit = spec.unit or ""
        self.min_val = spec.min_value
        self.max_val = spec.max_value
        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 10px;
            }
            QFrame:hover {
                border: 1px solid #3b82f6;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)

        # Header row: Name + Quick Plot Button
        h_layout = QHBoxLayout()
        name_label = QLabel(self.signal_name)
        name_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        name_label.setStyleSheet("color: #f8fafc;")

        plot_btn = QPushButton("📈")
        plot_btn.setToolTip("Click to add signal to Live Plot")
        plot_btn.setFixedSize(24, 24)
        plot_btn.setStyleSheet("""
            QPushButton { background-color: #334155; border: none; border-radius: 4px; color: #38bdf8; }
            QPushButton:hover { background-color: #2563eb; color: white; }
        """)
        plot_btn.clicked.connect(lambda: self.quick_plot_requested.emit(self.signal_name))

        h_layout.addWidget(name_label, 1)
        h_layout.addWidget(plot_btn)

        # Value row
        val_h = QHBoxLayout()
        self.val_label = QLabel("--")
        self.val_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.val_label.setStyleSheet("color: #38bdf8;")

        self.unit_label = QLabel(self.unit)
        self.unit_label.setFont(QFont("Segoe UI", 9))
        self.unit_label.setStyleSheet("color: #94a3b8;")

        val_h.addWidget(self.val_label)
        val_h.addWidget(self.unit_label)
        val_h.addStretch()

        # Status badge row
        stat_h = QHBoxLayout()
        self.status_pill = QLabel("OK")
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_pill.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.status_pill.setStyleSheet("""
            background-color: #10b981; color: white; border-radius: 10px; padding: 2px 8px;
        """)

        range_text = ""
        if self.min_val is not None and self.max_val is not None:
            range_text = f"Range: [{self.min_val:.1f} .. {self.max_val:.1f}]"
        self.range_label = QLabel(range_text)
        self.range_label.setFont(QFont("Segoe UI", 8))
        self.range_label.setStyleSheet("color: #64748b;")

        stat_h.addWidget(self.status_pill)
        stat_h.addStretch()
        stat_h.addWidget(self.range_label)

        layout.addLayout(h_layout)
        layout.addLayout(val_h)
        layout.addLayout(stat_h)

    def update_value(self, value: float | int | str, status: str = "ok") -> None:
        if isinstance(value, float):
            self.val_label.setText(f"{value:.3f}")
        else:
            self.val_label.setText(str(value))

        status_lower = str(status).lower()
        if "error" in status_lower or "fault" in status_lower:
            self.status_pill.setText("ERROR")
            self.status_pill.setStyleSheet("background-color: #ef4444; color: white; border-radius: 10px; padding: 2px 8px;")
            self.val_label.setStyleSheet("color: #ef4444;")
        elif "warn" in status_lower:
            self.status_pill.setText("WARN")
            self.status_pill.setStyleSheet("background-color: #f59e0b; color: white; border-radius: 10px; padding: 2px 8px;")
            self.val_label.setStyleSheet("color: #f59e0b;")
        else:
            self.status_pill.setText("OK")
            self.status_pill.setStyleSheet("background-color: #10b981; color: white; border-radius: 10px; padding: 2px 8px;")
            self.val_label.setStyleSheet("color: #38bdf8;")


class TelemetryCardsView(QWidget):
    """Grid container organizing signal cards into subsystem groups."""

    quick_plot_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: Dict[str, SignalCardWidget] = {}
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setSpacing(16)

        self.scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll_area)

    def rebuild_from_config(self, config: Optional[FrameConfig]) -> None:
        # Clear existing cards
        while self.content_layout.count():
            child = self.content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._cards.clear()

        if not config:
            empty_lbl = QLabel("No active protocol loaded.")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet("color: #64748b; font-size: 14px; margin-top: 40px;")
            self.content_layout.addWidget(empty_lbl)
            return

        # Group signals by spec.group
        groups: Dict[str, List[SignalSpec]] = {}
        for spec in config.all_signals:
            grp = spec.group or "General"
            groups.setdefault(grp, []).append(spec)

        for grp_name, specs in groups.items():
            grp_box = QGroupBox(f" Subsystem: {grp_name} ({len(specs)} signals)")
            grp_box.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            grp_box.setStyleSheet("""
                QGroupBox { border: 1px solid #334155; border-radius: 8px; margin-top: 10px; padding: 12px; }
                QGroupBox::title { color: #38bdf8; subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            """)
            grid = QGridLayout(grp_box)
            grid.setSpacing(12)

            col_count = 3
            for i, spec in enumerate(specs):
                card = SignalCardWidget(spec)
                card.quick_plot_requested.connect(self.quick_plot_requested.emit)
                self._cards[spec.signal_name] = card
                row = i // col_count
                col = i % col_count
                grid.addWidget(card, row, col)

            self.content_layout.addWidget(grp_box)

        self.content_layout.addStretch()

    def update_signal_value(self, signal_name: str, value: float | int | str, status: str = "ok") -> None:
        if signal_name in self._cards:
            self._cards[signal_name].update_value(value, status)
