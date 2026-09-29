"""Test suite for Pillar 1: IMP-01 (Crosshair HUD) and IMP-02 (Quick-Zoom Toolbar).

Verifies:
1. Quick-Zoom modes (FIT_ALL, CURRENT_STEP, CURRENT_CYCLE, LAST_10M, LAST_1M, MANUAL).
2. Range framing mathematics and auto-wrap preservation.
3. Mouse drag detection setting MANUAL zoom mode without timer overwrite.
4. Crosshair tracking and HUD text formatting for VI and Temp tabs.
5. Crosshair synchronization between VI and Temp charts.
6. Full reset behavior.
"""

from __future__ import annotations

import os
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from single_cell_cycler.comm.packet_codec import CellDataTelemetry
from single_cell_cycler.ui.widgets.live_plots import LivePlotWidget, ZoomMode


@pytest.fixture(scope="module")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _create_ready_widget(qapp) -> LivePlotWidget:
    w = LivePlotWidget()
    w.show()
    w.resize(1000, 600)
    qapp.processEvents()
    return w


def test_quick_zoom_toolbar_initialization(qapp):
    widget = _create_ready_widget(qapp)
    assert widget._zoom_mode == ZoomMode.FIT_ALL
    assert len(widget._zoom_buttons["fit"]) == 2  # VI tab and Temp tab
    assert len(widget._zoom_buttons["step"]) == 2
    assert len(widget._zoom_buttons["cycle"]) == 2
    assert len(widget._zoom_buttons["10m"]) == 2
    assert len(widget._zoom_buttons["1m"]) == 2

    assert widget.crosshair_v_vi.isVisible() is False
    assert widget.crosshair_v_temp.isVisible() is False
    assert "Hover over chart to inspect" in widget.lbl_hud_vi.text()
    assert "Hover over chart to inspect" in widget.lbl_hud_temp.text()


def test_quick_zoom_framing_modes(qapp):
    widget = _create_ready_widget(qapp)
    widget.set_relay_state(True, 1)

    # Ingest 100 seconds of telemetry points at 10 Hz
    t0 = widget.start_epoch
    for sec in range(0, 101):
        telem = CellDataTelemetry(
            timestamp=t0 + sec,
            voltage=3.65 + (sec * 0.005),
            current=1.50,
            terminal_temp=25.0 + (sec * 0.05),
            body_temp=26.0 + (sec * 0.05),
        )
        widget.add_telemetry(telem)

    assert len(widget._t) == 101

    # 1. FIT_ALL: should span 0 to 100
    widget.set_zoom_mode(ZoomMode.FIT_ALL)
    x_range = widget.plot_vi.viewRange()[0]
    assert x_range[0] <= 0.1
    assert x_range[1] >= 100.0

    # 2. LAST_1M: should span 100 - 60 = 40 to 100
    widget.set_zoom_mode(ZoomMode.LAST_1M)
    x_range = widget.plot_vi.viewRange()[0]
    assert 38.0 <= x_range[0] <= 42.0
    assert 98.0 <= x_range[1] <= 105.0

    # 3. Simulate step transition at t=100s
    widget.notify_step_started(cycle_idx=1, step_idx=2)
    # The step started at latest_t = 100.0
    # Add more points up to 150s
    for sec in range(101, 151):
        telem = CellDataTelemetry(
            timestamp=t0 + sec,
            voltage=4.15,
            current=0.50,
            terminal_temp=30.0,
            body_temp=31.0,
        )
        widget.add_telemetry(telem)

    # CURRENT_STEP: should start at ~100.0 and span to 150.0
    widget.set_zoom_mode(ZoomMode.CURRENT_STEP)
    x_range = widget.plot_vi.viewRange()[0]
    assert 95.0 <= x_range[0] <= 105.0
    assert 148.0 <= x_range[1] <= 155.0

    # 4. CURRENT_CYCLE: started at 0.0, should span 0 to 150
    widget.set_zoom_mode(ZoomMode.CURRENT_CYCLE)
    x_range = widget.plot_vi.viewRange()[0]
    assert x_range[0] <= 0.1
    assert x_range[1] >= 150.0


def test_manual_zoom_detection_and_no_timer_overwrite(qapp):
    widget = _create_ready_widget(qapp)
    widget.set_relay_state(True, 1)

    t0 = widget.start_epoch
    for sec in range(0, 50):
        telem = CellDataTelemetry(
            timestamp=t0 + sec,
            voltage=3.7,
            current=1.0,
            terminal_temp=25.0,
            body_temp=25.0,
        )
        widget.add_telemetry(telem)

    widget.set_zoom_mode(ZoomMode.FIT_ALL)
    assert widget._zoom_mode == ZoomMode.FIT_ALL

    # User manually drags plot
    widget._on_manual_view_changed()
    assert widget._zoom_mode == ZoomMode.MANUAL

    # Operator zooms into custom range (12.0 to 18.0)
    widget.plot_vi.setXRange(12.0, 18.0, padding=0.0)

    # Add more telemetry and trigger 10 Hz redraw
    telem = CellDataTelemetry(
        timestamp=t0 + 51,
        voltage=3.7,
        current=1.0,
        terminal_temp=25.0,
        body_temp=25.0,
    )
    widget.add_telemetry(telem)
    widget.tick_update()

    # MANUAL zoom must NOT have been overridden by tick_update
    cur_range = widget.plot_vi.viewRange()[0]
    assert 11.5 <= cur_range[0] <= 12.5
    assert 17.5 <= cur_range[1] <= 18.5

    # Clicking "Fit All" restores automatic tracking
    widget._zoom_buttons["fit"][0].click()
    assert widget._zoom_mode == ZoomMode.FIT_ALL
    fit_range = widget.plot_vi.viewRange()[0]
    assert fit_range[0] <= 0.1
    assert fit_range[1] >= 50.0


def test_crosshair_and_hud_readout(qapp):
    widget = _create_ready_widget(qapp)
    widget.set_relay_state(True, 1)

    t0 = widget.start_epoch
    # Add known deterministic points
    for sec in [0.0, 10.0, 20.0, 30.0, 40.0]:
        telem = CellDataTelemetry(
            timestamp=t0 + sec,
            voltage=3.200 + (sec * 0.01),  # at 20s -> 3.400 V
            current=1.500,
            terminal_temp=22.0 + (sec * 0.1),  # at 20s -> 24.0 C
            body_temp=23.0 + (sec * 0.1),      # at 20s -> 25.0 C
        )
        widget.add_telemetry(telem)

    widget.tick_update()
    qapp.processEvents()

    # Map time t=20.0 to scene coordinates
    vb = widget.plot_vi.plotItem.vb
    scene_pt = vb.mapViewToScene(QPointF(20.0, 3.4))

    # Simulate hover event
    widget._on_mouse_moved_vi(scene_pt)

    assert widget.crosshair_v_vi.isVisible() is True
    assert widget.crosshair_v_temp.isVisible() is True  # Crosshairs synchronized!
    assert abs(widget.crosshair_v_vi.getPos()[0] - 20.0) < 0.1

    hud_text = widget.lbl_hud_vi.text()
    assert "20.0s" in hud_text
    assert "3.400 V" in hud_text
    assert "+1.500 A" in hud_text

    # Switch to Temp tab and test hover
    widget.tabs.setCurrentIndex(1)
    qapp.processEvents()

    vb_temp = widget.plot_temp.plotItem.vb
    scene_pt_temp = vb_temp.mapViewToScene(QPointF(20.0, 24.0))
    widget._on_mouse_moved_temp(scene_pt_temp)

    hud_temp_text = widget.lbl_hud_temp.text()
    assert "20.0s" in hud_temp_text
    assert "24.0 °C" in hud_temp_text
    assert "25.0 °C" in hud_temp_text

    # Test leaving chart area
    widget._on_mouse_moved_vi(QPointF(-100, -100))
    assert widget.crosshair_v_vi.isVisible() is False
    assert widget.crosshair_v_temp.isVisible() is False
    assert "Hover over chart to inspect" in widget.lbl_hud_vi.text()


def test_reset_all_cleans_zoom_and_hud(qapp):
    widget = _create_ready_widget(qapp)
    widget.set_relay_state(True, 1)

    t0 = widget.start_epoch
    for sec in range(10):
        telem = CellDataTelemetry(
            timestamp=t0 + sec,
            voltage=3.7,
            current=1.0,
            terminal_temp=25.0,
            body_temp=25.0,
        )
        widget.add_telemetry(telem)

    widget.set_zoom_mode(ZoomMode.MANUAL)
    widget.lbl_hud_vi.setText("Some inspected value")

    widget.reset_all()

    assert widget._zoom_mode == ZoomMode.FIT_ALL
    assert len(widget._t) == 0
    assert "Hover over chart to inspect" in widget.lbl_hud_vi.text()
    assert "Hover over chart to inspect" in widget.lbl_hud_temp.text()
    assert widget.crosshair_v_vi.isVisible() is False
