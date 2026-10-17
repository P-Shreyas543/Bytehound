"""Project-root conftest: ensure `app` package is importable from tests.

pytest rootdir defaults to this file's directory, so adding it to
``sys.path`` makes `from app.protocol.crc import ...` resolve regardless
of where pytest is invoked from.
"""

from __future__ import annotations

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


def pytest_sessionfinish(session, exitstatus):
    """Tear Qt down while QApplication is still alive.

    The suite intermittently exited with code 139 after every test passed:
    an access violation in the interpreter's final garbage collection (Python
    wrappers of Qt objects freed after Qt was gone). Destroy every top-level
    widget and run the deferred deletions now, then collect.
    """
    try:
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QApplication
    except Exception:
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in list(app.topLevelWidgets()):
        try:
            w.close()
            w.deleteLater()
        except RuntimeError:
            pass
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    import gc
    gc.collect()
