"""Project-root conftest: ensure `app` package is importable from tests.

pytest rootdir defaults to this file's directory, so adding it to
``sys.path`` makes `from app.protocol.crc import ...` resolve regardless
of where pytest is invoked from.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
import pytest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def mock_temp_log_recovery():
    """Ensure tests never block on the GUI recovery prompt for orphaned logs."""
    with patch("app.ui.main_window.MainWindow._check_and_recover_temp_logs", return_value=None):
        yield


# ---------------------------------------------------------------------------
# Settings isolation: tests must never read or write the user's real
# Bytehound settings (Windows registry), and two test runs must not race on
# them (seen: test_window_state_schema_version_discards_stale_blobs failing
# while two suites ran at once). Every QSettings(org, app) — wherever it is
# constructed — is redirected to an .ini file in a per-run temp folder.
# Explicit file-based QSettings(path, format) pass through unchanged.
# ---------------------------------------------------------------------------
import PySide6.QtCore as _QtCore  # noqa: E402

_RealQSettings = _QtCore.QSettings


def _make_isolated_qsettings(folder: Path):
    class IsolatedQSettings(_RealQSettings):
        def __init__(self, *args, **kwargs):
            if len(args) >= 2 and isinstance(args[1], _RealQSettings.Format):
                super().__init__(*args, **kwargs)          # (path, format): a real file
                return
            names = [a for a in args if isinstance(a, str)]
            if not names:
                app = _QtCore.QCoreApplication
                names = [app.organizationName() or "Bytehound", app.applicationName() or "Bytehound"]
            org = names[0]
            app_name = names[1] if len(names) > 1 else ""
            safe = "".join(ch if ch.isalnum() else "_" for ch in f"{org}__{app_name}")
            parent = next((a for a in args if isinstance(a, _QtCore.QObject)), None)
            super().__init__(str(folder / f"{safe}.ini"), _RealQSettings.Format.IniFormat, parent)

    return IsolatedQSettings


@pytest.fixture(autouse=True, scope="session")
def _isolated_config_history(tmp_path_factory):
    """Rollback history (Part C4) goes to a temp folder, never the user's
    app data."""
    old = os.environ.get("BYTEHOUND_CONFIG_HISTORY_DIR")
    os.environ["BYTEHOUND_CONFIG_HISTORY_DIR"] = str(tmp_path_factory.mktemp("config_history"))
    yield
    if old is None:
        os.environ.pop("BYTEHOUND_CONFIG_HISTORY_DIR", None)
    else:
        os.environ["BYTEHOUND_CONFIG_HISTORY_DIR"] = old


@pytest.fixture(autouse=True, scope="session")
def _isolated_qsettings(tmp_path_factory):
    folder = tmp_path_factory.mktemp("qsettings")
    isolated = _make_isolated_qsettings(folder)
    patched = []
    _QtCore.QSettings = isolated
    for mod in list(sys.modules.values()):
        try:
            if getattr(mod, "QSettings", None) is _RealQSettings:
                mod.QSettings = isolated
                patched.append(mod)
        except Exception:
            continue
    yield folder
    _QtCore.QSettings = _RealQSettings
    for mod in patched:
        mod.QSettings = _RealQSettings


_FINAL_EXIT_STATUS = None


def pytest_sessionfinish(session, exitstatus):
    """Remember pytest's verdict for :func:`pytest_unconfigure`."""
    global _FINAL_EXIT_STATUS
    _FINAL_EXIT_STATUS = int(exitstatus)


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    """Exit with pytest's own status once every report has been written.

    With a QApplication alive the interpreter's final teardown frees Python
    wrappers of Qt objects after Qt is gone and intermittently dies with an
    access violation (exit 139) after every test passed. Destroying the
    leftover widgets first does not help: flushing their deferred deletes
    aborts too, and so did ``os._exit`` on Windows (DLL detach). Nothing
    useful happens after this hook, so end the process without teardown.
    """
    if _FINAL_EXIT_STATUS is None:
        return
    import os
    if os.environ.get("BYTEHOUND_TEST_NORMAL_EXIT"):
        # Diagnostics (task.md Phase 4): run the normal interpreter teardown
        # to observe the underlying exit failure instead of hiding it.
        return
    try:
        from PySide6.QtCore import QCoreApplication
    except Exception:
        return
    if QCoreApplication.instance() is None:
        return
    sys.stdout.flush()
    sys.stderr.flush()
    if sys.platform == "win32":
        # os._exit() calls ExitProcess, which still runs every DLL's detach
        # routine, and Qt's crashed there (access violation inside os._exit,
        # seen 2026-10-17). TerminateProcess does not notify DLLs.
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        kernel32.TerminateProcess(kernel32.GetCurrentProcess(), _FINAL_EXIT_STATUS)
    os._exit(_FINAL_EXIT_STATUS)
