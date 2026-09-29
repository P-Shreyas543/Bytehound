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
        notify_safety_trip=True,
        notify_test_completed=False,
        operator_tag="Metrologist Alice",
    )
    settings.save(cfg_file)
    assert cfg_file.exists()

    loaded = WebhookSettings.load(cfg_file)
    assert loaded.url == settings.url
    assert loaded.enabled is True
    assert loaded.notify_test_completed is False
    assert loaded.operator_tag == "Metrologist Alice"


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

    # Notification queue dispatch should not throw
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Offline")):
        notifier.notify_test_started(1, "RecipeA", "NMC", 4)
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

    # Simulate user enabling and changing operator tag
    dlg.chk_enable.setChecked(True)
    dlg.edit_operator.setText("Lead Engineer Bob")
    dlg._on_save()

    assert settings.enabled is True
    assert settings.operator_tag == "Lead Engineer Bob"
    notifier.close()
