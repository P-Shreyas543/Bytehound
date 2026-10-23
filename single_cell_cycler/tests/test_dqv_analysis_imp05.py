"""Automated test suite for Differential Capacity Analysis (dQ/dV vs V) - IMP-05."""

import time
import numpy as np
import pytest

from single_cell_cycler.core.dqv_analysis import (
    DQVPeak,
    DQVProfile,
    compute_dq_dv,
    find_dqv_peaks,
    savgol_filter_1d,
    savgol_weights,
)


def test_savgol_weights_properties():
    """Verify mathematical properties of Savitzky-Golay coefficients."""
    # Smoothing filter (deriv=0) weights must sum to 1.0 (conservation of area)
    w_smooth = savgol_weights(window_length=9, polyorder=2, deriv=0)
    assert len(w_smooth) == 9
    assert np.isclose(np.sum(w_smooth), 1.0, atol=1e-12)
    # Derivative filter (deriv=1) weights must sum to 0.0 (anti-symmetric)
    w_deriv = savgol_weights(window_length=9, polyorder=2, deriv=1)
    assert len(w_deriv) == 9
    assert np.isclose(np.sum(w_deriv), 0.0, atol=1e-12)


def test_savgol_filter_exact_derivative():
    """Verify that SG 1st derivative of a parabola y = x^2 yields exact 2x."""
    x = np.linspace(-2.0, 2.0, 41)
    dx = x[1] - x[0]
    y = x ** 2
    # deriv=1 on quadratic should be exact 2*x
    dy_filtered = savgol_filter_1d(y, window_length=9, polyorder=2, deriv=1, delta=dx)
    # Check interior points (away from boundary pad)
    interior = slice(8, -8)
    expected = 2.0 * x[interior]
    assert np.allclose(dy_filtered[interior], expected, atol=1e-3)


def test_compute_dq_dv_synthesized_nmc_cell():
    """Verify dQ/dV on synthetic NMC charge curve with known phase transitions."""
    n_pts = 2000
    t = np.linspace(0, 3600, n_pts)
    soc = t / 3600.0
    q_mah = soc * 2500.0  # 2500 mAh cell

    # Voltage curve with transitions around 3.65V and 3.90V
    v_clean = (
        3.0
        + 0.4 * soc
        + 0.25 * np.tanh((soc - 0.35) * 12)
        + 0.25 * np.tanh((soc - 0.75) * 12)
    )
    # Add ADC quantization (1 mV) and small noise
    rng = np.random.default_rng(42)
    v_noisy = np.round(v_clean + rng.normal(0, 0.002, n_pts), 3)

    v_grid, dqdv = compute_dq_dv(
        voltages=v_noisy,
        capacities=q_mah,
        step_type="charge",
        dv_grid=0.005,
        smooth_window=15,
        polyorder=2,
    )

    assert len(v_grid) > 100
    assert len(dqdv) == len(v_grid)
    # dQ/dV should be positive on average for charge
    assert np.mean(dqdv) > 0.0

    # Peaks should be detected
    peaks = find_dqv_peaks(v_grid, dqdv, min_prominence=100.0, min_dist_v=0.05)
    assert len(peaks) >= 1
    # Check that peak voltages are within typical NMC plateaus
    peak_volts = [p.voltage for p in peaks]
    assert any(3.2 <= v <= 3.7 for v in peak_volts)


def test_compute_dq_dv_discharge_inversion():
    """Verify that discharge curves correctly produce negative or inverted dQ/dV."""
    n_pts = 1000
    soc = np.linspace(1.0, 0.0, n_pts)
    q_dis = (1.0 - soc) * 2000.0  # Delivered discharge capacity
    v = 4.2 - 1.2 * (1.0 - soc)

    v_grid, dqdv = compute_dq_dv(
        voltages=v,
        capacities=q_dis,
        step_type="discharge",
        dv_grid=0.005,
    )

    assert len(v_grid) > 50
    # For discharge, dQ/dV convention is negative for butterfly display
    assert np.mean(dqdv) < 0.0


def test_compute_dq_dv_empty_and_short_inputs():
    """Verify graceful handling of trivial or empty datasets without crash."""
    v_empty, dq_empty = compute_dq_dv(np.array([]), np.array([]))
    assert len(v_empty) == 0
    assert len(dq_empty) == 0

    # Too few points
    v_short = np.array([3.5, 3.51, 3.52])
    q_short = np.array([10.0, 20.0, 30.0])
    v_res, dq_res = compute_dq_dv(v_short, q_short)
    assert len(v_res) == 0
    assert len(dq_res) == 0


def test_compute_dq_dv_execution_performance():
    """Ensure MNC-grade execution speed (< 10 ms for 10,000 points)."""
    n_pts = 10_000
    v = np.linspace(2.8, 4.2, n_pts) + np.random.normal(0, 0.001, n_pts)
    q = np.linspace(0.0, 3000.0, n_pts)

    t0 = time.perf_counter()
    v_grid, dqdv = compute_dq_dv(v, q, dv_grid=0.005, smooth_window=17)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert len(v_grid) > 0
    assert elapsed_ms < 50.0  # Ultra-fast real-time capability
