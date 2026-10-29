"""Fixtures for system tests: the real MainWindow, loaded with the real
canonical config, connected over a real transport to a simulated BMS."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Dict

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.serial_io.serial_worker import SerialSettings
from tests.system.sim_device import TcpBms

CANONICAL_CONFIG = Path(__file__).resolve().parents[1] / "fixtures" / "canonical_config"


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Application set up the way app.main.run() does it (theme, font,
    title-bar filter), minus the blocking exec()."""
    import qdarktheme
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QFont

    from app.ui.main_window import APP_NAME, APP_ORG
    from app.ui.widgets import TitleBarThemeFilter

    app = QApplication.instance() or QApplication([])
    settings = QSettings(APP_ORG, APP_NAME)
    qdarktheme.setup_theme(str(settings.value("ui/theme", "dark")), corner_shape="rounded")
    app.setFont(QFont("PT Sans", 10))
    app._titlebar_filter = TitleBarThemeFilter(settings)
    app.installEventFilter(app._titlebar_filter)
    return app


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0, what: str = "condition") -> None:
    """Pump the Qt event loop (so the 60 Hz UI timer runs) until predicate()."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out after {timeout:.1f}s waiting for {what}")


def table_values(window) -> Dict[str, str]:
    """{variable name: Value cell text} exactly as the telemetry table shows it."""
    from app.ui.telemetry_model import COLUMN_HEADERS

    model = window._table.model()
    var_col = COLUMN_HEADERS.index("Variable")
    val_col = COLUMN_HEADERS.index("Value")
    return {
        model.data(model.index(r, var_col)): model.data(model.index(r, val_col))
        for r in range(model.rowCount())
    }


def number(text: str) -> float:
    return float(str(text).split()[0])


@pytest.fixture
def error_boxes(monkeypatch):
    """Record modal critical boxes instead of blocking the test on them."""
    shown = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: shown.append(a[1:3]))
    return shown


@pytest.fixture
def window(qapp, error_boxes):
    from app.ui.main_window import MainWindow

    w = MainWindow()
    w.show()
    w._load_config_from_path(CANONICAL_CONFIG, suppress_popups=True)
    assert w._config is not None, "canonical config failed to load"
    yield w
    w._disconnect(reason="Application closed")
    w.close()


@pytest.fixture
def device():
    bms = TcpBms().start()
    yield bms
    bms.stop()


def tcp_settings(device: TcpBms, **overrides) -> SerialSettings:
    return SerialSettings(
        port=f"127.0.0.1:{device.port}", connection_type="tcp",
        host="127.0.0.1", port_num=device.port, **overrides,
    )
