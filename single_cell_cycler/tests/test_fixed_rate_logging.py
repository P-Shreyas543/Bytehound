"""Telemetry CSV logging runs on its own fixed clock (config/cycler_settings.json), independent of
telemetry arrival and UI load; SoC columns carry a fixed number of decimals."""

import csv
import json
import time

import numpy as np

from single_cell_cycler.config.cycler_config import LoggingSettings, load_logging_settings
from single_cell_cycler.data.async_logger import AsyncTelemetryLogger


def _record():
    now = time.time()
    return {"timestamp_epoch_s": round(now, 3), "voltage_v": 3.7, "soc_ocv_pct": 99.9,
            "soc_cc_pct": 64.97, "soc_ekf_pct": 50.0}


def _rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_rows_are_written_every_interval_even_while_the_main_thread_is_busy(tmp_path):
    log = AsyncTelemetryLogger(log_dir=tmp_path, interval_s=0.1)
    log.snapshot_provider = _record
    path = log.start_session("rate")
    t_end = time.perf_counter() + 2.05
    while time.perf_counter() < t_end:          # main thread never yields voluntarily (busy UI)
        sum(range(2000))
    log.stop_session()

    stamps = np.array([float(r["timestamp_epoch_s"]) for r in _rows(path)])
    assert 20 <= len(stamps) <= 22                       # one row per 0.1 s, first one at t = 0
    gaps = np.diff(stamps)
    assert abs(gaps.mean() - 0.1) < 0.003                # no drift
    assert gaps.max() < 0.16 and gaps.min() > 0.04       # no dropped or doubled slot
    assert log.slots_missed == 0


def test_interval_comes_from_settings_and_rows_repeat_without_new_telemetry(tmp_path):
    log = AsyncTelemetryLogger(log_dir=tmp_path, interval_s=0.05)
    frozen = _record()                                   # nothing new is "received" during the run
    log.snapshot_provider = lambda: dict(frozen)
    path = log.start_session("fast")
    time.sleep(1.02)
    log.stop_session()
    assert 20 <= len(_rows(path)) <= 22


def test_elapsed_column_steps_by_exactly_the_interval(tmp_path):
    """A coarse or jittery source clock must not show up as 0.31, 0.41, 0.52 ... in the CSV."""
    start = time.monotonic() - 0.2                       # test began 0.2 s before logging did
    log = AsyncTelemetryLogger(log_dir=tmp_path, interval_s=0.1)
    log.snapshot_provider = lambda: {"elapsed_s": round(time.monotonic() - start, 2), "voltage_v": 3.7}
    path = log.start_session("elapsed")
    time.sleep(1.25)
    log.stop_session()
    elapsed = [float(r["elapsed_s"]) for r in _rows(path)]
    assert len(elapsed) >= 12
    assert elapsed == [round(0.2 + 0.1 * k, 3) for k in range(len(elapsed))]


def test_no_rows_while_the_provider_reports_no_active_test(tmp_path):
    log = AsyncTelemetryLogger(log_dir=tmp_path, interval_s=0.05)
    log.snapshot_provider = lambda: None
    path = log.start_session("idle")
    time.sleep(0.3)
    log.stop_session()
    assert _rows(path) == []


def test_soc_columns_are_logged_with_two_decimals(tmp_path):
    log = AsyncTelemetryLogger(log_dir=tmp_path)
    path = log.start_session("soc")
    log.log_record(_record())
    log.stop_session()
    row = _rows(path)[0]
    assert (row["soc_ocv_pct"], row["soc_cc_pct"], row["soc_ekf_pct"]) == ("99.90", "64.97", "50.00")


def test_logging_settings_file_is_created_read_and_sanitised(tmp_path):
    path = tmp_path / "cycler_settings.json"
    assert load_logging_settings(path) == LoggingSettings()          # missing: defaults, file created
    assert json.loads(path.read_text(encoding="utf-8"))["logging"]["interval_s"] == 0.1

    path.write_text(json.dumps({"logging": {"interval_s": 0.5, "thread_priority": "highest",
                                            "soc_decimals": 3}}), encoding="utf-8")
    cfg = load_logging_settings(path)
    assert (cfg.interval_s, cfg.thread_priority, cfg.soc_decimals) == (0.5, "highest", 3)

    path.write_text(json.dumps({"logging": {"interval_s": 0, "thread_priority": "turbo"}}), encoding="utf-8")
    cfg = load_logging_settings(path)
    assert cfg.interval_s == 0.02 and cfg.thread_priority == "above_normal"

    path.write_text("{ not json", encoding="utf-8")
    assert load_logging_settings(path) == LoggingSettings()
