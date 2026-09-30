"""Unit tests for IMP-13: Remote Lab Notifications (Discord / Slack / Teams Webhooks)."""

import json
import os
import urllib.error
import pytest
from unittest.mock import MagicMock, patch

from single_cell_cycler.comm.webhook_notifier import (
    NotificationEvent,
    WebhookNotifier,
    WebhookSettings,
    build_universal_payload,
)
from single_cell_cycler.ui.widgets.webhook_dialog import WebhookSettingsDialog


def test_build_universal_payload():
    """Verify universal payload format includes Discord embeds and Slack text fallback.

    Note: 'attachments' was intentionally removed from the payload — Discord's Webhooks
    API rejects Slack-formatted attachment objects with HTTP 400. The payload now uses
    Discord-native 'embeds' + a plain 'text' field as a Slack-compatible fallback.
    """
    fields = [
        {"name": "Recipe", "value": "1C_Cycling"},
        {"name": "Cell", "value": "Cell 2"},
    ]
    payload = build_universal_payload(
        event=NotificationEvent.TEST_STARTED,
        title="Test Commenced",
        description="Cycling test started",
        fields=fields,
        color=0x22C55E,
    )

    # Discord native fields
    assert "content" in payload
    assert "**[Bytehound Lab Alert]**" in payload["content"]
    assert "embeds" in payload
    assert len(payload["embeds"]) == 1
    assert payload["embeds"][0]["title"] == "Test Commenced"
    assert payload["embeds"][0]["color"] == 0x22C55E
    assert len(payload["embeds"][0]["fields"]) == 2
    assert payload["embeds"][0]["footer"]["text"] == "Bytehound Single-Cell BMS Cycler"

    # Slack plain-text fallback field
    assert "text" in payload
    assert "Test Commenced" in payload["text"]

    # Discord's API rejects Slack-formatted 'attachments' with HTTP 400 — must not be present
    assert "attachments" not in payload


def test_webhook_settings_persistence(tmp_path):
    """Verify settings save and load to/from JSON."""
    cfg_file = tmp_path / "webhook_settings.json"
    settings = WebhookSettings(
        url="https://discord.com/api/webhooks/test/123",
        enabled=True,
        notify_test_started=True,
        notify_step_completed=True,
        notify_cycle_completed=True,
        notify_safety_trip=True,
        notify_test_completed=False,
        notify_test_paused_resumed=True,
        notify_emergency_stop=True,
        operator_tag="Metrologist Alice",
        bms_serial_number="BMS-TEST-0042",
    )
    settings.save(cfg_file)
    assert cfg_file.exists()

    loaded = WebhookSettings.load(cfg_file)
    assert loaded.url == settings.url
    assert loaded.enabled is True
    assert loaded.notify_step_completed is True
    assert loaded.notify_cycle_completed is True
    assert loaded.notify_test_completed is False
    assert loaded.operator_tag == "Metrologist Alice"
    assert loaded.bms_serial_number == "BMS-TEST-0042"


def test_webhook_payload_includes_bms_identity():
    settings = WebhookSettings(
        url="https://discord.com/api/webhooks/mock",
        enabled=True,
        bms_serial_number="BMS-TEST-0042",
    )
    notifier = WebhookNotifier(settings=settings)
    payload = build_universal_payload(
        event=NotificationEvent.SAFETY_TRIP,
        title="Safety Trip",
        description="Trip",
        fields=[],
        color=0xEF4444,
    )
    notifier._add_bms_identity(payload)
    assert payload["embeds"][0]["fields"][0] == {
        "name": "BMS Serial / Device ID",
        "value": "BMS-TEST-0042",
        "inline": True,
    }
    assert "BMS-TEST-0042" in payload["content"]
    notifier.close()


def test_webhook_notifier_dispatch_success():
    """Verify successful HTTP POST delivery via mocked urlopen."""
    settings = WebhookSettings(
        url="https://discord.com/api/webhooks/mock",
        enabled=True,
    )
    notifier = WebhookNotifier(settings=settings)

    mock_resp = MagicMock()
    mock_resp.status = 204
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        success, msg = notifier.send_ping()
        assert success is True
        assert "204" in msg

    notifier.close()


def test_webhook_notifier_network_failure_graceful():
    """Verify network disconnects or HTTP errors do not raise or crash."""
    settings = WebhookSettings(
        url="https://discord.com/api/webhooks/offline",
        enabled=True,
    )
    notifier = WebhookNotifier(settings=settings)

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("DNS Resolution Failed")):
        success, msg = notifier.send_ping()
        assert success is False
        assert "DNS Resolution Failed" in msg

    # Notification queue dispatch should not throw for all event types
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Offline")):
        notifier.notify_test_started(1, "RecipeA", "NMC", 4)
        notifier.notify_step_completed(
            cell_id=1,
            cycle_idx=1,
            step_idx=1,
            step_name="CC Charge",
            step_type="charge",
            next_step_desc="Step 2: Rest (15m)",
            capacity_mah=1250.4,
            energy_mwh=4850.0,
            duration_s=3600.0,
            end_voltage_v=4.20,
            peak_current_a=1.5,
            peak_temp_c=28.5,
            cutoff_reason="Voltage >= 4.20V",
            dcir_mohm=22.4,
        )
        notifier.notify_cycle_completed(
            cell_id=1,
            cycle_idx=1,
            total_cycles=5,
            charge_cap_mah=2500.0,
            discharge_cap_mah=2480.0,
            coulombic_eff_pct=99.2,
            energy_eff_pct=93.5,
            duration_s=7200.0,
            dcir_mohm=23.1,
        )
        notifier.notify_test_paused(1, "CC Charge", 4.10, 1.5)
        notifier.notify_test_resumed(1, "CC Charge", 4.10, 1.5)
        notifier.notify_emergency_stop(1, "CC Charge", 4.10, 1.5)
        notifier.notify_safety_trip(1, "Voltage OOR", 4.35, 1.0, 25.0)
        notifier.notify_test_completed(1, "RecipeA", 5, 2450.0, 9.1, 3600.0)

    notifier.close()


def test_webhook_dialog_interaction():
    """Verify WebhookSettingsDialog loads, allows editing, and saves."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    settings = WebhookSettings(url="https://hooks.slack.com/services/XYZ", enabled=False)
    notifier = WebhookNotifier(settings=settings)

    dlg = WebhookSettingsDialog(notifier=notifier)
    assert dlg.edit_url.text() == "https://hooks.slack.com/services/XYZ"
    assert dlg.chk_enable.isChecked() is False
    assert hasattr(dlg, "chk_step")
    assert hasattr(dlg, "chk_cycle")
    assert hasattr(dlg, "chk_pause")
    assert hasattr(dlg, "chk_estop")
    assert hasattr(dlg, "edit_bms_serial")

    # Simulate user enabling and changing operator tag
    dlg.chk_enable.setChecked(True)
    dlg.chk_step.setChecked(True)
    dlg.chk_cycle.setChecked(True)
    dlg.edit_operator.setText("Lead Engineer Bob")
    dlg.edit_bms_serial.setText("BMS-LAB-001")
    dlg._on_save()

    assert settings.enabled is True
    assert settings.notify_step_completed is True
    assert settings.notify_cycle_completed is True
    assert settings.operator_tag == "Lead Engineer Bob"
    assert settings.bms_serial_number == "BMS-LAB-001"
    notifier.close()


# --- Identification, live readings, CSV upload -------------------------------------------------

def _ctx():
    return {
        "cell": 2, "port": "COM15", "adapter": "(Silicon Labs CP210x, SN 0001)", "host": "LAB-PC-07",
        "run_id": "20260930-140541", "recipe": "CCCV Cycling (15 Cycles)", "chemistry": "NMC",
        "app_version": "v1.2.3",
        "live_lines": ["State        : Running", "Voltage      : 4.119 V", "Current      : +1.161 A"],
    }


def test_every_message_identifies_device_cell_host_and_run():
    n = WebhookNotifier(settings=WebhookSettings(url="https://discord.com/api/webhooks/1/x", bms_serial_number="BMS-LAB-001"))
    n.context_provider = _ctx
    captured = []
    n._queue_json = captured.append
    n.notify_test_started(2, "CCCV Cycling (15 Cycles)", "NMC", 5)
    p = captured[0]
    embed = p["embeds"][0]
    assert p["content"].startswith("**[BMS-LAB-001 · Cell 2]**")        # visible in the push preview
    assert "LAB-PC-07" in embed["author"]["name"] and "COM15" in embed["author"]["name"]
    names = [f["name"] for f in embed["fields"]]
    assert names[0] == "BMS Serial / Device ID"
    assert "🔎 Device & Run" in names and "📊 Readings at this moment" in names
    device = next(f["value"] for f in embed["fields"] if f["name"] == "🔎 Device & Run")
    for text in ("BMS-LAB-001", "COM15", "SN 0001", "LAB-PC-07", "20260930-140541", "v1.2.3"):
        assert text in device
    assert len(embed["fields"]) <= 25 and all(len(f["value"]) <= 1024 for f in embed["fields"])
    n.close()


def test_stop_is_now_reported():
    n = WebhookNotifier(settings=WebhookSettings(url="https://discord.com/api/webhooks/1/x"))
    captured = []
    n._queue_json = captured.append
    n.notify_test_stopped(2, "1. CC/CV Charge")
    assert "Test Stopped" in captured[0]["embeds"][0]["title"]
    n.close()


def test_run_files_are_zipped_and_split_under_the_upload_limit(tmp_path):
    import zipfile
    from single_cell_cycler.comm.webhook_notifier import package_run_files
    tele = tmp_path / "run.csv"
    rows = ["timestamp,voltage_v,current_a\n"] + [f"2026-09-30T08:36:{k % 60:02d}Z,{4.0 + (k % 97) / 1000:.3f},{1.2:.3f}\n" for k in range(120_000)]
    tele.write_text("".join(rows), encoding="utf-8")
    steps = tmp_path / "summary_steps_1.csv"
    steps.write_text("cycle,step\n1,1\n", encoding="utf-8")

    parts = package_run_files([tele, steps], tmp_path / "out", "20260930-140541_Cell2_BMS", part_limit=200_000)
    assert len(parts) >= 2
    rebuilt = []
    for zp in parts:
        assert zp.stat().st_size <= 200_000 * 1.1
        with zipfile.ZipFile(zp) as z:
            for name in z.namelist():
                text = z.read(name).decode()
                if name.startswith("run_chunk"):
                    assert text.startswith("timestamp,voltage_v,current_a\n")   # every chunk opens alone
                    rebuilt.extend(text.splitlines()[1:])
    assert len(rebuilt) == 120_000                           # no row lost or duplicated


def test_slack_gets_a_file_listing_instead_of_an_upload(tmp_path):
    f = tmp_path / "run.csv"
    f.write_text("a,b\n1,2\n", encoding="utf-8")
    n = WebhookNotifier(settings=WebhookSettings(url="https://hooks.slack.com/services/T/B/C"))
    captured = []
    n._queue_json = captured.append
    n.send_run_files([f], "Completed", tmp_path / "up")
    assert captured and "Saved on workstation" in json.dumps(captured[0])
    n.close()


def test_tests_never_touch_the_real_settings_file():
    from single_cell_cycler.comm import webhook_notifier
    assert "pytest" in str(webhook_notifier.CONFIG_PATH).lower() or "tmp" in str(webhook_notifier.CONFIG_PATH).lower()


def test_installed_app_keeps_webhook_settings_in_localappdata(monkeypatch, tmp_path):
    """Program Files is read-only and the file holds a secret: never inside the install folder."""
    import sys
    from single_cell_cycler.comm import webhook_notifier
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    path = webhook_notifier._resolve_settings_path()
    assert path == tmp_path / "Bytehound" / "SingleCellCycler" / "webhook_settings.json"


def test_template_has_no_webhook_url():
    import json
    from pathlib import Path
    tmpl = Path(__file__).resolve().parent.parent / "config" / "webhook_settings.example.json"
    assert json.loads(tmpl.read_text(encoding="utf-8"))["url"] == ""
