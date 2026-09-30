"""Test isolation for the cycler suite.

- Webhook settings: every test gets its own temporary settings file, so tests can never
  overwrite the operator's real config/webhook_settings.json (they used to, replacing the
  Discord URL with a dummy one).
- Network: real HTTP is blocked, so no test can post fake alerts to a real channel. Tests that
  exercise delivery patch urllib.request.urlopen themselves, which overrides this block.
"""

import json
import urllib.error
import urllib.request

import pytest


@pytest.fixture(autouse=True)
def _isolate_webhook(tmp_path, monkeypatch):
    from single_cell_cycler.comm import webhook_notifier

    cfg = tmp_path / "webhook_settings.json"
    cfg.write_text(json.dumps({"url": "https://discord.com/api/webhooks/0/test-only", "enabled": True}), encoding="utf-8")
    monkeypatch.setattr(webhook_notifier, "CONFIG_PATH", cfg)

    def _blocked(*args, **kwargs):
        raise urllib.error.URLError("network disabled in tests")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)
    yield
