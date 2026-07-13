"""Interactive Configuration Editor GUI for Bytehound."""

import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeySequence, QShortcut, QColor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QComboBox, QHeaderView
)

from ..decoder.config_loader import _read_excel_tables
from ..decoder.template_io import CONFIG_CSV_FILES, _sheet_name_from_csv
from ..decoder.types import SUPPORTED_CRC_TYPES, SUPPORTED_FMT_TYPES, SUPPORTED_DATA_TYPES, ByteOrder, ParserType, ReadWrite

class ConfigEditorWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bytehound Configuration Editor")
        self.resize(1100, 750)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self._active_config_path: Optional[Path] = None
        self._is_dirty = False

        self._tabs = QTabWidget()
        self._tables: Dict[str, QTableWidget] = {}

        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)

        # Toolbar
        btn_layout = QHBoxLayout()
        
        load_btn = QPushButton("📂 Load Config...")
        load_btn.clicked.connect(self._load_config)

        self.save_active_btn = QPushButton("💾 Save & Apply")
        self.save_active_btn.clicked.connect(self._on_validate_and_save)
        self.save_active_btn.setEnabled(False)

        save_json_btn = QPushButton("Save as JSON...")
        save_json_btn.clicked.connect(self._save_json)

        save_excel_btn = QPushButton("Save as Excel...")
        save_excel_btn.clicked.connect(self._save_excel)

        validate_btn = QPushButton("🔍 Validate")
        validate_btn.clicked.connect(self._on_validate)

        new_row_btn = QPushButton("➕ Add Row")
        new_row_btn.clicked.connect(self._add_row)

        del_row_btn = QPushButton("❌ Delete Row")
        del_row_btn.clicked.connect(self._delete_row)

        btn_layout.addWidget(load_btn)
        btn_layout.addWidget(self.save_active_btn)
        btn_layout.addWidget(save_json_btn)
        btn_layout.addWidget(save_excel_btn)
        btn_layout.addWidget(validate_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(new_row_btn)
        btn_layout.addWidget(del_row_btn)

        layout.addLayout(btn_layout)
        layout.addWidget(self._tabs)

        self.setCentralWidget(main_widget)

        self._init_tabs()
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # Register keyboard shortcuts
        self.add_shortcut = QShortcut(QKeySequence("Ctrl+="), self)
        self.add_shortcut.activated.connect(self._add_row)
        
        self.del_shortcut = QShortcut(QKeySequence("Ctrl+-"), self)
        self.del_shortcut.activated.connect(self._delete_row)

    def _load_default_headers(self) -> Dict[str, List[str]]:
        headers = {}
        template_dir = Path(__file__).resolve().parents[1] / "resources" / "config_template"
        for csv_file in CONFIG_CSV_FILES:
            name = csv_file.replace(".csv", "")
            path = template_dir / csv_file
            if path.exists():
                try:
                    with path.open("r", encoding="utf-8-sig") as fp:
                        reader = csv.reader(fp)
                        header_row = next(reader)
                        headers[name] = [h.strip() for h in header_row if h.strip()]
                except Exception:
                    pass
        return headers

    def _init_tabs(self):
        default_headers = self._load_default_headers()
        for csv_file in CONFIG_CSV_FILES:
            name = csv_file.replace(".csv", "")
            table = QTableWidget()
            table.horizontalHeader().setStretchLastSection(True)
            table.setAlternatingRowColors(True)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            table.installEventFilter(self)
            table.itemChanged.connect(self._on_item_changed)
            
            headers = default_headers.get(name, [])
            if headers:
                table.setColumnCount(len(headers))
                table.setHorizontalHeaderLabels(headers)
            
            self._tables[name] = table
            self._tabs.addTab(table, _sheet_name_from_csv(csv_file))

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and isinstance(obj, QTableWidget):
            if event.key() == Qt.Key.Key_Delete:
                # Clear cell contents on Delete key press
                for item in obj.selectedItems():
                    r = item.row()
                    c = item.column()
                    widget = obj.cellWidget(r, c)
                    if isinstance(widget, QComboBox):
                        widget.setCurrentText("")
                    else:
                        item.setText("")
                self._mark_dirty()
                return True
        return super().eventFilter(obj, event)

    def _mark_dirty(self):
        if not self._is_dirty:
            self._is_dirty = True
            self._update_title()

    def _mark_clean(self):
        self._is_dirty = False
        self._update_title()

    def _update_title(self):
        base_title = "Bytehound Configuration Editor"
        if self._active_config_path:
            base_title += f" - {self._active_config_path.name}"
        if self._is_dirty:
            base_title += " *"
        self.setWindowTitle(base_title)

    def _on_item_changed(self, item: QTableWidgetItem):
        self._mark_dirty()
        
        # Clear validation row highlights dynamically when edited
        table = item.tableWidget()
        if table:
            row = item.row()
            for c in range(table.columnCount()):
                it = table.item(row, c)
                if it:
                    it.setBackground(Qt.BrushStyle.NoBrush)

    def closeEvent(self, event):
        if self._is_dirty:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Would you like to save them before closing?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                if self.validate_data():
                    self._on_validate_and_save()
                    event.accept()
                else:
                    event.ignore()
            elif reply == QMessageBox.No:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def set_active_config_path(self, path: Path):
        self._active_config_path = Path(path) if path else None
        self._update_title()
        if self._active_config_path:
            self.save_active_btn.setEnabled(True)
        else:
            self.save_active_btn.setEnabled(False)

    def _add_row(self):
        current_table = self._tabs.currentWidget()
        if not isinstance(current_table, QTableWidget):
            return

        if current_table.columnCount() == 0:
            current_table.setColumnCount(1)
            current_table.setHorizontalHeaderLabels(["Column1"])

        current_row = current_table.currentRow()
        if current_row < 0:
            current_row = current_table.rowCount()
            
        current_table.insertRow(current_row)
        self._apply_dropdowns(current_table, current_row)
        self._mark_dirty()

    def _delete_row(self):
        current_table = self._tabs.currentWidget()
        if not isinstance(current_table, QTableWidget):
            return
        current_row = current_table.currentRow()
        if current_row >= 0:
            current_table.removeRow(current_row)
            self._mark_dirty()

    def _apply_dropdowns(self, table: QTableWidget, row: int, refresh_only=False):
        for col in range(table.columnCount()):
            col_name = table.horizontalHeaderItem(col).text()
            items = []
            is_editable = False
            
            if col_name in ("data_type", "data_type"):
                table_name = ""
                for name, tbl in self._tables.items():
                    if tbl is table:
                        table_name = name
                        break
                
                if table_name == "frame_config":
                    items = sorted(list(SUPPORTED_DATA_TYPES))
                else:
                    items = sorted(list(SUPPORTED_FMT_TYPES))
            elif col_name == "crc_type":
                items = sorted(list(SUPPORTED_CRC_TYPES))
            elif col_name in ("endianness", "byte_order", "frame_id_byte_order", "crc_byte_order", "length_byte_order"):
                items = [m.value for m in ByteOrder]
            elif col_name == "parser_type":
                items = [m.value for m in ParserType]
            elif col_name == "read_write":
                items = [m.value for m in ReadWrite]
            elif col_name == "direction":
                items = ["rx", "tx", "rxtx"]
            elif col_name in ("enabled", "waveshare_fixed_20_bytes", "waveshare_fixed"):
                items = ["TRUE", "FALSE"]
            elif col_name == "length_meaning":
                items = ["payload_only", "frame_total", "header_to_crc", "payload_plus_crc"]
            elif col_name == "crc_coverage":
                items = ["header_to_payload", "frame_id_to_payload", "payload_only", "full_frame"]
            elif col_name == "escape_mode":
                items = ["none", "slip", "hdlc", "cobs"]
            elif col_name == "raw_log_format":
                items = ["hex", "compact"]
            elif col_name == "baud_rate":
                items = ["9600", "19200", "38400", "57600", "115200"]
                is_editable = True
            elif col_name == "data_bits":
                items = ["5", "6", "7", "8"]
            elif col_name == "stop_bits":
                items = ["1", "1.5", "2"]
            elif col_name == "parity":
                items = ["N", "E", "O", "M", "S"]
            elif col_name == "operations":
                items = ["min", "max", "sum", "diff", "avg", "min|max", "min|max|avg", "min|max|diff|avg", "sum|avg"]
                is_editable = True
            elif col_name == "frame_id_size":
                items = ["1", "2", "4"]
            elif col_name == "length_size":
                items = ["0", "1", "2", "4"]
            elif col_name == "crc_size":
                items = ["0", "2", "4"]
            elif col_name == "unit":
                items = ["V", "A", "°C", "%", "s", "ms", "Hz", "W", "Wh", "Ohm", "m/s", "RPM"]
                is_editable = True
            elif col_name == "active_text":
                items = ["ON", "YES", "TRUE", "FAULT", "ACTIVE", "HIGH"]
                is_editable = True
            elif col_name == "inactive_text":
                items = ["OFF", "NO", "FALSE", "OK", "INACTIVE", "LOW"]
                is_editable = True
            elif col_name in ("id_or_address", "frame_id", "frame_id_hex", "signal_name", "variable_name", "group", "group_name", "command_name"):
                items = self._get_dynamic_options(col_name)
                is_editable = True

            if items:
                combo = table.cellWidget(row, col)
                if refresh_only:
                    if isinstance(combo, QComboBox):
                        current_text = combo.currentText()
                        combo.blockSignals(True)
                        combo.clear()
                        combo.addItems([""] + items)
                        combo.setCurrentText(current_text)
                        combo.blockSignals(False)
                else:
                    combo = QComboBox()
                    if is_editable:
                        combo.setEditable(True)
                    combo.addItems([""] + items)
                    item = table.item(row, col)
                    current_text = item.text() if item else ""
                    combo.setCurrentText(current_text)

                    def make_on_change(combo_widget=combo, table_widget=table):
                        def on_change(text):
                            for r in range(table_widget.rowCount()):
                                for c in range(table_widget.columnCount()):
                                    if table_widget.cellWidget(r, c) is combo_widget:
                                        it = table_widget.item(r, c)
                                        if it:
                                            it.setText(text)
                                        else:
                                            table_widget.setItem(r, c, QTableWidgetItem(text))
                                        return
                        return on_change

                    combo.currentTextChanged.connect(make_on_change(combo, table))
                    table.setCellWidget(row, col, combo)

    def _get_cell_value(self, table: QTableWidget, r: int, c: int) -> str:
        widget = table.cellWidget(r, c)
        if isinstance(widget, QComboBox):
            return widget.currentText()
        item = table.item(r, c)
        return item.text() if item else ""

    def _get_dynamic_options(self, col_name: str) -> List[str]:
        options = []
        if col_name in ("id_or_address", "frame_id", "frame_id_hex"):
            ids = set()
            for name in ("frames", "variables", "frame_config", "polling_schedule", "tx_commands"):
                table = self._tables.get(name)
                if table:
                    id_col = -1
                    for col in range(table.columnCount()):
                        hdr = table.horizontalHeaderItem(col).text()
                        if hdr in ("frame_id", "id_or_address", "frame_id_hex"):
                            id_col = col
                            break
                    if id_col != -1:
                        for r in range(table.rowCount()):
                            val = self._get_cell_value(table, r, id_col)
                            if val.strip():
                                ids.add(val.strip())
            options = sorted(list(ids))
            
        elif col_name in ("signal_name", "variable_name"):
            names = set()
            for name in ("variables", "frame_config"):
                table = self._tables.get(name)
                if table:
                    sig_col = -1
                    for col in range(table.columnCount()):
                        hdr = table.horizontalHeaderItem(col).text()
                        if hdr == "signal_name":
                            sig_col = col
                            break
                    if sig_col != -1:
                        for r in range(table.rowCount()):
                            val = self._get_cell_value(table, r, sig_col)
                            if val.strip():
                                names.add(val.strip())
            options = sorted(list(names))
            
        elif col_name in ("group", "group_name"):
            groups = set()
            table = self._tables.get("variables")
            if table:
                group_col = -1
                for col in range(table.columnCount()):
                    hdr = table.horizontalHeaderItem(col).text()
                    if hdr == "group":
                        group_col = col
                        break
                if group_col != -1:
                    for r in range(table.rowCount()):
                        val = self._get_cell_value(table, r, group_col)
                        if val.strip():
                            groups.add(val.strip())
            options = sorted(list(groups))
            
        elif col_name == "command_name":
            cmds = set()
            table = self._tables.get("tx_commands")
            if table:
                cmd_col = -1
                for col in range(table.columnCount()):
                    hdr = table.horizontalHeaderItem(col).text()
                    if hdr == "command_name":
                        cmd_col = col
                        break
                if cmd_col != -1:
                    for r in range(table.rowCount()):
                        val = self._get_cell_value(table, r, cmd_col)
                        if val.strip():
                            cmds.add(val.strip())
            options = sorted(list(cmds))
            
        return options

    def _on_tab_changed(self, index: int):
        table = self._tabs.widget(index)
        if isinstance(table, QTableWidget):
            for r in range(table.rowCount()):
                self._apply_dropdowns(table, r, refresh_only=True)

    def _load_config(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Config", "", "Config Files (*.json *.xlsx *.csv);;All Files (*)")
        if not path:
            return

        try:
            path_obj = Path(path)
            if path_obj.suffix.lower() == ".json":
                with path_obj.open("r", encoding="utf-8") as fp:
                    data = json.load(fp)
            elif path_obj.suffix.lower() in {".xlsx", ".xlsm"}:
                data = _read_excel_tables(path_obj)
            elif path_obj.suffix.lower() == ".csv":
                from ..decoder.config_loader import _read_csv_tables
                path_obj = path_obj.parent
                data = _read_csv_tables(path_obj)
            elif path_obj.is_dir():
                from ..decoder.config_loader import _read_csv_tables
                data = _read_csv_tables(path_obj)
            else:
                QMessageBox.warning(self, "Error", "Unsupported file type. Please select a JSON, Excel, or CSV file.")
                return

            self.set_active_config_path(path_obj)
            self.load_data(data)
            self._mark_clean()
        except Exception as e:
            QMessageBox.critical(self, "Error loading config", str(e))

    def load_data(self, data: Dict[str, List[Dict[str, str]]]):
        for name, table in self._tables.items():
            table.setRowCount(0)

        for name, rows in data.items():
            if name in self._tables and rows:
                table = self._tables[name]
                columns = list(rows[0].keys())
                table.setColumnCount(len(columns))
                table.setHorizontalHeaderLabels(columns)
                table.setRowCount(len(rows))

                for row_idx, row_dict in enumerate(rows):
                    for col_idx, col_name in enumerate(columns):
                        val = str(row_dict.get(col_name, ""))
                        table.setItem(row_idx, col_idx, QTableWidgetItem(val))
                    self._apply_dropdowns(table, row_idx)
                table.resizeColumnsToContents()
        self._mark_clean()

    def get_data(self) -> Dict[str, List[Dict[str, str]]]:
        data = {}
        for name, table in self._tables.items():
            rows = []
            cols = table.columnCount()
            if cols == 0:
                continue
            headers = [table.horizontalHeaderItem(i).text() for i in range(cols)]
            for r in range(table.rowCount()):
                row_data = {}
                empty_row = True
                for c in range(cols):
                    widget = table.cellWidget(r, c)
                    if isinstance(widget, QComboBox):
                        val = widget.currentText()
                    else:
                        item = table.item(r, c)
                        val = item.text() if item else ""
                    if val.strip():
                        empty_row = False
                    row_data[headers[c]] = val
                if not empty_row:
                    rows.append(row_data)
            if rows:
                data[name] = rows
        return data

    def validate_data(self) -> bool:
        """Validate the current configuration tables using load_config on a temporary JSON file.
        
        Highlights any errors in the tables and displays details in a messagebox.
        """
        self.clear_validation_highlights()
        data = self.get_data()
        
        import tempfile
        import os
        from ..decoder.config_loader import load_config, ConfigError
        
        temp_fd, temp_path = tempfile.mkstemp(suffix=".json", text=True)
        os.close(temp_fd)
        
        try:
            with open(temp_path, "w", encoding="utf-8") as fp:
                json.dump(data, fp, indent=2)
            
            load_config(temp_path)
            return True
            
        except (ConfigError, ValueError) as exc:
            error_msg = str(exc)
            if not error_msg.startswith(tuple(self._tables.keys())):
                lower_msg = error_msg.lower()
                if any(k in lower_msg for k in ("parser_type", "crc_type", "length_meaning", "escape_mode", "raw_log_format", "profile_name")):
                    error_msg = f"protocol: {error_msg}"
                elif "operations" in lower_msg:
                    error_msg = f"calc_groups: {error_msg}"
            self._handle_validation_error(error_msg)
            return False
        except Exception as exc:
            QMessageBox.critical(self, "Unexpected Validation Error", f"An unexpected error occurred during validation:\n{exc}")
            return False
        finally:
            try:
                os.remove(temp_path)
            except Exception:
                pass

    def clear_validation_highlights(self):
        for table in self._tables.values():
            table.blockSignals(True)
            for r in range(table.rowCount()):
                for c in range(table.columnCount()):
                    it = table.item(r, c)
                    if it:
                        it.setBackground(Qt.BrushStyle.NoBrush)
            table.blockSignals(False)

    def _handle_validation_error(self, error_msg: str):
        match_row = re.search(r"(\w+)\s+row\s+(\d+)", error_msg)
        match_sheet = re.search(r"^(\w+):", error_msg)
        
        target_sheet = None
        target_row_idx = None
        
        if match_row:
            sheet_name_raw = match_row.group(1)
            row_no = int(match_row.group(2))
            target_row_idx = row_no - 2
            from ..decoder.config_loader import _normalize_table_name
            target_sheet = _normalize_table_name(sheet_name_raw)
        elif match_sheet:
            sheet_name_raw = match_sheet.group(1)
            from ..decoder.config_loader import _normalize_table_name
            target_sheet = _normalize_table_name(sheet_name_raw)
            
        if target_sheet and target_sheet in self._tables:
            table = self._tables[target_sheet]
            self._tabs.setCurrentWidget(table)
            
            if target_row_idx is None and target_sheet == "protocol" and table.rowCount() > 0:
                target_row_idx = 0

            if target_row_idx is not None and 0 <= target_row_idx < table.rowCount():
                highlight_brush = QColor(255, 204, 204)
                table.blockSignals(True)
                for c in range(table.columnCount()):
                    it = table.item(target_row_idx, c)
                    if not it:
                        it = QTableWidgetItem()
                        table.setItem(target_row_idx, c, it)
                    it.setBackground(highlight_brush)
                table.blockSignals(False)
                
                table.scrollToItem(table.item(target_row_idx, 0))
                
        QMessageBox.critical(self, "Validation Error", f"Configuration is invalid:\n\n{error_msg}")

    def _on_validate(self):
        if self.validate_data():
            QMessageBox.information(self, "Validation Successful", "Configuration schema is valid!")

    def _on_validate_and_save(self):
        if not self.validate_data():
            return
            
        if not self._active_config_path:
            self._save_as_dialog()
            return
            
        try:
            self._save_to_path(self._active_config_path)
            QMessageBox.information(self, "Success", f"Configuration successfully saved to {self._active_config_path}!")
            self._mark_clean()
            
            if self.parent() and hasattr(self.parent(), "_load_config_from_path"):
                self.parent()._load_config_from_path(self._active_config_path)
        except Exception as e:
            QMessageBox.critical(self, "Error Saving", f"Failed to save configuration:\n{e}")

    def _save_as_dialog(self):
        reply = QMessageBox.question(
            self,
            "Save Configuration",
            "No active configuration file is set. Would you like to save as an Excel Workbook?",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            self._save_excel()
        elif reply == QMessageBox.No:
            self._save_json()

    def _save_to_path(self, path: Path):
        suffix = path.suffix.lower()
        data = self.get_data()
        
        if suffix == ".json":
            with path.open("w", encoding="utf-8") as fp:
                json.dump(data, fp, indent=2)
        elif suffix in {".xlsx", ".xlsm"}:
            import pandas as pd
            with pd.ExcelWriter(path) as writer:
                for name, rows in data.items():
                    df = pd.DataFrame(rows)
                    df.to_excel(writer, sheet_name=_sheet_name_from_csv(name + ".csv"), index=False)
        elif path.is_dir() or suffix == "":
            self._save_csv_dir(path)
        else:
            raise ValueError(f"Unsupported save format for path: {path}")

    def _save_csv_dir(self, directory: Path):
        data = self.get_data()
        try:
            directory.mkdir(parents=True, exist_ok=True)
            for name, rows in data.items():
                if not rows:
                    continue
                file_path = directory / f"{name}.csv"
                columns = list(rows[0].keys())
                import csv
                with file_path.open("w", encoding="utf-8", newline="") as fp:
                    writer = csv.DictWriter(fp, fieldnames=columns)
                    writer.writeheader()
                    writer.writerows(rows)
        except Exception as e:
            raise RuntimeError(f"Failed to save CSV directory: {e}")

    def _save_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save JSON Config", "", "JSON Config (*.json)")
        if not path:
            return

        data = self.get_data()
        try:
            with open(path, "w", encoding="utf-8") as fp:
                json.dump(data, fp, indent=2)
            QMessageBox.information(self, "Success", f"Saved to {path}")
            self.set_active_config_path(Path(path))
            self._mark_clean()
            if self.parent() and hasattr(self.parent(), "_load_config_from_path"):
                self.parent()._load_config_from_path(Path(path))
        except Exception as e:
            QMessageBox.critical(self, "Error saving", str(e))

    def _save_excel(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Excel Config", "", "Excel Config (*.xlsx)")
        if not path:
            return

        data = self.get_data()
        try:
            import pandas as pd
            with pd.ExcelWriter(path) as writer:
                for name, rows in data.items():
                    df = pd.DataFrame(rows)
                    df.to_excel(writer, sheet_name=_sheet_name_from_csv(name + ".csv"), index=False)
            QMessageBox.information(self, "Success", f"Saved to {path}")
            self.set_active_config_path(Path(path))
            self._mark_clean()
            if self.parent() and hasattr(self.parent(), "_load_config_from_path"):
                self.parent()._load_config_from_path(Path(path))
        except Exception as e:
            QMessageBox.critical(self, "Error saving", str(e))
