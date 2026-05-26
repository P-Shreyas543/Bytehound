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
    _is_time_like_param,
    _PARAM_COLORS,
)
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
