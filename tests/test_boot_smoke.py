"""Boot-smoke for the MainWindow mixin stack.

Constructs MainWindow under an offscreen QPA plugin, exercises one
representative method per mixin, and tears down cleanly. Catches the
class of bugs that "import-level OK" smoke can't: missing cross-mixin
references, attribute-ordering issues in __init__, and missing module
imports that only fire when a method is actually called.

This file does not require a display server (uses ``QT_QPA_PLATFORM=offscreen``)
so it runs in CI / headless agents.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Force offscreen BEFORE any Qt import. Test-session order matters: this module
# must be imported before QApplication is created with a real platform plugin.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QHBoxLayout

import qdarktheme

from app.ui.main_window import (
    MainWindow,
    APP_ORG,
    APP_NAME,
    TitleBarThemeFilter,
)


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    settings = QSettings(APP_ORG, APP_NAME)
    saved = str(settings.value("ui/theme", "dark"))
    qdarktheme.setup_theme(saved, corner_shape="rounded")
    font = QFont("PT Sans", 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)
    tbf = TitleBarThemeFilter(settings)
    app.installEventFilter(tbf)
    app._titlebar_filter = tbf
    return app


@pytest.fixture
def window(qapp: QApplication):
    w = MainWindow()
    w.show()
    QTimer.singleShot(100, qapp.quit)
    qapp.exec()
    yield w
    w.close()


def test_mainwindow_constructs_and_shows(window: MainWindow) -> None:
    """All eleven mixin __init__/_build_ui paths run without error."""
    # Spot-check a representative attribute set up by each mixin.
    expected = [
        "_connect_action",       # UIBuildersMixin._build_actions
        "_table",                # UIBuildersMixin._build_main_layout
        "_console",              # UIBuildersMixin._build_main_layout
        "_tx_command_combo",     # TxPanelMixin._build_tx_tab
        "_tx_field_inputs",      # MainWindow.__init__
        "_plot_panels",          # MainWindow.__init__ (PlotOrch consumes)
        "_plot_history",         # MainWindow.__init__
        "_plot_palette",         # ThemingMixin._apply_plot_theme
        "_settings",             # MainWindow.__init__
        "_polling_list",         # UIBuildersMixin._build_left_panel
        "_led_label",            # UIBuildersMixin._build_ui (status bar)
        "_bitfield_table",       # UIBuildersMixin._build_bitfield_tab
        "_enum_table",           # UIBuildersMixin._build_enum_tab
        "_layout_combo",         # UIBuildersMixin._build_plot_tab
    ]
    missing = [attr for attr in expected if not hasattr(window, attr)]
    assert not missing, f"Missing attributes: {missing}"


def test_theming_mixin_methods(window: MainWindow) -> None:
    window._current_plot_palette()
    window._plot_crosshair_pen("dark")
    window._apply_plot_theme("light")
    window._apply_plot_theme("dark")


def test_theme_toggle_round_trip(window: MainWindow) -> None:
    """_apply_theme fans out to every theme-aware mixin — exercise both directions."""
    saved = str(window._settings.value("ui/theme", "dark"))
    other = "light" if saved == "dark" else "dark"
    window._apply_theme(other)
    window._apply_theme(saved)


def test_plot_orchestration_methods(window: MainWindow) -> None:
    window._redraw_plot()
    window._apply_plot_time_mode("elapsed", persist=False)
    window._apply_plot_time_mode("clock", persist=False)
    window._format_plot_time(42.5)
    window._plot_time_axis_label()
    window._curve_color_icon("#60A5FA")
    window._refresh_plot_indicators()
    window._read_saved_y_range(0)
    window._rebuild_plot_grid(2, 1)
    window._refresh_panel_strip_contents(0, QHBoxLayout())
    window._rebuild_panel_strips()


def test_detail_tabs_methods(window: MainWindow) -> None:
    window._populate_group_selector()
    assert window._row_visible_for_group(set(), "anything") is True
    window._apply_group_filter()
    window._apply_bitfield_group_filter()
    window._apply_enum_group_filter()


def test_tx_panel_methods(window: MainWindow) -> None:
    window._populate_tx_commands()
    window._rebuild_tx_fields()
    assert window._tx_values() == {}
    window._preview_tx_command()


def test_config_loader_helpers(window: MainWindow) -> None:
    assert isinstance(window._recent_paths(), list)
    window._populate_recent_selector()
    window._refresh_config_status()


def test_logging_session_apply_level(window: MainWindow) -> None:
    window._apply_logging_level("INFO")


def test_polling_session_helpers(window: MainWindow) -> None:
    window._populate_polling_list()
    window._update_poll_status_sidebar(set())


def test_popups_log_helper(window: MainWindow) -> None:
    # Doesn't open a dialog — just routes through _log_activity.
    window._log_popup("INFO", "smoke", "test")


def test_updater_methods_resolved(window: MainWindow) -> None:
    """Verify the updater methods are bound (don't call — would hit the network)."""
    for name in (
        "_on_check_updates",
        "_on_update_available",
        "_download_update",
        "_on_download_progress",
        "_on_download_finished",
    ):
        assert callable(getattr(window, name)), f"{name} not bound"


def test_load_canonical_config_end_to_end(window: MainWindow) -> None:
    """Exercise ConfigLoader -> table populate -> DetailTabs -> plot reset."""
    config_path = Path(__file__).resolve().parent / "fixtures" / "canonical_config"
    if not config_path.exists():
        pytest.skip(f"canonical config fixture not found: {config_path}")
    window._load_config_from_path(config_path)
    assert window._config is not None, "config did not load"
    assert window._parser is not None, "parser did not get created"
    # After load, the detail-tabs + plot path should be repopulated.
    window._populate_group_selector()
    window._apply_group_filter()
    window._redraw_plot()
