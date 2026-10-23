"""Focused verification for the September 2026 GUI backlog implementation."""

import os

import pytest
from PySide6.QtWidgets import QApplication

from single_cell_cycler.ui.main_window import MainWindow
from single_cell_cycler.ui.widgets.kpi_dashboard import KPIDashboard
from single_cell_cycler.ui.widgets.profile_editor import ProfileEditorWidget


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication([])
    return app


def test_start_gate_compact_mode_and_event_filter(qapp):
    window = MainWindow()
    try:
        assert not window.btn_start_stop.isEnabled()
        assert "Start locked:" in window.btn_start_stop.toolTip()

        window._append_event("normal event", "info")
        window._append_event("warning event", "warning")
        window._append_event("critical event", "critical")
        window.btn_event_log.click()
        window.combo_event_severity.setCurrentIndex(2)
        assert "critical event" in window.event_text.toPlainText()
        assert "normal event" not in window.event_text.toPlainText()

        window.btn_compact.click()
        assert window._compact_mode is True
        assert window.tabs.isTabVisible(0)
        assert window.tabs.isTabVisible(4)
        assert not window.tabs.isTabVisible(1)
    finally:
        window.close()


def test_font_scale_and_kpi_reflow(qapp):
    window = MainWindow()
    try:
        for index in range(window.combo_font.count()):
            window.combo_font.setCurrentIndex(index)
            qapp.processEvents()
            assert window.combo_font.currentText()

        dashboard = KPIDashboard()
        dashboard.resize(650, 500)
        dashboard.show()
        qapp.processEvents()
        assert dashboard._last_columns == 1
        dashboard.resize(850, 500)
        qapp.processEvents()
        assert dashboard._last_columns == 2
        dashboard.resize(1300, 500)
        qapp.processEvents()
        assert dashboard._last_columns == 4
        dashboard.close()
    finally:
        window.close()


def test_recipe_editor_lock_and_summary(qapp):
    editor = ProfileEditorWidget()
    try:
        assert editor.lbl_recipe_summary.text()
        editor.set_editing_enabled(False)
        assert not editor.btn_add_step.isEnabled()
        assert not editor.btn_duplicate_step.isEnabled()
        assert "locked" in editor.lbl_recipe_state.toolTip().lower()
        editor.set_editing_enabled(True)
        assert editor.btn_add_step.isEnabled()
    finally:
        editor.close()
