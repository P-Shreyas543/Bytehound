"""Convert Bytehound Excel configuration workbooks (e.g. DB_48100.xlsx)
to Vector CAN Database (.dbc) format without comments or min/max values.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Add project root to Python path to import Bytehound config loader
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from app.decoder.config_loader import load_config


def sanitize_name(name: str) -> str:
    """Sanitize signal/frame names for standard DBC identifiers."""
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', name.strip())
    if sanitized and sanitized[0].isdigit():
        sanitized = f"SIG_{sanitized}"
    return sanitized


def sanitize_unit(unit: str | None) -> str:
    """Normalize unit string for DBC compatibility."""
    if not unit or unit.strip() in {"BitFields", "Enums"}:
        return ""
    u = unit.strip()
    if u in {"°C", "C"}:
        return "degC"
    return u


def convert_excel_to_dbc(excel_path: Path, dbc_path: Path) -> None:
    cfg = load_config(excel_path)

    lines: list[str] = []
    lines.append('VERSION ""\n')
    lines.append('NS_ :\n')
    lines.append(
        '\tNS_DESC_\n\tCM_\n\tBA_DEF_\n\tBA_\n\tVAL_\n\tCAT_MACRO_\n\tCAT_\n'
        '\tFILTER\n\tBA_DEF_DEF_\n\tEV_DATA_\n\tENVVAR_DATA_\n\tSGTYPE_\n'
        '\tSGTYPE_VAL_\n\tBA_DEF_SGTYPE_\n\tBA_SGTYPE_\n\tSIG_TYPE_REF_\n'
        '\tVAL_TABLE_\n\tSIG_GROUP_\n\tSIG_VALTYPE_\n\tSIGTYPE_VALTYPE_\n'
        '\tBO_TX_BU_\n\tBA_DEF_REL_\n\tBA_REL_\n\tBA_DEF_DEF_REL_\n'
        '\tBA_REL_DEF_\n\tBU_SG_REL_\n\tBU_EV_REL_\n\tBU_BO_REL_\n\tSG_MUL_VAL_\n'
    )
    lines.append('BS_:\n')
    lines.append('BU_: BMS Vector__XXX\n')

    valtype_lines: list[str] = []
    val_lines: list[str] = []

    for fid in sorted(cfg.signals_by_frame.keys()):
        frame_def = cfg.frames.get(fid)
        raw_frame_name = cfg.frame_names.get(fid, f"Frame_0x{fid:X}")
        frame_name = sanitize_name(raw_frame_name)
        signals = cfg.signals_by_frame[fid]

        max_byte = max(s.start_byte + s.byte_length for s in signals)
        dlc = max(max_byte, frame_def.payload_length if (frame_def and frame_def.payload_length) else 8)

        lines.append(f'\nBO_ {fid} {frame_name}: {dlc} BMS')

        for sig in signals:
            sig_name = sanitize_name(sig.signal_name)
            start_bit = sig.start_byte * 8 + (sig.bit_offset if sig.bit_offset is not None else 0)
            bit_size = sig.byte_length * 8 if sig.bit_offset is None else 1

            byte_order = 1 if sig.endianness == 'little' else 0  # 1 = Intel, 0 = Motorola
            sign = '-' if sig.data_type == 'int' else '+'

            scale = sig.scale if sig.scale is not None else 1.0
            offset = sig.offset if sig.offset is not None else 0.0

            unit_str = sanitize_unit(sig.unit)

            # Min and Max are omitted (set to [0|0])
            lines.append(
                f' SG_ {sig_name} : {start_bit}|{bit_size}@{byte_order}{sign} '
                f'({scale:g},{offset:g}) [0|0] "{unit_str}" Vector__XXX'
            )

            # Float signal type marker
            if sig.data_type == 'float':
                valtype = 1 if sig.byte_length == 4 else 2
                valtype_lines.append(f'SIG_VALTYPE_ {fid} {sig_name} : {valtype};')

            # Enums
            enum_key = (fid, sig.source_name or sig.signal_name)
            if enum_key in cfg.enums:
                enum_dict = cfg.enums[enum_key]
                entries = [f'{v} "{lbl}"' for v, lbl in enum_dict.items()]
                val_lines.append(f'VAL_ {fid} {sig_name} {" ".join(entries)} ;')

    lines.append('')
    if valtype_lines:
        lines.extend(valtype_lines)
        lines.append('')
    if val_lines:
        lines.extend(val_lines)
        lines.append('')

    content = '\n'.join(lines)
    dbc_path.write_text(content, encoding='utf-8')
    print(f"Successfully generated CAN DBC at: {dbc_path.resolve()}")


def main():
    parser = argparse.ArgumentParser(description="Convert Excel DBC specification to Vector CAN DBC file")
    parser.add_argument("excel", type=Path, nargs="?", default=PROJECT_ROOT / "DB_48100.xlsx", help="Input Excel file")
    parser.add_argument("dbc", type=Path, nargs="?", default=PROJECT_ROOT / "DB_48100.dbc", help="Output DBC file")
    args = parser.parse_args()

    convert_excel_to_dbc(args.excel, args.dbc)


if __name__ == "__main__":
    main()
