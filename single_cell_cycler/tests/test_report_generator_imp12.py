"""Unit tests for IMP-12: One-Click HTML / PDF Test Certification Report Generator."""

from pathlib import Path
import pytest

from single_cell_cycler.core.metrics_tracker import CycleSummary, MetricsTracker
from single_cell_cycler.core.profile_model import TestRecipe, TestStep, StepType
from single_cell_cycler.data.report_generator import generate_html_report, _generate_capacity_svg, _generate_dcir_svg


def test_generate_html_report_full(tmp_path):
    """Verify full certification report generation with SVG charts, KPIs, and cycle table."""
    cycles = [
        CycleSummary(
            cycle_index=1,
            charge_capacity_mah=2500.0,
            discharge_capacity_mah=2490.0,
            charge_energy_mwh=9250.0,
            discharge_energy_mwh=9100.0,
            coulombic_efficiency_pct=99.6,
            energy_efficiency_pct=98.3,
            duration_s=7200.0,
            dcir_10s_mohm=16.2,
        ),
        CycleSummary(
            cycle_index=2,
            charge_capacity_mah=2495.0,
            discharge_capacity_mah=2480.0,
            charge_energy_mwh=9230.0,
            discharge_energy_mwh=9050.0,
            coulombic_efficiency_pct=99.4,
            energy_efficiency_pct=98.0,
            duration_s=7180.0,
            dcir_10s_mohm=16.5,
        ),
        CycleSummary(
            cycle_index=3,
            charge_capacity_mah=2485.0,
            discharge_capacity_mah=2470.0,
            charge_energy_mwh=9200.0,
            discharge_energy_mwh=9000.0,
            coulombic_efficiency_pct=99.4,
            energy_efficiency_pct=97.8,
            duration_s=7150.0,
            dcir_10s_mohm=16.8,
        ),
    ]

    recipe = TestRecipe(
        recipe_name="High-Rate Cycle Life Qualification",
        chemistry="NMC",
        cell_nominal_capacity_mah=2500.0,
    )

    tracker = MetricsTracker()
    tracker.cumulative_charge_mah = 7480.0
    tracker.cumulative_discharge_mah = 7440.0
    tracker.cumulative_charge_mwh = 27680.0
    tracker.cumulative_discharge_mwh = 27150.0

    out_file = tmp_path / "reports" / "test_certificate.html"
    res_path = generate_html_report(
        output_html_path=out_file,
        cell_id=2,
        recipe=recipe,
        cycles=cycles,
        metrics_tracker=tracker,
        operator="Senior Metrology Eng Bob",
        notes="IEC 62660-1 cycle aging run",
    )

    assert res_path.exists()
    assert res_path == out_file

    content = res_path.read_text(encoding="utf-8")
    # Verify branding and compliance
    assert "BYTEHOUND" in content
    assert "IEC 62660-1 / USABC COMPLIANT" in content
    assert "Senior Metrology Eng Bob" in content
    assert "High-Rate Cycle Life Qualification" in content

    # Verify KPIs
    assert "2490" in content  # Initial capacity
    assert "2470" in content  # Final capacity
    assert "99.2" in content or "99.4" in content or "99.6" in content  # Efficiencies
    assert "27.15" in content  # Wh discharged

    # Verify embedded SVGs
    assert "<svg" in content
    assert "Discharge Capacity (mAh)" in content
    assert "R₁₀ₛ (mΩ)" in content

    # Verify print stylesheet
    assert "@media print" in content


def test_generate_html_report_empty_cycles(tmp_path):
    """Verify report handles empty cycle dataset without errors."""
    out_file = tmp_path / "reports" / "empty_report.html"
    res_path = generate_html_report(
        output_html_path=out_file,
        cell_id=1,
        recipe=None,
        cycles=[],
        metrics_tracker=None,
    )

    assert res_path.exists()
    content = res_path.read_text(encoding="utf-8")
    assert "No cycles completed yet." in content
    assert "BYTEHOUND" in content


def test_svg_generators_isolated():
    """Verify SVG generator functions produce valid XML/SVG output."""
    svg_cap = _generate_capacity_svg([])
    assert "<svg" in svg_cap
    assert "No Cycle Data Available" in svg_cap

    svg_dcir = _generate_dcir_svg([])
    assert "<svg" in svg_dcir
    assert "No Standardized Pulse DCIR" in svg_dcir


def test_main_window_generate_test_report(tmp_path):
    """Verify MainWindow.generate_test_report builds HTML document properly."""
    import os
    from PySide6.QtWidgets import QApplication
    from single_cell_cycler.ui.main_window import MainWindow

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    win = MainWindow()
    dest_html = tmp_path / "win_certificate.html"
    try:
        res_path = win.generate_test_report(target_html=dest_html, auto_open=False)
        assert res_path is not None
        assert res_path.exists()
        content = res_path.read_text(encoding="utf-8")
        assert "BYTEHOUND" in content
        assert "Cell Cycler Qualification" in content
    finally:
        win._ui_tick_timer.stop()
        win.transceiver.disconnect_serial(send_safe_zero=False)
        win.logger.stop_session()


def test_generate_html_report_boolean_guard():
    """Verify generate_html_report safely tolerates boolean / Qt signal checked parameter."""
    res_path = generate_html_report(output_html_path=False)
    assert res_path is not None
    assert res_path.exists()
    assert res_path.suffix == ".html"
    # Clean up test output
    try:
        res_path.unlink()
    except Exception:
        pass


def test_main_window_btn_report_click():
    """Verify clicking btn_report (which passes bool checked=False via Qt) succeeds cleanly."""
    import os
    from PySide6.QtWidgets import QApplication
    from single_cell_cycler.ui.main_window import MainWindow

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    win = MainWindow()
    try:
        # Simulate button click (PySide6 QPushButton emits clicked(bool checked=False))
        win.btn_report.click()
        # Verify generate_test_report called with False does not raise TypeError
        res = win.generate_test_report(False, auto_open=False)
        assert res is not None
        assert res.exists()
        try:
            res.unlink()
        except Exception:
            pass
    finally:
        win._ui_tick_timer.stop()
        win.transceiver.disconnect_serial(send_safe_zero=False)
        win.logger.stop_session()


