"""Interactive Configuration Editor GUI for Bytehound."""

import json
from pathlib import Path
from typing import Dict, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QHeaderView, QComboBox
)

from ..decoder.config_loader import _read_excel_tables, _read_csv_tables
from ..decoder.template_io import CONFIG_CSV_FILES, _sheet_name_from_csv
from ..decoder.types import SUPPORTED_CRC_TYPES, SUPPORTED_FMT_TYPES, ByteOrder, ParserType, ReadWrite

class ConfigEditorWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bytehound Configuration Editor")
        self.resize(1100, 750)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self._tabs = QTabWidget()
        self._tables: Dict[str, QTableWidget] = {}
        
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        
        # Toolbar
        btn_layout = QHBoxLayout()
        load_btn = QPushButton("Load Config...")
        load_btn.clicked.connect(self._load_config)
        
        save_json_btn = QPushButton("Save as JSON...")
        save_json_btn.clicked.connect(self._save_json)
        
        save_excel_btn = QPushButton("Save as Excel...")
        save_excel_btn.clicked.connect(self._save_excel)
        
        new_row_btn = QPushButton("Add Row")
        new_row_btn.clicked.connect(self._add_row)
        
        del_row_btn = QPushButton("Delete Row")
        del_row_btn.clicked.connect(self._delete_row)

        btn_layout.addWidget(load_btn)
        btn_layout.addWidget(save_json_btn)
        btn_layout.addWidget(save_excel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(new_row_btn)
        btn_layout.addWidget(del_row_btn)
        
        layout.addLayout(btn_layout)
        layout.addWidget(self._tabs)
        
        self.setCentralWidget(main_widget)
        
        self._init_tabs()

    def _init_tabs(self):
        # We initialize empty tables for all expected config files
        for csv_file in CONFIG_CSV_FILES:
            name = csv_file.replace(".csv", "")
            table = QTableWidget()
            table.horizontalHeader().setStretchLastSection(True)
            table.setAlternatingRowColors(True)
            self._tables[name] = table
            self._tabs.addTab(table, _sheet_name_from_csv(csv_file))
            
    def _add_row(self):
        current_table = self._tabs.currentWidget()
        if not isinstance(current_table, QTableWidget):
            return
        
        # If table has 0 columns, add a dummy column so they can at least add a row
        if current_table.columnCount() == 0:
            current_table.setColumnCount(1)
            current_table.setHorizontalHeaderLabels(["Column1"])
            
        row = current_table.rowCount()
        current_table.insertRow(row)
        # Apply dropdowns to new row
        self._apply_dropdowns(current_table, row)

    def _delete_row(self):
        current_table = self._tabs.currentWidget()
        if not isinstance(current_table, QTableWidget):
            return
        current_row = current_table.currentRow()
        if current_row >= 0:
            current_table.removeRow(current_row)

    def _apply_dropdowns(self, table: QTableWidget, row: int):
        for col in range(table.columnCount()):
            col_name = table.horizontalHeaderItem(col).text()
            items = []
            if col_name == "data_type":
                items = sorted(SUPPORTED_FMT_TYPES)
            elif col_name == "crc_type":
                items = sorted(SUPPORTED_CRC_TYPES)
            elif col_name in ("endianness", "frame_id_byte_order", "crc_byte_order", "length_byte_order"):
                items = [m.value for m in ByteOrder]
            elif col_name == "parser_type":
                items = [m.value for m in ParserType]
            elif col_name == "read_write":
                items = [m.value for m in ReadWrite]
                
            if items:
                combo = QComboBox()
                combo.addItems([""] + items)
                item = table.item(row, col)
                current_text = item.text() if item else ""
                combo.setCurrentText(current_text)
                
                # Make a cell widget transparently update the underlying item
                # so get_data doesn't only rely on the widget state if it gets detached
                def on_change(text, r=row, c=col, t=table):
                    it = t.item(r, c)
                    if it:
                        it.setText(text)
                    else:
                        t.setItem(r, c, QTableWidgetItem(text))
                combo.currentTextChanged.connect(on_change)
                table.setCellWidget(row, col, combo)

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
            else:
                QMessageBox.warning(self, "Error", "Only JSON and Excel loading is supported in the editor currently.")
                return
                
            self.load_data(data)
        except Exception as e:
            QMessageBox.critical(self, "Error loading config", str(e))

    def load_data(self, data: Dict[str, List[Dict[str, str]]]):
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

    def _save_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save JSON Config", "", "JSON Config (*.json)")
        if not path:
            return
        
        data = self.get_data()
        try:
            with open(path, "w", encoding="utf-8") as fp:
                json.dump(data, fp, indent=2)
            QMessageBox.information(self, "Success", f"Saved to {path}")
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
        except Exception as e:
            QMessageBox.critical(self, "Error saving", str(e))
