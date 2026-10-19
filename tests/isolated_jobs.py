"""Jobs for tests/test_isolated.py. They run in the helper process, so they
must live in an importable module (spawn imports them by name)."""

from __future__ import annotations

import os
import time
from pathlib import Path


def pid() -> int:
    return os.getpid()


def sleep_then_write(seconds: float, partial: str) -> None:
    Path(partial).write_text("half written", encoding="utf-8")
    time.sleep(seconds)


def crash(partial: str) -> None:
    Path(partial).write_text("half written", encoding="utf-8")
    os._exit(3)


def crash_once(marker: str) -> int:
    """Dies the first time (no marker yet), succeeds on the retry."""
    m = Path(marker)
    if not m.exists():
        m.write_text("crashed once", encoding="utf-8")
        os._exit(3)
    return os.getpid()


def unpicklable_result():
    return lambda: None


def boom() -> None:
    raise ValueError("bad input")
