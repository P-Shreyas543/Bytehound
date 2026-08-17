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

    quick_plot_requested = Signal(str, object)  # signal_name, target_widget

    def __init__(self, spec: SignalSpec, parent=None):
        super().__init__(parent)
        self.signal_name = spec.signal_name
        self.unit = spec.unit or ""
        self.min_val = spec.min_value
        self.max_val = spec.max_value
        self.data_type = (spec.data_type or "").lower()
        self.is_boolean = spec.is_boolean or self.data_type in ("bool", "boolean")
        self.group_name = spec.group.strip() if spec.group else "General Subsystem"
        self.frame_name = spec.frame_name or ""
        self._init_ui()

    def _init_ui(self) -> None:
        self.setObjectName("SignalCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(10, 10, 10, 10)

        # Header row: Name + Quick Plot Feedback Button
        h_layout = QHBoxLayout()
        h_layout.setSpacing(4)
        name_label = QLabel(self.signal_name)

        self.plot_btn = QPushButton()
        self.plot_btn.setObjectName("quickPlotBtn")
        self.plot_btn.setCheckable(True)
        self.plot_btn.setToolTip("Click to add signal to Live Plot")
        self.plot_btn.setAccessibleName(f"Quick plot {self.signal_name}")
        self.plot_btn.setFixedSize(24, 24)
        self.plot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.plot_btn.clicked.connect(lambda: self.quick_plot_requested.emit(self.signal_name, self.plot_btn))

        h_layout.addWidget(name_label, 1)
        h_layout.addWidget(self.plot_btn)

        # Value + Unit Row
        val_h = QHBoxLayout()
        val_h.setSpacing(6)
        self.val_label = QLabel("--")
        self.val_label.setAccessibleName(f"{self.signal_name} value")

        self.unit_label = QLabel(self.unit)
        self.unit_label.setStyleSheet("margin-top: 6px;")

        val_h.addWidget(self.val_label)
        val_h.addWidget(self.unit_label)
        val_h.addStretch()

        # Optional Range Progress Bar / Gauge
        self.range_bar = QProgressBar()
        self.range_bar.setFixedHeight(5)
        self.range_bar.setTextVisible(False)
        has_range = (self.min_val is not None and self.max_val is not None and self.max_val > self.min_val)
        self.range_bar.setVisible(has_range and not self.is_boolean)

        # Status badge & Range text row
        stat_h = QHBoxLayout()
        stat_h.setSpacing(6)
        self.status_pill = QLabel("OK")
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_pill.setProperty("status_type", "ok")

        range_text = ""
        if has_range:
            range_text = f"[{self.min_val:g} .. {self.max_val:g}]"
        self.range_label = QLabel(range_text)
        self.range_label.setObjectName("hintLabel")

        stat_h.addWidget(self.status_pill)
        stat_h.addStretch()
        if range_text:
            stat_h.addWidget(self.range_label)

        layout.addLayout(h_layout)
        layout.addLayout(val_h)
        if has_range and not self.is_boolean:
            layout.addWidget(self.range_bar)
        layout.addLayout(stat_h)

    def set_plot_active(self, active: bool, panels: Optional[List[int]] = None) -> None:
        """Update active plot selection state with visual checkmark feedback."""
        self.plot_btn.setChecked(active)
        self.plot_btn.setProperty("active", active)
        if active:
            self.plot_btn.setText("✓")
            panel_str = f" (Panel {', '.join(map(str, panels))})" if panels else ""
            self.plot_btn.setToolTip(f"In Live Plot{panel_str} — Click to manage graph panels")
        else:
            self.plot_btn.setText("")
            self.plot_btn.setToolTip("Click to add signal to Live Plot")
        self.plot_btn.style().unpolish(self.plot_btn)
        self.plot_btn.style().polish(self.plot_btn)

    def update_value(self, value: float | int | str, status: str = "ok") -> None:
        if self.is_boolean:
            try:
                numeric = float(value)
                is_on = (numeric != 0)
            except (ValueError, TypeError):
                is_on = str(value).strip().lower() in ("1", "true", "on", "active")
            if is_on:
                self.val_label.setText("ACTIVE (1)")
                self.val_label.setProperty("value_state", "active")
                self.status_pill.setText("ON")
                self.status_pill.setProperty("status_type", "ok")
            else:
                self.val_label.setText("OFF (0)")
                self.val_label.setProperty("value_state", "inactive")
                self.status_pill.setText("OFF")
                self.status_pill.setProperty("status_type", "inactive")
            
            self.val_label.style().unpolish(self.val_label)
            self.val_label.style().polish(self.val_label)
            self.status_pill.style().unpolish(self.status_pill)
            self.status_pill.style().polish(self.status_pill)
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
            self.status_pill.setProperty("status_type", "error")
            self.val_label.setProperty("value_state", "error")
        elif "warn" in status_lower:
            self.status_pill.setText("WARN")
            self.status_pill.setProperty("status_type", "warn")
            self.val_label.setProperty("value_state", "warn")
        else:
            self.status_pill.setText("OK")
            self.status_pill.setProperty("status_type", "ok")
            self.val_label.setProperty("value_state", "ok")
            
        self.val_label.style().unpolish(self.val_label)
        self.val_label.style().polish(self.val_label)
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)


class TelemetryCardsView(QWidget):
    """Grid container organizing signal cards into subsystem groups with live search filter."""

    quick_plot_requested = Signal(str, object)  # signal_name, target_widget

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
        self.search_input.setAccessibleName("Search telemetry signals")
        self.search_input.textChanged.connect(self._apply_filter)

        self.group_combo = QComboBox()
        self.group_combo.addItem("📁 Group by Subsystem", "subsystem")
        self.group_combo.addItem("📦 Group by Message Frame", "frame")
        self.group_combo.setAccessibleName("Group signals by")
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

        self.empty_label = QLabel("No signals match the search filter.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setObjectName("hintLabel")
        self.empty_label.hide()
        main_layout.addWidget(self.empty_label)

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
            match = (not q) or (q in card_name.lower()) or (q in card.unit.lower()) or (q in card.group_name.lower()) or (q in card.frame_name.lower())
            card.setVisible(match)

        # Hide empty group boxes
        any_visible = False
        for grp_box in self._group_boxes:
            visible_count = 0
            for child in grp_box.findChildren(SignalCardWidget):
                if not child.isHidden():
                    visible_count += 1
            grp_box.setVisible(visible_count > 0)
            if visible_count > 0:
                any_visible = True
                
        self.empty_label.setVisible(not any_visible and bool(self._cards))
        self.scroll_area.setVisible(any_visible or not bool(self._cards))

    def update_signal_value(self, signal_name: str, value: float | int | str, status: str = "ok") -> None:
        if signal_name in self._cards:
            self._cards[signal_name].update_value(value, status)

    def sync_plot_active_states(self, panels_or_keys: Any) -> None:
        """Synchronize checkmark selection states across all signal cards."""
        card_panels: Dict[str, List[int]] = {}
        if isinstance(panels_or_keys, list) and panels_or_keys and hasattr(panels_or_keys[0], "assigned_keys"):
            for idx, panel in enumerate(panels_or_keys):
                for key in panel.assigned_keys:
                    sig_name = key[1]
                    card_panels.setdefault(sig_name, []).append(idx + 1)
        elif isinstance(panels_or_keys, (list, set, tuple)):
            for item in panels_or_keys:
                if isinstance(item, tuple) and len(item) == 2:
                    sig_name = item[1]
                    card_panels.setdefault(sig_name, []).append(1)

        for sig_name, card in self._cards.items():
            assigned = card_panels.get(sig_name, [])
            card.set_plot_active(bool(assigned), assigned)
