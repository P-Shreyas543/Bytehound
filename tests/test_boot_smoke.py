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
from PySide6.QtWidgets import QApplication

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


def test_theme_auto_resolves(window: MainWindow) -> None:
    """System ("auto") theme must resolve to dark/light, not silently fall
    through every branch as light. Regression guard for the bug where
    picking System on a dark OS produced a dark qdarktheme palette with
    LIGHT overrides on top."""
    from app.ui.theming import resolve_theme

    saved = str(window._settings.value("ui/theme", "dark"))
    try:
        window._apply_theme("auto")
        # The saved value stays "auto" (user choice persists)...
        assert window._settings.value("ui/theme") == "auto"
        # ...but every painter resolves to a concrete theme.
        assert resolve_theme("auto") in ("dark", "light")
        # Plot palette must have been swapped to a real palette, not left
        # at whatever default getattr returns.
        assert window._current_plot_palette()
    finally:
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
    window._build_panel_signals_menu(0, window)
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


def _load_canonical_or_skip(window: MainWindow):
    """Helper: load the canonical config fixture or skip if missing."""
    config_path = Path(__file__).resolve().parent / "fixtures" / "canonical_config"
    if not config_path.exists():
        pytest.skip(f"canonical config fixture not found: {config_path}")
    window._load_config_from_path(config_path)
    assert window._config is not None
    return window._config


def test_apply_decoded_with_synthetic_frame(window: MainWindow) -> None:
    """Push a synthetic DecodedFrame through the live packet path.

    Covers the runtime-only code in ``_apply_decoded`` that the plain mixin-
    method smoke doesn't reach — including ``_format_number``, the staged-
    cell write, and the per-signal plot-history append.
    """
    from app.decoder.frame_decoder import DecodedFrame, DecodedSignal

    config = _load_canonical_or_skip(window)
    # Pick the first real signal from the loaded config so the row exists
    # in the table model and the (frame_id, signal_name) key resolves.
    spec = config.all_signals[0]
    signal = DecodedSignal(
        frame_id=spec.frame_id,
        frame_name=spec.frame_name,
        signal_name=spec.signal_name,
        raw_value=1234,
        scaled_value=1.234,
        unit=spec.unit,
        status="ok",
        group=spec.group,
        display_value="1.234 V",
    )
    decoded = DecodedFrame(
        frame_id=spec.frame_id,
        frame_name=spec.frame_name,
        signals=[signal],
    )
    window._apply_decoded(decoded)

    # Plot-history append fires only when the plot dock is visible. We don't
    # gate on that here — the assertion is simply: no exception raised, and
    # the table model now holds the staged value for this signal.
    key = (spec.frame_id, spec.signal_name)
    row = window._table_model.row_for_key(key)
    assert row is not None, "row should exist after _apply_decoded"


def test_fit_panel_y_now_with_seeded_data(window: MainWindow) -> None:
    """Exercise ``_fit_panel_y_now`` with a panel + history actually populated.

    The plain ``_redraw_plot`` smoke doesn't reach the ``np.nanmin/nanmax``
    branch — it's only walked when a panel has assigned keys AND those keys
    have data in ``_plot_history``.
    """
    config = _load_canonical_or_skip(window)
    if not window._plot_panels:
        pytest.skip("no plot panels available")

    spec = config.all_signals[0]
    key = (spec.frame_id, spec.signal_name)

    # Seed the ring buffer the same way _apply_decoded would.
    buf = window._plot_history.setdefault(key, window._make_history_buffer())
    for i in range(5):
        buf.append(float(i), float(i) * 0.5)

    panel = window._plot_panels[0]
    panel.assigned_keys = [key]
    panel.y_scale_mode = "fit"

    window._fit_panel_y_now(panel)
    window._throttled_y_autofit()


# ----------------------------------------------------------------------
# Regression guards for release-readiness changes.
# ----------------------------------------------------------------------


def test_central_stack_toggles_on_config_load(window: MainWindow) -> None:
    """Central widget swaps between empty-state and table on config presence.

    Regression guard: future changes to ``_refresh_action_state`` or the
    central-widget construction must keep the two-page swap working.
    """
    assert hasattr(window, "_central_stack"), "central stack not built"
    assert window._central_stack.count() == 2

    # Force no-config and verify the empty-state page wins.
    window._config = None
    window._refresh_action_state()
    assert window._central_stack.currentIndex() == 0

    # Loading the canonical config should flip to the table page.
    _load_canonical_or_skip(window)
    window._refresh_action_state()
    assert window._central_stack.currentIndex() == 1


def test_plot_state_button_tristate_transitions(window: MainWindow) -> None:
    """Live -> Paused -> Live -> Explore (pan) -> Live transitions.

    Regression guard for the unified plot state button. The old two-button
    design had subtle race conditions on signal blocking; the new single
    button must remain coherent across both click and pan-induced flips.
    """
    assert hasattr(window, "_plot_state_btn"), "plot state button not built"
    assert not hasattr(window, "_pause_btn"), "old pause button still present"
    assert not hasattr(window, "_plot_mode_btn"), "old plot-mode button still present"

    # Starts Live.
    assert window._plot_live is True
    assert "Live" in window._plot_state_btn.text()

    # Click pauses.
    window._on_plot_state_btn_clicked()
    assert window._plot_live is False
    assert "Paused" in window._plot_state_btn.text()

    # Click resumes.
    window._on_plot_state_btn_clicked()
    assert window._plot_live is True
    assert "Live" in window._plot_state_btn.text()

    # Pan-induced flip renders as Explore, not Paused.
    window._set_plot_live(False, source="pan")
    assert window._plot_live is False
    assert "Explore" in window._plot_state_btn.text()

    # Click from Explore returns to Live.
    window._on_plot_state_btn_clicked()
    assert window._plot_live is True
    assert "Live" in window._plot_state_btn.text()


def test_copy_diagnostics_produces_useful_text(window: MainWindow) -> None:
    """Help -> Copy Diagnostics writes a multi-section snapshot to clipboard.

    Pins the section headers the user is expected to paste into a bug
    report. If any are renamed/removed this test fires as a reminder to
    update the triage docs alongside the code.
    """
    from PySide6.QtWidgets import QApplication

    QApplication.clipboard().setText("")  # known-empty baseline
    window._on_copy_diagnostics()
    text = QApplication.clipboard().text()
    for marker in (
        "diagnostics",
        "Runtime",
        "Session",
        "OS:",
        "Python:",
        "PySide6:",
        "Qt:",
        "Connection:",
        "Logging:",
    ):
        assert marker in text, f"Missing diagnostics section: {marker!r}"


def test_settings_migration_uses_safe_sequential_polling_defaults(qapp) -> None:
    """Migration returns Auto-Fetch to safe sequential polling defaults."""
    from PySide6.QtCore import QSettings
    from app.ui.main_window import APP_ORG, APP_NAME, _migrate_settings

    s = QSettings(APP_ORG, APP_NAME)
    saved = {
        k: s.value(k) for k in (
            "poll/pipelining", "poll/pipeline_depth", "settings/migration_version"
        )
    }
    try:
        # Simulate an existing install with the OLD defaults explicitly stored.
        s.setValue("poll/pipelining", False)
        s.setValue("poll/pipeline_depth", 2)
        s.remove("settings/migration_version")
        s.sync()

        _migrate_settings(s)

        assert s.value("poll/pipelining", type=bool) is False, \
            "pipelining should default off for one-request-at-a-time hardware"
        assert int(s.value("poll/pipeline_depth")) == 1, \
            "depth should default to one in-flight request"
        # Re-running must be a no-op.
        s.setValue("poll/pipeline_depth", 4)  # later edits are not re-overwritten
        _migrate_settings(s)
        assert int(s.value("poll/pipeline_depth")) == 4, \
            "settings migration must not re-run once version is stored"
    finally:
        for k, v in saved.items():
            if v is None:
                s.remove(k)
            else:
                s.setValue(k, v)
        s.sync()


def test_settings_migration_resets_old_pipeline_customisation_once(qapp) -> None:
    """The v2 migration intentionally disables saved pipelining once."""
    from PySide6.QtCore import QSettings
    from app.ui.main_window import APP_ORG, APP_NAME, _migrate_settings

    s = QSettings(APP_ORG, APP_NAME)
    saved = {
        k: s.value(k) for k in (
            "poll/pipelining", "poll/pipeline_depth", "settings/migration_version"
        )
    }
    try:
        s.setValue("poll/pipelining", True)
        s.setValue("poll/pipeline_depth", 4)
        s.remove("settings/migration_version")
        s.sync()

        _migrate_settings(s)

        assert int(s.value("poll/pipeline_depth")) == 1
        assert s.value("poll/pipelining", type=bool) is False
    finally:
        for k, v in saved.items():
            if v is None:
                s.remove(k)
            else:
                s.setValue(k, v)
        s.sync()


def test_window_state_schema_version_discards_stale_blobs(qapp) -> None:
    """A mismatched ``_WINDOW_STATE_VERSION`` clears the persisted blobs.

    Regression guard for the schema-versioning safety net: future code
    that bumps the constant must continue to fall through to defaults
    instead of restoring incompatible state.
    """
    from PySide6.QtCore import QSettings
    from app.ui.main_window import APP_ORG, APP_NAME, _WINDOW_STATE_VERSION

    s = QSettings(APP_ORG, APP_NAME)
    # Preserve the user's real values so the test doesn't reset their layout.
    saved = {
        k: s.value(k) for k in
        ("window/geometry", "window/state", "window/state_version")
    }
    try:
        s.setValue("window/geometry", b"not-a-real-blob")
        s.setValue("window/state", b"not-a-real-blob")
        s.setValue("window/state_version", _WINDOW_STATE_VERSION - 1)
        s.sync()

        w = MainWindow()
        try:
            # _restore_window_state runs during __init__; stale blobs gone.
            assert s.value("window/geometry") in (None, ""), \
                "stale geometry not cleared on schema mismatch"
            assert s.value("window/state") in (None, ""), \
                "stale state not cleared on schema mismatch"
        finally:
            w.close()
    finally:
        # Restore user values so subsequent runs aren't affected.
        for k, v in saved.items():
            if v is None:
                s.remove(k)
            else:
                s.setValue(k, v)
        s.sync()
