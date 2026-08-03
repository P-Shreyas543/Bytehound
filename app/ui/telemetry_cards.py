"""Subsystem Telemetry Card & Grid View for Bytehound."""

from __future__ import annotations

from typing import Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QGridLayout, QScrollArea, QGroupBox, QLineEdit, QProgressBar, QComboBox
)

from ..decoder.types import SignalSpec, FrameConfig


class SignalCardWidget(QFrame):
    """Sleek visual telemetry card displaying real-time value, status, range gauge, and quick plot."""

    quick_plot_requested = Signal(str)  # signal_name

    def __init__(self, spec: SignalSpec, parent=None):
        super().__init__(parent)
        self.signal_name = spec.signal_name
        self.unit = spec.unit or ""
        self.min_val = spec.min_value
        self.max_val = spec.max_value
        self.data_type = (spec.data_type or "").lower()
        self.is_boolean = spec.is_boolean or self.data_type in ("bool", "boolean")
        self._init_ui()

    def _init_ui(self) -> None:
        self.setObjectName("SignalCard")
        self.setStyleSheet("""
            QFrame#SignalCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e293b, stop:1 #0f172a);
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 6px;
            }
            QFrame#SignalCard:hover {
                border: 1px solid #38bdf8;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #334155, stop:1 #1e293b);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(10, 10, 10, 10)

        # Header row: Name + Quick Plot Button
        h_layout = QHBoxLayout()
        h_layout.setSpacing(4)
        name_label = QLabel(self.signal_name)
        name_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        name_label.setStyleSheet("color: #f8fafc;")

        plot_btn = QPushButton("📈")
        plot_btn.setToolTip("Click to add signal to Live Plot")
        plot_btn.setFixedSize(26, 26)
        plot_btn.setCursor(Qt.PointingHandCursor)
        plot_btn.setStyleSheet("""
            QPushButton {
                background-color: #334155;
                border: 1px solid #475569;
                border-radius: 5px;
                color: #38bdf8;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #2563eb;
                color: #ffffff;
                border: 1px solid #60a5fa;
            }
        """)
        plot_btn.clicked.connect(lambda: self.quick_plot_requested.emit(self.signal_name))

        h_layout.addWidget(name_label, 1)
        h_layout.addWidget(plot_btn)

        # Value + Unit Row
        val_h = QHBoxLayout()
        val_h.setSpacing(6)
        self.val_label = QLabel("--")
        self.val_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.val_label.setStyleSheet("color: #38bdf8;")

        self.unit_label = QLabel(self.unit)
        self.unit_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.unit_label.setStyleSheet("color: #94a3b8; margin-top: 6px;")

        val_h.addWidget(self.val_label)
        val_h.addWidget(self.unit_label)
        val_h.addStretch()

        # Optional Range Progress Bar / Gauge
        self.range_bar = QProgressBar()
        self.range_bar.setFixedHeight(5)
        self.range_bar.setTextVisible(False)
        self.range_bar.setStyleSheet("""
            QProgressBar {
                background-color: #0f172a;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #38bdf8;
                border-radius: 2px;
            }
        """)
        has_range = (self.min_val is not None and self.max_val is not None and self.max_val > self.min_val)
        self.range_bar.setVisible(has_range and not self.is_boolean)

        # Status badge & Range text row
        stat_h = QHBoxLayout()
        stat_h.setSpacing(6)
        self.status_pill = QLabel("OK")
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_pill.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.status_pill.setStyleSheet("""
            background-color: #064e3b; color: #34d399; border: 1px solid #059669; border-radius: 8px; padding: 2px 8px;
        """)

        range_text = ""
        if has_range:
            range_text = f"[{self.min_val:g} .. {self.max_val:g}]"
        self.range_label = QLabel(range_text)
        self.range_label.setFont(QFont("Segoe UI", 8))
        self.range_label.setStyleSheet("color: #64748b;")

        stat_h.addWidget(self.status_pill)
        stat_h.addStretch()
        if range_text:
            stat_h.addWidget(self.range_label)

        layout.addLayout(h_layout)
        layout.addLayout(val_h)
        if has_range and not self.is_boolean:
            layout.addWidget(self.range_bar)
        layout.addLayout(stat_h)

    def update_value(self, value: float | int | str, status: str = "ok") -> None:
        if self.is_boolean:
            try:
                numeric = float(value)
                is_on = (numeric != 0)
            except (ValueError, TypeError):
                is_on = str(value).strip().lower() in ("1", "true", "on", "active")
            if is_on:
                self.val_label.setText("ACTIVE (1)")
                self.val_label.setStyleSheet("color: #34d399;")
                self.status_pill.setText("ON")
                self.status_pill.setStyleSheet("background-color: #064e3b; color: #34d399; border: 1px solid #059669; border-radius: 8px; padding: 2px 8px;")
            else:
                self.val_label.setText("OFF (0)")
                self.val_label.setStyleSheet("color: #94a3b8;")
                self.status_pill.setText("OFF")
                self.status_pill.setStyleSheet("background-color: #1e293b; color: #64748b; border: 1px solid #334155; border-radius: 8px; padding: 2px 8px;")
            return

        if isinstance(value, float):
            self.val_label.setText(f"{value:.3f}")
            if self.min_val is not None and self.max_val is not None and self.max_val > self.min_val:
                pct = int(max(0.0, min(100.0, ((value - self.min_val) / (self.max_val - self.min_val)) * 100)))
                self.range_bar.setValue(pct)
        else:
            self.val_label.setText(str(value))

        status_lower = str(status).lower()
        if "error" in status_lower or "fault" in status_lower:
            self.status_pill.setText("ERROR")
            self.status_pill.setStyleSheet("background-color: #7f1d1d; color: #fca5a5; border: 1px solid #dc2626; border-radius: 8px; padding: 2px 8px;")
            self.val_label.setStyleSheet("color: #f87171;")
        elif "warn" in status_lower:
            self.status_pill.setText("WARN")
            self.status_pill.setStyleSheet("background-color: #78350f; color: #fde047; border: 1px solid #d97706; border-radius: 8px; padding: 2px 8px;")
            self.val_label.setStyleSheet("color: #fbbf24;")
        else:
            self.status_pill.setText("OK")
            self.status_pill.setStyleSheet("background-color: #064e3b; color: #34d399; border: 1px solid #059669; border-radius: 8px; padding: 2px 8px;")
            self.val_label.setStyleSheet("color: #38bdf8;")


class TelemetryCardsView(QWidget):
    """Grid container organizing signal cards into subsystem groups with live search filter."""

    quick_plot_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: Dict[str, SignalCardWidget] = {}
        self._group_boxes: List[QGroupBox] = []
        self._config: Optional[FrameConfig] = None
        self._group_by = "subsystem"  # "subsystem" | "frame"
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # Top Controls Bar: Search Filter & Group Switcher
        ctrl_bar = QHBoxLayout()
        ctrl_bar.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search telemetry signals or subsystems...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #0f172a;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #38bdf8;
            }
        """)
        self.search_input.textChanged.connect(self._apply_filter)

        self.group_combo = QComboBox()
        self.group_combo.addItem("📁 Group by Subsystem", "subsystem")
        self.group_combo.addItem("📦 Group by Message Frame", "frame")
        self.group_combo.setStyleSheet("""
            QComboBox {
                background-color: #0f172a;
                color: #38bdf8;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QComboBox:hover {
                border: 1px solid #38bdf8;
            }
        """)
        self.group_combo.currentIndexChanged.connect(self._on_group_mode_changed)

        ctrl_bar.addWidget(self.search_input, 1)
        ctrl_bar.addWidget(self.group_combo)

        main_layout.addLayout(ctrl_bar)

        # Scroll Area for Card Grids
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setSpacing(16)

        self.scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll_area)

    def _on_group_mode_changed(self) -> None:
        self._group_by = self.group_combo.currentData() or "subsystem"
        self.rebuild_from_config(self._config)

    def rebuild_from_config(self, config: Optional[FrameConfig]) -> None:
        self._config = config
        while self.content_layout.count():
            child = self.content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._cards.clear()
        self._group_boxes.clear()

        if not config:
            empty_lbl = QLabel("No active protocol configuration loaded.")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet("color: #64748b; font-size: 14px; margin-top: 40px;")
            self.content_layout.addWidget(empty_lbl)
            return

        # Group signals based on active grouping mode
        groups: Dict[str, List[SignalSpec]] = {}
        for spec in config.all_signals:
            if self._group_by == "frame":
                grp = f"Frame 0x{spec.frame_id:04X}: {spec.frame_name}"
            else:
                grp = spec.group.strip() if spec.group and spec.group.strip() else "General Subsystem"
            groups.setdefault(grp, []).append(spec)

        for grp_name, specs in groups.items():
            grp_box = QGroupBox(f" {grp_name} ({len(specs)} signals)")
            grp_box.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            grp_box.setStyleSheet("""
                QGroupBox {
                    border: 1px solid #334155;
                    border-radius: 8px;
                    margin-top: 10px;
                    padding: 12px;
                    background-color: #0b1329;
                }
                QGroupBox::title {
                    color: #38bdf8;
                    subcontrol-origin: margin;
                    left: 12px;
                    padding: 0 6px;
                }
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

            self._group_boxes.append(grp_box)
            self.content_layout.addWidget(grp_box)

        self.content_layout.addStretch()
        self._apply_filter(self.search_input.text())

    def _apply_filter(self, query: str) -> None:
        q = (query or "").strip().lower()
        for card_name, card in self._cards.items():
            match = (not q) or (q in card_name.lower()) or (q in card.unit.lower())
            card.setVisible(match)

        # Hide empty group boxes
        for grp_box in self._group_boxes:
            visible_count = 0
            for child in grp_box.findChildren(SignalCardWidget):
                if child.isVisible():
                    visible_count += 1
            grp_box.setVisible(visible_count > 0)

    def update_signal_value(self, signal_name: str, value: float | int | str, status: str = "ok") -> None:
        if signal_name in self._cards:
            self._cards[signal_name].update_value(value, status)

