"""Acceptance tests: the single-cell cycler requirements in ProjectRequirement.md
("Current Single-Cell Cycler Requirements Status") and the README promises
they rest on, checked through the shipped components."""

from __future__ import annotations

import os
import sys
import time
from collections import namedtuple

import pytest

from single_cell_cycler.data.async_logger import AsyncTelemetryLogger
from single_cell_cycler.tests.system.conftest import posix_only, wait_until

Usage = namedtuple("Usage", "total used free")


def record(i: int = 0) -> dict:
    return {name: i for name in AsyncTelemetryLogger.FIELDNAMES}


def write_records(logger: AsyncTelemetryLogger, n: int) -> None:
    for i in range(n):
        logger.log_record(record(i))
    logger.stop_session()


def test_frozen_builds_log_to_a_per_user_directory(tmp_path, monkeypatch):
    from single_cell_cycler.config import cycler_config

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert cycler_config._resolve_log_dir() == tmp_path / "Bytehound" / "SingleCellCycler" / "logs"


def test_csv_log_rotates_at_256_mb(tmp_path, monkeypatch):
    assert AsyncTelemetryLogger.MAX_FILE_BYTES == 256 * 1024 * 1024
    monkeypatch.setattr(AsyncTelemetryLogger, "MAX_FILE_BYTES", 2_000)   # same logic, small files
    logger = AsyncTelemetryLogger(log_dir=tmp_path)
    first = logger.start_session("run")
    write_records(logger, 400)
    parts = sorted(p.name for p in tmp_path.glob("run_*.csv"))
    assert len(parts) >= 3, parts
    assert first.name in parts
    for p in tmp_path.glob("run_*.csv"):
        assert p.read_text().startswith("timestamp_iso,"), f"{p.name} has no CSV header"


@pytest.mark.xfail(strict=True, reason=(
    "Open finding: each rotated part is named from the previous part's stem, so the third "
    "file is 'run_<ts>_part001_part002.csv' instead of 'run_<ts>_part002.csv'."))
def test_rotated_parts_are_numbered_from_the_session_name(tmp_path, monkeypatch):
    monkeypatch.setattr(AsyncTelemetryLogger, "MAX_FILE_BYTES", 2_000)
    logger = AsyncTelemetryLogger(log_dir=tmp_path)
    stem = logger.start_session("run").stem
    write_records(logger, 400)
    names = {p.name for p in tmp_path.glob("run_*.csv")}
    assert {f"{stem}_part001.csv", f"{stem}_part002.csv"} <= names, sorted(names)


def test_logging_pauses_below_1_gb_free_and_resumes_after(tmp_path, monkeypatch):
    import single_cell_cycler.data.async_logger as async_logger

    assert AsyncTelemetryLogger.MIN_FREE_BYTES == 1024 ** 3
    free = {"bytes": 500 * 1024 ** 2}
    monkeypatch.setattr(async_logger.shutil, "disk_usage", lambda _p: Usage(0, 0, free["bytes"]))
    logger = AsyncTelemetryLogger(log_dir=tmp_path)
    path = logger.start_session("lowdisk")
    for i in range(50):
        logger.log_record(record(i))
    time.sleep(1.0)
    assert path.read_text().count("\n") == 1, "rows written with < 1 GB free"
    free["bytes"] = 5 * 1024 ** 3
    write_records(logger, 50)
    assert path.read_text().count("\n") > 1, "logging did not resume once space was back"


def test_webhook_failures_retry_with_backoff_without_blocking_the_caller(monkeypatch):
    from single_cell_cycler.comm.webhook_notifier import WebhookNotifier, WebhookSettings

    attempts = []

    def flaky_post(self, url, payload, timeout_s=4.0):
        attempts.append(time.monotonic())
        return (len(attempts) >= 3, "simulated outage")

    monkeypatch.setattr(WebhookNotifier, "_post_http", flaky_post)   # never touches the network
    notifier = WebhookNotifier(WebhookSettings(url="https://example.invalid/hook", enabled=True))
    try:
        t0 = time.monotonic()
        notifier.notify_test_started(cell_id=1, recipe_name="R", chemistry="NMC", steps_count=4)
        assert time.monotonic() - t0 < 0.1, "notify blocked the caller"
        deadline = time.monotonic() + 6
        while len(attempts) < 3 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert len(attempts) == 3
        gaps = [b - a for a, b in zip(attempts, attempts[1:], strict=False)]
        assert gaps[0] == pytest.approx(1.0, abs=0.3) and gaps[1] == pytest.approx(2.0, abs=0.3), gaps
    finally:
        notifier.close()


@posix_only
def test_alerts_carry_the_configured_bms_id_else_the_port(cycler, cell):
    # Fixture connected with no BMS ID configured: falls back to the port
    # (a pty has no USB serial number).
    assert cycler.lbl_bms_identity.text() == f"BMS: {cell.port}"
    cycler.webhook_notifier.settings.bms_serial_number = "BMS-LAB-007"
    cycler._set_bms_identity_from_port(cell.port)
    assert cycler.lbl_bms_identity.text() == "BMS: BMS-LAB-007"


@posix_only
def test_serial_link_reconnects_when_the_port_appears(qapp, cell, tmp_path):
    from single_cell_cycler.comm.transceiver import SerialTransceiver

    link = tmp_path / "ttyBMS"            # the port does not exist yet (cable unplugged)
    transceiver = SerialTransceiver()
    rx, transceiver_states = [], []
    transceiver.cell_data_received.connect(rx.append)
    transceiver.connection_changed.connect(lambda state, msg: transceiver_states.append(state))
    transceiver.connect_serial(str(link))
    try:
        wait_until(lambda: "error" in " ".join(transceiver_states).lower(), 3, "port-unavailable state")
        os.symlink(cell.port, link)       # cable plugged back in
        wait_until(lambda: len(rx) >= 3, 8, "telemetry after the port appeared")
    finally:
        transceiver.disconnect_serial(send_safe_zero=False)
