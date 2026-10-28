"""Crash-safe workbook save."""

from __future__ import annotations

import os
from pathlib import Path


def save_workbook_atomic(wb, path: Path) -> None:
    """Save *wb* to a temp name beside *path*, then rename it into place.

    Compiling a large log can take a while; if the app exits or crashes
    mid-save, *path* is either the previous file or absent — never a truncated
    .xlsx the user might open. The source temp files are only deleted after
    this returns, so an interrupted save is simply redone on the next launch.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    try:
        wb.save(partial)
        os.replace(partial, path)
    finally:
        if partial.exists():
            try:
                partial.unlink()
            except OSError:
                pass
