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

from ..decoder.template_io import load_template_tables, write_workbook_from_tables
from ..decoder.types import SUPPORTED_CRC_TYPES, SUPPORTED_DATA_TYPES, ParserType
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
    """Interactive 5-Step Visual Protocol, Frame, Signal & TX Command Builder Wizard."""

    protocol_created = Signal(str)  # Output path of generated xlsx config

    def __init__(self, parent=None):
        super().__init__(parent)
        apply_dialog_theme(self)
        self.setWindowTitle("🪄 Visual Protocol & Frame Configuration Wizard")
        self.resize(980, 720)
        self.setMinimumSize(800, 560)

        # Load baseline schema and defaults directly from bundled config template
        self._template_tables = load_template_tables()

        p_df = self._template_tables.get("Protocol")
        if p_df is not None and not p_df.empty:
            p_row = p_df.iloc[0].to_dict()
            self._profile_name = p_row.get("profile_name", "Custom Device Protocol")
            self._parser_type = p_row.get("parser_type", "framed")
            self._header_hex = p_row.get("header_hex", "AA 55")
            self._frame_id_size = int(p_row.get("frame_id_size", 2)) if str(p_row.get("frame_id_size", "2")).isdigit() else 2
            self._length_size = int(p_row.get("length_size", 1)) if str(p_row.get("length_size", "1")).isdigit() else 1
            self._crc_type = p_row.get("crc_type", "crc16_modbus")
        else:
            self._profile_name = "Custom Device Protocol"
            self._parser_type = "framed"
            self._header_hex = "AA 55"
            self._frame_id_size = 2
            self._length_size = 1
            self._crc_type = "crc16_modbus"

        s_df = self._template_tables.get("SerialDefaults")
        if s_df is not None and not s_df.empty:
            s_row = s_df.iloc[0].to_dict()
            self._baud_rate = int(s_row.get("baud_rate", 115200)) if str(s_row.get("baud_rate", "115200")).isdigit() else 115200
        else:
            self._baud_rate = 115200

        f_df = self._template_tables.get("Frames")
        if f_df is not None and not f_df.empty:
            self._frames = f_df.to_dict(orient="records")
        else:
            self._frames = [
                {"frame_id": "0x1000", "frame_name": "Telemetry Data", "payload_length": 8, "direction": "rxtx", "description": "Sensor Stream"}
            ]

        v_df = self._template_tables.get("Variables")
        if v_df is not None and not v_df.empty:
            self._variables = v_df.to_dict(orient="records")
        else:
            self._variables = [
                {"id_or_address": "0x1000", "signal_name": "Voltage", "data_type": "uint16", "count": 1, "start_index": 1, "scale": 0.001, "offset": 0, "unit": "V", "group": "Main", "description": "System Voltage"}
            ]

        tx_df = self._template_tables.get("TxCommands")
        if tx_df is not None and not tx_df.empty:
            self._tx_commands = tx_df.to_dict(orient="records")
        else:
            self._tx_commands = [
                {"command_name": "Reset Faults", "id_or_address": "0x1000", "payload_hex": "FF FF", "description": "Clears active fault flags on the device"}
            ]

        tx_f_df = self._template_tables.get("TxCommandFields")
        if tx_f_df is not None and not tx_f_df.empty:
            self._tx_command_fields = tx_f_df.to_dict(orient="records")
        else:
            self._tx_command_fields = [
                {"command_name": "Set Voltage Limit", "signal_name": "Voltage Limit (V)", "data_type": "uint16", "scale": 0.01, "offset": 0.0, "unit": "V", "default": 55.0}
            ]

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)

        # Header banner
        banner = QWidget()
        banner.setStyleSheet("background-color: palette(alternate-base); border-bottom: 1px solid palette(mid);")
        b_layout = QHBoxLayout(banner)
        b_layout.setContentsMargins(16, 12, 16, 12)

        self.title_lbl = QLabel("Step 1 of 5: Protocol & Communication Settings")
        self.title_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.title_lbl.setStyleSheet("color: palette(highlight);")
        b_layout.addWidget(self.title_lbl)

        main_layout.addWidget(banner)

        # Stacked Pages (5 Steps)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_step1_page())
        self.stack.addWidget(self._build_step2_page())
        self.stack.addWidget(self._build_step3_page())
        self.stack.addWidget(self._build_step4_page())
        self.stack.addWidget(self._build_step5_page())

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

        box = QGroupBox("Physical Serial & Protocol Header Setup")
        b_layout = QVBoxLayout(box)

        self.profile_name_edit = QLineEdit(self._profile_name)
        self.parser_type_combo = QComboBox()
        self.parser_type_combo.addItems([m.value for m in ParserType])
        self.parser_type_combo.setCurrentText(self._parser_type)
        self.parser_type_combo.currentTextChanged.connect(self._on_parser_type_changed)

        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600", "1000000", "2000000"])
        self.baud_combo.setCurrentText(str(self._baud_rate))

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
        h1.addWidget(QLabel("Parser Type:"))
        h1.addWidget(self.parser_type_combo)
        h1.addWidget(QLabel("Baud Rate:"))
        h1.addWidget(self.baud_combo)

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

        layout.addWidget(box)
        layout.addWidget(self.diagram_lbl)
        layout.addStretch()
        return page

    def _on_parser_type_changed(self, ptype: str) -> None:
        if ptype in ("waveshare_can", "waveshare_can_20_bytes"):
            self.header_hex_edit.setText("AA 55" if ptype == "waveshare_can_20_bytes" else "AA")
            self.crc_combo.setCurrentText("none")
            self.header_hex_edit.setEnabled(False)
            self.crc_combo.setEnabled(False)
            if self.baud_combo.currentText() == "115200":
                self.baud_combo.setCurrentText("2000000")
        else:
            self.header_hex_edit.setEnabled(True)
            self.crc_combo.setEnabled(True)
            if self.baud_combo.currentText() == "2000000":
                self.baud_combo.setCurrentText("115200")
        self._update_format_preview()

    def _update_format_preview(self) -> None:
        ptype = self.parser_type_combo.currentText() if hasattr(self, "parser_type_combo") else "framed"
        if ptype == "waveshare_can_20_bytes":
            self.diagram_lbl.setText("Waveshare CAN 20-Byte Packet:  [0xAA 0x55]  ➜  [Type 0x01]  ➜  [Mode]  ➜  [Seq]  ➜  [CAN ID (4B)]  ➜  [DLC (1B)]  ➜  [Data (8B)]  ➜  [Sum+1 (1B)]")
            return
        if ptype == "waveshare_can":
            fid_bytes = self.frame_id_size_spin.value()
            fid_desc = "2B (Standard 11-bit)" if fid_bytes == 2 else "4B (Extended 29-bit)"
            self.diagram_lbl.setText(f"Waveshare CAN Packet:  [0xAA]  ➜  [Type/DLC (0xC0..0xEF)]  ➜  [CAN ID ({fid_desc})]  ➜  [Data (0-8B)]  ➜  [0x55]")
            return

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
        self.frames_table.setItemDelegateForColumn(3, ComboBoxDelegate(["rxtx", "rx", "tx"], self.frames_table))

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
            self.frames_table.setItem(r, 0, QTableWidgetItem(str(f.get("frame_id", f"0x{1000+r*0x1000:04X}"))))
            self.frames_table.setItem(r, 1, QTableWidgetItem(str(f.get("frame_name", f"Frame_{r+1}"))))
            self.frames_table.setItem(r, 2, QTableWidgetItem(str(f.get("payload_length", 8))))
            self.frames_table.setItem(r, 3, QTableWidgetItem(str(f.get("direction", "rxtx"))))

    def _build_step3_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        lbl = QLabel("Define telemetry signals (data types, counts, array index, scale factors, units, and groups):")
        lbl.setStyleSheet("color: palette(mid);")

        self.vars_table = QTableWidget(len(self._variables), 10)
        self.vars_table.setAccessibleName("Signals Configuration Table")
        self.vars_table.setHorizontalHeaderLabels([
            "Frame ID", "Signal Name", "Data Type", "Count", "Start Index", "Scale", "Offset", "Unit", "Group", "Description"
        ])
        self.vars_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

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
            self.vars_table.setItem(r, 0, QTableWidgetItem(str(v.get("id_or_address", "0x1000"))))
            self.vars_table.setItem(r, 1, QTableWidgetItem(str(v.get("signal_name", f"Signal_{r+1}"))))
            self.vars_table.setItem(r, 2, QTableWidgetItem(str(v.get("data_type", "uint16"))))
            self.vars_table.setItem(r, 3, QTableWidgetItem(str(v.get("count", 1))))
            self.vars_table.setItem(r, 4, QTableWidgetItem(str(v.get("start_index", 1))))
            self.vars_table.setItem(r, 5, QTableWidgetItem(str(v.get("scale", 1.0))))
            self.vars_table.setItem(r, 6, QTableWidgetItem(str(v.get("offset", 0.0))))
            self.vars_table.setItem(r, 7, QTableWidgetItem(str(v.get("unit", ""))))
            self.vars_table.setItem(r, 8, QTableWidgetItem(str(v.get("group", "General"))))
            self.vars_table.setItem(r, 9, QTableWidgetItem(str(v.get("description", ""))))

    def _build_step4_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        lbl = QLabel("Configure outgoing transmit (TX) commands and interactive input fields:")
        lbl.setStyleSheet("color: palette(mid);")
        layout.addWidget(lbl)

        # 1. TX Commands Master Table
        cmd_box = QGroupBox("1. Transmit Commands (Selectable in TX Panel)")
        c_layout = QVBoxLayout(cmd_box)
        self.tx_cmd_table = QTableWidget(len(self._tx_commands), 4)
        self.tx_cmd_table.setAccessibleName("TX Commands Table")
        self.tx_cmd_table.setHorizontalHeaderLabels([
            "Command Name", "Target Frame ID", "Static Payload Hex (Optional)", "Description / Tooltip"
        ])
        self.tx_cmd_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._populate_tx_cmd_table()

        cmd_btns = QHBoxLayout()
        add_cmd_btn = QPushButton("➕ Add TX Command")
        add_cmd_btn.clicked.connect(self._add_tx_cmd_row)
        del_cmd_btn = QPushButton("❌ Delete Selected Command")
        del_cmd_btn.clicked.connect(self._del_tx_cmd_row)
        cmd_btns.addWidget(add_cmd_btn)
        cmd_btns.addWidget(del_cmd_btn)
        cmd_btns.addStretch()

        c_layout.addWidget(self.tx_cmd_table)
        c_layout.addLayout(cmd_btns)
        layout.addWidget(cmd_box)

        # 2. Dynamic Input Fields Table
        fields_box = QGroupBox("2. Command Parameters & Input Fields (Dynamic UI Inputs)")
        f_layout = QVBoxLayout(fields_box)
        self.tx_fields_table = QTableWidget(len(self._tx_command_fields), 9)
        self.tx_fields_table.setAccessibleName("TX Command Fields Table")
        self.tx_fields_table.setHorizontalHeaderLabels([
            "Command Name", "Parameter Label", "Data Type", "Scale", "Offset", "Unit", "Min Value", "Max Value", "Default Value"
        ])
        self.tx_fields_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        valid_dtypes = sorted(list(SUPPORTED_DATA_TYPES))
        self.tx_fields_table.setItemDelegateForColumn(2, ComboBoxDelegate(valid_dtypes, self.tx_fields_table))
        self._populate_tx_fields_table()

        field_btns = QHBoxLayout()
        add_fld_btn = QPushButton("➕ Add Parameter Field")
        add_fld_btn.clicked.connect(self._add_tx_field_row)
        del_fld_btn = QPushButton("❌ Delete Selected Field")
        del_fld_btn.clicked.connect(self._del_tx_field_row)
        field_btns.addWidget(add_fld_btn)
        field_btns.addWidget(del_fld_btn)
        field_btns.addStretch()

        f_layout.addWidget(self.tx_fields_table)
        f_layout.addLayout(field_btns)
        layout.addWidget(fields_box)

        return page

    def _populate_tx_cmd_table(self) -> None:
        self.tx_cmd_table.setRowCount(len(self._tx_commands))
        for r, cmd in enumerate(self._tx_commands):
            self.tx_cmd_table.setItem(r, 0, QTableWidgetItem(str(cmd.get("command_name", f"Cmd_{r+1}"))))
            self.tx_cmd_table.setItem(r, 1, QTableWidgetItem(str(cmd.get("id_or_address", "0x1000"))))
            self.tx_cmd_table.setItem(r, 2, QTableWidgetItem(str(cmd.get("payload_hex", ""))))
            self.tx_cmd_table.setItem(r, 3, QTableWidgetItem(str(cmd.get("description", ""))))

    def _populate_tx_fields_table(self) -> None:
        self.tx_fields_table.setRowCount(len(self._tx_command_fields))
        for r, fld in enumerate(self._tx_command_fields):
            self.tx_fields_table.setItem(r, 0, QTableWidgetItem(str(fld.get("command_name", ""))))
            self.tx_fields_table.setItem(r, 1, QTableWidgetItem(str(fld.get("signal_name", "Parameter"))))
            self.tx_fields_table.setItem(r, 2, QTableWidgetItem(str(fld.get("data_type", "uint16"))))
            self.tx_fields_table.setItem(r, 3, QTableWidgetItem(str(fld.get("scale", 1.0))))
            self.tx_fields_table.setItem(r, 4, QTableWidgetItem(str(fld.get("offset", 0.0))))
            self.tx_fields_table.setItem(r, 5, QTableWidgetItem(str(fld.get("unit", ""))))
            self.tx_fields_table.setItem(r, 6, QTableWidgetItem(str(fld.get("min_value", "")) if fld.get("min_value") is not None and str(fld.get("min_value")) != "None" else ""))
            self.tx_fields_table.setItem(r, 7, QTableWidgetItem(str(fld.get("max_value", "")) if fld.get("max_value") is not None and str(fld.get("max_value")) != "None" else ""))
            self.tx_fields_table.setItem(r, 8, QTableWidgetItem(str(fld.get("default", "")) if fld.get("default") is not None and str(fld.get("default")) != "None" else "0"))

    def _add_tx_cmd_row(self) -> None:
        r = self.tx_cmd_table.rowCount()
        self.tx_cmd_table.insertRow(r)
        fid = self.frames_table.item(0, 0).text() if self.frames_table.rowCount() > 0 and self.frames_table.item(0, 0) else "0x1000"
        self.tx_cmd_table.setItem(r, 0, QTableWidgetItem(f"Command_{r+1}"))
        self.tx_cmd_table.setItem(r, 1, QTableWidgetItem(fid))
        self.tx_cmd_table.setItem(r, 2, QTableWidgetItem(""))
        self.tx_cmd_table.setItem(r, 3, QTableWidgetItem(""))

    def _del_tx_cmd_row(self) -> None:
        r = self.tx_cmd_table.currentRow()
        if r >= 0:
            self.tx_cmd_table.removeRow(r)

    def _add_tx_field_row(self) -> None:
        r = self.tx_fields_table.rowCount()
        self.tx_fields_table.insertRow(r)
        cmd_name = self.tx_cmd_table.item(0, 0).text() if self.tx_cmd_table.rowCount() > 0 and self.tx_cmd_table.item(0, 0) else "Command_1"
        self.tx_fields_table.setItem(r, 0, QTableWidgetItem(cmd_name))
        self.tx_fields_table.setItem(r, 1, QTableWidgetItem(f"Field_{r+1}"))
        self.tx_fields_table.setItem(r, 2, QTableWidgetItem("uint16"))
        self.tx_fields_table.setItem(r, 3, QTableWidgetItem("1.0"))
        self.tx_fields_table.setItem(r, 4, QTableWidgetItem("0"))
        self.tx_fields_table.setItem(r, 5, QTableWidgetItem(""))
        self.tx_fields_table.setItem(r, 6, QTableWidgetItem(""))
        self.tx_fields_table.setItem(r, 7, QTableWidgetItem(""))
        self.tx_fields_table.setItem(r, 8, QTableWidgetItem("0"))

    def _del_tx_field_row(self) -> None:
        r = self.tx_fields_table.currentRow()
        if r >= 0:
            self.tx_fields_table.removeRow(r)

    def _build_step5_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        box = QGroupBox("📋 Configuration Summary & Export")
        b_layout = QVBoxLayout(box)

        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("font-size: 13px; line-height: 1.6; padding: 12px;")

        save_btn = QPushButton("💾 Generate & Save Workbook (.xlsx)")
        save_btn.setAccessibleName("Generate and Save Configuration")
        save_btn.setStyleSheet("font-weight: bold; padding: 10px; font-size: 14px;")
        save_btn.clicked.connect(self._save_wizard_config)

        b_layout.addWidget(self.summary_label)
        b_layout.addSpacing(16)
        b_layout.addWidget(save_btn)

        layout.addWidget(box)
        layout.addStretch()
        return page

    def _refresh_step5_summary(self) -> None:
        pname = self.profile_name_edit.text() or "Custom Protocol"
        ptype = self.parser_type_combo.currentText()
        baud = self.baud_combo.currentText()
        n_frames = self.frames_table.rowCount()
        
        total_signals = 0
        for r in range(self.vars_table.rowCount()):
            cnt_item = self.vars_table.item(r, 3)
            cnt = int(cnt_item.text()) if cnt_item and cnt_item.text().isdigit() else 1
            total_signals += cnt

        n_tx = self.tx_cmd_table.rowCount()
        n_tx_flds = self.tx_fields_table.rowCount()
        crc = self.crc_combo.currentText() if ptype == "framed" else "None (Hardware DLC Checksum)"
        hdr = self.header_hex_edit.text() if ptype == "framed" else "0xAA (CAN Type Byte)"

        self.summary_label.setText(
            f"<b>Profile Name:</b> {pname}<br>"
            f"<b>Parser Engine:</b> <code>{ptype}</code><br>"
            f"<b>Default Baud Rate:</b> {baud} baud<br>"
            f"<b>Framing & Checksum:</b> Header: <code>{hdr}</code> | CRC: <code>{crc}</code><br>"
            f"<b>Configured Frames:</b> {n_frames} frame(s)<br>"
            f"<b>Telemetry Signals (RX):</b> {total_signals} signal(s)<br>"
            f"<b>Transmit Commands (TX):</b> {n_tx} command(s) with {n_tx_flds} parameter field(s)<br><br>"
            f"Click <b>'Generate & Save Workbook'</b> below to export your ready-to-run Excel configuration file."
        )

    def _add_frame_row(self) -> None:
        r = self.frames_table.rowCount()
        self.frames_table.insertRow(r)
        self.frames_table.setItem(r, 0, QTableWidgetItem(f"0x{2000+r*0x1000:04X}"))
        self.frames_table.setItem(r, 1, QTableWidgetItem(f"Frame_{r+1}"))
        self.frames_table.setItem(r, 2, QTableWidgetItem("8"))
        self.frames_table.setItem(r, 3, QTableWidgetItem("rxtx"))

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
        self.vars_table.setItem(r, 3, QTableWidgetItem("1"))
        self.vars_table.setItem(r, 4, QTableWidgetItem("1"))
        self.vars_table.setItem(r, 5, QTableWidgetItem("1.0"))
        self.vars_table.setItem(r, 6, QTableWidgetItem("0"))
        self.vars_table.setItem(r, 7, QTableWidgetItem("V"))
        self.vars_table.setItem(r, 8, QTableWidgetItem("General"))
        self.vars_table.setItem(r, 9, QTableWidgetItem(""))

    def _del_var_row(self) -> None:
        r = self.vars_table.currentRow()
        if r >= 0:
            self.vars_table.removeRow(r)

    def _on_next(self) -> None:
        idx = self.stack.currentIndex()
        if idx < 4:
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
        self.next_btn.setVisible(idx < 4)

        if idx == 2:
            self._update_step3_delegates()
        elif idx == 3:
            self._update_step4_delegates()
        elif idx == 4:
            self._refresh_step5_summary()

        titles = [
            "Step 1 of 5: Protocol & Communication Settings",
            "Step 2 of 5: Frame Identifiers & Directions",
            "Step 3 of 5: Telemetry Signals & Array Definitions (RX)",
            "Step 4 of 5: Transmit Commands & Control Parameters (TX)",
            "Step 5 of 5: Review & Generate Configuration (.xlsx)"
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
        valid_dtypes = sorted(list(SUPPORTED_DATA_TYPES))
        self.vars_table.setItemDelegateForColumn(0, ComboBoxDelegate(frame_ids, self.vars_table))
        self.vars_table.setItemDelegateForColumn(2, ComboBoxDelegate(valid_dtypes, self.vars_table))
        self.vars_table.setItemDelegateForColumn(7, ComboBoxDelegate(["V", "A", "°C", "%", "s", "ms", "Hz", "W", "Wh", "Ohm", "m/s", "RPM"], self.vars_table))
        self.vars_table.setItemDelegateForColumn(8, ComboBoxDelegate(["Cell Voltages", "Pack Parameters", "Temperatures", "Pressures", "Main", "General"], self.vars_table))

    def _update_step4_delegates(self) -> None:
        """Populate Frame ID and Command Name dropdown delegates in Step 4 tables."""
        frame_ids = []
        for r in range(self.frames_table.rowCount()):
            item = self.frames_table.item(r, 0)
            if item and item.text().strip():
                frame_ids.append(item.text().strip())
        if not frame_ids:
            frame_ids = ["0x1000"]
        self.tx_cmd_table.setItemDelegateForColumn(1, ComboBoxDelegate(frame_ids, self.tx_cmd_table))

        cmd_names = []
        for r in range(self.tx_cmd_table.rowCount()):
            item = self.tx_cmd_table.item(r, 0)
            if item and item.text().strip():
                cmd_names.append(item.text().strip())
        if not cmd_names:
            cmd_names = ["Command_1"]
        self.tx_fields_table.setItemDelegateForColumn(0, ComboBoxDelegate(cmd_names, self.tx_fields_table))

    def _save_wizard_config(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Protocol Workbook", "custom_protocol.xlsx", "Excel Files (*.xlsx)")
        if not file_path:
            return

        try:
            ptype = self.parser_type_combo.currentText() if hasattr(self, "parser_type_combo") else "framed"
            crc_type = self.crc_combo.currentText()
            if crc_type == "none" or ptype == "waveshare_can":
                crc_size = 0
            elif crc_type == "crc32":
                crc_size = 4
            elif crc_type.startswith("crc16"):
                crc_size = 2
            else:
                crc_size = 0

            length_size = self.length_size_spin.value()
            if length_size < 1 and ptype == "framed":
                QMessageBox.warning(self, "Invalid Input", "Payload Length Size must be >= 1 for framed protocols.")
                return

            protocol_df = pd.DataFrame([{
                "profile_name": self.profile_name_edit.text() or "Custom Protocol",
                "parser_type": ptype,
                "header_hex": "AA" if ptype == "waveshare_can" else self.header_hex_edit.text(),
                "frame_id_size": self.frame_id_size_spin.value(),
                "frame_id_byte_order": "little",
                "length_size": self.length_size_spin.value(),
                "length_meaning": "payload_only",
                "length_byte_order": "",
                "crc_type": "none" if ptype == "waveshare_can" else crc_type,
                "crc_size": 0 if ptype == "waveshare_can" else crc_size,
                "crc_byte_order": "little",
                "crc_coverage": "header_to_payload",
                "footer_hex": "55" if ptype == "waveshare_can" else "",
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
                    "direction": self.frames_table.item(r, 3).text() if self.frames_table.item(r, 3) else "rxtx",
                    "enabled": True,
                    "description": ""
                })
            frames_df = pd.DataFrame(frames_rows)

            vars_rows = []
            for r in range(self.vars_table.rowCount()):
                cnt_str = self.vars_table.item(r, 3).text() if self.vars_table.item(r, 3) else "1"
                st_str = self.vars_table.item(r, 4).text() if self.vars_table.item(r, 4) else "1"
                scale_str = self.vars_table.item(r, 5).text() if self.vars_table.item(r, 5) else "1.0"
                offset_str = self.vars_table.item(r, 6).text() if self.vars_table.item(r, 6) else "0.0"

                vars_rows.append({
                    "id_or_address": self.vars_table.item(r, 0).text() if self.vars_table.item(r, 0) else "0x1000",
                    "signal_name": self.vars_table.item(r, 1).text() if self.vars_table.item(r, 1) else f"Signal_{r}",
                    "data_type": self.vars_table.item(r, 2).text() if self.vars_table.item(r, 2) else "uint16",
                    "count": int(cnt_str) if cnt_str.isdigit() else 1,
                    "start_index": int(st_str) if st_str.isdigit() else 1,
                    "byte_order": "little",
                    "scale": float(scale_str) if scale_str else 1.0,
                    "offset": float(offset_str) if offset_str else 0.0,
                    "unit": self.vars_table.item(r, 7).text() if self.vars_table.item(r, 7) else "",
                    "group": self.vars_table.item(r, 8).text() if self.vars_table.item(r, 8) else "General",
                    "read_write": "R",
                    "min_value": None,
                    "max_value": None,
                    "description": self.vars_table.item(r, 9).text() if self.vars_table.item(r, 9) else "",
                    "enabled": True
                })
            vars_df = pd.DataFrame(vars_rows)

            tx_rows = []
            for r in range(self.tx_cmd_table.rowCount()):
                cmd_name = self.tx_cmd_table.item(r, 0).text() if self.tx_cmd_table.item(r, 0) else f"Cmd_{r+1}"
                tx_rows.append({
                    "command_name": cmd_name,
                    "id_or_address": self.tx_cmd_table.item(r, 1).text() if self.tx_cmd_table.item(r, 1) else "0x1000",
                    "payload_hex": self.tx_cmd_table.item(r, 2).text() if self.tx_cmd_table.item(r, 2) else "",
                    "description": self.tx_cmd_table.item(r, 3).text() if self.tx_cmd_table.item(r, 3) else "",
                    "enabled": True
                })
            tx_df = pd.DataFrame(tx_rows)

            tx_fld_rows = []
            for r in range(self.tx_fields_table.rowCount()):
                cmd_n = self.tx_fields_table.item(r, 0).text() if self.tx_fields_table.item(r, 0) else ""
                sig_n = self.tx_fields_table.item(r, 1).text() if self.tx_fields_table.item(r, 1) else "Param"
                dtype = self.tx_fields_table.item(r, 2).text() if self.tx_fields_table.item(r, 2) else "uint16"
                scale_v = float(self.tx_fields_table.item(r, 3).text()) if self.tx_fields_table.item(r, 3) and self.tx_fields_table.item(r, 3).text() else 1.0
                offset_v = float(self.tx_fields_table.item(r, 4).text()) if self.tx_fields_table.item(r, 4) and self.tx_fields_table.item(r, 4).text() else 0.0
                unit_v = self.tx_fields_table.item(r, 5).text() if self.tx_fields_table.item(r, 5) else ""
                min_v = float(self.tx_fields_table.item(r, 6).text()) if self.tx_fields_table.item(r, 6) and self.tx_fields_table.item(r, 6).text() else None
                max_v = float(self.tx_fields_table.item(r, 7).text()) if self.tx_fields_table.item(r, 7) and self.tx_fields_table.item(r, 7).text() else None
                def_v = float(self.tx_fields_table.item(r, 8).text()) if self.tx_fields_table.item(r, 8) and self.tx_fields_table.item(r, 8).text() else 0.0

                if cmd_n:
                    tx_fld_rows.append({
                        "command_name": cmd_n,
                        "signal_name": sig_n,
                        "data_type": dtype,
                        "byte_order": "little",
                        "scale": scale_v,
                        "offset": offset_v,
                        "unit": unit_v,
                        "min_value": min_v,
                        "max_value": max_v,
                        "default": def_v
                    })
            tx_fields_df = pd.DataFrame(tx_fld_rows)

            baud_val = int(self.baud_combo.currentText()) if hasattr(self, "baud_combo") and self.baud_combo.currentText().isdigit() else 115200
            serial_df = pd.DataFrame([{"baud_rate": baud_val, "data_bits": 8, "stop_bits": 1, "parity": "N", "timeout_ms": 100}])

            # Package all tables into canonical workbook mapping synchronized with template_io
            export_tables = {
                "Protocol": protocol_df,
                "Frames": frames_df,
                "Variables": vars_df,
                "Bitfields": self._template_tables.get("Bitfields", pd.DataFrame(columns=["id_or_address", "signal_name", "bit_index", "label", "active_text", "inactive_text"])),
                "Enums": self._template_tables.get("Enums", pd.DataFrame(columns=["id_or_address", "signal_name", "value", "label"])),
                "CalcGroups": self._template_tables.get("CalcGroups", pd.DataFrame(columns=["group_name", "operations", "unit", "frame_id", "enabled"])),
                "TxCommands": tx_df,
                "TxCommandFields": tx_fields_df,
                "PollingSchedule": self._template_tables.get("PollingSchedule", pd.DataFrame(columns=["id_or_address", "interval_ms", "timeout_ms", "enabled"])),
                "SerialDefaults": serial_df,
            }

            write_workbook_from_tables(export_tables, file_path)

            QMessageBox.information(self, "Success", f"Created configuration workbook:\n{file_path}")
            self.protocol_created.emit(file_path)
            self.accept()

        except Exception as ex:
            QMessageBox.critical(self, "Error", f"Failed to generate configuration workbook:\n{ex}")
