"""Export config templates and session snapshots."""

from __future__ import annotations

import shutil
from pathlib import Path


CONFIG_CSV_FILES = (
    "protocol.csv",
    "frames.csv",      # per-frame names and payload_length (replaces protocol-level payload_length)
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
        from openpyxl.worksheet.datavalidation import DataValidation
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter
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

    from .types import SUPPORTED_CRC_TYPES, SUPPORTED_FMT_TYPES, ByteOrder, ParserType, ReadWrite

    with pd.ExcelWriter(target, engine="openpyxl") as writer:
        workbook = writer.book
        readme = workbook.create_sheet("ReadMe", 0)
        readme.append(["Bytehound Configuration Template"])
        readme.append([])
        readme.append(["This workbook contains the configuration for Bytehound."])
        readme.append(["Please fill in the sheets according to your protocol."])
        readme.append(["Dropdowns are provided for constrained fields."])
        readme["A1"].font = Font(bold=True, size=14)

        for name in CONFIG_CSV_FILES:
            src = source / name
            if not src.exists():
                continue
            sheet_name = _sheet_name_from_csv(name)
            df = pd.read_csv(src, dtype=str).fillna("")
            df.to_excel(writer, sheet_name=sheet_name, index=False)

            ws = writer.sheets[sheet_name]
            header_fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
            for col_num, col_name in enumerate(df.columns, 1):
                cell = ws.cell(row=1, column=col_num)
                cell.font = Font(bold=True)
                cell.fill = header_fill

                max_len = max((len(str(v)) for v in df[col_name]), default=0)
                max_len = max(max_len, len(str(col_name)))
                ws.column_dimensions[get_column_letter(col_num)].width = min(max_len + 2, 50)

                col_letter = get_column_letter(col_num)
                val_range = f"{col_letter}2:{col_letter}1048576"
                dv = None
                if col_name == "data_type":
                    dv = DataValidation(type="list", formula1=f'"{",".join(sorted(SUPPORTED_FMT_TYPES))}"', allow_blank=True)
                elif col_name == "crc_type":
                    dv = DataValidation(type="list", formula1=f'"{",".join(sorted(SUPPORTED_CRC_TYPES))}"', allow_blank=True)
                elif col_name in ("endianness", "frame_id_byte_order", "crc_byte_order", "length_byte_order"):
                    dv = DataValidation(type="list", formula1=f'"{",".join([m.value for m in ByteOrder])}"', allow_blank=True)
                elif col_name == "parser_type":
                    dv = DataValidation(type="list", formula1=f'"{",".join([m.value for m in ParserType])}"', allow_blank=True)
                elif col_name == "read_write":
                    dv = DataValidation(type="list", formula1=f'"{",".join([m.value for m in ReadWrite])}"', allow_blank=True)

                if dv:
                    dv.add(val_range)
                    ws.add_data_validation(dv)
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
