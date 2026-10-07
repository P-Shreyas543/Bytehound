"""Test isolation for the cycler suite.

- Webhook settings: every test gets its own temporary settings file, so tests can never
  overwrite the operator's real config/webhook_settings.json (they used to, replacing the
  Discord URL with a dummy one).
- Network: real HTTP is blocked, so no test can post fake alerts to a real channel. Tests that
  exercise delivery patch urllib.request.urlopen themselves, which overrides this block.
- Logs: tests write telemetry CSVs and crash-recovery journals into a temporary folder instead
  of the operator's real single_cell_cycler/logs/ folder. DEFAULT_LOG_DIR is patched across all
  modules that import it by value.
"""

import json
import urllib.error
import urllib.request

import pytest


@pytest.fixture(scope="session", autouse=True)
def _offscreen_qt_with_real_fonts():
    """Headless Qt has no fonts of its own; its fallback is far wider than Segoe UI and inflates
    every layout (the 1280x720 fit test measured a 1700 px minimum width). Load the fonts the
    app actually runs with."""
    import os
    from pathlib import Path

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "seguisym.ttf", "consola.ttf"):
        if (fonts / name).exists():
            QFontDatabase.addApplicationFont(str(fonts / name))
    app.setFont(QFont("Segoe UI", 10))
    yield


@pytest.fixture(autouse=True)
def _isolate_webhook(tmp_path, monkeypatch):
    from single_cell_cycler.comm import webhook_notifier

    cfg = tmp_path / "webhook_settings.json"
    cfg.write_text(
        json.dumps({
            "url": "https://discord.com/api/webhooks/0/test-only",
            "enabled": True,
            "workstation": "Test Workstation",
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(webhook_notifier, "CONFIG_PATH", cfg)

    def _blocked(*args, **kwargs):
        raise urllib.error.URLError("network disabled in tests")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)
    yield


@pytest.fixture(scope="session", autouse=True)
def _real_settings_file_unchanged():
    """Fail the run if any test rewrote the real cycler_settings.json (it holds safety switches)."""
    import single_cell_cycler.config.cycler_config as _cfg

    real = _cfg.SETTINGS_PATH
    before = real.read_bytes() if real.exists() else None
    yield
    after = real.read_bytes() if real.exists() else None
    if after != before:
        if before is not None:
            real.write_bytes(before)        # put the operator's settings back
        pytest.fail(f"A test modified the real settings file {real}; restored it", pytrace=False)


@pytest.fixture(autouse=True)
def _isolate_logs(tmp_path, monkeypatch):
    test_logs = tmp_path / "logs"
    test_logs.mkdir(parents=True, exist_ok=True)

    modules_to_patch = [
        "single_cell_cycler.config.cycler_config",
        "single_cell_cycler.config",
        "single_cell_cycler.core.state_journal",
        "single_cell_cycler.data.async_logger",
        "single_cell_cycler.data.run_exporter",
        "single_cell_cycler.data.report_generator",
        "single_cell_cycler.ui.main_window",
    ]
    for mod_name in modules_to_patch:
        try:
            mod = __import__(mod_name, fromlist=["DEFAULT_LOG_DIR"])
            monkeypatch.setattr(mod, "DEFAULT_LOG_DIR", test_logs)
        except (ImportError, AttributeError):
            pass

    try:
        import single_cell_cycler.main as _main
        monkeypatch.setattr(_main, "DEFAULT_LOG_DIR", test_logs)
    except (ImportError, AttributeError):
        pass

    # cycler_settings.json: tests read a copy, so toggling a safety setting never rewrites the
    # tracked file (or an installed app's LOCALAPPDATA file)
    import shutil
    import single_cell_cycler.config.cycler_config as _cfg
    settings_copy = tmp_path / "cycler_settings.json"
    if _cfg.SETTINGS_PATH.exists():
        shutil.copyfile(_cfg.SETTINGS_PATH, settings_copy)
    monkeypatch.setattr(_cfg, "SETTINGS_PATH", settings_copy)

    yield test_logs

