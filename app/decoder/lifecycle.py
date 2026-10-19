"""Configuration lifecycle (Plane.md Part C, step C4).

1. ``prepare_candidate`` imports a source into a **candidate**: it is read,
   converted to canonical JSON, validated and compared with the active
   configuration. Nothing active is touched; a failed import is a candidate
   with errors, never an exception that leaves half-applied state.
2. The caller shows the preview (errors, warnings, ``ConfigDiff``) and
   activates only on an explicit confirm, and only when there are no errors.
3. ``ConfigHistory`` keeps the last activated configurations as canonical
   documents so an earlier one can be restored.

Pure Python, no Qt: the Config Editor / Protocol Studio (Part D) use the
same services.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import canonical
from .types import FrameConfig, SignalSpec
from .validation import Issue, ValidationReport, validate

Key = Tuple[int, str]

# Sections compared as a whole (any difference is reported by name).
_SECTIONS = ("bitfields", "enums", "calc_groups", "tx_commands", "serial_defaults",
             "polling_schedules", "sequence_counters")


@dataclass
class SignalChange:
    key: Key
    changes: Dict[str, Tuple[Any, Any]]       # field -> (old, new)


@dataclass
class ConfigDiff:
    """Active → candidate, signals matched by their stable id
    ``(frame_id, signal_name)``."""

    added: List[Key] = field(default_factory=list)
    removed: List[Key] = field(default_factory=list)
    modified: List[SignalChange] = field(default_factory=list)
    unchanged: int = 0
    frames_added: List[int] = field(default_factory=list)
    frames_removed: List[int] = field(default_factory=list)
    protocol: Dict[str, Tuple[Any, Any]] = field(default_factory=dict)
    sections: List[str] = field(default_factory=list)   # other tables that differ

    @property
    def identical(self) -> bool:
        return not (self.added or self.removed or self.modified or self.frames_added
                    or self.frames_removed or self.protocol or self.sections)

    def summary_lines(self) -> List[str]:
        if self.identical:
            return [f"No changes ({self.unchanged} signals)."]
        out = [f"Signals: {len(self.added)} added, {len(self.removed)} removed, "
               f"{len(self.modified)} modified, {self.unchanged} unchanged"]
        if self.frames_added or self.frames_removed:
            out.append(f"Frames: {len(self.frames_added)} added, {len(self.frames_removed)} removed")
        for name, (old, new) in sorted(self.protocol.items()):
            out.append(f"Protocol {name}: {_show(old)} → {_show(new)}")
        if self.sections:
            out.append("Also changed: " + ", ".join(self.sections))
        return out

    def detail_lines(self, limit: int = 200) -> List[str]:
        out: List[str] = []
        for fid, name in self.added:
            out.append(f"+ 0x{fid:X} {name}")
        for fid, name in self.removed:
            out.append(f"- 0x{fid:X} {name}")
        for ch in self.modified:
            fid, name = ch.key
            what = ", ".join(f"{k} {_show(a)} → {_show(b)}" for k, (a, b) in sorted(ch.changes.items()))
            out.append(f"~ 0x{fid:X} {name}: {what}")
        if len(out) > limit:
            out = out[:limit] + [f"… and {len(out) - limit} more"]
        return out


def _show(value: Any) -> str:
    if isinstance(value, bytes):
        return value.hex(" ").upper() or "(none)"
    return repr(value)


def _signals(config: FrameConfig) -> Dict[Key, SignalSpec]:
    return {(s.frame_id, s.signal_name): s for s in config.all_signals}


def diff_configs(old: Optional[FrameConfig], new: FrameConfig) -> ConfigDiff:
    diff = ConfigDiff()
    new_sigs = _signals(new)
    if old is None:
        diff.added = sorted(new_sigs)
        diff.frames_added = sorted(new.frames)
        return diff
    old_sigs = _signals(old)
    diff.added = sorted(k for k in new_sigs if k not in old_sigs)
    diff.removed = sorted(k for k in old_sigs if k not in new_sigs)
    for key in sorted(k for k in new_sigs if k in old_sigs):
        a, b = old_sigs[key], new_sigs[key]
        changes = {f.name: (getattr(a, f.name), getattr(b, f.name))
                   for f in fields(SignalSpec) if getattr(a, f.name) != getattr(b, f.name)}
        if changes:
            diff.modified.append(SignalChange(key, changes))
        else:
            diff.unchanged += 1
    diff.frames_added = sorted(set(new.frames) - set(old.frames))
    diff.frames_removed = sorted(set(old.frames) - set(new.frames))
    for f in fields(type(new.protocol)):
        a, b = getattr(old.protocol, f.name, None), getattr(new.protocol, f.name, None)
        if a != b:
            diff.protocol[f.name] = (a, b)
    changed_frames = [fid for fid in set(old.frames) & set(new.frames) if old.frames[fid] != new.frames[fid]]
    if changed_frames:
        diff.sections.append("frames (" + ", ".join(f"0x{fid:X}" for fid in sorted(changed_frames)) + ")")
    diff.sections += [name for name in _SECTIONS if getattr(old, name) != getattr(new, name)]
    return diff


@dataclass
class Candidate:
    """An imported configuration that is not active yet."""

    source: Any
    doc: Optional[Dict[str, Any]]
    report: ValidationReport
    diff: Optional[ConfigDiff]

    @property
    def can_activate(self) -> bool:
        return self.report.ok and self.report.config is not None

    @property
    def config(self) -> Optional[FrameConfig]:
        return self.report.config

    @property
    def fingerprint(self) -> Optional[str]:
        return self.report.fingerprint


def prepare_candidate(source: Any, active: Optional[FrameConfig] = None) -> Candidate:
    """Import ``source`` (path, canonical document or table mapping) as a
    candidate. Never raises for a bad configuration: problems are in
    ``candidate.report``."""
    doc: Optional[Dict[str, Any]] = None
    if isinstance(source, dict) and canonical.is_canonical(source):
        doc = source
    elif not isinstance(source, dict):
        try:
            doc = canonical.import_config(source)
        except Exception as exc:  # unreadable source: reported, not raised
            report = ValidationReport(issues=[Issue("error", "source", str(exc))])
            return Candidate(source, None, report, None)
    report = validate(doc if doc is not None else source)
    diff = diff_configs(active, report.config) if report.config is not None else None
    return Candidate(source, doc, report, diff)


# ---------------------------------------------------------------------------
# Rollback history
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HistoryEntry:
    path: Path
    saved_utc: str
    fingerprint: str
    source_name: str
    profile_name: str

    @property
    def label(self) -> str:
        return f"{self.saved_utc}  {self.profile_name or '?'}  ({self.source_name or 'unknown source'})"


class ConfigHistory:
    """The last ``keep`` activated configurations, newest first, as canonical
    JSON files in ``folder``. Recording the configuration that is already
    newest does nothing, so reloading the same file does not fill the list."""

    INDEX = "index.json"

    def __init__(self, folder: Path, keep: int = 20) -> None:
        self.folder = Path(folder)
        self.keep = max(1, int(keep))

    def _read_index(self) -> List[Dict[str, Any]]:
        try:
            data = json.loads((self.folder / self.INDEX).read_text(encoding="utf-8"))
            return [e for e in data.get("entries", []) if isinstance(e, dict) and e.get("file")]
        except (OSError, ValueError, AttributeError):
            return []

    def _write_index(self, entries: List[Dict[str, Any]]) -> None:
        tmp = self.folder / (self.INDEX + ".partial")
        with tmp.open("w", encoding="utf-8") as fp:
            json.dump({"entries": entries}, fp, indent=2)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp, self.folder / self.INDEX)

    def entries(self) -> List[HistoryEntry]:
        out = []
        for e in self._read_index():
            path = self.folder / e["file"]
            if path.exists():
                out.append(HistoryEntry(path, e.get("saved_utc", ""), e.get("fingerprint", ""),
                                        e.get("source_name", ""), e.get("profile_name", "")))
        return out

    def record(self, doc: Dict[str, Any]) -> Optional[HistoryEntry]:
        """Save ``doc`` as the newest entry; returns it, or ``None`` when it
        is already the newest."""
        fp = canonical.fingerprint(doc)
        index = self._read_index()
        if index and index[0].get("fingerprint") == fp and (self.folder / index[0]["file"]).exists():
            return None
        self.folder.mkdir(parents=True, exist_ok=True)
        now = time.time()
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
        name = f"{stamp}_{fp[:12]}.json"
        canonical.save_canonical(doc, self.folder / name)
        protocol = (doc.get("tables", {}).get("protocol") or [{}])[0]
        entry = {
            "file": name,
            "saved_utc": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime(now)),
            "fingerprint": fp,
            "source_name": str(doc.get("import", {}).get("source_name", "")),
            "profile_name": str(protocol.get("profile_name", "")),
        }
        index = [entry] + [e for e in index if e["file"] != name]
        keep, drop = index[: self.keep], index[self.keep:]
        self._write_index(keep)
        for e in drop:
            try:
                (self.folder / e["file"]).unlink(missing_ok=True)
            except OSError:
                pass
        return self.entries()[0]
