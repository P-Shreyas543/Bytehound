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


# Test files that exercise several modules together (a real MainWindow,
# worker threads, loggers writing to disk, sockets). Everything else under a
# tests/ directory is a unit test; tests/system and tests/acceptance carry
# their own level. See the markers in pytest.ini.
INTEGRATION_MODULES = {
    # main app
    "test_analysis_suite_integration", "test_backpressure_buffering",
    "test_bms_polling_smoke", "test_boolean_rx_tx_workflow", "test_boot_smoke",
    "test_exhaustive_user_scenarios", "test_gui_lifecycle_and_elements",
    "test_main_window_integration", "test_plot_layouts_and_resolutions",
    "test_plot_settings", "test_polling_worker", "test_popups_and_logging_guarantees",
    "test_reconnect", "test_serial_worker", "test_serial_workers_and_timing",
    "test_socket_io", "test_warning_badge",
    # single-cell cycler
    "test_crash_recovery_imp08", "test_gui_backlog_imp14", "test_preflight_ui_imp10",
    "test_report_generator_imp12", "test_run_exporter_imp11",
}
_LEVEL_DIRS = {"system", "acceptance"}


def pytest_collection_modifyitems(config, items):
    for item in items:
        path = Path(str(item.fspath))
        level = next((p for p in path.parts if p in _LEVEL_DIRS), None)
        if level is None:
            level = "integration" if path.stem in INTEGRATION_MODULES else "unit"
        item.add_marker(getattr(pytest.mark, level))


@pytest.fixture(autouse=True)
def mock_temp_log_recovery():
    """Ensure tests never block on the GUI recovery prompt for orphaned logs."""
    with patch("app.ui.main_window.MainWindow._check_and_recover_temp_logs", return_value=None):
        yield


@pytest.fixture(autouse=True)
def isolated_qsettings(tmp_path):
    """Point QSettings(APP_ORG, APP_NAME) at a fresh per-test directory.

    Without this every test shares the developer's real settings, so a value
    written by one test (theme, recent configs, plot layout, baud) leaks into
    the next and into the next real app launch. setPath has no effect on the
    Windows registry, so on Windows tests still share the real store.
    """
    from PySide6.QtCore import QSettings

    for fmt in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
        QSettings.setPath(fmt, QSettings.Scope.UserScope, str(tmp_path / "qsettings"))
    yield


@pytest.fixture(autouse=True)
def isolated_cycler_logs(tmp_path, monkeypatch):
    """Send the single-cell cycler's CSV logs and crash-recovery journal to a
    per-test directory. In a dev checkout DEFAULT_LOG_DIR is
    single_cell_cycler/logs, and a journal left there by a test makes the
    next real launch offer to resume a run that never happened."""
    for name in ("single_cell_cycler.data.async_logger",
                 "single_cell_cycler.core.state_journal",
                 "single_cell_cycler.ui.main_window"):
        module = sys.modules.get(name)
        if module is not None:
            monkeypatch.setattr(module, "DEFAULT_LOG_DIR", tmp_path / "cycler_logs")


@pytest.fixture(autouse=True)
def delete_leaked_windows():
    """Delete top-level widgets a test created and left behind.

    Tests close their MainWindow but never delete it, and MainWindow has no
    WA_DeleteOnClose, so each test leaked a full window (plots, timers,
    docks). Theme changes repolish every top-level widget in the app, so the
    leaked windows made later tests progressively slower and larger until
    the run was OOM-killed. Widgets that existed before the test (module or
    session fixtures) are left alone.
    """
    import shiboken6
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    def address(w):
        return shiboken6.getCppPointer(w)[0]

    app = QApplication.instance()
    before = set(map(address, app.topLevelWidgets())) if app else set()
    yield
    app = QApplication.instance()
    if app is None:
        return
    import pyqtgraph as pg
    from PySide6.QtWidgets import QMessageBox

    # close() still runs each window's closeEvent (stops workers/timers), but
    # an "unsaved changes?" prompt there would block forever: answer No.
    No = QMessageBox.StandardButton.No
    with patch.object(QMessageBox, "question", return_value=No), \
            patch.object(QMessageBox, "warning", return_value=No), \
            patch.object(QMessageBox, "exec", return_value=No):
        for w in app.topLevelWidgets():
            # Closing one window can delete others (WA_DeleteOnClose popups).
            if shiboken6.isValid(w) and address(w) not in before:
                w.close()
                # Tear pyqtgraph scenes down from the Python side first; letting
                # ~QGraphicsScene delete Python-owned items segfaults.
                for view in w.findChildren(pg.GraphicsView):
                    view.close()
                w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
