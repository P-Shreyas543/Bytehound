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
