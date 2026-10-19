"""Configuration validation report (Plane.md Part C, step C2).

Three layers, each reported with where the problem is and what to do:

1. **Structure** of a canonical document (``check_structure``): format and
   schema version, table / row / value shapes, required tables. Errors.
2. **Loader rules**: everything ``load_config`` already rejects (types,
   duplicates, byte overlaps, unknown references, …). Errors — unchanged,
   so every configuration that loads today still loads.
3. **Semantic warnings** (``semantic_warnings``): problems the loader has
   never rejected. They are reported, never block loading: 6 signals in the
   regression corpus already extend past their frame's declared
   ``payload_length`` and those configurations must keep working.

``validate(source)`` runs all three and returns a ``ValidationReport``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import canonical
from .types import FrameConfig


@dataclass(frozen=True)
class Issue:
    level: str          # "error" | "warning"
    where: str          # e.g. "variables row 7", "frame 0x1F0 / Balancing_Status"
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper()}: {self.where}: {self.message}"


@dataclass
class ValidationReport:
    issues: List[Issue] = field(default_factory=list)
    config: Optional[FrameConfig] = None
    fingerprint: Optional[str] = None

    @property
    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> List[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


_SCALAR = (str, int, float, bool, type(None))


def check_structure(doc: Any) -> List[Issue]:
    """Shape of a canonical document (the in-house equivalent of the shipped
    JSON Schema ``protocol_config.schema.json``)."""
    issues: List[Issue] = []
    try:
        canonical.check_document(doc)
    except canonical.CanonicalError as exc:
        return [Issue("error", "document", str(exc))]
    tables = doc["tables"]
    for name, rows in tables.items():
        if not isinstance(rows, list):
            issues.append(Issue("error", f"tables.{name}", "must be a list of rows"))
            continue
        for i, row in enumerate(rows, start=1):
            where = f"tables.{name}[{i}]"
            if not isinstance(row, dict):
                issues.append(Issue("error", where, "a row must be an object"))
                continue
            for col, value in row.items():
                if col == "extensions":
                    if not isinstance(value, dict) or not all(isinstance(v, str) for v in value.values()):
                        issues.append(Issue("error", f"{where}.extensions", "must map column names to text"))
                elif not isinstance(value, _SCALAR):
                    issues.append(Issue("error", f"{where}.{col}", "must be text, a number, true/false or null"))
                elif isinstance(value, float) and not math.isfinite(value):
                    issues.append(Issue("error", f"{where}.{col}", "numbers must be finite"))
    if "protocol" not in tables:
        issues.append(Issue("error", "tables", 'a "protocol" table is required'))
    if "variables" not in tables and "frame_config" not in tables:
        issues.append(Issue("error", "tables", 'a "variables" (or legacy "frame_config") table is required'))
    extra = doc.get("extra_tables", {})
    if not isinstance(extra, dict):
        issues.append(Issue("error", "extra_tables", "must be an object"))
    return issues


def semantic_warnings(config: FrameConfig) -> List[Issue]:
    out: List[Issue] = []
    for fid in sorted(config.frames):
        if not config.signals_by_frame.get(fid):
            out.append(Issue("warning", f"frame 0x{fid:X}", "has no signals"))
    for fid, sigs in sorted(config.signals_by_frame.items()):
        plen = getattr(config.frames.get(fid), "payload_length", None)
        for s in sigs:
            where = f"frame 0x{fid:X} / {s.signal_name}"
            if plen and s.start_byte + s.byte_length > plen:
                out.append(Issue("warning", where,
                                 f"bytes {s.start_byte}..{s.start_byte + s.byte_length - 1} lie beyond the frame's "
                                 f"payload_length {plen}: it can only decode if the device sends a longer payload "
                                 "(fix payload_length or the signal's start_byte)"))
            if not math.isfinite(s.scale) or s.scale == 0:
                out.append(Issue("warning", where, f"scale {s.scale} makes every value the offset"))
            if s.min_value is not None and s.max_value is not None and s.min_value > s.max_value:
                out.append(Issue("warning", where, f"min_value {s.min_value} > max_value {s.max_value}"))
    for (fid, name), bits in sorted(config.bitfields.items()):
        sig = next((s for s in config.signals_by_frame.get(fid, [])
                    if s.signal_name == name or s.source_name == name), None)
        if sig is None:
            continue
        width = sig.bit_length or sig.byte_length * 8
        for b in bits:
            if b.bit_index >= width:
                out.append(Issue("warning", f"frame 0x{fid:X} / {name}",
                                 f"bitfield {b.bit_name!r} uses bit {b.bit_index}, beyond the {width}-bit signal"))
    return out


def validate(source: Any) -> ValidationReport:
    """Validate a canonical document, a table mapping or a path to any
    supported configuration source."""
    from .config_loader import ConfigError, load_config

    report = ValidationReport()
    doc: Optional[Dict[str, Any]] = None
    if isinstance(source, dict) and canonical.is_canonical(source):
        doc = source
    elif not isinstance(source, dict):
        try:
            doc = canonical.import_config(source)
        except (ConfigError, canonical.CanonicalError, OSError, ValueError) as exc:
            report.issues.append(Issue("error", "source", str(exc)))
            return report
    if doc is not None:
        report.issues += check_structure(doc)
        if report.errors:
            return report
        report.fingerprint = canonical.fingerprint(doc)
    try:
        report.config = load_config(doc if doc is not None else source)
    except ConfigError as exc:
        report.issues.append(Issue("error", "configuration", str(exc)))
        return report
    report.issues += semantic_warnings(report.config)
    return report
