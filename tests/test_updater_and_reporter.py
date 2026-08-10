"""Unit tests for the auto-updater and issue reporter modules."""

import base64
import hashlib
import json
import os
import tempfile
import urllib.error
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.ui.dialogs import ReportIssueDialog
from app.ui.report_issue import IssueReporter
from app.ui.updater import UpdateChecker, UpdateDownloader, get_current_version


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ─────────────────────────────────────────────────────────────────────────────
# Auto-Updater Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_get_current_version():
    ver = get_current_version()
    assert isinstance(ver, str)
    assert len(ver) > 0


def test_update_checker_update_available(monkeypatch, tmp_path):
    version_file = tmp_path / "version.json"
    local_data = {
        "version": "1.0.0",
        "manifest_url": "https://example.com/manifest.json"
    }
    version_file.write_text(json.dumps(local_data), encoding="utf-8")
    monkeypatch.setattr("app.ui.updater.VERSION_FILE", version_file)

    remote_data = {
        "version": "1.1.0",
        "installer_url": "https://example.com/Bytehound_Setup.exe",
        "release_notes": "New features and fixes",
        "sha256": "abc123def456"
    }

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(remote_data).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    checker = UpdateChecker()
    results = {}

    checker.update_available.connect(
        lambda ver, url, notes, sha: results.update(
            {"version": ver, "url": url, "notes": notes, "sha": sha}
        )
    )

    with patch("urllib.request.urlopen", return_value=mock_response):
        checker.run()

    assert results["version"] == "1.1.0"
    assert results["url"] == "https://example.com/Bytehound_Setup.exe"
    assert results["notes"] == "New features and fixes"
    assert results["sha"] == "abc123def456"


def test_update_checker_up_to_date(monkeypatch, tmp_path):
    version_file = tmp_path / "version.json"
    local_data = {
        "version": "1.1.0",
        "manifest_url": "https://example.com/manifest.json"
    }
    version_file.write_text(json.dumps(local_data), encoding="utf-8")
    monkeypatch.setattr("app.ui.updater.VERSION_FILE", version_file)

    remote_data = {"version": "1.1.0"}

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(remote_data).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    checker = UpdateChecker()
    up_to_date_emitted = []

    checker.up_to_date.connect(lambda: up_to_date_emitted.append(True))

    with patch("urllib.request.urlopen", return_value=mock_response):
        checker.run()

    assert up_to_date_emitted == [True]


def test_update_downloader_success(tmp_path):
    payload = b"Fake installer content"
    expected_hash = hashlib.sha256(payload).hexdigest()

    dest_file = tmp_path / "installer.exe"

    mock_response = MagicMock()
    mock_response.getheader.return_value = str(len(payload))
    mock_response.read.side_effect = [payload, b""]
    mock_response.__enter__.return_value = mock_response

    downloader = UpdateDownloader(
        "https://example.com/setup.exe",
        str(dest_file),
        expected_sha256=expected_hash
    )

    finished_file = []
    downloader.finished.connect(lambda path: finished_file.append(path))

    with patch("urllib.request.urlopen", return_value=mock_response):
        downloader.run()

    assert len(finished_file) == 1
    assert finished_file[0] == str(dest_file)
    assert dest_file.read_bytes() == payload


def test_update_downloader_hash_mismatch(tmp_path):
    payload = b"Fake installer content"
    wrong_hash = "0000000000000000000000000000000000000000000000000000000000000000"

    dest_file = tmp_path / "installer.exe"

    mock_response = MagicMock()
    mock_response.getheader.return_value = str(len(payload))
    mock_response.read.side_effect = [payload, b""]
    mock_response.__enter__.return_value = mock_response

    downloader = UpdateDownloader(
        "https://example.com/setup.exe",
        str(dest_file),
        expected_sha256=wrong_hash
    )

    errors = []
    downloader.error.connect(lambda err: errors.append(err))

    with patch("urllib.request.urlopen", return_value=mock_response):
        downloader.run()

    assert len(errors) == 1
    assert "integrity check" in errors[0]
    assert not dest_file.exists()


# ─────────────────────────────────────────────────────────────────────────────
# Issue Reporter Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_issue_reporter_success(qapp):
    reporter = IssueReporter(
        title="Test Bug",
        description="Something failed",
        diagnostics="OS: Win11",
        log_content="Log line 1\nLog line 2",
        attachments=[],
        worker_url="https://example.com/report_issue"
    )

    results = []
    reporter.finished.connect(lambda success, msg: results.append((success, msg)))

    mock_response = MagicMock()
    mock_response.status = 201
    mock_response.__enter__.return_value = mock_response

    captured_req = []

    def mock_urlopen(req, data=None, timeout=None):
        captured_req.append((req, json.loads(data.decode("utf-8"))))
        return mock_response

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        reporter.run()

    assert len(results) == 1
    assert results[0][0] is True
    assert "successfully" in results[0][1]

    assert len(captured_req) == 1
    req_body = captured_req[0][1]
    assert req_body["title"] == "[App Report] Test Bug"
    assert "Something failed" in req_body["body"]
    assert "OS: Win11" in req_body["body"]


def test_issue_reporter_http_error(qapp):
    reporter = IssueReporter(
        title="Test Bug",
        description="Something failed",
        diagnostics="OS: Win11",
        log_content=None,
        attachments=[],
        worker_url="https://example.com/report_issue"
    )

    results = []
    reporter.finished.connect(lambda success, msg: results.append((success, msg)))

    def mock_urlopen(req, data=None, timeout=None):
        raise urllib.error.HTTPError("url", 403, "Forbidden", {}, None)

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        reporter.run()

    assert len(results) == 1
    assert results[0][0] is False
    assert "HTTP 403" in results[0][1]


def test_report_issue_dialog_data(qapp, tmp_path):
    dlg = ReportIssueDialog()
    dlg._title_input.setText("GUI Crash on connect")
    dlg._desc_input.setPlainText("App freezes when clicking connect.")

    # Attach dummy file
    dummy_file = tmp_path / "test_attachment.txt"
    dummy_file.write_text("Hello World", encoding="utf-8")
    dlg._add_attachment(str(dummy_file))

    title, desc, attachments = dlg.get_data()
    assert title == "GUI Crash on connect"
    assert desc == "App freezes when clicking connect."
    assert len(attachments) == 1
    assert attachments[0]["name"] == "test_attachment.txt"
    assert attachments[0]["data"] == b"Hello World"
