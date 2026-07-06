import pytest
from app.ui.config_editor import ConfigEditorWindow
from app.decoder.template_io import CONFIG_CSV_FILES
from pathlib import Path

def test_config_editor_smoke():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
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
