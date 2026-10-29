"""Fixtures for cycler system tests: the real cycler MainWindow connected to a
simulated cell over a pseudo-terminal, with remote webhooks switched off."""

from __future__ import annotations

import os
import time
from typing import Callable

import pytest
from PySide6.QtWidgets import QApplication

# Test modules using these fixtures set this as their pytestmark (it has no
# effect in a conftest).
posix_only = pytest.mark.skipif(os.name != "posix", reason="pseudo-terminals are POSIX only")


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0, what: str = "condition") -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out after {timeout:.1f}s waiting for {what}")


@pytest.fixture
def cell():
    from single_cell_cycler.tests.system.sim_cell import SimulatedCell

    sim = SimulatedCell().start()
    yield sim
    sim.stop()


@pytest.fixture
def cycler(qapp, cell, monkeypatch):
    """The cycler window, connected to ``cell`` the way an operator does it:
    pick the port in the toolbar combo and press Connect. (Logs and the
    journal already go to a temp dir via the root conftest.)"""
    from single_cell_cycler.comm.webhook_notifier import WebhookSettings
    from single_cell_cycler.ui.main_window import MainWindow

    monkeypatch.setattr(WebhookSettings, "load", classmethod(lambda cls, *a, **k: cls(enabled=False)))

    w = MainWindow()
    # Headless (offscreen) runs switch the step-transition handshake to
    # "no settle delays"; the shipped GUI runs with them, so do the same here
    # (connecting already switches auto-ack off, as on real hardware).
    w.engine.transition_controller.delays_enabled = True
    w.show()
    w.combo_port.addItem(cell.port, cell.port)
    w.combo_port.setCurrentIndex(w.combo_port.count() - 1)
    w._toggle_connection()
    wait_until(lambda: w._last_cell_data is not None, 5, "first cell telemetry")
    yield w
    if w.transceiver.isRunning():
        w._toggle_connection()
    w.close()
