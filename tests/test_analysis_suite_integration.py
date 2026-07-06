"""Integration smoke tests for AnalysisSuiteWindow."""
import pytest
from PySide6.QtWidgets import QApplication
from app.ui.analysis_suite import AnalysisSuiteWindow
from unittest.mock import patch, MagicMock

@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])

@pytest.fixture
def analysis_window(qapp):
    window = AnalysisSuiteWindow()
    yield window
    window.close()

def test_analysis_window_instantiation(analysis_window):
    assert analysis_window is not None
    assert "Analysis Suite" in analysis_window.windowTitle()
    # Verify the UI built successfully and has the main splitter
    assert analysis_window.centralWidget() is not None

def test_analysis_window_menus(analysis_window):
    # Verify menus are populated
    menubar = analysis_window.menuBar()
    actions = menubar.actions()
    menus = [a.text().replace("&", "") for a in actions]
    assert "File" in menus
    assert "View" in menus
    assert "Tools" in menus
    assert "Scatter" in menus

def test_analysis_window_load_log_mocked(analysis_window):
    # Verify that triggering load dialog works (if we mock QFileDialog)
    with patch("app.ui.analysis_suite.QFileDialog.getOpenFileNames") as mock_fd:
        mock_fd.return_value = (["fake_log.csv"], "CSV (*.csv)")
        with patch("app.ui.analysis_suite.LogLoaderThread") as mock_loader:
            mock_instance = MagicMock()
            mock_loader.return_value = mock_instance
            
            analysis_window._on_load_logs()
            
            # The loader should have been started
            mock_loader.assert_called_once()
            mock_instance.start.assert_called_once()
