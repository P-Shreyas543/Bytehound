from app.ui.config_editor import ConfigEditorWindow
from app.decoder.template_io import CONFIG_CSV_FILES
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QTableWidgetItem

def test_config_editor_smoke(monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    QApplication.instance() or QApplication([])

    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    editor = ConfigEditorWindow()

    # Check that tabs were created for each config file
    assert editor._tabs.count() == len(CONFIG_CSV_FILES)

    # Load canonical config
    bundled_template_dir = Path(__file__).resolve().parents[1] / "app" / "resources" / "config_template"

    from app.decoder.config_loader import _read_csv_tables
    data = _read_csv_tables(bundled_template_dir)

    # Make sure we got data
    assert "protocol" in data

    # Load into editor
    editor.load_data(data)

    # Retrieve data back and check it's non-empty
    retrieved = editor.get_data()
    assert "protocol" in retrieved
    assert len(retrieved["protocol"]) > 0
    assert retrieved["protocol"][0]["profile_name"] == data["protocol"][0]["profile_name"]

def test_config_editor_validation_and_highlighting(monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    QApplication.instance() or QApplication([])

    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    editor = ConfigEditorWindow()

    # Load canonical template config
    bundled_template_dir = Path(__file__).resolve().parents[1] / "app" / "resources" / "config_template"
    from app.decoder.config_loader import _read_csv_tables
    data = _read_csv_tables(bundled_template_dir)
    editor.load_data(data)

    # Verify that initial valid data passes validation
    assert editor.validate_data() is True

    # Intentionally corrupt the data (e.g. invalid parser_type in protocol)
    protocol_table = editor._tables["protocol"]
    parser_type_col = -1
    for col in range(protocol_table.columnCount()):
        if protocol_table.horizontalHeaderItem(col).text() == "parser_type":
            parser_type_col = col
            break

    assert parser_type_col != -1

    # Set invalid value in parser_type combobox
    combo = protocol_table.cellWidget(0, parser_type_col)
    assert isinstance(combo, QComboBox)
    combo.addItem("invalid_parser_name")
    combo.setCurrentText("invalid_parser_name")

    # Now validation should fail
    assert editor.validate_data() is False

    # Verify highlighting: the protocol tab should have the first row colored
    item = protocol_table.item(0, 0)
    assert item is not None
    assert item.background().style() != Qt.BrushStyle.NoBrush

def test_config_editor_index_shift_resilience(monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    QApplication.instance() or QApplication([])

    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    editor = ConfigEditorWindow()

    # Load default template config
    bundled_template_dir = Path(__file__).resolve().parents[1] / "app" / "resources" / "config_template"
    from app.decoder.config_loader import _read_csv_tables
    data = _read_csv_tables(bundled_template_dir)
    editor.load_data(data)

    protocol_table = editor._tables["protocol"]
    parser_type_col = -1
    for col in range(protocol_table.columnCount()):
        if protocol_table.horizontalHeaderItem(col).text() == "parser_type":
            parser_type_col = col
            break
    assert parser_type_col != -1

    # Initially we have 1 row. Add two more rows.
    editor._tabs.setCurrentWidget(protocol_table)
    editor._add_row()
    editor._add_row()

    assert protocol_table.rowCount() == 3

    combo0 = protocol_table.cellWidget(0, parser_type_col)
    combo1 = protocol_table.cellWidget(1, parser_type_col)
    combo2 = protocol_table.cellWidget(2, parser_type_col)
    assert combo0 is not None and combo1 is not None and combo2 is not None

    # Delete row 0
    protocol_table.setCurrentCell(0, 0)
    editor._delete_row()

    assert protocol_table.rowCount() == 2
    assert protocol_table.cellWidget(0, parser_type_col) is combo1
    combo1.setCurrentText("framed")

    item0 = protocol_table.item(0, parser_type_col)
    assert item0 is not None
    assert item0.text() == "framed"

def test_config_editor_calc_groups_operations(monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    QApplication.instance() or QApplication([])

    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    editor = ConfigEditorWindow()

    # Load default template config
    bundled_template_dir = Path(__file__).resolve().parents[1] / "app" / "resources" / "config_template"
    from app.decoder.config_loader import _read_csv_tables
    data = _read_csv_tables(bundled_template_dir)
    editor.load_data(data)

    calc_table = editor._tables["calc_groups"]
    operations_col = -1
    for col in range(calc_table.columnCount()):
        if calc_table.horizontalHeaderItem(col).text() == "operations":
            operations_col = col
            break
    assert operations_col != -1

    # Add a row to calc_groups
    editor._tabs.setCurrentWidget(calc_table)
    editor._add_row()

    row_idx = calc_table.rowCount() - 1
    combo = calc_table.cellWidget(row_idx, operations_col)
    assert isinstance(combo, QComboBox)
    assert combo.isEditable() is True

    # Check that "min", "max", "sum", "diff", "avg" options exist in the items
    combo_items = [combo.itemText(i) for i in range(combo.count())]
    assert "min" in combo_items
    assert "max" in combo_items
    assert "sum" in combo_items
    assert "diff" in combo_items
    assert "avg" in combo_items
    assert "min|max|diff|avg" in combo_items

def test_config_editor_ux_features(monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    QApplication.instance() or QApplication([])

    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No) # discard on close

    editor = ConfigEditorWindow()

    # Initially dirty is false and no asterisk in title
    assert editor._is_dirty is False
    assert "*" not in editor.windowTitle()

    # Load canonical data
    bundled_template_dir = Path(__file__).resolve().parents[1] / "app" / "resources" / "config_template"
    from app.decoder.config_loader import _read_csv_tables
    data = _read_csv_tables(bundled_template_dir)
    editor.load_data(data)

    # Still not dirty immediately after load
    assert editor._is_dirty is False

    # Edit an item -> marks dirty and sets asterisk
    protocol_table = editor._tables["protocol"]
    item = QTableWidgetItem("NewProfile")
    protocol_table.setItem(0, 0, item)

    assert editor._is_dirty is True
    assert "*" in editor.windowTitle()

    # Verify row insertion at current selection
    protocol_table.setRowCount(3)
    protocol_table.setCurrentCell(1, 0)
    editor._add_row() # should insert a row at index 1
    assert protocol_table.rowCount() == 4

    # Verify event filter for Key_Delete
    item_to_clear = protocol_table.item(0, 0)
    assert item_to_clear is not None
    assert item_to_clear.text() == "NewProfile"

    # Select item
    item_to_clear.setSelected(True)

    # Simulate Delete Key Press
    delete_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(protocol_table, delete_event)

    # Verify that the cell text is cleared
    assert item_to_clear.text() == ""



