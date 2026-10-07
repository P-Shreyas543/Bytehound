"""Thermal protection settings in cycler_settings.json ("safety") and the Safety-tab switch."""

import json
import os

import pytest
from PySide6.QtWidgets import QApplication

from single_cell_cycler.comm.packet_codec import CellDataTelemetry
from single_cell_cycler.config import cycler_config
from single_cell_cycler.config.cycler_config import ThermalSafetySettings, load_safety_settings
from single_cell_cycler.core.safety_monitor import SafetyLimits, SafetyMonitor


@pytest.fixture(scope="module")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    return QApplication.instance() or QApplication([])


def test_missing_section_is_added_and_logging_kept(tmp_path):
    path = tmp_path / "cycler_settings.json"
    path.write_text(json.dumps({"logging": {"interval_s": 0.5}}), encoding="utf-8")
    s = load_safety_settings(path)
    assert s == ThermalSafetySettings()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["logging"] == {"interval_s": 0.5}            # operator's other settings untouched
    assert data["safety"]["rate_of_rise_enabled"] is False     # off by default since v1.3.1


def test_values_are_clamped_to_safe_bounds(tmp_path):
    path = tmp_path / "cycler_settings.json"
    path.write_text(json.dumps({"safety": {"rate_of_rise_enabled": False, "max_temp_c": 150,
                                           "rate_of_rise_c_per_min": "fast", "warn_temp_c": 99}}),
                    encoding="utf-8")
    s = load_safety_settings(path)
    assert s.rate_of_rise_enabled is False
    assert s.max_temp_c == 80.0                              # never above 80 °C
    assert s.rate_of_rise_c_per_min == 1.5                   # bad value -> default
    assert s.warn_temp_c <= s.max_temp_c


def _ramp(monitor, rate_c_per_min, seconds=60.0):
    t, temp = 1000.0, 30.0
    for _ in range(int(seconds * 10)):
        t += 0.1
        temp += rate_c_per_min / 600.0
        if not monitor.check_telemetry(CellDataTelemetry(timestamp=t, voltage=3.7, current=1.0,
                                                         terminal_temp=temp, body_temp=temp)):
            return True
    return False


def test_rate_trip_off_keeps_the_absolute_limit():
    off = SafetyMonitor(command_sender=lambda *a: None, limits=SafetyLimits(temp_rate_enabled=False))
    assert _ramp(off, 5.0) is False                          # 5 °C/min no longer trips
    hot = SafetyMonitor(command_sender=lambda *a: None, limits=SafetyLimits(temp_rate_enabled=False))
    assert hot.check_telemetry(CellDataTelemetry(timestamp=1.0, voltage=3.7, current=1.0,
                                                 terminal_temp=61.0, body_temp=40.0)) is False
    assert hot.trip_kind == "thermal"
    on = SafetyMonitor(command_sender=lambda *a: None, limits=SafetyLimits())
    assert _ramp(on, 5.0) is True


def test_safety_tab_switch_saves_and_applies(qapp):
    from single_cell_cycler.ui.main_window import MainWindow

    w = MainWindow()
    try:
        # Shipped default (v1.3.1): off
        assert not w.safety_panel.chk_rate.isChecked()
        assert w.engine.safety_monitor.limits.temp_rate_enabled is False

        w.safety_panel.chk_rate.setChecked(True)
        assert w.engine.safety_monitor.limits.temp_rate_enabled is True
        saved = json.loads(cycler_config.SETTINGS_PATH.read_text(encoding="utf-8"))
        assert saved["safety"]["rate_of_rise_enabled"] is True

        w.safety_panel.chk_rate.setChecked(False)            # offscreen: no confirmation dialog
        assert w.engine.safety_monitor.limits.temp_rate_enabled is False
        saved = json.loads(cycler_config.SETTINGS_PATH.read_text(encoding="utf-8"))
        assert saved["safety"]["rate_of_rise_enabled"] is False
        assert "logging" in saved
        assert any("turned OFF" in m for _, _, m in w._event_records)

        w._set_test_running_ui(True)
        assert not w.safety_panel.chk_rate.isEnabled()       # locked while a test runs
        w._set_test_running_ui(False)
        assert w.safety_panel.chk_rate.isEnabled()
    finally:
        w.close()


def test_edited_file_applies_at_next_start_and_sets_alarm_levels(qapp):
    from single_cell_cycler.ui.main_window import MainWindow

    w = MainWindow()
    try:
        cycler_config.save_safety_settings(ThermalSafetySettings(
            rate_of_rise_enabled=True, rate_of_rise_c_per_min=3.0, max_temp_c=55.0, warn_temp_c=40.0))
        w._apply_thermal_settings()                          # what START does
        lim = w.engine.safety_monitor.limits
        assert (lim.max_temp_rate_of_rise_c_per_min, lim.max_temp_c) == (3.0, 55.0)

        w._on_cell_data(CellDataTelemetry(voltage=3.7, current=0.0, terminal_temp=41.0, body_temp=30.0))
        assert "High cell temperature" in w.lbl_alarm_banner.text()
    finally:
        w.close()
