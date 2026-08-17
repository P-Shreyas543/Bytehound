"""Visual Protocol & Frame Configuration Wizard GUI for Bytehound."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Any, Optional

import pandas as pd
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QLineEdit, QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QStackedWidget, QMessageBox, QGroupBox, QFileDialog, QItemDelegate
)

from ..decoder.types import SUPPORTED_CRC_TYPES, SUPPORTED_DATA_TYPES
from .theming import apply_dialog_theme


class ComboBoxDelegate(QItemDelegate):
    """Table cell delegate rendering a dropdown combo box for seamless options picking."""

    def __init__(self, options: List[str], parent=None):
        super().__init__(parent)
        self.options = options

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.addItems(self.options)
        return combo

    def setEditorData(self, editor: QComboBox, index):
        val = index.model().data(index, Qt.ItemDataRole.EditRole) or ""
        idx = editor.findText(str(val))
        if idx >= 0:
            editor.setCurrentIndex(idx)

    def setModelData(self, editor: QComboBox, model, index):
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)


class ProtocolWizardDialog(QDialog):
    """Interactive Step-by-Step Protocol & Frame Builder Wizard with Presets and Dropdown Delegates."""

    protocol_created = Signal(str)  # Output path of generated xlsx config

    def __init__(self, parent=None):
        super().__init__(parent)
        apply_dialog_theme(self)
        self.setWindowTitle("🪄 Protocol & Frame Configuration Wizard")
        self.resize(920, 680)
        self.setMinimumSize(750, 520)

        # Config state
        self._profile_name = "Custom Device Protocol"
        self._parser_type = "framed"
        self._header_hex = "AA 55"
        self._frame_id_size = 2
        self._length_size = 1
        self._crc_type = "crc16_modbus"
        self._baud_rate = 115200

        self._frames: List[Dict[str, Any]] = [
            {"frame_id": "0x1000", "frame_name": "Telemetry Data", "payload_length": 8, "direction": "rx", "description": "Sensor Stream"}
        ]
        self._variables: List[Dict[str, Any]] = [
            {"id_or_address": "0x1000", "signal_name": "Voltage", "data_type": "uint16", "count": 1, "byte_order": "little", "scale": 0.001, "offset": 0, "unit": "V", "group": "Main", "read_write": "R", "min_value": 0.0, "max_value": 60.0, "description": "System Voltage", "enabled": True},
            {"id_or_address": "0x1000", "signal_name": "Current", "data_type": "int16", "count": 1, "byte_order": "little", "scale": 0.01, "offset": 0, "unit": "A", "group": "Main", "read_write": "R", "min_value": -100.0, "max_value": 100.0, "description": "System Current", "enabled": True}
        ]

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)

        # Header banner
        banner = QWidget()
        banner.setStyleSheet("background-color: palette(alternate-base); border-bottom: 1px solid palette(mid);")
        b_layout = QHBoxLayout(banner)
        b_layout.setContentsMargins(16, 12, 16, 12)

        self.title_lbl = QLabel("Step 1 of 4: Communication & Framing Setup")
        self.title_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.title_lbl.setStyleSheet("color: palette(highlight);")
        b_layout.addWidget(self.title_lbl)

        main_layout.addWidget(banner)

        # Stacked Pages
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_step1_page())
        self.stack.addWidget(self._build_step2_page())
        self.stack.addWidget(self._build_step3_page())
        self.stack.addWidget(self._build_step4_page())

        main_layout.addWidget(self.stack, 1)

        # Navigation Footer Buttons
        nav_h = QHBoxLayout()
        nav_h.setContentsMargins(16, 8, 16, 16)

        self.back_btn = QPushButton("⬅ Previous")
        self.back_btn.setAccessibleName("Previous Step")
        self.back_btn.setEnabled(False)
        self.back_btn.clicked.connect(self._on_prev)

        self.next_btn = QPushButton("Next Step ➡")
        self.next_btn.setAccessibleName("Next Step")
        self.next_btn.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self.next_btn.clicked.connect(self._on_next)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setAccessibleName("Cancel")
        cancel_btn.clicked.connect(self.reject)

        nav_h.addWidget(cancel_btn)
        nav_h.addStretch()
        nav_h.addWidget(self.back_btn)
        nav_h.addWidget(self.next_btn)

        main_layout.addLayout(nav_h)

    def _build_step1_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        # Quick Preset Toolbar
        preset_box = QGroupBox("🚀 Quick-Start Presets (1-Click Template Setup)")
        p_layout = QHBoxLayout(preset_box)
        
        bms_16c_btn = QPushButton("🔋 16-Cell BMS Pack")
        bms_16c_btn.setToolTip("Auto-load 16-Cell BMS frame structure and signal definitions")
        bms_16c_btn.clicked.connect(self._apply_16cell_bms_preset)

        bms_single_btn = QPushButton("⚡ Single-Cell BMS")
        bms_single_btn.setToolTip("Auto-load single cell BMS telemetry profile")
        bms_single_btn.clicked.connect(self._apply_single_cell_preset)

        can_telemetry_btn = QPushButton("📡 CAN/RS485 Telemetry Stream")
        can_telemetry_btn.setToolTip("Auto-load multi-sensor telemetry stream profile")
        can_telemetry_btn.clicked.connect(self._apply_sensor_preset)

        p_layout.addWidget(bms_16c_btn)
        p_layout.addWidget(bms_single_btn)
        p_layout.addWidget(can_telemetry_btn)

        box = QGroupBox("Physical Serial & Protocol Header Setup")
        b_layout = QVBoxLayout(box)

        self.profile_name_edit = QLineEdit(self._profile_name)
        self.header_hex_edit = QLineEdit(self._header_hex)
        self.header_hex_edit.textChanged.connect(self._update_format_preview)

        self.crc_combo = QComboBox()
        self.crc_combo.addItems(sorted(SUPPORTED_CRC_TYPES))
        self.crc_combo.setCurrentText(self._crc_type)
        self.crc_combo.currentTextChanged.connect(self._update_format_preview)

        self.frame_id_size_spin = QSpinBox()
        self.frame_id_size_spin.setRange(1, 4)
        self.frame_id_size_spin.setValue(self._frame_id_size)
        self.frame_id_size_spin.valueChanged.connect(self._update_format_preview)

        self.length_size_spin = QSpinBox()
        self.length_size_spin.setRange(1, 4)
        self.length_size_spin.setValue(self._length_size)
        self.length_size_spin.valueChanged.connect(self._update_format_preview)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Protocol Name:"))
        h1.addWidget(self.profile_name_edit, 1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Header Hex (e.g. AA 55):"))
        h2.addWidget(self.header_hex_edit, 1)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel("Frame ID Size (bytes):"))
        h3.addWidget(self.frame_id_size_spin)
        h3.addWidget(QLabel("Payload Length Size (bytes):"))
        h3.addWidget(self.length_size_spin)

        h4 = QHBoxLayout()
        h4.addWidget(QLabel("CRC Type:"))
        h4.addWidget(self.crc_combo, 1)

        b_layout.addLayout(h1)
        b_layout.addLayout(h2)
        b_layout.addLayout(h3)
        b_layout.addLayout(h4)

        # On-wire Diagram Banner
        self.diagram_lbl = QLabel()
        self.diagram_lbl.setStyleSheet(
            "background-color: palette(window); border: 1px dashed palette(mid); "
            "border-radius: 6px; padding: 8px; font-family: Consolas, monospace; "
            "font-weight: bold; color: palette(highlight);"
        )
        self._update_format_preview()

        layout.addWidget(preset_box)
        layout.addWidget(box)
        layout.addWidget(self.diagram_lbl)
        layout.addStretch()
        return page

    def _update_format_preview(self) -> None:
        hdr = self.header_hex_edit.text().strip() or "NONE"
        fid = f"Frame ID ({self.frame_id_size_spin.value()}B)"
        len_s = f"Length ({self.length_size_spin.value()}B)"
        crc_name = self.crc_combo.currentText()
        if crc_name == "none":
            crc = "NO CRC (0B)"
        elif crc_name.startswith("crc16"):
            crc = f"CRC-16 ({crc_name})"
        elif crc_name == "crc32":
            crc = f"CRC-32 ({crc_name})"
        else:
            crc = f"CRC ({crc_name})"
        self.diagram_lbl.setText(f"On-Wire Packet Diagram:  [{hdr}]  ➜  [{fid}]  ➜  [{len_s}]  ➜  [Payload...]  ➜  [{crc}]")

    def _build_step2_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        lbl = QLabel("Define message frame IDs, frame names, payload lengths, and directions:")
        lbl.setStyleSheet("color: palette(mid);")

        self.frames_table = QTableWidget(len(self._frames), 4)
        self.frames_table.setAccessibleName("Frames Configuration Table")
        self.frames_table.setHorizontalHeaderLabels(["Frame ID", "Frame Name", "Payload Length", "Direction"])
        self.frames_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.frames_table.setItemDelegateForColumn(3, ComboBoxDelegate(["rx", "rxtx", "tx"], self.frames_table))

        self._populate_frames_table()

        btn_h = QHBoxLayout()
        add_f_btn = QPushButton("➕ Add Frame")
        add_f_btn.clicked.connect(self._add_frame_row)
        del_f_btn = QPushButton("❌ Delete Selected")
        del_f_btn.clicked.connect(self._del_frame_row)

        btn_h.addWidget(add_f_btn)
        btn_h.addWidget(del_f_btn)
        btn_h.addStretch()

        layout.addWidget(lbl)
        layout.addWidget(self.frames_table, 1)
        layout.addLayout(btn_h)
        return page

    def _populate_frames_table(self) -> None:
        self.frames_table.setRowCount(len(self._frames))
        for r, f in enumerate(self._frames):
            self.frames_table.setItem(r, 0, QTableWidgetItem(f["frame_id"]))
            self.frames_table.setItem(r, 1, QTableWidgetItem(f["frame_name"]))
            self.frames_table.setItem(r, 2, QTableWidgetItem(str(f["payload_length"])))
            self.frames_table.setItem(r, 3, QTableWidgetItem(f["direction"]))

    def _build_step3_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        lbl = QLabel("Define telemetry signals (data types, scale factors, units, and groups):")
        lbl.setStyleSheet("color: palette(mid);")

        self.vars_table = QTableWidget(len(self._variables), 8)
        self.vars_table.setAccessibleName("Signals Configuration Table")
        self.vars_table.setHorizontalHeaderLabels(["Frame ID", "Signal Name", "Data Type", "Scale", "Offset", "Unit", "Group", "Description"])
        self.vars_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # Dropdown delegates for Data Type
        valid_dtypes = sorted(list(SUPPORTED_DATA_TYPES))
        self.vars_table.setItemDelegateForColumn(2, ComboBoxDelegate(valid_dtypes, self.vars_table))

        self._populate_vars_table()

        btn_h = QHBoxLayout()
        add_v_btn = QPushButton("➕ Add Signal")
        add_v_btn.clicked.connect(self._add_var_row)
        del_v_btn = QPushButton("❌ Delete Selected")
        del_v_btn.clicked.connect(self._del_var_row)

        btn_h.addWidget(add_v_btn)
        btn_h.addWidget(del_v_btn)
        btn_h.addStretch()

        layout.addWidget(lbl)
        layout.addWidget(self.vars_table, 1)
        layout.addLayout(btn_h)
        return page

    def _populate_vars_table(self) -> None:
        self.vars_table.setRowCount(len(self._variables))
        for r, v in enumerate(self._variables):
            self.vars_table.setItem(r, 0, QTableWidgetItem(v["id_or_address"]))
            self.vars_table.setItem(r, 1, QTableWidgetItem(v["signal_name"]))
            self.vars_table.setItem(r, 2, QTableWidgetItem(v["data_type"]))
            self.vars_table.setItem(r, 3, QTableWidgetItem(str(v["scale"])))
            self.vars_table.setItem(r, 4, QTableWidgetItem(str(v["offset"])))
            self.vars_table.setItem(r, 5, QTableWidgetItem(v["unit"]))
            self.vars_table.setItem(r, 6, QTableWidgetItem(v["group"]))
            self.vars_table.setItem(r, 7, QTableWidgetItem(v.get("description", "")))

    def _build_step4_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        box = QGroupBox("Review & Generate Configuration File")
        b_layout = QVBoxLayout(box)

        self.summary_label = QLabel("Click 'Generate & Save' to export your new configuration workbook.")
        self.summary_label.setStyleSheet("font-size: 14px;")

        save_btn = QPushButton("💾 Generate & Save Workbook (.xlsx)")
        save_btn.setAccessibleName("Generate and Save Configuration")
        save_btn.setStyleSheet("font-weight: bold; padding: 10px; font-size: 14px;")
        save_btn.clicked.connect(self._save_wizard_config)

        b_layout.addWidget(self.summary_label)
        b_layout.addSpacing(20)
        b_layout.addWidget(save_btn)

        layout.addWidget(box)
        layout.addStretch()
        return page

    # --- Preset Quick-Starts ---
    def _apply_16cell_bms_preset(self) -> None:
        self.profile_name_edit.setText("16-Cell BMS Telemetry")
        self.header_hex_edit.setText("AA 55")
        self.crc_combo.setCurrentText("crc16_modbus")
        self.frame_id_size_spin.setValue(2)
        self.length_size_spin.setValue(1)

        self._frames = [
            {"frame_id": "0x2F0", "frame_name": "BMS_Stack_Current", "payload_length": 8, "direction": "rx"},
            {"frame_id": "0x2F1", "frame_name": "BMS_Cell_Voltages_1_4", "payload_length": 8, "direction": "rx"},
            {"frame_id": "0x2F2", "frame_name": "BMS_Cell_Voltages_5_8", "payload_length": 8, "direction": "rx"},
            {"frame_id": "0x2F3", "frame_name": "BMS_Cell_Voltages_9_12", "payload_length": 8, "direction": "rx"},
            {"frame_id": "0x2F4", "frame_name": "BMS_Cell_Voltages_13_16", "payload_length": 8, "direction": "rx"},
        ]
        self._populate_frames_table()

        self._variables = [
            {"id_or_address": "0x2F0", "signal_name": "Pack_Voltage", "data_type": "uint32", "scale": 0.001, "offset": 0, "unit": "V", "group": "Pack Parameters"},
            {"id_or_address": "0x2F0", "signal_name": "Pack_Current", "data_type": "int32", "scale": 0.001, "offset": 0, "unit": "A", "group": "Pack Parameters"},
        ]
        for i in range(1, 17):
            fid = f"0x2F{(i-1)//4 + 1}"
            self._variables.append({
                "id_or_address": fid,
                "signal_name": f"Cell_Voltage_{i}",
                "data_type": "uint16",
                "scale": 0.001,
                "offset": 0,
                "unit": "V",
                "group": "Cell Voltages"
            })
        self._populate_vars_table()

    def _apply_single_cell_preset(self) -> None:
        self.profile_name_edit.setText("Single-Cell BMS Protocol")
        self.header_hex_edit.setText("AA 55")
        self.crc_combo.setCurrentText("crc16_modbus")

        self._frames = [
            {"frame_id": "0x1000", "frame_name": "BMS Status", "payload_length": 8, "direction": "rx"},
            {"frame_id": "0x2000", "frame_name": "Cell Voltages", "payload_length": 8, "direction": "rx"},
        ]
        self._populate_frames_table()

        self._variables = [
            {"id_or_address": "0x1000", "signal_name": "Cell Voltage", "data_type": "uint16", "scale": 0.001, "offset": 0, "unit": "V", "group": "Main"},
            {"id_or_address": "0x1000", "signal_name": "Cell Current", "data_type": "int16", "scale": 0.01, "offset": 0, "unit": "A", "group": "Main"},
            {"id_or_address": "0x2000", "signal_name": "SOC", "data_type": "uint8", "scale": 1.0, "offset": 0, "unit": "%", "group": "Status"},
        ]
        self._populate_vars_table()

    def _apply_sensor_preset(self) -> None:
        self.profile_name_edit.setText("Multi-Sensor Telemetry")
        self.header_hex_edit.setText("AA 55")
        self.crc_combo.setCurrentText("none")

        self._frames = [
            {"frame_id": "0x0100", "frame_name": "Sensors 1-4", "payload_length": 8, "direction": "rx"},
        ]
        self._populate_frames_table()

        self._variables = [
            {"id_or_address": "0x0100", "signal_name": "Temp_Sensor_1", "data_type": "int16", "scale": 0.1, "offset": 0, "unit": "°C", "group": "Temperatures"},
            {"id_or_address": "0x0100", "signal_name": "Temp_Sensor_2", "data_type": "int16", "scale": 0.1, "offset": 0, "unit": "°C", "group": "Temperatures"},
            {"id_or_address": "0x0100", "signal_name": "Pressure_1", "data_type": "uint16", "scale": 0.01, "offset": 0, "unit": "bar", "group": "Pressures"},
        ]
        self._populate_vars_table()

    def _add_frame_row(self) -> None:
        r = self.frames_table.rowCount()
        self.frames_table.insertRow(r)
        self.frames_table.setItem(r, 0, QTableWidgetItem(f"0x{2000+r*0x1000:04X}"))
        self.frames_table.setItem(r, 1, QTableWidgetItem(f"Frame_{r+1}"))
        self.frames_table.setItem(r, 2, QTableWidgetItem("8"))
        self.frames_table.setItem(r, 3, QTableWidgetItem("rx"))

    def _del_frame_row(self) -> None:
        r = self.frames_table.currentRow()
        if r >= 0:
            self.frames_table.removeRow(r)

    def _add_var_row(self) -> None:
        r = self.vars_table.rowCount()
        self.vars_table.insertRow(r)
        fid = self.frames_table.item(0, 0).text() if self.frames_table.rowCount() > 0 and self.frames_table.item(0, 0) else "0x1000"
        self.vars_table.setItem(r, 0, QTableWidgetItem(fid))
        self.vars_table.setItem(r, 1, QTableWidgetItem(f"Signal_{r+1}"))
        self.vars_table.setItem(r, 2, QTableWidgetItem("uint16"))
        self.vars_table.setItem(r, 3, QTableWidgetItem("1.0"))
        self.vars_table.setItem(r, 4, QTableWidgetItem("0"))
        self.vars_table.setItem(r, 5, QTableWidgetItem("V"))
        self.vars_table.setItem(r, 6, QTableWidgetItem("General"))
        self.vars_table.setItem(r, 7, QTableWidgetItem(""))

    def _del_var_row(self) -> None:
        r = self.vars_table.currentRow()
        if r >= 0:
            self.vars_table.removeRow(r)

    def _on_next(self) -> None:
        idx = self.stack.currentIndex()
        if idx < 3:
            self.stack.setCurrentIndex(idx + 1)
            self._update_wizard_nav()

    def _on_prev(self) -> None:
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
            self._update_wizard_nav()

    def _update_wizard_nav(self) -> None:
        idx = self.stack.currentIndex()
        self.back_btn.setEnabled(idx > 0)
        self.next_btn.setVisible(idx < 3)

        if idx == 2:
            self._update_step3_delegates()

        titles = [
            "Step 1 of 4: Communication & Framing Setup",
            "Step 2 of 4: Serial Frame Definitions",
            "Step 3 of 4: Decoded Telemetry Signals",
            "Step 4 of 4: Export Configuration Workbook"
        ]
        self.title_lbl.setText(titles[idx])

    def _update_step3_delegates(self) -> None:
        """Populate Frame ID, Unit, and Group dropdown delegates in Step 3 table."""
        frame_ids = []
        for r in range(self.frames_table.rowCount()):
            item = self.frames_table.item(r, 0)
            if item and item.text().strip():
                frame_ids.append(item.text().strip())
        if not frame_ids:
            frame_ids = ["0x1000"]
        self.vars_table.setItemDelegateForColumn(0, ComboBoxDelegate(frame_ids, self.vars_table))
        self.vars_table.setItemDelegateForColumn(5, ComboBoxDelegate(["V", "A", "°C", "%", "s", "ms", "Hz", "W", "Wh", "Ohm", "m/s", "RPM"], self.vars_table))
        self.vars_table.setItemDelegateForColumn(6, ComboBoxDelegate(["Cell Voltages", "Pack Parameters", "Temperatures", "Pressures", "Main", "General"], self.vars_table))

    def _save_wizard_config(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Protocol Workbook", "custom_protocol.xlsx", "Excel Files (*.xlsx)")
        if not file_path:
            return

        try:
            crc_type = self.crc_combo.currentText()
            if crc_type == "none":
                crc_size = 0
            elif crc_type == "crc32":
                crc_size = 4
            elif crc_type.startswith("crc16"):
                crc_size = 2
            else:
                crc_size = 0

            length_size = self.length_size_spin.value()
            if length_size < 1:
                QMessageBox.warning(self, "Invalid Input", "Payload Length Size must be >= 1 for framed protocols.")
                return

            protocol_df = pd.DataFrame([{
                "profile_name": self.profile_name_edit.text() or "Custom Protocol",
                "header_hex": self.header_hex_edit.text(),
                "frame_id_size": self.frame_id_size_spin.value(),
                "frame_id_byte_order": "little",
                "length_size": self.length_size_spin.value(),
                "length_meaning": "payload_only",
                "length_byte_order": "",
                "crc_type": crc_type,
                "crc_size": crc_size,
                "crc_byte_order": "little",
                "crc_coverage": "header_to_payload",
                "footer_hex": "",
                "escape_mode": "none",
                "raw_log_format": "hex",
                "inter_frame_delay_ms": 10,
                "tx_pad_length": 0,
                "enabled": True
            }])

            frames_rows = []
            for r in range(self.frames_table.rowCount()):
                frames_rows.append({
                    "frame_id": self.frames_table.item(r, 0).text() if self.frames_table.item(r, 0) else f"0x{1000+r}",
                    "frame_name": self.frames_table.item(r, 1).text() if self.frames_table.item(r, 1) else f"Frame_{r}",
                    "payload_length": int(self.frames_table.item(r, 2).text()) if self.frames_table.item(r, 2) else 8,
                    "direction": self.frames_table.item(r, 3).text() if self.frames_table.item(r, 3) else "rx",
                    "enabled": True,
                    "description": ""
                })
            frames_df = pd.DataFrame(frames_rows)

            vars_rows = []
            for r in range(self.vars_table.rowCount()):
                vars_rows.append({
                    "id_or_address": self.vars_table.item(r, 0).text() if self.vars_table.item(r, 0) else "0x1000",
                    "signal_name": self.vars_table.item(r, 1).text() if self.vars_table.item(r, 1) else f"Signal_{r}",
                    "data_type": self.vars_table.item(r, 2).text() if self.vars_table.item(r, 2) else "uint16",
                    "count": 1,
                    "byte_order": "little",
                    "scale": float(self.vars_table.item(r, 3).text()) if self.vars_table.item(r, 3) else 1.0,
                    "offset": float(self.vars_table.item(r, 4).text()) if self.vars_table.item(r, 4) else 0.0,
                    "unit": self.vars_table.item(r, 5).text() if self.vars_table.item(r, 5) else "",
                    "group": self.vars_table.item(r, 6).text() if self.vars_table.item(r, 6) else "General",
                    "read_write": "R",
                    "min_value": None,
                    "max_value": None,
                    "description": self.vars_table.item(r, 7).text() if self.vars_table.item(r, 7) else "",
                    "enabled": True
                })
            vars_df = pd.DataFrame(vars_rows)

            empty_bf = pd.DataFrame(columns=["id_or_address", "signal_name", "bit_index", "label", "active_text", "inactive_text"])
            empty_enums = pd.DataFrame(columns=["id_or_address", "signal_name", "value", "label"])
            empty_calc = pd.DataFrame(columns=["group_name", "operations", "unit", "frame_id", "enabled"])
            empty_tx = pd.DataFrame(columns=["command_name", "id_or_address", "payload_hex", "description", "enabled"])
            empty_tx_fields = pd.DataFrame(columns=["command_name", "signal_name", "data_type", "byte_order", "scale", "offset", "unit", "min_value", "max_value", "default"])
            empty_poll = pd.DataFrame(columns=["id_or_address", "interval_ms", "timeout_ms", "enabled"])
            serial_df = pd.DataFrame([{"baud_rate": self._baud_rate, "data_bits": 8, "stop_bits": 1, "parity": "N", "timeout_ms": 100}])

            with pd.ExcelWriter(file_path) as writer:
                protocol_df.to_excel(writer, sheet_name="Protocol", index=False)
                frames_df.to_excel(writer, sheet_name="Frames", index=False)
                vars_df.to_excel(writer, sheet_name="Variables", index=False)
                empty_bf.to_excel(writer, sheet_name="Bitfields", index=False)
                empty_enums.to_excel(writer, sheet_name="Enums", index=False)
                empty_calc.to_excel(writer, sheet_name="CalcGroups", index=False)
                empty_tx.to_excel(writer, sheet_name="TxCommands", index=False)
                empty_tx_fields.to_excel(writer, sheet_name="TxCommandFields", index=False)
                empty_poll.to_excel(writer, sheet_name="PollingSchedule", index=False)
                serial_df.to_excel(writer, sheet_name="SerialDefaults", index=False)

            QMessageBox.information(self, "Success", f"Created configuration workbook:\n{file_path}")
            self.protocol_created.emit(file_path)
            self.accept()

        except Exception as ex:
            QMessageBox.critical(self, "Error", f"Failed to generate configuration workbook:\n{ex}")
