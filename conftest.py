"""Project-root conftest: ensure `app` package is importable from tests.

pytest rootdir defaults to this file's directory, so adding it to
``sys.path`` makes `from app.protocol.crc import ...` resolve regardless
of where pytest is invoked from.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
