"""Help → Report Issue posts a *public* GitHub issue (owner review
2026-10-23): the loaded configuration is sent only when the user ticks it,
diagnostics carry the app version but not the whole settings store, and
the user's folder / name are hidden."""

from __future__ import annotations

import io
import urllib.error
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.ui import report_issue as ri


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _host(tmp_path, config_path):
    s = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    s.setValue("recent_configs", [str(Path.home() / "secret" / "customer.xlsx")])
    s.setValue("conn/host", "10.1.2.3")
    s.setValue("logging/fixed_step_s", 0.2)

    class Host(ri.ReportIssueMixin):
        _version_info = {"version": "9.9.9", "issue_url": "https://example.invalid/report"}
        _config_path = config_path
        _settings = s
        _serial = None
        _logging = False
        _packet_count = _error_count = _timeouts = _rx_bytes = _tx_bytes = 0

        def __init__(self):
            from datetime import datetime
            self._session_started = datetime.now()
            self.activity = []
            self.popups = []

        def _log_activity(self, text):
            self.activity.append(text)

        def _popup_information(self, *a):
            self.popups.append(("info", a))

        def _popup_critical(self, *a):
            self.popups.append(("critical", a))

        @staticmethod
        def _find_log_file_path():
            return None

    return Host()


def _submit(monkeypatch, host, *, include_config, include_diag=True):
    sent = {}

    class Dialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, parent):
            pass

        def exec(self):
            return 1

        def get_data(self):
            return "Title", "Description", []

        def include_config(self):
            return include_config

        def include_diagnostics(self):
            return include_diag

    class Reporter:
        def __init__(self, title, description, diagnostics, log_content, attachments, url, parent):
            sent.update(diagnostics=diagnostics, log=log_content, attachments=attachments)
            self.finished = type("S", (), {"connect": lambda self_, f: None})()

        def start(self):
            pass

    monkeypatch.setattr(ri, "ReportIssueDialog", Dialog)
    monkeypatch.setattr(ri, "IssueReporter", Reporter)
    monkeypatch.setattr(ri, "QProgressDialog", lambda *a, **k: _NullProgress())
    host._on_report_issue()
    return sent


class _NullProgress:
    canceled = type("S", (), {"connect": lambda self, f: None})()

    def __getattr__(self, name):
        return lambda *a, **k: None


def test_the_dialog_says_reports_are_public_and_sends_no_configuration_by_default(qapp):
    from PySide6.QtWidgets import QLabel

    from app.ui.dialogs import ReportIssueDialog

    dlg = ReportIssueDialog()
    assert dlg.include_config() is False and dlg.include_diagnostics() is True
    assert any("public" in w.text() for w in dlg.findChildren(QLabel))


def test_the_configuration_is_attached_only_when_ticked(qapp, tmp_path, monkeypatch):
    cfg = tmp_path / "device.xlsx"
    cfg.write_bytes(b"PK device layout")
    host = _host(tmp_path, cfg)
    assert _submit(monkeypatch, host, include_config=False)["attachments"] == []
    attached = _submit(monkeypatch, host, include_config=True)["attachments"]
    assert [a["name"] for a in attached] == ["auto_config_device.xlsx"]


def test_diagnostics_name_the_version_and_leave_out_personal_settings(qapp, tmp_path, monkeypatch):
    host = _host(tmp_path, Path.home() / "Documents" / "exp.xlsx")
    diag = _submit(monkeypatch, host, include_config=False)["diagnostics"]
    assert "Bytehound: 9.9.9" in diag
    assert "logging/fixed_step_s" in diag
    assert "recent_configs" not in diag and "10.1.2.3" not in diag
    assert str(Path.home()) not in diag and "%USERPROFILE%" in diag


def test_without_diagnostics_only_the_version_is_sent(qapp, tmp_path, monkeypatch):
    sent = _submit(monkeypatch, _host(tmp_path, None), include_config=False, include_diag=False)
    assert sent["diagnostics"] == "Bytehound 9.9.9 (diagnostics not included)" and sent["log"] is None


def test_redaction_hides_the_home_folder_and_user_name(monkeypatch):
    monkeypatch.setenv("USERNAME", "Ant")
    home = str(Path.home())
    text = f"{home}\\x.csv | {home.replace(chr(92), '/')}/y | user Ant | Antenna_Temp"
    out = ri._redact(text)
    assert home not in out and out.count("%USERPROFILE%") == 2
    assert "user <user>" in out and "Antenna_Temp" in out          # whole words only


def test_server_errors_are_explained_and_200_counts_as_success(qapp, monkeypatch):
    reporter = ri.IssueReporter("T", "D", "diag", None, [], "https://example.invalid/report")
    got = []
    reporter.finished.connect(lambda ok, msg: got.append((ok, msg)))

    def fail(req, data=None, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(b"bad user agent"))

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    reporter.run()
    assert got[-1] == (False, "HTTP 403: Forbidden (bad user agent)")

    class Ok:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Ok())
    reporter.run()
    assert got[-1][0] is True


def test_a_cancelled_report_shows_no_result_popup(qapp, tmp_path):
    host = _host(tmp_path, None)
    host._on_report_cancelled()
    host._on_report_finished(False, "timed out")
    assert host.popups == [] and "cancelled" in host.activity[-1]
