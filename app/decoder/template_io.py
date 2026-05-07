"""Export config templates and session snapshots."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable


CONFIG_CSV_FILES = (
    "protocol.csv",
    "frames.csv",
    "variables.csv",
    "frame_config.csv",
    "bitfields.csv",
    "enums.csv",
    "calc_groups.csv",
    "tx_commands.csv",
    "tx_command_fields.csv",
    "serial_defaults.csv",
    "polling_schedule.csv",
)


def export_csv_template(source_dir: str | Path, target_dir: str | Path) -> list[Path]:
    """Copy all known CSV template files to ``target_dir``."""

    source = Path(source_dir)
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for name in CONFIG_CSV_FILES:
        src = source / name
        if src.exists():
            dst = target / name
            shutil.copy2(src, dst)
            copied.append(dst)
    return copied


def export_excel_template(source_dir: str | Path, target_path: str | Path) -> Path:
    """Create an Excel workbook from the known CSV template files.

    If ``source_dir`` is already an Excel workbook (``.xlsx``/``.xlsm``), it is
    copied to ``target_path``.
    """

    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("Excel export requires pandas and openpyxl") from exc

    source = Path(source_dir)
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    if source.is_file() and source.suffix.lower() in {".xlsx", ".xlsm"}:
        shutil.copy2(source, target)
        return target
    if source.is_file():
        raise ValueError(f"Excel export source must be a directory or .xlsx file: {source}")

    with pd.ExcelWriter(target, engine="openpyxl") as writer:
        for name in CONFIG_CSV_FILES:
            src = source / name
            if not src.exists():
                continue
            sheet = _sheet_name_from_csv(name)
            pd.read_csv(src, dtype=str).fillna("").to_excel(
                writer, sheet_name=sheet, index=False
            )
    return target


def snapshot_config(source_path: str | Path, target_dir: str | Path) -> Path:
    """Copy the active config beside a log session."""

    source = Path(source_path)
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        snapshot_dir = target / "config_snapshot"
        export_csv_template(source, snapshot_dir)
        return snapshot_dir
    snapshot_file = target / f"config_snapshot{source.suffix}"
    shutil.copy2(source, snapshot_file)
    return snapshot_file


def _sheet_name_from_csv(name: str) -> str:
    words = Path(name).stem.split("_")
    return "".join(word.capitalize() for word in words)[:31]
