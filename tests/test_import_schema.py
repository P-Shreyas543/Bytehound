"""Tests for SchemaMapperDialog and log loaders custom schema matching."""

from __future__ import annotations

import os
import pytest
import numpy as np
import pandas as pd
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings

from app.ui.dialogs import SchemaMapperDialog
from app.ui.log_io import LogLoaderThread


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_schema_mapper_dialog(qapp):
    settings = QSettings("BytehoundTest", "TestSchemaMapperDialog")
    settings.clear()

    # Initial defaults
    dlg = SchemaMapperDialog(settings)
    assert dlg._sheets_edit.text() == "Data,Record"
    assert dlg._cols_edit.text() == "Elapsed (s),elapsed_ms"

    # Edit settings
    dlg._sheets_edit.setText("MyCustomSheet")
    dlg._cols_edit.setText("time_us")
    dlg._scale_edit.setPlainText("time_us: 0.000001")
    dlg._on_accept()

    # Verify settings persisted
    assert settings.value("import/sheet_names") == "MyCustomSheet"
    assert settings.value("import/elapsed_cols") == "time_us"
    assert settings.value("import/elapsed_scales") == "time_us: 0.000001"

    settings.clear()


def test_loader_respects_custom_schema(qapp, tmp_path, monkeypatch):
    # Setup custom settings
    class MockSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__("BytehoundTestOrg", "BytehoundTestApp")
            self.clear()
            self.setValue("import/sheet_names", "MyCustomSheet")
            self.setValue("import/elapsed_cols", "time_us")
            self.setValue("import/elapsed_scales", "time_us: 0.000001")

    monkeypatch.setattr("PySide6.QtCore.QSettings", MockSettings)

    # 1. Create a dummy CSV with custom elapsed column "time_us"
    csv_file = tmp_path / "custom_test.csv"
    df_csv = pd.DataFrame({
        "time_us": [1000000, 2000000, 3000000],
        "Voltage": [3.6, 3.7, 3.8]
    })
    df_csv.to_csv(csv_file, index=False)

    # Load the CSV in a LogLoaderThread
    loader = LogLoaderThread(str(csv_file), "log1", "#FF0000")
    
    # Run the CSV loading method directly
    loader._load_csv()
    
    # Get cached entry
    from app.ui.log_io import _CSV_CACHE
    entry = _CSV_CACHE.get(str(csv_file))
    
    assert entry is not None
    # time_us scaled by 0.000001 should equal [1.0, 2.0, 3.0]
    np.testing.assert_array_almost_equal(entry.elapsed, [1.0, 2.0, 3.0])
    assert "Voltage" in entry.columns
    np.testing.assert_array_almost_equal(entry.columns["Voltage"], [3.6, 3.7, 3.8])

    # 2. Create a dummy XLSX with custom sheet "MyCustomSheet" and elapsed column "time_us"
    xlsx_file = tmp_path / "custom_test.xlsx"
    with pd.ExcelWriter(xlsx_file) as writer:
        df_csv.to_excel(writer, sheet_name="MyCustomSheet", index=False)

    loader_xlsx = LogLoaderThread(str(xlsx_file), "log2", "#00FF00")
    loader_xlsx._load_xlsx()
    
    entry_xlsx = _CSV_CACHE.get(str(xlsx_file))
    assert entry_xlsx is not None
    np.testing.assert_array_almost_equal(entry_xlsx.elapsed, [1.0, 2.0, 3.0])
    assert "Voltage" in entry_xlsx.columns
    np.testing.assert_array_almost_equal(entry_xlsx.columns["Voltage"], [3.6, 3.7, 3.8])
