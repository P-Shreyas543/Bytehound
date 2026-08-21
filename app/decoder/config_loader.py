"""Load and validate CSV/Excel configuration files.

Primary schema:
  protocol.csv, frames.csv, frame_variables.csv, bitfields.csv, enums.csv,
  calc_groups.csv, tx_commands.csv, tx_command_fields.csv

Compatibility schema:
  protocol.csv + frame_config.csv
"""

from __future__ import annotations

import csv
import difflib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .types import (
    FMT_SIZES,
    BitfieldSpec,
    CalcGroupSpec,
    CrcType,
    DataType,
    FmtType,
    FrameConfig,
    FrameDefinition,
    ParserType,
    PollingScheduleSpec,
    ProtocolConfig,
    ReadWrite,
    SignalSpec,
    SerialDefaults,
    TxCommandFieldSpec,
    TxCommandSpec,
)


class ConfigError(ValueError):
    """Raised when configuration cannot be loaded or validated."""


_PROTOCOL_REQUIRED = {
    "profile_name",
    "header_hex",
    "frame_id_size",
    "length_size",
    "crc_type",
}

_LEGACY_FRAME_CONFIG_REQUIRED = {
    "frame_id_hex",
    "frame_name",
    "signal_name",
    "start_byte",
    "byte_length",
    "endianness",
    "data_type",
    "scale",
    "offset",
    "unit",
}

_FRAMES_REQUIRED = {"frame_id", "frame_name"}
_VARIABLES_REQUIRED = {"id_or_address", "signal_name", "data_type"}
_POLLING_SCHEDULE_REQUIRED = {"id_or_address", "interval_ms", "timeout_ms"}
_BITFIELDS_REQUIRED = {"id_or_address", "signal_name", "bit_index", "label"}
_ENUMS_REQUIRED = {"id_or_address", "signal_name", "value", "label"}
_CALC_GROUPS_REQUIRED = {"group_name", "operations"}
_TX_COMMANDS_REQUIRED = {"command_name", "id_or_address"}
_TX_COMMAND_FIELDS_REQUIRED = {"command_name", "signal_name", "data_type"}
_SERIAL_DEFAULTS_REQUIRED = {"baud_rate"}


def load_config(path: str | Path | dict) -> FrameConfig:
    """Load a config directory, an Excel workbook, or a preset dictionary."""

    if isinstance(path, dict):
        tables = _coerce_mapping_tables(path)
        base_label = "Preset"
    else:
        source = Path(path)
        if source.is_file() and source.suffix.lower() in {".xlsx", ".xlsm"}:
            tables = _read_excel_tables(source)
            base_label = source.name
        elif source.is_file() and source.suffix.lower() == ".json":
            import json
            with source.open("r", encoding="utf-8") as fp:
                tables = _coerce_mapping_tables(json.load(fp))
            base_label = source.name
        elif source.is_file() and source.suffix.lower() in {".yaml", ".yml"}:
            try:
                import yaml
            except ImportError as exc:
                raise ConfigError("YAML config requires pyyaml") from exc
            with source.open("r", encoding="utf-8") as fp:
                tables = _coerce_mapping_tables(yaml.safe_load(fp))
            base_label = source.name
        elif source.is_dir():
            tables = _read_csv_tables(source)
            base_label = str(source)
        else:
            raise ConfigError(f"Config path does not exist or format unsupported: {source}")
    protocol_rows = tables.get("protocol", [])
    required_cols = set(_PROTOCOL_REQUIRED)
    if protocol_rows:
        for r in protocol_rows:
            if not _is_blank_row(r) and _to_bool(r.get("enabled", "true"), default=True, field_name="protocol.enabled"):
                try:
                    parser_type_val = ParserType.parse(r.get("parser_type", "")).value
                    if parser_type_val == "waveshare_can":
                        required_cols = {"profile_name"}
                except ValueError:
                    pass
                break

    protocol = _parse_protocol(_required_table(tables, "protocol", required_cols))

    if "variables" in tables:
        if "frames" in tables:
            frames = _parse_frames(_required_table(tables, "frames", _FRAMES_REQUIRED))
        else:
            frames = {}
        signals = _parse_variables(
            _required_table(tables, "variables", _VARIABLES_REQUIRED),
            frames,
            parser_type=protocol.parser_type,
        )
        if not frames:
            for sig in signals:
                if sig.frame_id not in frames:
                    frames[sig.frame_id] = FrameDefinition(
                        frame_id=sig.frame_id,
                        frame_name=sig.frame_name or f"Frame 0x{sig.frame_id:X}"
                    )
    elif "frame_config" in tables:
        signals, frames = _parse_legacy_frame_config(
            _required_table(tables, "frame_config", _LEGACY_FRAME_CONFIG_REQUIRED),
            parser_type=protocol.parser_type,
        )
    elif "frames" in tables or "tx_commands" in tables or "polling_schedule" in tables:
        signals = []
        if "frames" in tables:
            frames = _parse_frames(_required_table(tables, "frames", _FRAMES_REQUIRED))
        else:
            frames = {}
    else:
        raise ConfigError(
            f"{base_label}: expected variables.csv + frames.csv or frame_config.csv"
        )

    _validate_signal_ranges(signals)

    signals_by_frame: Dict[int, List[SignalSpec]] = {}
    frame_names: Dict[int, str] = {}
    for frame_id, frame in frames.items():
        frame_names[frame_id] = frame.frame_name
    for sig in signals:
        if sig.enabled:
            signals_by_frame.setdefault(sig.frame_id, []).append(sig)
            frame_names.setdefault(sig.frame_id, sig.frame_name)

    cfg = FrameConfig(
        protocol=protocol,
        frames=frames,
        signals_by_frame=signals_by_frame,
        frame_names=frame_names,
    )
    cfg.bitfields = _parse_bitfields(tables.get("bitfields", []), cfg)
    cfg.enums = _parse_enums(tables.get("enums", []), cfg)
    cfg.calc_groups = _parse_calc_groups(tables.get("calc_groups", []), cfg)
    cfg.tx_commands = _parse_tx_commands(
        tables.get("tx_commands", []), tables.get("tx_command_fields", [])
    )
    cfg.serial_defaults = _parse_serial_defaults(tables.get("serial_defaults", []))
    cfg.polling_schedules = _parse_polling_schedules(tables.get("polling_schedule", []))
    return cfg


def _coerce_mapping_tables(raw_tables: dict) -> Dict[str, List[Dict[str, str]]]:
    """Normalize table names and scalar values for dict/JSON/YAML configs."""

    if not isinstance(raw_tables, dict):
        raise ConfigError("Config mapping must be a dictionary of table rows")

    tables: Dict[str, List[Dict[str, str]]] = {}
    for key, rows in raw_tables.items():
        table_name = _normalize_table_name(str(key))
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            raise ConfigError(f"{table_name}: expected a list of row objects")
        normalized_rows: List[Dict[str, str]] = []
        for row in rows:
            if not isinstance(row, dict):
                raise ConfigError(f"{table_name}: expected row objects")
            normalized_rows.append(
                {
                    str(k).strip(): (
                        hex(v)
                        if k in {"id_or_address", "frame_id", "frame_id_hex"}
                        and isinstance(v, int)
                        and not isinstance(v, bool)
                        else str(v)
                    )
                    for k, v in row.items()
                }
            )
        tables.setdefault(table_name, []).extend(normalized_rows)
    return tables


def _read_csv_tables(directory: Path) -> Dict[str, List[Dict[str, str]]]:
    tables: Dict[str, List[Dict[str, str]]] = {}
    for file in directory.glob("*.csv"):
        tables[_normalize_table_name(file.stem)] = _read_csv(file)
    return tables


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        if reader.fieldnames is None:
            raise ConfigError(f"{path.name}: header row missing")
        return [
            {(k or "").strip(): (v or "").strip() for k, v in row.items()}
            for row in reader
            if any((v or "").strip() for v in row.values())
        ]


def _read_excel_tables(path: Path) -> Dict[str, List[Dict[str, str]]]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise ConfigError("Excel config requires pandas and openpyxl") from exc

    sheets = pd.read_excel(path, sheet_name=None, dtype=str).items()
    tables: Dict[str, List[Dict[str, str]]] = {}
    for name, df in sheets:
        key = _normalize_table_name(name)
        rows = df.fillna("").to_dict("records")
        tables[key] = [
            {(k or "").strip(): str(v or "").strip() for k, v in row.items()}
            for row in rows
            if any(str(v or "").strip() for v in row.values())
        ]
    return tables


def _normalize_table_name(name: str) -> str:
    chars = []
    for ch in name.strip():
        chars.append(ch.lower() if ch.isalnum() else "_")
    normalized = "_".join(part for part in "".join(chars).split("_") if part)
    aliases = {
        "protocols": "protocol",
        "protocol": "protocol",
        "frames": "frames",
        "frame": "frames",
        "variables": "variables",
        "variable": "variables",
        "framevariables": "variables",
        "framevariable": "variables",
        "frame_variables": "variables",
        "frame_variable": "variables",
        "frameconfig": "frame_config",
        "frameconfigs": "frame_config",
        "frame_config": "frame_config",
        "frame_configs": "frame_config",
        "bitfield": "bitfields",
        "bitfields": "bitfields",
        "enum": "enums",
        "enums": "enums",
        "calcgroup": "calc_groups",
        "calcgroups": "calc_groups",
        "calc_group": "calc_groups",
        "calc_groups": "calc_groups",
        "txcommand": "tx_commands",
        "txcommands": "tx_commands",
        "tx_command": "tx_commands",
        "tx_commands": "tx_commands",
        "txcommandfield": "tx_command_fields",
        "txcommandfields": "tx_command_fields",
        "tx_command_field": "tx_command_fields",
        "tx_command_fields": "tx_command_fields",
        "serialdefault": "serial_defaults",
        "serialdefaults": "serial_defaults",
        "serial_default": "serial_defaults",
        "serial_defaults": "serial_defaults",
        "pollingschedule": "polling_schedule",
        "pollingschedules": "polling_schedule",
        "polling_schedule": "polling_schedule",
        "polling_schedules": "polling_schedule",
    }
    return aliases.get(normalized, normalized)


def _format_missing_columns(missing: set[str], available: set[str]) -> str:
    """Render a missing-columns list with did-you-mean hints."""
    import difflib
    parts: List[str] = []
    for col in sorted(missing):
        match = difflib.get_close_matches(col, list(available), n=1, cutoff=0.6)
        if match:
            parts.append(f"{col!r} (did you mean {match[0]!r}?)")
        else:
            parts.append(repr(col))
    return ", ".join(parts)


def _required_table(
    tables: Dict[str, List[Dict[str, str]]], name: str, required: set[str]
) -> List[Dict[str, str]]:
    if name not in tables:
        raise ConfigError(f"Missing required config file/sheet: {name}")
    rows = tables[name]
    if not rows:
        raise ConfigError(f"{name}: no data rows")
    fields = set(rows[0])
    missing = required - fields
    if missing:
        raise ConfigError(
            f"{name}: missing required columns: {_format_missing_columns(missing, fields)}"
        )
    return rows


def _optional_columns_ok(rows: List[Dict[str, str]], required: set[str], name: str) -> None:
    if not rows:
        return
    fields = set(rows[0])
    missing = required - fields
    if missing:
        raise ConfigError(
            f"{name}: missing required columns: {_format_missing_columns(missing, fields)}"
        )


def _is_blank_row(row: Dict[str, str]) -> bool:
    return all((v or "").strip() == "" for v in row.values())


def _check_signal_uniqueness(
    seen: Dict[int, set[str]], frame_id: int, signal_name: str, *, source: str
) -> None:
    """Reject duplicate signal names within the same frame.

    Both the modern Variables loader and the legacy FrameConfig loader
    enforce this rule. Sharing the helper means a future tweak (e.g.
    case-insensitive uniqueness, or unicode-normalised) lands in one place.
    """
    frame_seen = seen.setdefault(frame_id, set())
    if signal_name in frame_seen:
        raise ConfigError(
            f"{source}: duplicate signal {signal_name!r} in frame 0x{frame_id:X}"
        )
    frame_seen.add(signal_name)


def _normalize_byte_order(
    value: str,
    *,
    source: str,
    column: str = "byte_order",
    default: str = "little",
) -> str:
    """Return ``"big"`` or ``"little"`` for a byte-order cell, defaulting to
    *default* when blank. Raises a clear ConfigError on any other value.

    Both signal loaders (modern + legacy) and the TX-fields loader need this
    check; centralising it avoids three slightly-different error messages.
    ``column`` is the user-facing column name so legacy callers (which use
    ``endianness``) get an error that names the column they actually edited.
    """
    normalised = (value or "").strip().lower()
    if normalised == "":
        return default
    if normalised in {"big", "little"}:
        return normalised
    raise ConfigError(f"{source}: {column} must be 'big' or 'little' (got {value!r})")


def _to_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    val_str = str(value).strip()
    try:
        return int(val_str, 0)
    except ValueError:
        try:
            return int(val_str, 16)
        except ValueError as exc:
            raise ConfigError(f"Invalid integer for {field_name!r}: {value!r}") from exc


def _to_optional_int(value: Any, *, field_name: str) -> Optional[int]:
    if value is None or str(value).strip() == "":
        return None
    return _to_int(value, field_name=field_name)


def _to_float(value: Any, default: float, field_name: str) -> float:
    if value is None or str(value).strip() == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigError(f"Invalid number for {field_name!r}: {value!r}") from exc


def _to_optional_float(value: Any, field_name: str) -> Optional[float]:
    if value is None or str(value).strip() == "":
        return None
    return _to_float(value, 0.0, field_name)


def _to_bool(value: Any, *, default: bool = False, field_name: str = "") -> bool:
    if isinstance(value, bool):
        return value
    # Excel sometimes delivers numeric cell values directly (int/float).
    # Treat non-zero as True, zero as False — consistent with Python truthiness.
    if isinstance(value, (int, float)):
        return value != 0
    s = str(value).strip().lower()
    if s == "":
        return default
    if s in {"true", "1", "yes", "y", "t"}:
        return True
    if s in {"false", "0", "no", "n", "f"}:
        return False
    # Last-chance: if the string represents an integer, use its truthiness.
    try:
        return int(s) != 0
    except ValueError:
        pass
    raise ConfigError(f"Invalid boolean for {field_name!r}: {value!r}")


def _hex_to_bytes(value: str, field_name: str) -> bytes:
    cleaned = value.replace(" ", "").replace("0x", "").replace("0X", "")
    if cleaned == "":
        return b""
    if len(cleaned) % 2 != 0:
        raise ConfigError(f"{field_name}: hex string must have even length: {value!r}")
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise ConfigError(f"{field_name}: invalid hex {value!r}") from exc


def _parse_frame_id(value: str, *, field_name: str = "frame_id") -> int:
    cleaned = value.strip()
    if cleaned == "":
        raise ConfigError(f"{field_name} is required")
    if cleaned.lower().startswith("0x"):
        return _to_int(cleaned, field_name=field_name)
    # Spreadsheet users often write IDs as 0010; treat that as hex.
    try:
        return int(cleaned, 16)
    except ValueError as exc:
        raise ConfigError(f"Invalid frame ID for {field_name}: {value!r}") from exc


def _parse_protocol(rows: List[Dict[str, str]]) -> ProtocolConfig:
    non_blank_rows = [r for r in rows if not _is_blank_row(r)]
    enabled_rows = [
        r for r in non_blank_rows if _to_bool(r.get("enabled", "true"), default=True, field_name="protocol.enabled")
    ]
    if not enabled_rows:
        raise ConfigError("protocol: no enabled protocol profile found")
    if len(enabled_rows) > 1:
        raise ConfigError("protocol: more than one enabled profile")

    row = enabled_rows[0]
    parser_type_val = ParserType.parse(row.get("parser_type", "")).value
    return rows


def _optional_columns_ok(rows: List[Dict[str, str]], required: set[str], name: str) -> None:
    if not rows:
        return
    fields = set(rows[0])
    missing = required - fields
    if missing:
        raise ConfigError(
            f"{name}: missing required columns: {_format_missing_columns(missing, fields)}"
        )


def _is_blank_row(row: Dict[str, str]) -> bool:
    return all((v or "").strip() == "" for v in row.values())


def _check_signal_uniqueness(
    seen: Dict[int, set[str]], frame_id: int, signal_name: str, *, source: str
) -> None:
    """Reject duplicate signal names within the same frame.

    Both the modern Variables loader and the legacy FrameConfig loader
    enforce this rule. Sharing the helper means a future tweak (e.g.
    case-insensitive uniqueness, or unicode-normalised) lands in one place.
    """
    frame_seen = seen.setdefault(frame_id, set())
    if signal_name in frame_seen:
        raise ConfigError(
            f"{source}: duplicate signal {signal_name!r} in frame 0x{frame_id:X}"
        )
    frame_seen.add(signal_name)


def _normalize_byte_order(
    value: str,
    *,
    source: str,
    column: str = "byte_order",
    default: str = "little",
) -> str:
    """Return ``"big"`` or ``"little"`` for a byte-order cell, defaulting to
    *default* when blank. Raises a clear ConfigError on any other value.

    Both signal loaders (modern + legacy) and the TX-fields loader need this
    check; centralising it avoids three slightly-different error messages.
    ``column`` is the user-facing column name so legacy callers (which use
    ``endianness``) get an error that names the column they actually edited.
    """
    normalised = (value or "").strip().lower()
    if normalised == "":
        return default
    if normalised in {"big", "little"}:
        return normalised
    raise ConfigError(f"{source}: {column} must be 'big' or 'little' (got {value!r})")


def _to_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    val_str = str(value).strip()
    try:
        return int(val_str, 0)
    except ValueError:
        try:
            return int(val_str, 16)
        except ValueError as exc:
            raise ConfigError(f"Invalid integer for {field_name!r}: {value!r}") from exc


def _to_optional_int(value: Any, *, field_name: str) -> Optional[int]:
    if value is None or str(value).strip() == "":
        return None
    val = _to_int(value, field_name=field_name)
    if val <= 0:
        return None
    return val


def _to_float(value: Any, default: float, field_name: str) -> float:
    if value is None or str(value).strip() == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigError(f"Invalid number for {field_name!r}: {value!r}") from exc


def _to_optional_float(value: Any, field_name: str) -> Optional[float]:
    if value is None or str(value).strip() == "":
        return None
    return _to_float(value, 0.0, field_name)


def _to_bool(value: Any, *, default: bool = False, field_name: str = "") -> bool:
    if isinstance(value, bool):
        return value
    # Excel sometimes delivers numeric cell values directly (int/float).
    # Treat non-zero as True, zero as False — consistent with Python truthiness.
    if isinstance(value, (int, float)):
        return value != 0
    s = str(value).strip().lower()
    if s == "":
        return default
    if s in {"true", "1", "yes", "y", "t"}:
        return True
    if s in {"false", "0", "no", "n", "f"}:
        return False
    # Last-chance: if the string represents an integer, use its truthiness.
    try:
        return int(s) != 0
    except ValueError:
        pass
    raise ConfigError(f"Invalid boolean for {field_name!r}: {value!r}")


def _hex_to_bytes(value: str, field_name: str) -> bytes:
    cleaned = value.replace(" ", "").replace("0x", "").replace("0X", "")
    if cleaned == "":
        return b""
    if len(cleaned) % 2 != 0:
        raise ConfigError(f"{field_name}: hex string must have even length: {value!r}")
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise ConfigError(f"{field_name}: invalid hex {value!r}") from exc


def _parse_frame_id(value: str, *, field_name: str = "frame_id") -> int:
    cleaned = value.strip()
    if cleaned == "":
        raise ConfigError(f"{field_name} is required")
    if cleaned.lower().startswith("0x"):
        return _to_int(cleaned, field_name=field_name)
    # Spreadsheet users often write IDs as 0010; treat that as hex.
    try:
        return int(cleaned, 16)
    except ValueError as exc:
        raise ConfigError(f"Invalid frame ID for {field_name}: {value!r}") from exc


def _parse_protocol(rows: List[Dict[str, str]]) -> ProtocolConfig:
    non_blank_rows = [r for r in rows if not _is_blank_row(r)]
    enabled_rows = [
        r for r in non_blank_rows if _to_bool(r.get("enabled", "true"), default=True, field_name="protocol.enabled")
    ]
    if not enabled_rows:
        raise ConfigError("protocol: no enabled protocol profile found")
    if len(enabled_rows) > 1:
        raise ConfigError("protocol: more than one enabled profile")

    row = enabled_rows[0]
    parser_type_val = ParserType.parse(row.get("parser_type", "")).value
    is_waveshare = parser_type_val in ("waveshare_can", "waveshare_can_20_bytes")

    try:
        crc_type = CrcType.parse(row.get("crc_type", "none" if is_waveshare else "")).value
    except ValueError as exc:
        raise ConfigError(f"protocol: {exc}") from exc
    length_byte_order_raw = (row.get("length_byte_order") or "").strip().lower()
    length_byte_order: Optional[str]
    if length_byte_order_raw == "":
        length_byte_order = None
    elif length_byte_order_raw in {"big", "little"}:
        length_byte_order = length_byte_order_raw
    else:
        raise ConfigError(
            f"protocol: length_byte_order must be 'big', 'little', or empty (got {length_byte_order_raw!r})"
        )

    raw_log_format_raw = (row.get("raw_log_format") or "hex").strip().lower()
    if raw_log_format_raw not in {"hex", "compact"}:
        raise ConfigError(
            f"protocol: raw_log_format must be 'hex' or 'compact' (got {raw_log_format_raw!r})"
        )

    frame_id_default = "little"
    crc_default = "little"

    header_hex_val = row.get("header_hex", "")
    if is_waveshare and not header_hex_val:
        header_hex_val = "AA"

    frame_id_size_val = row.get("frame_id_size", "")
    if is_waveshare and not frame_id_size_val:
        frame_id_size = 2
    else:
        frame_id_size = _to_int(frame_id_size_val, field_name="frame_id_size")

    length_size_val = row.get("length_size", "")
    if is_waveshare and not length_size_val:
        length_size = 1
    else:
        length_size = _to_int(length_size_val, field_name="length_size")

    length_meaning_val = (row.get("length_meaning") or "").strip().lower()
    if not length_meaning_val:
        length_meaning = "payload_only"
    else:
        length_meaning = length_meaning_val

    crc_size_val = (row.get("crc_size") or "").strip()
    if is_waveshare and not crc_size_val:
        crc_size = 0
    elif not crc_size_val:
        expected_crc_sizes = {"none": 0, "crc16_modbus": 2, "crc16_ccitt": 2, "crc32": 4}
        crc_size = expected_crc_sizes.get(crc_type, 0)
    else:
        crc_size = _to_int(crc_size_val, field_name="crc_size")

    footer_hex_val = row.get("footer_hex", "")
    if is_waveshare and not footer_hex_val:
        footer_hex_val = "55"

    waveshare_fixed_val = row.get("waveshare_fixed_20_bytes") or row.get("waveshare_fixed") or ""
    waveshare_fixed_20_bytes = _to_bool(waveshare_fixed_val, default=False, field_name="protocol.waveshare_fixed_20_bytes")
    if parser_type_val == "waveshare_can_20_bytes":
        waveshare_fixed_20_bytes = True

    protocol = ProtocolConfig(
        profile_name=(row.get("profile_name") or "Default").strip(),
        header=_hex_to_bytes(header_hex_val, "header_hex"),
        frame_id_size=frame_id_size,
        frame_id_byte_order=_normalize_byte_order(
            row.get("frame_id_byte_order", ""), source="protocol", column="frame_id_byte_order", default=frame_id_default),
        length_size=length_size,
        length_meaning=length_meaning,
        crc_type=crc_type,
        crc_size=crc_size,
        crc_byte_order=_normalize_byte_order(
            row.get("crc_byte_order", ""), source="protocol", column="crc_byte_order", default=crc_default),
        crc_coverage=(row.get("crc_coverage") or "header_to_payload").strip().lower(),
        footer=_hex_to_bytes(footer_hex_val, "footer_hex"),
        escape_mode=(row.get("escape_mode") or "none").strip().lower(),
        enabled=True,
        parser_type=parser_type_val,
        tx_pad_length=_to_optional_int(row.get("tx_pad_length", ""), field_name="tx_pad_length"),
        inter_frame_delay_ms=_to_int(row.get("inter_frame_delay_ms", "10"), field_name="inter_frame_delay_ms"),
        length_byte_order=length_byte_order,
        raw_log_format=raw_log_format_raw,
        waveshare_fixed_20_bytes=waveshare_fixed_20_bytes,
    )
    _validate_protocol(protocol)
    return protocol


def _validate_protocol(protocol: ProtocolConfig) -> None:
    if protocol.frame_id_size < 1:
        raise ConfigError("protocol: frame_id_size must be >= 1")
    if protocol.parser_type == "framed" and protocol.length_size < 1:
        raise ConfigError("protocol: length_size must be >= 1 for framed protocols")

    expected_crc_sizes = {
        "none": 0,
        "crc16_modbus": 2,
        "crc16_ccitt": 2,
        "crc32": 4,
    }
    expected_crc_size = expected_crc_sizes.get(protocol.crc_type)
    if expected_crc_size is not None and protocol.crc_size != expected_crc_size:
        raise ConfigError(
            f"protocol: crc_size must be {expected_crc_size} when "
            f"crc_type is {protocol.crc_type!r} (got {protocol.crc_size})"
        )

    if protocol.parser_type == "waveshare_can":
        if protocol.header != b"\xAA":
            raise ConfigError("protocol: Waveshare CAN header must be 0xAA")
        if protocol.footer != b"\x55":
            raise ConfigError("protocol: Waveshare CAN footer must be 0x55")
    else:
        if not protocol.header:
            raise ConfigError("protocol: header_hex must not be empty")
    if protocol.frame_id_byte_order not in {"big", "little"}:
        raise ConfigError("protocol: frame_id_byte_order must be big or little")
    if protocol.crc_byte_order not in {"big", "little"}:
        raise ConfigError("protocol: crc_byte_order must be big or little")
    if protocol.length_meaning not in {"payload_only", "frame_total", "header_to_crc", "payload_plus_crc"}:
        raise ConfigError(
            f"protocol: length_meaning must be one of "
            f"'payload_only', 'frame_total', 'header_to_crc', 'payload_plus_crc' "
            f"(got {protocol.length_meaning!r})"
        )
    if protocol.crc_coverage not in {"header_to_payload", "frame_id_to_payload", "payload_only", "full_frame"}:
        raise ConfigError(
            f"protocol: crc_coverage must be one of "
            f"'header_to_payload', 'frame_id_to_payload', 'payload_only', 'full_frame' "
            f"(got {protocol.crc_coverage!r})"
        )
    if protocol.escape_mode not in {"none", "slip", "hdlc", "cobs"}:
        raise ConfigError(
            f"protocol: escape_mode must be one of "
            f"'none', 'slip', 'hdlc', 'cobs' (got {protocol.escape_mode!r})"
        )
    if protocol.parser_type not in {"framed", "waveshare_can", "waveshare_can_20_bytes"}:
        raise ConfigError("protocol: parser_type must be framed, waveshare_can, or waveshare_can_20_bytes")


def _parse_frames(rows: List[Dict[str, str]]) -> Dict[int, FrameDefinition]:
    frames: Dict[int, FrameDefinition] = {}
    for row_no, row in enumerate(rows, start=2):
        if _is_blank_row(row) or (not row.get("frame_id", "").strip() and not row.get("frame_name", "").strip()):
            continue
        frame_id = _parse_frame_id(row["frame_id"], field_name=f"frames row {row_no}.frame_id")
        enabled = _to_bool(row.get("enabled", "true"), default=True, field_name="frames.enabled")
        if not enabled:
            continue
        direction_raw = (row.get("direction", "") or "").strip().lower()
        if direction_raw == "":
            direction = "rxtx"
        elif direction_raw in {"rx", "tx", "rxtx"}:
            direction = direction_raw
        else:
            raise ConfigError(
                f"frames row {row_no}: direction must be 'rx', 'tx', 'rxtx', "
                f"or blank (got {direction_raw!r})"
            )

        payload_length = _to_optional_int(row.get("payload_length", ""), field_name="payload_length")
        if frame_id in frames:
            existing = frames[frame_id]
            merged_dir = "rxtx" if existing.direction != direction else direction
            use_existing_rx = (existing.direction == "rx" or direction == "tx")
            frames[frame_id] = FrameDefinition(
                frame_id=frame_id,
                frame_name=existing.frame_name if use_existing_rx else row.get("frame_name", existing.frame_name),
                payload_length=existing.payload_length if (use_existing_rx and existing.payload_length is not None) else payload_length,
                enabled=enabled or existing.enabled,
                description=existing.description or row.get("description", ""),
                direction=merged_dir,
            )
            continue

        frames[frame_id] = FrameDefinition(
            frame_id=frame_id,
            frame_name=row.get("frame_name", ""),
            payload_length=payload_length,
            enabled=enabled,
            description=row.get("description", ""),
            direction=direction,
        )
    return frames


def _parse_variables(
    rows: List[Dict[str, str]], frames: Dict[int, FrameDefinition], parser_type: str = "framed"
) -> List[SignalSpec]:
    signals: List[SignalSpec] = []
    offsets: Dict[int, int] = {}
    bool_bit_counts: Dict[int, int] = {}
    seen: Dict[int, set[str]] = {}

    default_endian = "little"

    for row_no, row in enumerate(rows, start=2):
        if _is_blank_row(row) or (not row.get("id_or_address", "").strip() and not row.get("signal_name", "").strip()):
            continue
        if not _to_bool(row.get("enabled", "true"), default=True, field_name="variables.enabled"):
            continue
        frame_id = _parse_frame_id(row["id_or_address"], field_name=f"variables row {row_no}.id_or_address")
        if frame_id not in frames:
            frames[frame_id] = FrameDefinition(frame_id=frame_id, frame_name=f"Frame 0x{frame_id:X}")

        name = row["signal_name"].strip()
        if not name:
            raise ConfigError(f"variables row {row_no}: signal_name is required")
        try:
            fmt = FmtType.parse(row["data_type"]).value
        except ValueError as exc:
            raise ConfigError(f"variables row {row_no}: {exc}") from exc

        count = _to_int(row.get("count", "1") or "1", field_name="count")
        if count < 1:
            raise ConfigError(f"variables row {row_no}: count must be >= 1")

        start_index = _to_int(row.get("start_index", "1") or "1", field_name="start_index")

        is_bool = fmt in ("bool", "boolean")
        byte_length = FMT_SIZES[fmt]
        data_type = _fmt_to_data_type(fmt)

        explicit_start = _to_optional_int(row.get("start_byte"), field_name=f"variables row {row_no}.start_byte")
        if explicit_start is not None:
            if frame_id in bool_bit_counts:
                pending = bool_bit_counts.pop(frame_id)
                used = (pending + 7) // 8
                offsets[frame_id] = max(offsets.get(frame_id, 0) + used, explicit_start)
            else:
                offsets[frame_id] = explicit_start
            start = explicit_start
        else:
            start = offsets.get(frame_id, 0)

        if not is_bool and frame_id in bool_bit_counts:
            pending = bool_bit_counts.pop(frame_id)
            used = (pending + 7) // 8
            offsets[frame_id] = max(offsets.get(frame_id, 0) + used, start)
            start = offsets[frame_id]

        frame = frames[frame_id]
        group = row.get("group", "")
        unit = row.get("unit", "")
        endian = _normalize_byte_order(row.get("byte_order", ""), source=f"variables row {row_no}", default=default_endian)

        for idx in range(count):
            curr_idx = start_index + idx
            signal_name = name if count == 1 else f"{name}_{curr_idx}"
            _check_signal_uniqueness(seen, frame_id, signal_name, source="variables")

            explicit_bit_raw = row.get("bit_index") or row.get("bit_offset") or row.get("bit_pos") or ""
            bit_order_raw = (row.get("bit_order") or "").strip().lower()
            if bit_order_raw not in {"", "lsb", "msb"}:
                raise ConfigError(
                    f"variables row {row_no}: bit_order must be 'lsb', 'msb', or blank "
                    f"(got {bit_order_raw!r})"
                )

            if is_bool:
                if explicit_bit_raw.strip():
                    bit_base = _to_int(explicit_bit_raw.strip(), field_name="bit_index")
                    bit_off_val = bit_base + idx
                    sig_start = start + (bit_off_val // 8)
                    bit_in_byte = bit_off_val % 8
                    bool_bit_counts[frame_id] = max(
                        bool_bit_counts.get(frame_id, 0),
                        (sig_start - start) * 8 + bit_in_byte + 1,
                    )
                else:
                    bit_idx = bool_bit_counts.get(frame_id, 0)
                    byte_off = bit_idx // 8
                    bit_in_byte = bit_idx % 8
                    sig_start = start + byte_off
                    bool_bit_counts[frame_id] = bit_idx + 1

                if bit_order_raw == "msb" or (endian == "big" and bit_order_raw != "lsb"):
                    sig_bit_off = 7 - (bit_in_byte % 8)
                else:
                    sig_bit_off = bit_in_byte
            else:
                sig_start = start + idx * byte_length
                sig_bit_off = None

            signals.append(
                SignalSpec(
                    frame_id=frame_id,
                    frame_name=frame.frame_name,
                    signal_name=signal_name,
                    start_byte=sig_start,
                    byte_length=byte_length,
                    endianness=endian,
                    data_type=data_type,
                    scale=_to_float(row.get("scale", ""), 1.0, "scale"),
                    offset=_to_float(row.get("offset", ""), 0.0, "offset"),
                    unit=unit,
                    group=group,
                    index=curr_idx if count > 1 else None,
                    source_name=name,
                    enabled=True,
                    description=row.get("description", ""),
                    read_write=ReadWrite.parse(row.get("read_write", "")).value,
                    min_value=_to_optional_float(row.get("min_value", ""), "variables.min_value"),
                    max_value=_to_optional_float(row.get("max_value", ""), "variables.max_value"),
                    bit_offset=sig_bit_off,
                )
            )
        if not is_bool:
            offsets[frame_id] = start + count * byte_length

    for fid, pending in bool_bit_counts.items():
        used = (pending + 7) // 8
        offsets[fid] = offsets.get(fid, 0) + used

    return signals


def _fmt_to_data_type(fmt: str) -> str:
    if fmt in ("bool", "boolean"):
        return fmt
    if fmt.startswith("float"):
        return "float"
    if fmt.startswith("int"):
        return "int"
    return "uint"


def _parse_legacy_frame_config(
    rows: List[Dict[str, str]], parser_type: str = "framed"
) -> tuple[List[SignalSpec], Dict[int, FrameDefinition]]:
    signals: List[SignalSpec] = []
    frames: Dict[int, FrameDefinition] = {}
    seen_per_frame: Dict[int, set[str]] = {}
    legacy_bool_counts: Dict[tuple[int, int], int] = {}

    default_endian = "little"

    for row_no, row in enumerate(rows, start=2):
        if _is_blank_row(row) or (not row.get("frame_id_hex", "").strip() and not row.get("signal_name", "").strip()):
            continue
        frame_id = _parse_frame_id(row["frame_id_hex"], field_name="frame_id_hex")
        signal_name = row["signal_name"]
        if not signal_name:
            raise ConfigError(f"frame_config row {row_no}: signal_name is required")
        _check_signal_uniqueness(seen_per_frame, frame_id, signal_name, source="frame_config")

        endianness = _normalize_byte_order(
            row["endianness"],
            source=f"frame_config row {row_no}",
            column="endianness",
            default=default_endian,
        )
        byte_length = _to_int(row["byte_length"], field_name="byte_length")
        if byte_length < 1 or byte_length > 8:
            raise ConfigError(f"frame_config row {row_no}: byte_length must be 1..8")
        try:
            raw_dt_str = row["data_type"]
            data_type = DataType.parse(raw_dt_str).value
        except ValueError as exc:
            raise ConfigError(f"frame_config row {row_no}: {exc}") from exc
        if data_type == DataType.FLOAT.value and byte_length not in (4, 8):
            raise ConfigError(f"frame_config row {row_no}: float data_type requires byte_length 4 or 8")

        start_b = _to_int(row["start_byte"], field_name="start_byte")
        is_bool = raw_dt_str.strip().lower() in ("bool", "boolean")
        bit_raw = (row.get("bit_index") or row.get("bit_offset") or row.get("bit_pos") or "").strip()
        bit_order_raw = (row.get("bit_order") or "").strip().lower()
        if bit_order_raw not in {"", "lsb", "msb"}:
            raise ConfigError(
                f"frame_config row {row_no}: bit_order must be 'lsb', 'msb', or blank "
                f"(got {bit_order_raw!r})"
            )

        if is_bool or bit_raw:
            if bit_raw:
                bit_idx_val = _to_int(bit_raw, field_name="bit_index")
            else:
                bit_idx_val = legacy_bool_counts.get((frame_id, start_b), 0)
                legacy_bool_counts[(frame_id, start_b)] = bit_idx_val + 1

            if bit_order_raw == "msb" or (endianness == "big" and bit_order_raw != "lsb"):
                sig_bit_off = 7 - (bit_idx_val % 8)
            else:
                sig_bit_off = bit_idx_val % 8
        else:
            sig_bit_off = None

        frame_name = row["frame_name"]
        frames.setdefault(frame_id, FrameDefinition(frame_id=frame_id, frame_name=frame_name))
        signals.append(
            SignalSpec(
                frame_id=frame_id,
                frame_name=frame_name,
                signal_name=signal_name,
                start_byte=start_b,
                byte_length=byte_length,
                endianness=endianness,
                data_type=data_type,
                scale=_to_float(row["scale"], 1.0, "scale"),
                offset=_to_float(row["offset"], 0.0, "offset"),
                unit=row["unit"],
                source_name=signal_name,
                bit_offset=sig_bit_off,
            )
        )
    return signals, frames


def _validate_signal_ranges(signals: Iterable[SignalSpec]) -> None:
    by_frame: Dict[int, List[SignalSpec]] = {}
    for sig in signals:
        if sig.start_byte < 0:
            raise ConfigError(f"{sig.signal_name}: start_byte must be >= 0")
        by_frame.setdefault(sig.frame_id, []).append(sig)
    for frame_id, specs in by_frame.items():
        ordered = sorted(specs, key=lambda s: (s.start_byte, s.end_byte, s.bit_offset if s.bit_offset is not None else -1))
        last_end = -1
        last_sig: Optional[SignalSpec] = None
        bool_bits_seen: Dict[int, set[int]] = {}  # start_byte → set of bit_offsets
        for sig in ordered:
            if sig.is_boolean and last_sig is not None and last_sig.is_boolean and sig.start_byte == last_sig.start_byte:
                # Check for bit_offset collision within the same byte
                if sig.bit_offset is not None:
                    byte_bits = bool_bits_seen.setdefault(sig.start_byte, set())
                    if sig.bit_offset in byte_bits:
                        raise ConfigError(
                            f"frame 0x{frame_id:X}: boolean signal {sig.signal_name!r} "
                            f"collides with another boolean on byte {sig.start_byte}, "
                            f"bit_offset {sig.bit_offset}"
                        )
                    byte_bits.add(sig.bit_offset)
            elif sig.start_byte < last_end:
                last_name = last_sig.signal_name if last_sig else ""
                raise ConfigError(
                    f"frame 0x{frame_id:X}: signal {sig.signal_name!r} overlaps {last_name!r}"
                )
            else:
                # First boolean at a new start_byte — register its bit
                if sig.is_boolean and sig.bit_offset is not None:
                    bool_bits_seen.setdefault(sig.start_byte, set()).add(sig.bit_offset)
            last_end = sig.end_byte
            last_sig = sig


def _parse_bitfields(
    rows: List[Dict[str, str]], cfg: FrameConfig
) -> Dict[tuple[int, str], List[BitfieldSpec]]:
    _optional_columns_ok(rows, _BITFIELDS_REQUIRED, "bitfields")
    out: Dict[tuple[int, str], List[BitfieldSpec]] = {}
    known = {(s.frame_id, s.source_name or s.signal_name) for s in cfg.all_signals}
    known.update((s.frame_id, s.signal_name) for s in cfg.all_signals)

    seen_bit_indices = {}
    seen_labels = {}

    for row_no, row in enumerate(rows, start=2):
        if _is_blank_row(row) or (not row.get("id_or_address", "").strip() and not row.get("signal_name", "").strip()):
            continue
        frame_id = _parse_frame_id(row["id_or_address"], field_name="bitfields.id_or_address")
        variable_name = row["signal_name"]
        if (frame_id, variable_name) not in known:
            raise ConfigError(f"bitfields row {row_no}: unknown variable {variable_name!r}")

        bit_index = _to_int(row["bit_index"], field_name="bit_index")
        label = row["label"]

        sig_key = (frame_id, variable_name)
        if sig_key not in seen_bit_indices:
            seen_bit_indices[sig_key] = set()
        if bit_index in seen_bit_indices[sig_key]:
            raise ConfigError(
                f"bitfields row {row_no}: duplicate bit_index {bit_index} for signal {variable_name!r}"
            )
        seen_bit_indices[sig_key].add(bit_index)

        if sig_key not in seen_labels:
            seen_labels[sig_key] = set()
        if label in seen_labels[sig_key]:
            raise ConfigError(
                f"bitfields row {row_no}: duplicate bit label {label!r} for signal {variable_name!r}"
            )
        seen_labels[sig_key].add(label)

        out.setdefault((frame_id, variable_name), []).append(
            BitfieldSpec(
                frame_id=frame_id,
                variable_name=variable_name,
                bit_index=bit_index,
                bit_name=label,
                active_text=row.get("active_text", "ON") or "ON",
                inactive_text=row.get("inactive_text", "OFF") or "OFF",
            )
        )
    return out


def _parse_enums(
    rows: List[Dict[str, str]], cfg: FrameConfig
) -> Dict[tuple[int, str], Dict[int, str]]:
    _optional_columns_ok(rows, _ENUMS_REQUIRED, "enums")
    out: Dict[tuple[int, str], Dict[int, str]] = {}
    known = {(s.frame_id, s.source_name or s.signal_name) for s in cfg.all_signals}
    known.update((s.frame_id, s.signal_name) for s in cfg.all_signals)
    for row_no, row in enumerate(rows, start=2):
        if _is_blank_row(row) or (not row.get("id_or_address", "").strip() and not row.get("signal_name", "").strip()):
            continue
        frame_id = _parse_frame_id(row["id_or_address"], field_name="enums.id_or_address")
        variable_name = row["signal_name"]
        if (frame_id, variable_name) not in known:
            raise ConfigError(f"enums row {row_no}: unknown variable {variable_name!r}")
        val = _to_int(row["value"], field_name="enum.value")
        signal_enums = out.setdefault((frame_id, variable_name), {})
        if val in signal_enums:
            raise ConfigError(f"enums row {row_no}: duplicate enum value {val} for signal {variable_name!r}")
        signal_enums[val] = row["label"]
    return out


def _parse_calc_groups(rows: List[Dict[str, str]], cfg: FrameConfig) -> List[CalcGroupSpec]:
    _optional_columns_ok(rows, _CALC_GROUPS_REQUIRED, "calc_groups")
    valid_stats = {"min", "max", "diff", "sum", "avg"}
    groups = {s.group for s in cfg.all_signals if s.group}
    out: List[CalcGroupSpec] = []
    seen = set()
    for row_no, row in enumerate(rows, start=2):
        if _is_blank_row(row) or (not row.get("group_name", "").strip() and not row.get("operations", "").strip()):
            continue
        group = row["group_name"]
        if group not in groups:
            raise ConfigError(f"calc_groups row {row_no}: unknown group {group!r}")
        frame_id = _to_optional_int(row.get("frame_id", ""), field_name="calc_groups.frame_id")
        for stat in row["operations"].split("|"):
            stat = stat.strip().lower()
            if not stat:
                continue
            if stat not in valid_stats:
                raise ConfigError(f"calc_groups row {row_no}: unsupported stat {stat!r}")

            key = (group, stat, frame_id)
            if key in seen:
                raise ConfigError(
                    f"calc_groups row {row_no}: duplicate calculation {stat!r} "
                    f"for group {group!r} (frame {f'0x{frame_id:X}' if frame_id is not None else 'all'})"
                )
            seen.add(key)

            out.append(
                CalcGroupSpec(
                    group=group,
                    stat=stat,
                    unit=row.get("unit", ""),
                    frame_id=frame_id,
                    enabled=_to_bool(row.get("enabled", "true"), default=True, field_name="calc_groups.enabled"),
                )
            )
    return [g for g in out if g.enabled]


def _parse_tx_commands(
    command_rows: List[Dict[str, str]], field_rows: List[Dict[str, str]]
) -> Dict[str, TxCommandSpec]:
    _optional_columns_ok(command_rows, _TX_COMMANDS_REQUIRED, "tx_commands")
    _optional_columns_ok(field_rows, _TX_COMMAND_FIELDS_REQUIRED, "tx_command_fields")

    # Field order on the wire is **row order** in the ``tx_command_fields``
    # sheet. There is no separate ``field_order`` column; reordering the rows
    # silently reorders the payload bytes. The regression test in
    # ``tests/test_tx_command_builder.py::test_field_order_follows_sheet_rows``
    # locks this behaviour so a future shuffle of the loader doesn't break it.
    fields_by_command: Dict[str, List[TxCommandFieldSpec]] = {}
    for row in field_rows:
        if _is_blank_row(row) or (not row.get("command_name", "").strip() and not row.get("signal_name", "").strip()):
            continue
        try:
            fmt = FmtType.parse(row["data_type"]).value
        except ValueError as exc:
            raise ConfigError(f"tx_command_fields: {exc}") from exc
        byte_order = _normalize_byte_order(row.get("byte_order", ""), source="tx_command_fields")
        fields_by_command.setdefault(row["command_name"], []).append(
            TxCommandFieldSpec(
                command_name=row["command_name"],
                field_name=row["signal_name"],
                fmt=fmt,
                unit=row.get("unit", ""),
                factor=_to_float(row.get("scale", ""), 1.0, "tx field scale"),
                offset=_to_float(row.get("offset", ""), 0.0, "tx field offset"),
                byte_order=byte_order,
                min_value=_to_optional_float(row.get("min_value", ""), "tx field min"),
                max_value=_to_optional_float(row.get("max_value", ""), "tx field max"),
                default=_to_optional_float(row.get("default", ""), "tx field default"),
            )
        )

    commands: Dict[str, TxCommandSpec] = {}
    seen_names = set()
    for row in command_rows:
        if _is_blank_row(row) or (not row.get("command_name", "").strip() and not row.get("id_or_address", "").strip()):
            continue
        name = row["command_name"]
        if name in seen_names:
            raise ConfigError(f"Duplicate tx_command defined with name '{name}'")
        seen_names.add(name)
        enabled = _to_bool(row.get("enabled", "true"), default=True, field_name="tx_commands.enabled")
        if not enabled:
            continue
        commands[name] = TxCommandSpec(
            command_name=row["command_name"],
            frame_id=_parse_frame_id(row["id_or_address"], field_name="tx_commands.id_or_address"),
            payload_hex=row.get("payload_hex", ""),
            description=row.get("description", ""),
            enabled=enabled,
            fields=fields_by_command.get(row["command_name"], []),
        )
    return commands


def _parse_serial_defaults(rows: List[Dict[str, str]]) -> SerialDefaults:
    non_blank = [r for r in rows if not _is_blank_row(r)]
    if not non_blank:
        return SerialDefaults()
    _optional_columns_ok(non_blank, _SERIAL_DEFAULTS_REQUIRED, "serial_defaults")
    row = non_blank[0]
    return SerialDefaults(
        baud_rate=_to_int(row.get("baud_rate", 115200), field_name="serial_defaults.baud_rate"),
        data_bits=_to_int(row.get("data_bits", 8), field_name="serial_defaults.data_bits"),
        stop_bits=_to_float(row.get("stop_bits", 1.0), 1.0, "serial_defaults.stop_bits"),
        parity=(row.get("parity", "N") or "N").strip().upper(),
        timeout_ms=_to_int(row.get("timeout_ms", 100), field_name="serial_defaults.timeout_ms"),
    )


def _parse_polling_schedules(rows: List[Dict[str, str]]) -> List[PollingScheduleSpec]:
    if not rows:
        return []
    _optional_columns_ok(rows, _POLLING_SCHEDULE_REQUIRED, "polling_schedule")
    schedules: List[PollingScheduleSpec] = []
    seen_ids = set()
    for row_no, row in enumerate(rows, start=2):
        if _is_blank_row(row) or not row.get("id_or_address", "").strip():
            continue
        enabled = _to_bool(row.get("enabled", "true"), default=True, field_name="polling_schedule.enabled")
        if not enabled:
            continue
        target_id = _parse_frame_id(row["id_or_address"], field_name=f"polling_schedule row {row_no}.id_or_address")
        if target_id in seen_ids:
            raise ConfigError(f"polling_schedule row {row_no}: duplicate polling schedule for ID 0x{target_id:X}")
        seen_ids.add(target_id)
        schedules.append(
            PollingScheduleSpec(
                target_id=target_id,
                interval_ms=_to_int(row["interval_ms"], field_name="polling_schedule.interval_ms"),
                timeout_ms=_to_int(row["timeout_ms"], field_name="polling_schedule.timeout_ms"),
                enabled=enabled,
            )
        )
    return schedules
