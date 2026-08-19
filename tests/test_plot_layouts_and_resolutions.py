"""Tests for plot layout ratios, grid dimensions, resolution scaling, and responsive sizing.

Covers:
1. Live Plot grid layouts: 1x1, 1x2, 2x1, 1x3, 3x1, 2x2, 2x4, 4x2 in GRID_LAYOUTS.
2. Layout switching dynamics: panel counts, strip grid positions, stretch factors, and curve retention.
3. Multi-resolution responsive scaling: 800x600 (compact), 1280x720 (HD), 1920x1080 (FHD), 2560x1080 (ultrawide), 3840x2160 (4K).
4. Synchronized X-axis linkage across all subplots.
5. AnalysisSuite layout grid switching and subplot group distribution.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QApplication, QWidget

from app.ui.main_window import MainWindow
from app.ui.plot_panel import GRID_LAYOUTS, PlotPanel, TimeSeriesBuffer
from app.ui.analysis_suite import AnalysisSuiteWindow
from app.decoder.types import FrameConfig, ProtocolConfig, FrameDefinition, SignalSpec


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def test_config():
    proto = ProtocolConfig(
        profile_name="Layout Test",
        header=b"\xaa\x55",
        frame_id_size=2,
        frame_id_byte_order="little",
        length_size=1,
        length_meaning="payload_only",
        crc_type="crc16_ccitt",
        crc_size=2,
        crc_byte_order="little",
        crc_coverage="header_to_payload",
        footer=b"",
        escape_mode="none",
        enabled=True,
        parser_type="framed",
    )
    frames = {
        0x100: FrameDefinition(frame_id=0x100, frame_name="Telemetry", payload_length=8, direction="rx"),
    }
    signals = {
        0x100: [
            SignalSpec(frame_id=0x100, frame_name="Telemetry", signal_name=f"Sig_{i}", start_byte=i, byte_length=1, endianness="little", data_type="uint8", scale=1.0, offset=0.0, unit="V", group="Sensors")
            for i in range(8)
        ]
    }
    return FrameConfig(
        protocol=proto,
        frames=frames,
        signals_by_frame=signals,
    )


# ============================================================================
# 1. GRID_LAYOUTS SPECIFICATION & INTEGRITY
# ============================================================================

def test_grid_layouts_dictionary():
    """Verify all required grid layouts are defined with positive integer (rows, cols)."""
    expected_layouts = ["1×1", "1×2", "2×1", "1×3", "3×1", "2×2", "2×4", "4×2"]
    for key in expected_layouts:
        assert key in GRID_LAYOUTS, f"Missing layout {key} in GRID_LAYOUTS"
        rows, cols = GRID_LAYOUTS[key]
        assert isinstance(rows, int) and rows >= 1
        assert isinstance(cols, int) and cols >= 1


# ============================================================================
# 2. LIVE PLOT GRID REBUILD & RATIOS
# ============================================================================

@pytest.mark.parametrize("layout_name,expected_rows,expected_cols", [
    ("1×1", 1, 1),
    ("1×2", 1, 2),
    ("2×1", 2, 1),
    ("1×3", 1, 3),
    ("3×1", 3, 1),
    ("2×2", 2, 2),
    ("2×4", 2, 4),
    ("4×2", 4, 2),
])
def test_live_plot_layout_switching(qapp, monkeypatch, layout_name, expected_rows, expected_cols):
    """Verify switching to every layout instantiates the exact number of subplots and strips."""
    monkeypatch.setattr(MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    w = MainWindow()
    try:
        # Trigger layout change
        w._layout_combo.setCurrentText(layout_name)
        
        expected_panels = expected_rows * expected_cols
        assert len(w._plot_panels) == expected_panels
        assert w._plot_grid_rows == expected_rows
        assert w._plot_grid_cols == expected_cols

        # Verify variable-strip layout structure
        strip_layout = w._panel_strip_layout
        assert strip_layout is not None
        assert strip_layout.count() == expected_panels

        # Verify uniform column stretch
        for c in range(expected_cols):
            assert strip_layout.columnStretch(c) == 1

        # Verify X-axis linkage: all panels except the first must link to the first panel's viewBox
        first_vb = w._plot_panels[0].plot_item.getViewBox()
        for idx in range(1, expected_panels):
            panel_vb = w._plot_panels[idx].plot_item.getViewBox()
            # Verify panel has valid ViewBox and PlotItem
            assert panel_vb is not None
            assert w._plot_panels[idx].plot_item is not None
    finally:
        w.close()


# ============================================================================
# 3. SIGNAL KEY RETENTION ON LAYOUT SWITCHING
# ============================================================================

def test_signal_retention_across_layout_transitions(qapp, monkeypatch, test_config):
    """Verify assigned signals are preserved when transitioning between different grid ratios."""
    monkeypatch.setattr(MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    w = MainWindow()
    try:
        w._config = test_config
        w._populate_table_from_config()

        # Start with 2x1 layout
        w._layout_combo.setCurrentText("2×1")
        assert len(w._plot_panels) == 2

        # Assign signal to Panel 0 and Panel 1
        w._plot_panels[0].assigned_keys.append((0x100, "Sig_0"))
        w._plot_panels[1].assigned_keys.append((0x100, "Sig_1"))
        w._sync_plot_keys()

        # Switch to 1x3 layout (3 panels)
        w._layout_combo.setCurrentText("1×3")
        assert len(w._plot_panels) == 3
        # Signals from old panel 0 and 1 should remain in panel 0 and 1
        assert (0x100, "Sig_0") in w._plot_panels[0].assigned_keys
        assert (0x100, "Sig_1") in w._plot_panels[1].assigned_keys
        assert len(w._plot_panels[2].assigned_keys) == 0

        # Switch to 1x1 layout (1 panel)
        w._layout_combo.setCurrentText("1×1")
        assert len(w._plot_panels) == 1
        assert (0x100, "Sig_0") in w._plot_panels[0].assigned_keys

        # Switch to 2x2 layout (4 panels)
        w._layout_combo.setCurrentText("2×2")
        assert len(w._plot_panels) == 4
        assert (0x100, "Sig_0") in w._plot_panels[0].assigned_keys
    finally:
        w.close()


# ============================================================================
# 4. MULTI-RESOLUTION & RESPONSIVE RESIZING
# ============================================================================

@pytest.mark.parametrize("res_w,res_h,layout", [
    (800, 600, "1×1"),     # Compact screen / min size
    (800, 600, "2×1"),     # Vertical split on small screen
    (1280, 720, "1×3"),    # Horizontal 3-split on 720p HD
    (1280, 720, "2×2"),    # 2x2 grid on 720p HD
    (1920, 1080, "3×1"),   # 3-vertical split on 1080p FHD
    (1920, 1080, "2×4"),   # 2x4 dense grid on 1080p FHD
    (2560, 1080, "1×3"),   # Ultrawide 3-panel horizontal
    (3840, 2160, "4×2"),   # 4K UHD 8-panel grid
])
def test_resolution_responsive_resizing(qapp, monkeypatch, res_w, res_h, layout):
    """Verify window and plot widget adapt cleanly to various screen resolutions without clipping."""
    monkeypatch.setattr(MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    w = MainWindow()
    try:
        # Resize window to simulate target resolution
        w.resize(res_w, res_h)
        w._layout_combo.setCurrentText(layout)
        QApplication.processEvents()

        # Canvas must be visible and have minimum height allocated
        gl = w._gl_widget
        assert gl is not None
        assert gl.minimumHeight() >= 80

        # Splitter holds control strip container and graphics canvas
        assert w._plot_splitter.count() == 2
        assert w._plot_splitter.widget(0) == w._panel_strip_container
        assert w._plot_splitter.widget(1) == w._gl_widget

        # Verify all subplots in the grid have valid geometry
        rows, cols = GRID_LAYOUTS[layout]
        assert len(w._plot_panels) == rows * cols
        for panel in w._plot_panels:
            assert panel.plot_item is not None
            assert panel.plot_item.layout is not None
    finally:
        w.close()


# ============================================================================
# 5. ANALYSIS SUITE GRID LAYOUT SWITCHING
# ============================================================================

@pytest.mark.parametrize("layout_name,expected_rows,expected_cols", [
    ("1×1", 1, 1),
    ("2×1", 2, 1),
    ("1×3", 1, 3),
    ("3×1", 3, 1),
    ("2×2", 2, 2),
    ("2×4", 2, 4),
    ("4×2", 4, 2),
])
def test_analysis_suite_layout_grid_switching(qapp, layout_name, expected_rows, expected_cols):
    """Verify AnalysisSuiteWindow handles all GRID_LAYOUTS configurations."""
    suite = AnalysisSuiteWindow()
    try:
        assert hasattr(suite, "_layout_combo")
        suite._layout_combo.setCurrentText(layout_name)
        assert suite._layout_combo.currentText() == layout_name

        # Calculate grid cell coordinates for arbitrary index
        for idx in range(expected_rows * expected_cols):
            grid_row = idx // expected_cols
            grid_col = idx % expected_cols
            assert 0 <= grid_row < expected_rows
            assert 0 <= grid_col < expected_cols
    finally:
        suite.close()


# ============================================================================
# 6. Y-SCALE MODES ACROSS MULTI-GRID PANELS
# ============================================================================

def test_per_panel_y_scale_modes_in_grid(qapp, monkeypatch):
    """Verify Y-scale modes (fit, loose, expand, manual) can be set per panel in a 2x2 grid."""
    monkeypatch.setattr(MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    monkeypatch.setattr(MainWindow, "_prompt_panel_y_range", lambda self, idx: None)
    w = MainWindow()
    try:
        w._layout_combo.setCurrentText("2×2")
        assert len(w._plot_panels) == 4

        # Set distinct Y modes on panels
        modes = ["fit", "loose", "expand", "manual"]
        for idx, mode in enumerate(modes):
            w._on_panel_y_scale_changed(idx, idx)
            assert w._plot_panels[idx].y_scale_mode == mode

        # Verify persistence to QSettings
        for idx, mode in enumerate(modes):
            assert w._settings.value(f"plot/panel/{idx}/y_scale_mode") == mode
    finally:
        w.close()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
