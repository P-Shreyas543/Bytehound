"""Canonical JSON protocol configuration (Plane.md Part C, step C1).

The canonical document is the typed, *pre-expansion* form of the
configuration tables every input format already produces (xlsx sheets, CSV
files, table JSON, YAML). It is converted back into the same string rows and
parsed by the existing loader, so live decoding from a canonical file is
identical by construction (tests/test_config_corpus.py proves it for every
configuration in the repository).

Lossless by design:

* known columns are stored as JSON numbers / booleans when their text
  converts and converts back to the same text; anything else stays the
  original text (validation, not conversion, decides whether it is valid);
* columns the loader does not know are kept per row under ``extensions``;
* sheets / files the loader does not know (e.g. a ``readme`` sheet) are kept
  under ``extra_tables``;
* column names are kept as written in the source (aliases included).

Document shape (``schema_version`` 1)::

    {"format": "bytehound.protocol", "schema_version": 1,
     "tables": {"protocol": [ {...}, ... ], "variables": [...], ...},
     "extra_tables": {"readme": [ {...} ]},
     "import": {"source_format": ..., "source_name": ..., "source_sha256": ...,
                "imported_utc": ..., "app_version": ...}}

The fingerprint is the SHA-256 of the document without its ``import`` block,
serialised with sorted keys and no whitespace: the same protocol imported
from CSV or from xlsx has the same fingerprint.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

FORMAT = "bytehound.protocol"
SCHEMA_VERSION = 1


class CanonicalError(ValueError):
    """The document is not a canonical configuration this version can read."""


# Columns the loader reads, per table, and their JSON type. Aliases the
# loader accepts are listed too. ``text`` stays a string (names, hex
# bytes / ids, enumerations); ``int`` / ``float`` / ``bool`` are converted
# only when the conversion round-trips exactly.
_T = "text"
KNOWN_COLUMNS: Dict[str, Dict[str, str]] = {
    "protocol": {
        "profile_name": _T, "parser_type": _T, "header_hex": _T, "frame_id_size": "int",
        "frame_id_byte_order": _T, "length_size": "int", "length_meaning": _T, "length_byte_order": _T,
        "crc_type": _T, "crc_size": "int", "crc_byte_order": _T, "crc_coverage": _T, "footer_hex": _T,
        "escape_mode": _T, "raw_log_format": _T, "inter_frame_delay_ms": "int", "tx_pad_length": "int",
        "waveshare_fixed": "bool", "waveshare_fixed_20_bytes": "bool", "enabled": "bool",
    },
    "frames": {
        "frame_id": _T, "frame_name": _T, "payload_length": "int", "direction": _T, "enabled": "bool",
        "description": _T,
    },
    "variables": {
        "id_or_address": _T, "signal_name": _T, "data_type": _T, "count": "int", "start_index": "int",
        "byte_order": _T, "scale": "float", "offset": "float", "unit": _T, "group": _T, "read_write": _T,
        "min_value": "float", "max_value": "float", "description": _T, "enabled": "bool",
        "start_byte": "int", "bit_offset": "int", "bit_index": "int", "bit_pos": "int", "bit_length": "int",
        "bit_count": "int", "bits": "int", "bit_order": _T,
    },
    "frame_config": {
        "frame_id_hex": _T, "frame_name": _T, "signal_name": _T, "start_byte": "int", "byte_length": "int",
        "endianness": _T, "data_type": _T, "scale": "float", "offset": "float", "unit": _T, "group": _T,
        "description": _T, "enabled": "bool", "bit_offset": "int", "bit_index": "int", "bit_pos": "int",
        "bit_order": _T,
    },
    "bitfields": {
        "id_or_address": _T, "signal_name": _T, "bit_index": "int", "label": _T, "active_text": _T,
        "inactive_text": _T,
    },
    "enums": {"id_or_address": _T, "signal_name": _T, "value": "int", "label": _T},
    "calc_groups": {"group_name": _T, "operations": _T, "unit": _T, "frame_id": _T, "enabled": "bool"},
    "tx_commands": {"command_name": _T, "id_or_address": _T, "payload_hex": _T, "description": _T,
                    "enabled": "bool"},
    "tx_command_fields": {
        "command_name": _T, "signal_name": _T, "data_type": _T, "byte_order": _T, "scale": "float",
        "offset": "float", "unit": _T, "min_value": "float", "max_value": "float", "default": "float",
    },
    "serial_defaults": {"baud_rate": "int", "data_bits": "int", "stop_bits": "float", "parity": _T,
                        "timeout_ms": "int"},
    "polling_schedule": {"id_or_address": _T, "interval_ms": "int", "timeout_ms": "int", "enabled": "bool"},
    "sequence_counters": {"id_or_address": _T, "signal_name": _T, "bits": "int", "step": "int",
                          "enabled": "bool"},
}

def _typed(text: str, kind: str) -> Any:
    """``text`` as a JSON value of ``kind`` when that is exact, else ``text``."""
    if kind == _T or text == "":
        return text
    if kind == "bool":
        # Only the exact texts the sheets use: "true" / "True" stay text so
        # the round trip is byte-for-byte (the loader reads all of them alike).
        return {"TRUE": True, "FALSE": False}.get(text, text)
    if kind == "int":
        try:
            v = int(text, 10)
        except ValueError:
            return text
        return v if str(v) == text else text
    if kind == "float":
        try:
            v = float(text)
        except ValueError:
            return text
        if not math.isfinite(v) or _text_of(v) != text:
            return text
        return v
    return text


def _text_of(value: Any) -> str:
    """The text a typed value came from (inverse of ``_typed``)."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        t = repr(value)
        return t[:-2] if t.endswith(".0") and "e" not in t else t
    return str(value)


def tables_to_canonical(tables: Dict[str, List[Dict[str, str]]],
                        source: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Tables of string rows (as the loader reads them) → canonical document."""
    known_out: Dict[str, List[Dict[str, Any]]] = {}
    extra: Dict[str, List[Dict[str, str]]] = {}
    for name in sorted(tables):
        rows = [r for r in tables[name] if any(str(v).strip() for v in r.values())]
        spec = KNOWN_COLUMNS.get(name)
        if spec is None:
            extra[name] = [dict(r) for r in rows]
            continue
        out_rows = []
        for r in rows:
            entry: Dict[str, Any] = {}
            ext: Dict[str, str] = {}
            for col, text in r.items():
                text = "" if text is None else str(text)
                if col in spec:
                    entry[col] = _typed(text, spec[col])
                elif col:
                    ext[col] = text
            if ext:
                entry["extensions"] = ext
            out_rows.append(entry)
        known_out[name] = out_rows
    doc: Dict[str, Any] = {"format": FORMAT, "schema_version": SCHEMA_VERSION, "tables": known_out}
    if extra:
        doc["extra_tables"] = extra
    if source:
        doc["import"] = dict(source)
    return doc


def canonical_to_tables(doc: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
    """Canonical document → the string rows the loader parses."""
    check_document(doc)
    tables: Dict[str, List[Dict[str, str]]] = {}
    for name, rows in doc.get("tables", {}).items():
        out = []
        for entry in rows:
            row = {col: _text_of(v) for col, v in entry.items() if col != "extensions"}
            row.update({col: str(v) for col, v in (entry.get("extensions") or {}).items()})
            out.append(row)
        tables[name] = out
    return tables


def check_document(doc: Any) -> None:
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise CanonicalError(f'not a canonical configuration (missing "format": "{FORMAT}")')
    version = doc.get("schema_version")
    if version != SCHEMA_VERSION:
        raise CanonicalError(f"schema_version {version!r} is not supported by this version "
                             f"(supports {SCHEMA_VERSION})")
    if not isinstance(doc.get("tables"), dict):
        raise CanonicalError('canonical configuration has no "tables" object')


def is_canonical(data: Any) -> bool:
    return isinstance(data, dict) and data.get("format") == FORMAT


def fingerprint(doc: Dict[str, Any]) -> str:
    """SHA-256 of the protocol content (the ``import`` block excluded)."""
    body = {k: v for k, v in doc.items() if k != "import"}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _source_sha256(path: Path) -> str:
    h = hashlib.sha256()
    files = sorted(path.glob("*.csv")) if path.is_dir() else [path]
    for f in files:
        h.update(f.name.encode("utf-8"))
        h.update(f.read_bytes())
    return h.hexdigest()


def import_config(path: str | Path, *, app_version: str = "") -> Dict[str, Any]:
    """Any supported input (xlsx, CSV folder, table JSON, YAML, canonical
    JSON) → canonical document. The source is never modified."""
    from .config_loader import read_source_tables
    path = Path(path)
    data = None
    if path.is_file() and path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if is_canonical(data):
            check_document(data)
            return data
    tables, fmt = read_source_tables(path)
    source = {
        "source_format": fmt,
        "source_name": path.name,
        "source_sha256": _source_sha256(path),
        "imported_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "app_version": app_version,
    }
    return tables_to_canonical(tables, source)


def dumps(doc: Dict[str, Any]) -> str:
    """Stable, readable serialisation (sorted keys, 2-space indent)."""
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def save_canonical(doc: Dict[str, Any], path: str | Path) -> None:
    """Write atomically: a crash mid-save leaves the previous file intact."""
    check_document(doc)
    path = Path(path)
    tmp = path.with_name(path.name + ".partial")
    with tmp.open("w", encoding="utf-8", newline="\n") as fp:
        fp.write(dumps(doc))
        fp.flush()
        os.fsync(fp.fileno())
    os.replace(tmp, path)
