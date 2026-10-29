"""Acceptance tests: ProjectRequirement.md, checked from the user's side.

One test per requirement, named after its PRD section. Requirements already
proven end to end by tests/system are referenced, not repeated. Where the
shipped app deliberately differs from the PRD the test is a strict xfail
naming the gap, so it stays visible until the PRD or the code is updated.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QDockWidget

from tests.system.conftest import CANONICAL_CONFIG, tcp_settings, wait_until
from tests.system.sim_device import TcpBms

ROOT = Path(__file__).resolve().parents[2]
RESOURCES = ROOT / "app" / "resources"


def connect(window, settings) -> None:
    assert window._attempt_connect(settings), "connection failed"
    wait_until(lambda: window._packet_count >= 10, 5, "first telemetry")


# ---------------------------------------------------------------- §4.1 config
@pytest.mark.parametrize("source", [
    RESOURCES / "frame_config_template.xlsx",   # single Excel workbook
    RESOURCES / "config_template",              # directory of CSVs
], ids=["xlsx workbook", "csv directory"])
def test_4_1_config_loads_from_workbook_or_csv_directory(window, source):
    window._load_config_from_path(source, suppress_popups=True)
    assert window._config is not None
    assert window._config_path == source
    assert window._config.frames, "no frames defined"
    assert window._table.model().rowCount() > 0, "telemetry table not populated"


def test_4_1_config_missing_required_sheet_is_rejected_and_previous_config_kept(window, tmp_path, error_boxes):
    from app.decoder.config_loader import ConfigError

    shutil.copy(CANONICAL_CONFIG / "protocol.csv", tmp_path / "protocol.csv")   # no variables.csv
    before = window._config
    with pytest.raises(ConfigError):
        window._load_config_from_path(tmp_path)
    assert window._config is before
    assert error_boxes and "variables.csv" in error_boxes[-1][1], error_boxes


# ---------------------------------------------------------------- §4.2 serial
def test_4_2_auto_reconnect_backs_off_exponentially_from_1s_to_16s(window, device):
    connect(window, tcp_settings(device, auto_reconnect=True))
    attempts = []
    real_attempt = window._attempt_connect

    def recording_attempt(settings, is_retry=False):
        attempts.append(time.monotonic())
        return real_attempt(settings, is_retry=is_retry)

    window._attempt_connect = recording_attempt
    device.stop()                       # device gone: every retry is refused
    dropped = time.monotonic()
    wait_until(lambda: len(attempts) >= 3, 12, "three reconnect attempts")
    gaps = [attempts[0] - dropped, attempts[1] - attempts[0], attempts[2] - attempts[1]]
    for gap, expected in zip(gaps, (1.0, 2.0, 4.0), strict=True):
        assert gap == pytest.approx(expected, abs=0.6), f"retry gaps {gaps}"
    # ... and the backoff is capped at 16 s.
    window._reconnect_attempts = 10
    window._reconnect_timer.stop()
    window._on_reconnect_timeout()
    assert window._reconnect_timer.interval() == 16_000
    window._reconnect_timer.stop()


@pytest.mark.parametrize("device_kind, earliest, latest", [
    # Request/response device, silent until polled (e.g. still in its
    # bootloader): polling waits out the 2.5 s grace window.
    ("silent", 2.3, 4.0),
    # A device that is already talking has proven it is alive, so the gate
    # opens on its first byte instead of waiting the full window.
    ("streaming", 0.0, 1.0),
])
def test_4_2_polling_boot_grace_gate(window, tmp_path, device_kind, earliest, latest):
    for csv in CANONICAL_CONFIG.glob("*.csv"):
        shutil.copy(csv, tmp_path / csv.name)
    (tmp_path / "polling_schedule.csv").write_text(
        "id_or_address,interval_ms,timeout_ms,enabled\n0x0010,100,50,TRUE\n")
    window._load_config_from_path(tmp_path, suppress_popups=True)
    assert window._config.polling_schedules
    window._polling_action.setChecked(True)

    bms = TcpBms(stream=device_kind == "streaming").start()
    try:
        poll = bytes.fromhex("AA550010")       # request header for frame 0x0010
        assert window._attempt_connect(tcp_settings(bms))
        opened = time.monotonic()
        wait_until(lambda: poll in bms.received(), 6, "first poll request")
        first_poll_after = time.monotonic() - opened
        assert earliest <= first_poll_after <= latest, f"first poll after {first_poll_after:.2f}s"
    finally:
        window._disconnect()
        bms.stop()


# --------------------------------------------------------------- §4.4 logging
def test_4_4_raw_log_reaches_disk_within_half_a_second_while_logging(window, device, tmp_path):
    connect(window, tcp_settings(device))
    assert window._start_logging_file(tmp_path / "s.xlsx", choice="Raw only")
    try:
        streaming = tmp_path / "s.xlsx.tmp_data"
        time.sleep(1.0)                 # no event-loop pumping needed for the writer thread
        wait_until(lambda: streaming.exists() and streaming.stat().st_size > 0, 1.0,
                   "raw rows on disk before the session ends")
        header = streaming.read_text().splitlines()[0]
        assert header == "timestamp,direction,hex,delta_t_ms"
    finally:
        window._stop_logging()


@pytest.mark.xfail(strict=True, reason=(
    "PRD §4.4 specifies a '*_raw.csv' file; the app streams CSV to a temp file but "
    "delivers '*_raw.xlsx' (a CSV is only kept as a crash fallback). Update the PRD or the code."))
def test_4_4_raw_log_is_delivered_as_raw_csv(window, device, tmp_path):
    connect(window, tcp_settings(device))
    assert window._start_logging_file(tmp_path / "s.xlsx", choice="Raw + Decoded")
    wait_until(lambda: window._packet_count > 30, 3)
    window._stop_logging()
    assert (tmp_path / "s_raw.csv").exists()


def test_4_4_decoded_log_metadata_records_version_port_and_session_start(window, device, tmp_path):
    import openpyxl

    connect(window, tcp_settings(device))
    assert window._start_logging_file(tmp_path / "s.xlsx", choice="Raw + Decoded")
    wait_until(lambda: window._packet_count > 30, 3)
    window._stop_logging()
    meta = dict(openpyxl.load_workbook(tmp_path / "s_decoded.xlsx", read_only=True)["Metadata"]
                .iter_rows(min_row=2, values_only=True))
    text = " ".join(f"{k}={v}" for k, v in meta.items())
    assert meta.get("app_version"), text
    assert str(device.port) in text, f"port configuration missing: {text}"
    assert any("start" in str(k).lower() for k in meta), f"no session start: {text}"


# ------------------------------------------------------------ §4.5 analysis
def test_4_5_analysis_suite_opens_non_modal_and_loads_two_session_logs(window, device, tmp_path):
    connect(window, tcp_settings(device))
    logs = []
    for name in ("run_a", "run_b"):
        assert window._start_logging_file(tmp_path / f"{name}.xlsx", choice="Decoded only")
        wait_until(lambda: window._packet_count > 60 * (len(logs) + 1), 5)
        window._stop_logging()
        logs.append(str(tmp_path / f"{name}.xlsx"))

    window._on_analysis_suite()
    suite = window._analysis_window
    assert suite.isVisible() and not suite.isModal()
    with patch("app.ui.analysis_suite.QFileDialog.getOpenFileNames", return_value=(logs, "")):
        suite._on_load_logs()
    wait_until(lambda: len(suite._logs) == 2, 15, "both logs loaded")
    for entry in suite._logs.values():
        assert len(entry.elapsed) > 5
        assert any("Cell Voltage 1" in p for p in entry.available_params()), entry.available_params()


# -------------------------------------------------------- §5.1 performance
def test_5_1_ui_refresh_timer_runs_at_about_60_hz(window):
    assert window._ui_timer.interval() == pytest.approx(1000 / 60, abs=1)


def test_5_1_serial_reads_never_run_on_the_ui_thread(window, device):
    from app.serial_io import serial_worker

    reader_threads = set()
    real_read = serial_worker.TcpSocketWrapper.read

    def spy(self, *args, **kwargs):
        reader_threads.add(threading.get_ident())
        return real_read(self, *args, **kwargs)

    with patch.object(serial_worker.TcpSocketWrapper, "read", spy):
        connect(window, tcp_settings(device))
    assert reader_threads, "no reads observed"
    assert threading.main_thread().ident not in reader_threads


@pytest.mark.xfail(strict=True, reason=(
    "PRD §5.1 asks for OpenGL-accelerated plotting where supported; main_window.py and "
    "analysis_suite.py set pg.setConfigOptions(useOpenGL=False) unconditionally."))
def test_5_1_plots_use_opengl_where_supported(window):
    import pyqtgraph as pg

    assert pg.getConfigOption("useOpenGL")


# ---------------------------------------------------------- §5.2 usability
def test_5_2_main_window_fits_a_640x480_screen(window):
    window.resize(640, 480)
    assert window.minimumSize().width() <= 640 and window.minimumSize().height() <= 480
    assert (window.width(), window.height()) == (640, 480)


def test_5_2_every_functional_block_is_a_movable_floatable_dock(window):
    docks = {d.windowTitle(): d for d in window.findChildren(QDockWidget)}
    for title in ("Live Plot", "Bitfields", "Enums", "TX Commands", "Parameter Editor"):
        assert title in docks, f"missing dock {title!r}"
        features = docks[title].features()
        assert features & QDockWidget.DockWidgetFeature.DockWidgetFloatable, title
        assert features & QDockWidget.DockWidgetFeature.DockWidgetMovable, title


def test_5_2_layout_geometry_and_last_baud_persist_across_restart(qapp, window, error_boxes, tmp_path):
    from app.ui.dialogs import ConnectionDialog
    from app.ui.main_window import MainWindow

    window._layout_combo.setCurrentText("2×2")
    window.resize(760, 560)          # inside the 800×600 offscreen screen (restore clamps to it)
    window._bitfields_dock.setVisible(False)
    window._settings.setValue("conn/baud", "57600")    # what ConnectionDialog stores on OK
    window.close()                                       # saves state

    again = MainWindow()
    again.show()
    try:
        wait_until(lambda: again._layout_combo.currentText() == "2×2", 2, "plot layout restored")
        assert (again.width(), again.height()) == (760, 560)
        assert not again._bitfields_dock.isVisible()
        def dialog_baud():
            return ConnectionDialog(again._settings, parent=again,
                                    config_defaults=again._config.serial_defaults).get_settings().baud_rate

        # The startup reload of the last config must not clobber the user's baud ...
        assert dialog_baud() == 57600
        # ... while a config the user explicitly loads still brings its own.
        config_9600 = tmp_path / "config_9600"
        shutil.copytree(CANONICAL_CONFIG, config_9600)
        (config_9600 / "serial_defaults.csv").write_text(
            "baud_rate,data_bits,stop_bits,parity,timeout_ms\n9600,8,1,N,100\n")
        again._load_config_from_path(config_9600)
        assert dialog_baud() == 9600
    finally:
        again.close()


# ------------------------------------------------------- §5.3 reliability
def test_5_3_uncaught_exception_goes_to_rotating_bytehound_log(tmp_path):
    probe = textwrap.dedent(f"""
        import logging, sys
        from pathlib import Path
        import app.main as m
        m._PROJECT_ROOT = Path({str(tmp_path)!r})
        m.configure_logging()
        handler = next(h for h in logging.getLogger().handlers
                       if type(h).__name__ == "RotatingFileHandler")
        print("ROTATION", handler.maxBytes, handler.backupCount)
        raise RuntimeError("acceptance-crash-probe")
    """)
    proc = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, capture_output=True, text=True,
                          timeout=120, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    assert f"ROTATION {5 * 1024 * 1024} 3" in proc.stdout, proc.stdout + proc.stderr
    log = (tmp_path / "logs" / "bytehound.log").read_text()
    assert "Uncaught exception" in log and "acceptance-crash-probe" in log


# §4.2 connect/disconnect lifecycle, §4.3 resync + CRC + scaling + calc groups,
# §4.4 decoded wide rows and RX/TX raw rows, and §5.3 the --validate CLI are
# verified end to end in tests/system/test_end_to_end.py.
