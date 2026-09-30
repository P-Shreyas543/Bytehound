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
        dashboard.resize(420, 500)
        dashboard.show()
        qapp.processEvents()
        assert dashboard._last_columns == 1
        dashboard.resize(700, 500)
        qapp.processEvents()
        assert dashboard._last_columns == 2
        dashboard.resize(1000, 500)
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


def test_window_fits_1280x720_and_estop_never_overflows(qapp):
    window = MainWindow()
    try:
        window.combo_font.setCurrentIndex(0)   # an earlier test may leave a large font applied
        window.combo_font.setCurrentIndex(1)   # default 11 pt
        window.show()
        qapp.processEvents()
        hint = window.minimumSizeHint()
        assert hint.width() <= 1280 and hint.height() <= 700, (hint.width(), hint.height())
        # E-STOP lives in the run-status row, not in the toolbar that can overflow
        assert window.btn_estop.parentWidget() is not window.toolbar
        assert window.btn_estop.isVisible()
        window.resize(1280, 720)
        qapp.processEvents()
        assert window.width() == 1280 and window.height() == 720
    finally:
        window.close()


def test_kpi_cards_have_no_stale_placeholder_or_label_blocks(qapp):
    dashboard = KPIDashboard()
    dashboard.show()
    qapp.processEvents()
    dashboard.set_telemetry_age(0.2)
    for card in dashboard._cards:
        assert card.lbl_age.text() == ""                       # fresh: no "No telemetry"
        assert "transparent" in card.styleSheet()              # labels don't paint dark boxes
    dashboard.set_telemetry_age(12.0)
    assert all("stale" in c.lbl_age.text().lower() for c in dashboard._cards)
    # Long subtitles stay on one line: card height does not change with text length
    card = dashboard.card_cycle_kpi
    h0 = card.sizeHint().height()
    card.set_value("Cycle 12", "A very long recipe name · 1. CC/CV Charge (1.5A to 4.2V, 0.18A taper) · 123:45")
    qapp.processEvents()
    assert card.sizeHint().height() == h0
    dashboard.close()
