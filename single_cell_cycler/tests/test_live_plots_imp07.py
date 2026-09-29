"""Integration and unit tests for IMP-07: Tab 5 Cycle Aging & Health tracking in LivePlotWidget."""

import os
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from single_cell_cycler.ui.widgets.live_plots import LivePlotWidget


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_aging_tab_initialization(qapp):
    widget = LivePlotWidget()
    assert widget.tabs.count() == 5
    assert "Cycle Aging" in widget.tabs.tabText(4)
    assert hasattr(widget, "plot_aging_cap")
    assert hasattr(widget, "plot_aging_eff")
    assert hasattr(widget, "view_aging_dcir")
    assert hasattr(widget, "curve_aging_q_dis")
    assert hasattr(widget, "curve_aging_q_chg")
    assert hasattr(widget, "curve_aging_q_proj")
    assert hasattr(widget, "curve_aging_ce")
    assert hasattr(widget, "curve_aging_ee")
    assert hasattr(widget, "curve_aging_dcir")
    assert hasattr(widget, "line_aging_eol")


def test_aging_tab_data_ingestion_and_forecasting(qapp):
    widget = LivePlotWidget()

    # Ingest 5 cycles of realistic capacity fade (-5 mAh/cycle)
    cycles_data = [
        (1, 2500.0, 99.5, 2512.0, 93.2, 14.8),
        (2, 2495.0, 99.6, 2505.0, 93.4, 14.9),
        (3, 2490.0, 99.65, 2498.0, 93.5, 15.0),
        (4, 2485.0, 99.7, 2492.0, 93.6, 15.1),
        (5, 2480.0, 99.75, 2486.0, 93.7, 15.2),
    ]

    for c_idx, q_dis, ce, q_chg, ee, dcir in cycles_data:
        widget.add_cycle_summary(
            c_idx,
            q_dis,
            ce,
            charge_mah=q_chg,
            energy_eff=ee,
            dcir_mohm=dcir,
        )

    # Verify buffers
    assert len(widget._cycle_indices) == 5
    assert len(widget._cycle_q_dis) == 5
    assert len(widget._cycle_dcir) == 5

    # Verify curve data
    c_x, q_y = widget.curve_aging_q_dis.getData()
    assert list(c_x) == [1, 2, 3, 4, 5]
    assert list(q_y) == [2500.0, 2495.0, 2490.0, 2485.0, 2480.0]

    # Verify 80% EOL line (2500 * 0.8 = 2000)
    assert widget.line_aging_eol.isVisible()
    assert abs(widget.line_aging_eol.value() - 2000.0) < 1e-3

    # Verify projected EOL cycle: 2500 - 5 * n = 2000 => n = 100 cycles
    proj_x, proj_y = widget.curve_aging_q_proj.getData()
    assert len(proj_x) > 5
    assert "Cycle 101" in widget.lbl_aging_health_badge.text() or "Cycle 100" in widget.lbl_aging_health_badge.text()
    assert "Fade: -5.00 mAh/cyc" in widget.lbl_aging_fade_badge.text()

    # Verify efficiency and DCIR curves
    _, ce_y = widget.curve_aging_ce.getData()
    assert len(ce_y) == 5
    assert abs(ce_y[-1] - 99.75) < 1e-2

    _, dcir_y = widget.curve_aging_dcir.getData()
    assert len(dcir_y) == 5
    assert abs(dcir_y[-1] - 15.2) < 1e-2


def test_aging_tab_model_switch_and_fit(qapp):
    widget = LivePlotWidget()
    for c in range(1, 6):
        widget.add_cycle_summary(c, 2500.0 - (c - 1) * 2.0, 99.5, 2510.0, 93.0, 15.0)

    # Switch to exponential model
    widget.set_aging_model("exponential")
    assert widget._aging_model == "exponential"
    assert widget.curve_aging_q_proj.getData()[0] is not None

    # Switch back to linear
    widget.set_aging_model("linear")
    assert widget._aging_model == "linear"

    # Fit view does not throw
    widget.fit_aging_view()


def test_aging_tab_reset_all(qapp):
    widget = LivePlotWidget()
    widget.add_cycle_summary(1, 2500.0, 99.5, 2510.0, 93.0, 15.0)
    assert len(widget._cycle_indices) == 1

    widget.reset_all()
    assert len(widget._cycle_indices) == 0
    assert len(widget._cycle_q_dis) == 0
    assert len(widget._cycle_dcir) == 0
    assert not widget.line_aging_eol.isVisible()
