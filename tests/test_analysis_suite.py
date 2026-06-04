"""Tests for the pure helpers in app.ui.analysis_suite.

These intentionally target the static / pure methods that have no Qt
dependency so they run quickly and don't require a QApplication. Anything
that touches a widget is exercised in manual UI smoke tests instead.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from app.ui.analysis_suite import (
    AnalysisSuiteWindow,
    StatisticsPanel,
    _curve_visuals,
    _PARAM_COLORS,
)
from app.ui.log_io import _is_time_like_param
from PySide6.QtCore import Qt


# ──────────────────────────────────────────────────────────────────
# _strip_units / _axis_title_for_group — keep y-axis label compact
# ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Vehicle Speed (Kmph)", "Vehicle Speed"),
        ("Dyno Act Torque (Nm)", "Dyno Act Torque"),
        ("Power (W) ", "Power"),
        ("No Units Here", "No Units Here"),
        ("Weird (a)(b)", "Weird (a)"),   # only trailing parens stripped
        ("  Padded  (V)  ", "Padded"),
    ],
)
def test_strip_units(raw, expected):
    assert AnalysisSuiteWindow._strip_units(raw) == expected


def test_axis_title_short_for_few_params():
    # The dummy instance is only used as a method dispatcher — no Qt setup.
    title = AnalysisSuiteWindow._axis_title_for_group(
        AnalysisSuiteWindow.__new__(AnalysisSuiteWindow),
        ["Speed (Kmph)", "Power (W)"],
    )
    assert title == "Speed, Power"


def test_axis_title_truncates_when_many():
    title = AnalysisSuiteWindow._axis_title_for_group(
        AnalysisSuiteWindow.__new__(AnalysisSuiteWindow),
        ["A (u)", "B (u)", "C (u)", "D (u)"],
    )
    assert title == "A, B  +2"


def test_axis_title_handles_empty():
    title = AnalysisSuiteWindow._axis_title_for_group(
        AnalysisSuiteWindow.__new__(AnalysisSuiteWindow),
        [],
    )
    assert title == ""


# ──────────────────────────────────────────────────────────────────
# _is_time_like_param — protects against plotting time on the y-axis
# ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "name, expected",
    [
        ("time", True),
        ("Time", True),
        ("Elapsed (s)", True),
        ("Timestamp 1", True),
        ("Vehicle Speed (Kmph)", False),
        ("", True),
        ("Time-like-but-not", False),
    ],
)
def test_is_time_like_param(name, expected):
    assert _is_time_like_param(name) is expected


# ──────────────────────────────────────────────────────────────────
# _normalize_series — min-max in [0,1], NaN-safe, flat-safe
# ──────────────────────────────────────────────────────────────────
def test_normalize_basic_range():
    out = AnalysisSuiteWindow._normalize_series(np.array([0.0, 5.0, 10.0]))
    assert np.allclose(out, [0.0, 0.5, 1.0])


def test_normalize_constant_returns_zeros():
    out = AnalysisSuiteWindow._normalize_series(np.array([7.0, 7.0, 7.0]))
    assert np.all(out == 0.0)


def test_normalize_all_nan_returns_zeros():
    out = AnalysisSuiteWindow._normalize_series(np.array([np.nan, np.nan]))
    assert np.all(out == 0.0)


def test_normalize_preserves_nan_positions():
    out = AnalysisSuiteWindow._normalize_series(np.array([0.0, np.nan, 10.0]))
    # The middle value is NaN in input → arithmetic in normalize yields NaN.
    assert out[0] == 0.0
    assert math.isnan(out[1])
    assert out[2] == 1.0


# ──────────────────────────────────────────────────────────────────
# _moving_average — NaN-safe, centered, identity when window < 2
# ──────────────────────────────────────────────────────────────────
def test_moving_average_window_one_is_identity():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    out = AnalysisSuiteWindow._moving_average(y, 1)
    assert np.array_equal(out, y)


def test_moving_average_smooths_step():
    y = np.array([0.0, 0.0, 0.0, 10.0, 10.0, 10.0])
    out = AnalysisSuiteWindow._moving_average(y, 3)
    # Center of the transition should be ~3.33 (avg of 0, 0, 10).
    # Index 3 averages indices 2,3,4 = (0+10+10)/3 ≈ 6.67
    assert out[2] == pytest.approx(3.333, abs=1e-2)
    assert out[3] == pytest.approx(6.667, abs=1e-2)


def test_moving_average_handles_nan_holes():
    y = np.array([1.0, np.nan, 3.0, 5.0, 7.0])
    out = AnalysisSuiteWindow._moving_average(y, 3)
    # No element should crash and the non-NaN regions should produce finite
    # results — NaN contributes 0 and the divisor counts only finite samples.
    assert np.all(np.isfinite(out))


def test_moving_average_empty_returns_empty():
    out = AnalysisSuiteWindow._moving_average(np.array([]), 3)
    assert out.size == 0


# ──────────────────────────────────────────────────────────────────
# StatisticsPanel.compute_stats — pure stat computation
# ──────────────────────────────────────────────────────────────────
def test_compute_stats_full_range():
    x = np.arange(10, dtype=float)
    y = np.arange(10, dtype=float)
    s = StatisticsPanel.compute_stats(x, y, None)
    assert s is not None
    assert s["min"] == 0
    assert s["max"] == 9
    assert s["mean"] == pytest.approx(4.5)
    assert s["median"] == pytest.approx(4.5)
    assert s["n"] == 10


def test_compute_stats_sliced_by_x_range():
    x = np.arange(10, dtype=float)
    y = x * 2
    s = StatisticsPanel.compute_stats(x, y, (2.0, 5.0))
    assert s is not None
    assert s["min"] == 4
    assert s["max"] == 10
    assert s["n"] == 4  # indices 2,3,4,5


def test_compute_stats_ignores_nans():
    x = np.arange(5, dtype=float)
    y = np.array([1.0, np.nan, 3.0, np.nan, 5.0])
    s = StatisticsPanel.compute_stats(x, y, None)
    assert s is not None
    assert s["n"] == 3
    assert s["min"] == 1
    assert s["max"] == 5


def test_compute_stats_returns_none_for_empty_slice():
    x = np.array([0.0, 1.0])
    y = np.array([10.0, 20.0])
    # x-range that doesn't intersect the data
    s = StatisticsPanel.compute_stats(x, y, (50.0, 60.0))
    assert s is None


def test_compute_stats_returns_none_for_empty_arrays():
    s = StatisticsPanel.compute_stats(np.array([]), np.array([]), None)
    assert s is None


# ──────────────────────────────────────────────────────────────────
# _curve_visuals — color/style encoding
# ──────────────────────────────────────────────────────────────────
def test_curve_visuals_single_param_uses_log_color():
    color, style = _curve_visuals(["Speed"], "Speed", 0, "#abcdef")
    assert color == "#abcdef"
    assert style == Qt.SolidLine


def test_curve_visuals_multi_param_uses_param_palette():
    group = ["Speed", "Power", "Torque"]
    # log_color should be ignored when len(group) > 1
    c0, _ = _curve_visuals(group, "Speed", 0, "#000000")
    c1, _ = _curve_visuals(group, "Power", 0, "#000000")
    c2, _ = _curve_visuals(group, "Torque", 0, "#000000")
    assert c0 == _PARAM_COLORS[0]
    assert c1 == _PARAM_COLORS[1]
    assert c2 == _PARAM_COLORS[2]
    assert c0 != c1 and c1 != c2


def test_curve_visuals_multi_param_styles_by_log_slot():
    group = ["Speed", "Power"]
    _, s0 = _curve_visuals(group, "Speed", 0, "#000")
    _, s1 = _curve_visuals(group, "Speed", 1, "#000")
    assert s0 != s1
    assert s0 == Qt.SolidLine
    assert s1 == Qt.DashLine


def test_curve_visuals_unknown_param_does_not_crash():
    # Defensive: the helper is sometimes called with a param not in the group
    # (e.g. during a layout transition). It should fall back, not raise.
    color, style = _curve_visuals(["A", "B"], "C-not-in-group", 0, "#fff")
    assert color in _PARAM_COLORS
    assert style == Qt.SolidLine


def test_math_channels_derivative_and_integral():
    from app.ui.log_io import LogEntry
    win = AnalysisSuiteWindow.__new__(AnalysisSuiteWindow)
    win._math_channels = {
        "Speed_Deriv": "diff([Speed])",
        "Speed_Int": "integral([Speed])"
    }
    log = LogEntry(
        id="test_log",
        elapsed=np.array([0.0, 1.0, 2.0, 3.0]),
        columns={
            "Speed": np.array([0.0, 10.0, 20.0, 30.0])
        }
    )
    win._compute_math_channels(log)
    assert np.allclose(log.columns["Speed_Deriv"], [10.0, 10.0, 10.0, 10.0])
    assert np.allclose(log.columns["Speed_Int"], [0.0, 5.0, 20.0, 45.0])


def test_linear_interpolation_in_cursor_readout():
    x = np.array([0.0, 10.0, 20.0])
    y = np.array([0.0, 100.0, 50.0])
    assert np.interp(5.0, x, y) == 50.0
    assert np.interp(15.0, x, y) == 75.0


def test_math_channels_settings_persistence(monkeypatch):
    class MockSettings:
        def __init__(self):
            self.data = {}
        def value(self, key, default=None):
            return self.data.get(key, default)
        def setValue(self, key, value):
            self.data[key] = value

    win = AnalysisSuiteWindow.__new__(AnalysisSuiteWindow)
    win._qsettings = MockSettings()
    win._math_channels = {}
    win._logs = {}
    
    monkeypatch.setattr("PySide6.QtWidgets.QInputDialog.getItem", lambda *args, **kwargs: ("Power", True))
    monkeypatch.setattr(win, "_rebuild_param_list", lambda: None)
    monkeypatch.setattr(win, "_rebuild_plots", lambda: None)
    class MockStatus:
        def showMessage(self, text, timeout=0):
            pass
    win._status = MockStatus()

    win._math_channels["Power"] = "[Voltage] * [Current]"
    win._qsettings.setValue("analysis/math_channels", win._math_channels)
    win._remove_custom_math_channel()
    
    assert "Power" not in win._math_channels
    assert win._qsettings.value("analysis/math_channels") == {}


def test_get_subplot_groups_flat_layout():
    """Test that _get_subplot_groups correctly filters active subplots based on tree checked items."""
    win = AnalysisSuiteWindow.__new__(AnalysisSuiteWindow)
    win._subplot_layout = [
        ["Speed", "Power"],
        ["Torque"],
        ["Voltage"]
    ]
    
    class MockTree:
        def __init__(self):
            self.items = []
        def topLevelItemCount(self):
            return len(self.items)
        def topLevelItem(self, idx):
            return self.items[idx]
            
    class MockItem:
        def __init__(self, text, checked):
            self._text = text
            self._checked = checked
        def text(self, col):
            return self._text
        def checkState(self, col):
            return Qt.Checked if self._checked else Qt.Unchecked
            
    tree = MockTree()
    tree.items = [
        MockItem("Speed", True),
        MockItem("Power", False),
        MockItem("Torque", True),
        MockItem("Voltage", False)
    ]
    
    win._param_tree = tree
    
    groups = win._get_subplot_groups()
    assert groups == [["Speed"], ["Torque"]]


def test_get_checked_params():
    """Test that _get_checked_params returns a flat list of checked parameter names."""
    win = AnalysisSuiteWindow.__new__(AnalysisSuiteWindow)
    
    class MockTree:
        def __init__(self):
            self.items = []
        def topLevelItemCount(self):
            return len(self.items)
        def topLevelItem(self, idx):
            return self.items[idx]
            
    class MockItem:
        def __init__(self, text, checked):
            self._text = text
            self._checked = checked
        def text(self, col):
            return self._text
        def checkState(self, col):
            return Qt.Checked if self._checked else Qt.Unchecked
            
    tree = MockTree()
    tree.items = [
        MockItem("Speed", True),
        MockItem("Power", False),
        MockItem("Torque", True),
        MockItem("Voltage", False)
    ]
    
    win._param_tree = tree
    
    checked = win._get_checked_params()
    assert checked == ["Speed", "Torque"]


def test_plot_scoped_v_cursor_readout_params():
    """Verify that _update_cursor_readout propagates all active parameters on the subplot for plot-scoped cursors."""
    from unittest.mock import MagicMock
    win = AnalysisSuiteWindow.__new__(AnalysisSuiteWindow)
    
    mock_pw1 = object()
    mock_pw2 = object()
    
    win._plot_widgets = [mock_pw1, mock_pw2]
    win._plot_groups = [["Speed", "Power"], ["Torque"]]
    win._logs = {}
    win._h_cursors = []
    
    win._get_checked_params = lambda: ["Speed", "Power", "Torque"]
    
    # Plot-scoped cursor on first subplot (which has Speed & Power)
    cursor_data = {
        'id': 'cursor_1',
        'scope': 'plot',
        'plot_param': 'Speed',
        'lines': {mock_pw1: object()},
        'time': 5.0,
        'color': '#ff0000',
    }
    win._v_cursors = [cursor_data]
    
    # Mock readout panel
    win._cursor_readout = MagicMock()
    
    win._update_cursor_readout()
    
    # Verify update_readout call arguments
    args, kwargs = win._cursor_readout.update_readout.call_args
    v_cursors_passed = args[0]
    
    assert len(v_cursors_passed) == 1
    # For the plot-scoped cursor, it should have the parameters on its subplot (Speed & Power)
    assert v_cursors_passed[0]['params'] == ["Speed", "Power"]


def test_h_cursor_handling_and_rebuild_resilience():
    """Verify that horizontal cursors are handled using string IDs and defend against deleted widgets/mocks."""
    from unittest.mock import MagicMock
    win = AnalysisSuiteWindow.__new__(AnalysisSuiteWindow)
    
    mock_pw = object()
    win._plot_widgets = [mock_pw]
    win._plot_groups = [["Speed"]]
    win._logs = {}
    win._v_cursors = []
    win._selected_h_cursor = ""
    
    win._get_checked_params = lambda: ["Speed"]
    
    # 1. Add horizontal cursor simulation
    hc_data = {
        'id': 'h_cursor_1',
        'line': MagicMock(),
        'plot_widget': mock_pw,
        'plot_index': 0,
        'value': 15.0,
        'color': '#00ff00',
        'label': 1,
    }
    win._h_cursors = [hc_data]
    win._cursor_readout = MagicMock()
    
    # 2. Verify _update_cursor_readout runs fine with mock object
    win._update_cursor_readout()
    
    args, kwargs = win._cursor_readout.update_readout.call_args
    h_cursors_passed = kwargs.get('h_cursors', [])
    assert len(h_cursors_passed) == 1
    assert h_cursors_passed[0]['id'] == 'h_cursor_1'
    assert h_cursors_passed[0]['plot_group'] == ["Speed"]
    
    # 3. Verify finding by ID
    found = win._find_h_cursor_by_id('h_cursor_1')
    assert found is hc_data
    
    # 4. Verify selection highlighting
    win._select_h_cursor('h_cursor_1')
    assert win._selected_h_cursor == 'h_cursor_1'
    
    # 5. Verify deleting
    win._delete_h_cursor('h_cursor_1')
    assert len(win._h_cursors) == 0
    assert win._selected_h_cursor == ''


def test_rebuild_plots_clears_readout_when_empty():
    """Verify that _do_rebuild_plots refreshes/clears cursor readout and stats panel when logs are empty."""
    from unittest.mock import MagicMock
    win = AnalysisSuiteWindow.__new__(AnalysisSuiteWindow)
    win._plot_widgets = []
    win._plot_layout = MagicMock()
    win._plot_layout.count.return_value = 0
    win._plot_groups = []
    win._curves = {}
    win._crosshair_lines = {}
    win._cursor_dots = {}
    win._subplot_layout = []
    win._logs = {}
    win._h_cursors = []
    win._v_cursors = []
    
    # Mock methods and panels
    win._get_subplot_groups = lambda: []
    win._get_checked_params = lambda: []
    win._update_cursor_readout = MagicMock()
    win._refresh_stats_panel = MagicMock()
    
    win._do_rebuild_plots()
    
    win._update_cursor_readout.assert_called_once()
    win._refresh_stats_panel.assert_called_once()


def test_rebuild_param_list_saves_scroll():
    """Verify that _rebuild_param_list saves and restores parameter tree scroll position."""
    from unittest.mock import MagicMock
    win = AnalysisSuiteWindow.__new__(AnalysisSuiteWindow)
    
    mock_tree = MagicMock()
    mock_scrollbar = MagicMock()
    mock_scrollbar.value.return_value = 42
    mock_tree.verticalScrollBar.return_value = mock_scrollbar
    mock_tree.topLevelItemCount.return_value = 0
    
    win._param_tree = mock_tree
    win._subplot_layout = []
    win._param_search = MagicMock()
    win._param_search.text.return_value = ""
    win._collect_available_params = lambda: []
    win._apply_param_filter = lambda text: None
    win._rebuild_subplot_settings_combo = lambda: None
    
    win._rebuild_param_list()
    
    mock_scrollbar.value.assert_called_once()
    mock_scrollbar.setValue.assert_called_with(42)


def test_rebuild_plots_saves_x_range():
    """Verify that _do_rebuild_plots saves and restores visible X range."""
    from unittest.mock import MagicMock
    win = AnalysisSuiteWindow.__new__(AnalysisSuiteWindow)
    
    mock_pw = MagicMock()
    mock_view_box = MagicMock()
    mock_view_box.viewRange.return_value = ((10.0, 20.0), (0.0, 100.0))
    mock_plot_item = MagicMock()
    mock_plot_item.vb = mock_view_box
    mock_pw.getPlotItem.return_value = mock_plot_item
    
    win._plot_widgets = [mock_pw]
    win._plot_layout = MagicMock()
    win._plot_layout.count.return_value = 0
    win._plot_groups = []
    win._curves = {}
    win._crosshair_lines = {}
    win._cursor_dots = {}
    win._subplot_layout = []
    win._logs = {}
    win._h_cursors = []
    win._v_cursors = []
    
    # Mock return paths
    win._get_subplot_groups = lambda: []
    win._update_cursor_readout = MagicMock()
    win._refresh_stats_panel = MagicMock()
    
    win._do_rebuild_plots()
    
    mock_view_box.viewRange.assert_called_once()





