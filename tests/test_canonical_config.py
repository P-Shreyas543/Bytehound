"""Canonical JSON configuration (Plane.md Part C, step C1)."""

from __future__ import annotations

import copy
import json

import pytest

from app.decoder import canonical
from app.decoder.config_loader import ConfigError, load_config, read_source_tables
from tools.make_decode_golden import GOLDEN, corpus, decode_snapshot

CORPUS = corpus()
IDS = [c for c, _ in CORPUS]


def _golden(cid):
    return json.loads((GOLDEN / f"{cid}.json").read_text(encoding="utf-8"))["frames"]


def _snap(config):
    return json.loads(json.dumps(decode_snapshot(config), sort_keys=True))


@pytest.mark.parametrize("cid, path", CORPUS, ids=IDS)
def test_canonical_path_decodes_exactly_like_the_source(cid, path, tmp_path):
    """Every configuration: import → canonical → load decodes identically to
    the recorded baseline, in memory and through a saved .json file."""
    doc = canonical.import_config(path)
    assert _snap(load_config(doc)) == _golden(cid)
    saved = tmp_path / "config.json"
    canonical.save_canonical(doc, saved)
    assert _snap(load_config(saved)) == _golden(cid)
    assert canonical.import_config(saved) == json.loads(saved.read_text(encoding="utf-8"))


@pytest.mark.parametrize("cid, path", CORPUS, ids=IDS)
def test_round_trip_is_lossless(cid, path):
    """Tables → canonical → tables gives back every non-blank row, every
    column (unknown ones included) and every unknown sheet, as text."""
    tables, _fmt = read_source_tables(path)
    doc = canonical.tables_to_canonical(tables)
    back = canonical.canonical_to_tables(doc)
    back.update(doc.get("extra_tables", {}))
    expect = {name: [r for r in rows if any(str(v).strip() for v in r.values())] for name, rows in tables.items()}
    assert back == expect


def test_unknown_sheets_and_columns_are_kept():
    tables = {
        "protocol": [{"profile_name": "P", "parser_type": "framed", "vendor_note": "keep me"}],
        "readme": [{"text": "how to use"}],
    }
    doc = canonical.tables_to_canonical(tables)
    assert doc["tables"]["protocol"][0]["extensions"] == {"vendor_note": "keep me"}
    assert doc["extra_tables"] == {"readme": [{"text": "how to use"}]}


@pytest.mark.parametrize("kind, text, typed", [
    ("int", "8", 8), ("int", "08", "08"), ("int", "0x10", "0x10"),
    ("float", "0.01", 0.01), ("float", "-40", -40.0), ("float", "1.0", "1.0"), ("float", "1e-3", "1e-3"),
    ("float", "nan", "nan"), ("bool", "TRUE", True), ("bool", "FALSE", False), ("bool", "true", "true"),
    ("text", "AA 55", "AA 55"), ("int", "", ""),
])
def test_values_are_typed_only_when_exact(kind, text, typed):
    value = canonical._typed(text, kind)
    assert value == typed and type(value) is type(typed)
    assert canonical._text_of(value) == text                # always back to the same text


def test_fingerprint_ignores_import_metadata_and_tracks_content(tmp_path):
    path = CORPUS[0][1]
    a = canonical.import_config(path)
    b = copy.deepcopy(a)
    b["import"] = {"source_format": "xlsx", "source_name": "elsewhere.xlsx"}
    assert canonical.fingerprint(a) == canonical.fingerprint(b)
    saved = tmp_path / "c.json"
    canonical.save_canonical(a, saved)
    assert canonical.fingerprint(json.loads(saved.read_text(encoding="utf-8"))) == canonical.fingerprint(a)
    b["tables"]["variables"][0]["scale"] = 0.02
    assert canonical.fingerprint(a) != canonical.fingerprint(b)


def test_unsupported_schema_version_is_rejected(tmp_path):
    doc = canonical.import_config(CORPUS[0][1])
    doc["schema_version"] = 99
    with pytest.raises(ConfigError, match="schema_version 99"):
        load_config(doc)
    p = tmp_path / "future.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ConfigError, match="schema_version 99"):
        load_config(p)


def test_legacy_table_json_still_loads():
    """The Config Editor's existing JSON (a mapping of tables) is not canonical
    and keeps loading through the old path."""
    tables, _ = read_source_tables(CORPUS[0][1])
    legacy = {name: rows for name, rows in tables.items()}
    assert not canonical.is_canonical(legacy)
    assert _snap(load_config(legacy)) == _golden(CORPUS[0][0])


def test_save_is_atomic(tmp_path, monkeypatch):
    doc = canonical.import_config(CORPUS[0][1])
    target = tmp_path / "config.json"
    canonical.save_canonical(doc, target)
    before = target.read_bytes()

    def crash(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(canonical.os, "fsync", crash)
    doc["tables"]["variables"][0]["scale"] = 0.5
    with pytest.raises(OSError):
        canonical.save_canonical(doc, target)
    assert target.read_bytes() == before                   # previous file intact
