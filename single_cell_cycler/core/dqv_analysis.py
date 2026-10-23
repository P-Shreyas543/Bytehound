"""Electrochemical Differential Capacity Analysis (dQ/dV vs V) engine.

Provides high-performance, pure-NumPy numerical differentiation and Savitzky-Golay
filtering for non-destructive battery degradation tracking, phase transition analysis,
and peak detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class DQVPeak:
    """Detected peak in dQ/dV curve corresponding to an electrochemical phase transition."""
    voltage: float           # Voltage at peak maximum (V)
    dq_dv: float             # Differential capacity value (mAh/V)
    prominence: float        # Relative peak height above surrounding baseline
    label: str = ""          # Optional phase transition descriptor (e.g. "Phase I")


@dataclass
class DQVProfile:
    """Processed differential capacity curve for a specific charge or discharge step."""
    cycle_index: int
    step_index: int
    step_type: str                         # "charge" or "discharge"
    voltages: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    dq_dv: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    capacities: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    peaks: List[DQVPeak] = field(default_factory=list)


def savgol_weights(window_length: int, polyorder: int, deriv: int = 0) -> np.ndarray:
    """Compute Savitzky-Golay convolution filter coefficients using pure NumPy."""
    if window_length % 2 == 0:
        window_length += 1
    half_window = window_length // 2
    x = np.arange(-half_window, half_window + 1, dtype=float)
    order_arr = np.arange(polyorder + 1)
    # Vandermonde matrix A of powers
    a_mat = x[:, None] ** order_arr[None, :]
    # Moore-Penrose pseudo-inverse
    pinv = np.linalg.pinv(a_mat)
    # Filter coefficients for specified derivative order
    weights = pinv[deriv] * math.factorial(deriv)
    return weights


def savgol_filter_1d(
    y: np.ndarray,
    window_length: int,
    polyorder: int,
    deriv: int = 0,
    delta: float = 1.0,
) -> np.ndarray:
    """Apply 1D Savitzky-Golay smoothing or differentiation filter."""
    if len(y) == 0:
        return np.array([], dtype=float)

    if window_length % 2 == 0:
        window_length += 1
    if window_length > len(y):
        window_length = len(y) if len(y) % 2 != 0 else len(y) - 1

    if window_length <= polyorder:
        if deriv == 1 and len(y) > 1:
            return np.gradient(y, delta)
        return y.copy()

    weights = savgol_weights(window_length, polyorder, deriv=deriv)
    pad = window_length // 2
    y_padded = np.pad(y, pad, mode="edge")
    filtered = np.convolve(y_padded, weights[::-1], mode="valid")

    if deriv > 0:
        filtered = filtered / (delta ** deriv)
    return filtered


def compute_dq_dv(
    voltages: np.ndarray,
    capacities: np.ndarray,
    step_type: str = "charge",
    dv_grid: float = 0.005,
    smooth_window: int = 15,
    polyorder: int = 2,
    return_capacity: bool = False,
) -> Tuple[np.ndarray, ...]:
    """Resample Q(V) onto a uniform voltage grid and compute smoothed dQ/dV.

    Parameters:
    -----------
    voltages : np.ndarray
        Raw measured cell voltages (V) during the step.
    capacities : np.ndarray
        Raw measured cumulative step capacity (mAh).
    step_type : str
        "charge" or "discharge". For discharge, dQ/dV can be negative or inverted.
    dv_grid : float
        Uniform voltage grid spacing in Volts (default: 0.005 V = 5 mV).
    smooth_window : int
        Window length for Savitzky-Golay polynomial derivative filter (must be odd).
    polyorder : int
        Polynomial degree for local fitting (default: 2 = quadratic).
    return_capacity : bool
        If True, also returns the resampled capacity array (v_grid, dq_dv, q_grid).

    Returns:
    --------
    Tuple[np.ndarray, np.ndarray] or Tuple[np.ndarray, np.ndarray, np.ndarray]
        (v_grid, dq_dv) or (v_grid, dq_dv, q_grid)
    """
    v_arr = np.asarray(voltages, dtype=float)
    q_arr = np.asarray(capacities, dtype=float)

    mask = np.isfinite(v_arr) & np.isfinite(q_arr)
    v_valid = v_arr[mask]
    q_valid = q_arr[mask]

    if len(v_valid) < 15:
        if return_capacity:
            return np.array([], dtype=float), np.array([], dtype=float), np.array([], dtype=float)
        return np.array([], dtype=float), np.array([], dtype=float)

    # Sort strictly by voltage to guarantee well-defined resampling
    sort_idx = np.argsort(v_valid)
    v_sorted = v_valid[sort_idx]
    q_sorted = q_valid[sort_idx]

    # Deduplicate voltages by averaging capacities at identical ADC voltage steps
    v_unique, indices = np.unique(v_sorted, return_inverse=True)
    counts = np.bincount(indices)
    q_sums = np.bincount(indices, weights=q_sorted)
    q_unique = q_sums / counts

    v_min, v_max = float(v_unique[0]), float(v_unique[-1])
    span = v_max - v_min
    if span < (dv_grid * 3.0):
        # Insufficient voltage variation during this step
        if return_capacity:
            return np.array([], dtype=float), np.array([], dtype=float), np.array([], dtype=float)
        return np.array([], dtype=float), np.array([], dtype=float)

    # Construct uniform voltage grid
    v_grid = np.arange(v_min + (dv_grid / 2.0), v_max, dv_grid, dtype=float)
    if len(v_grid) < 5:
        if return_capacity:
            return np.array([], dtype=float), np.array([], dtype=float), np.array([], dtype=float)
        return np.array([], dtype=float), np.array([], dtype=float)

    # Resample Q onto uniform V grid
    q_grid = np.interp(v_grid, v_unique, q_unique)

    # Differentiate Q with respect to V using Savitzky-Golay 1st derivative filter
    dq_dv = savgol_filter_1d(
        q_grid,
        window_length=smooth_window,
        polyorder=polyorder,
        deriv=1,
        delta=dv_grid,
    )

    # For discharge steps: capacity increases as voltage drops.
    # When sorted by increasing voltage, Q decreases, giving negative dq_dv.
    # Battery convention: if step_type is discharge, we can either retain negative or take abs.
    # In standard differential capacity analysis, charge is positive, discharge is negative
    # (butterfly plot) or both positive.
    is_discharge = "discharge" in step_type.lower()
    if is_discharge and np.mean(dq_dv) > 0:
        # If Q was already monotonic in the reverse direction, invert so discharge stays negative
        dq_dv = -dq_dv

    if return_capacity:
        return v_grid, dq_dv, q_grid
    return v_grid, dq_dv


def find_dqv_peaks(
    v_grid: np.ndarray,
    dqdv: np.ndarray,
    min_prominence: float = 50.0,
    min_dist_v: float = 0.04,
) -> List[DQVPeak]:
    """Detect local peak maxima in dQ/dV curves corresponding to phase transitions."""
    if len(v_grid) < 5 or len(dqdv) < 5:
        return []

    # Use absolute values for peak detection so both charge (+ peaks) and discharge (- peaks) are found
    abs_y = np.abs(dqdv)
    peaks: List[DQVPeak] = []

    # Find internal local maxima: y[i-1] < y[i] > y[i+1]
    for i in range(1, len(abs_y) - 1):
        if abs_y[i] > abs_y[i - 1] and abs_y[i] >= abs_y[i + 1]:
            val = abs_y[i]
            if val < min_prominence:
                continue

            # Estimate local baseline (minimum in a +/- 50 mV window)
            v_curr = v_grid[i]
            window_mask = np.abs(v_grid - v_curr) <= 0.06
            local_baseline = float(np.min(abs_y[window_mask]))
            prominence = val - local_baseline

            if prominence >= (min_prominence * 0.4):
                peaks.append(
                    DQVPeak(
                        voltage=round(float(v_curr), 3),
                        dq_dv=round(float(dqdv[i]), 1),
                        prominence=round(prominence, 1),
                    )
                )

    # Filter closely clustered peaks (enforce min_dist_v)
    if not peaks:
        return []

    # Sort by prominence descending
    peaks.sort(key=lambda p: p.prominence, reverse=True)
    filtered_peaks: List[DQVPeak] = []

    for candidate in peaks:
        is_isolated = all(
            abs(candidate.voltage - existing.voltage) >= min_dist_v
            for existing in filtered_peaks
        )
        if is_isolated:
            filtered_peaks.append(candidate)
            if len(filtered_peaks) >= 5:  # Cap at top 5 most prominent phase transitions
                break

    # Sort back by voltage ascending for logical display
    filtered_peaks.sort(key=lambda p: p.voltage)
    for idx, pk in enumerate(filtered_peaks, 1):
        pk.label = f"Peak {idx}: {pk.voltage:.2f}V"

    return filtered_peaks
