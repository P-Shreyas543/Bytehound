"""Unit tests for IMP-11: One-Click Run Diagnostic Package Exporter (.zip)."""

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from single_cell_cycler.core.metrics_tracker import CycleSummary, MetricsTracker, StepMetrics
from single_cell_cycler.core.profile_model import StepType, TestRecipe, TestStep
from single_cell_cycler.data.run_exporter import compute_sha256, export_run_package


def test_compute_sha256():
    """Verify cryptographic SHA-256 computation."""
    data = b"Bytehound Single-Cell BMS Cycler"
    expected = hashlib.sha256(data).hexdigest()
    assert compute_sha256(data) == expected


def test_export_run_package_full(tmp_path):
    """Verify complete export package with all telemetry, summaries, logs, and manifest."""
    # 1. Create mock recipe
    recipe = TestRecipe(
        recipe_name="Fast Charge Qualification",
        cell_nominal_capacity_mah=2500.0,
        steps=[
            TestStep(step_index=1, name="CC Charge", step_type=StepType.CHARGE, charge_current_1=True, charge_current_2=True),
            TestStep(step_index=2, name="Rest", step_type=StepType.REST),
        ],
    )

    # 2. Create mock raw CSV
    raw_csv = tmp_path / "test_session_raw.csv"
    raw_csv.write_text("timestamp_iso,voltage_v,current_a\n2026-09-29T10:00:00,3.650,2.000\n", encoding="utf-8")

    # 3. Create mock step metrics
    step_m = StepMetrics(
        cycle_index=1,
        step_index=1,
        step_name="CC Charge",
        step_type=StepType.CHARGE,
        start_time=1000.0,
        end_time=2800.0,
        duration_s=1800.0,
        start_voltage=3.200,
        end_voltage=4.200,
        peak_current=2.000,
        peak_temp=26.5,
        capacity_mah=1000.0,
        energy_mwh=3700.0,
    )

    # 4. Create mock cycle summary
    cycle_s = CycleSummary(
        cycle_index=1,
        charge_capacity_mah=1000.0,
        discharge_capacity_mah=990.0,
        charge_energy_mwh=3700.0,
        discharge_energy_mwh=3600.0,
        coulombic_efficiency_pct=99.0,
        energy_efficiency_pct=97.3,
        duration_s=3600.0,
        dcir_10s_mohm=18.5,
    )

    # 5. Create mock diagnostic log
    app_log = tmp_path / "cycler_app.txt"
    app_log.write_text("10:00:00 [INFO] Test started\n10:00:01 [INFO] Step 1 transition\n", encoding="utf-8")

    # 6. Create mock metrics tracker
    tracker = MetricsTracker()
    tracker.cumulative_charge_mah = 1000.0
    tracker.cumulative_discharge_mah = 990.0
    tracker.cumulative_charge_mwh = 3700.0
    tracker.cumulative_discharge_mwh = 3600.0

    # 7. Execute export
    dest_zip = tmp_path / "exports" / "test_run.zip"
    zip_result = export_run_package(
        output_zip_path=dest_zip,
        cell_id=2,
        recipe=recipe,
        raw_csv_path=raw_csv,
        step_history=[step_m],
        cycle_summaries=[cycle_s],
        app_log_path=app_log,
        metrics_tracker=tracker,
        operator="Test Engineer Alice",
        test_status="COMPLETED",
        notes="High-precision validation run",
    )

    assert zip_result.exists()
    assert zip_result == dest_zip

    # 8. Inspect ZIP archive
    with zipfile.ZipFile(dest_zip, "r") as zf:
        namelist = zf.namelist()
        assert "manifest.json" in namelist
        assert "recipe.json" in namelist
        assert "telemetry_raw_10hz.csv" in namelist
        assert "summary_steps.csv" in namelist
        assert "summary_cycles.csv" in namelist
        assert "diagnostic_log.txt" in namelist

        # Verify manifest
        manifest_raw = zf.read("manifest.json").decode("utf-8")
        manifest = json.loads(manifest_raw)
        assert manifest["format"] == "Bytehound-Run-Package"
        assert manifest["cell_id"] == 2
        assert manifest["operator"] == "Test Engineer Alice"
        assert manifest["test_status"] == "COMPLETED"
        assert manifest["cycles_completed"] == 1
        assert manifest["steps_completed"] == 1
        assert manifest["cumulative_metrics"]["charge_mah"] == 1000.0

        # Verify file hashes in manifest match extracted bytes
        for entry in manifest["archive_files"]:
            fname = entry["filename"]
            extracted_bytes = zf.read(fname)
            assert hashlib.sha256(extracted_bytes).hexdigest() == entry["sha256"]
            assert len(extracted_bytes) == entry["size_bytes"]


def test_export_run_package_partial(tmp_path):
    """Verify exporter functions gracefully with partial or missing inputs."""
    dest_zip = tmp_path / "exports" / "partial_run.zip"
    zip_result = export_run_package(
        output_zip_path=dest_zip,
        cell_id=1,
        recipe=None,
        raw_csv_path=None,
        step_history=None,
        cycle_summaries=None,
        app_log_path=None,
    )

    assert zip_result.exists()
    with zipfile.ZipFile(dest_zip, "r") as zf:
        namelist = zf.namelist()
        assert "manifest.json" in namelist
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest["cell_id"] == 1
        assert manifest["cycles_completed"] == 0


def test_main_window_export_run_bundle(tmp_path):
    """Verify MainWindow.export_run_bundle builds archive properly."""
    import os
    from PySide6.QtWidgets import QApplication
    from single_cell_cycler.ui.main_window import MainWindow

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    win = MainWindow()
    dest_zip = tmp_path / "win_exported_run.zip"
    exported_path = win.export_run_bundle(target_zip=dest_zip)

    assert exported_path is not None
    assert exported_path.exists()
    with zipfile.ZipFile(exported_path, "r") as zf:
        assert "manifest.json" in zf.namelist()


def test_export_run_package_boolean_guard():
    """Verify export_run_package safely tolerates boolean / Qt signal checked parameter."""
    res_path = export_run_package(output_zip_path=False)
    assert res_path is not None
    assert res_path.exists()
    assert res_path.suffix == ".zip"
    try:
        res_path.unlink()
    except Exception:
        pass


def test_main_window_btn_export_click():
    """Verify clicking btn_export_run (which passes bool checked=False via Qt) succeeds cleanly."""
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
        win.btn_export_run.click()
        # Verify export_run_bundle called with False does not raise TypeError
        res = win.export_run_bundle(False)
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


