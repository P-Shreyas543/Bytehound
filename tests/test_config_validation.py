"""Configuration validation report (Plane.md Part C, step C2)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.decoder import canonical
from app.decoder.config_loader import read_source_tables
from app.decoder.validation import check_structure, validate
from tools.make_decode_golden import corpus

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "app" / "resources" / "config_template"
CORPUS = corpus()

# The only problems the new rules find in the repository's configurations:
# frame 0x1F0 declares payload_length 3 but defines signals up to byte 4,
# in three related customer workbooks. They load and are only warned about.
KNOWN_CORPUS_WARNINGS = {
    "Blue01_M_CAN_4836_xlsx": 2, "DB_48100_xlsx": 2, "the_energy_company_4850_xlsx": 2,
}


@pytest.mark.parametrize("cid, path", CORPUS, ids=[c for c, _ in CORPUS])
def test_every_configuration_validates_without_errors(cid, path):
    report = validate(path)
    assert report.ok, [str(i) for i in report.errors]
    assert report.config is not None and len(report.fingerprint) == 64
    assert len(report.warnings) == KNOWN_CORPUS_WARNINGS.get(cid, 0), [str(w) for w in report.warnings]
    assert all("payload_length 3" in w.message for w in report.warnings)


def _doc():
    tables, _ = read_source_tables(TEMPLATE)
    return canonical.tables_to_canonical(tables)


@pytest.mark.parametrize("mutate, where", [
    (lambda d: d.pop("format"), "document"),
    (lambda d: d.__setitem__("schema_version", 2), "document"),
    (lambda d: d["tables"].__setitem__("frames", {"not": "a list"}), "tables.frames"),
    (lambda d: d["tables"]["frames"].__setitem__(0, ["row", "as", "list"]), "tables.frames[1]"),
    (lambda d: d["tables"]["variables"][0].__setitem__("scale", [1, 2]), "tables.variables[1].scale"),
    (lambda d: d["tables"]["variables"][0].__setitem__("scale", float("nan")), "tables.variables[1].scale"),
    (lambda d: d["tables"]["variables"][0].__setitem__("extensions", {"x": 5}), "tables.variables[1].extensions"),
    (lambda d: d["tables"].pop("protocol"), "tables"),
    (lambda d: (d["tables"].pop("variables"), d["tables"].pop("frame_config")), "tables"),
])
def test_structure_errors_say_where(mutate, where):
    doc = _doc()
    mutate(doc)
    issues = check_structure(doc)
    assert issues and all(i.level == "error" for i in issues)
    assert any(i.where == where for i in issues), [str(i) for i in issues]
    report = validate(doc) if canonical.is_canonical(doc) else None
    if report is not None:
        assert not report.ok and report.config is None


def test_loader_rules_stay_errors():
    doc = _doc()
    dup = copy.deepcopy(doc["tables"]["variables"][0])
    doc["tables"]["variables"].append(dup)                    # duplicate signal name in a frame
    report = validate(doc)
    assert not report.ok and report.config is None
    assert report.errors[0].where == "configuration"


@pytest.mark.parametrize("mutate, text", [
    (lambda d: d["tables"]["variables"][0].__setitem__("scale", 0), "scale 0"),
    (lambda d: (d["tables"]["variables"][0].__setitem__("min_value", 50.0),
                d["tables"]["variables"][0].__setitem__("max_value", 10.0)), "min_value 50.0 > max_value 10.0"),
    (lambda d: d["tables"]["bitfields"][0].__setitem__("bit_index", 15), "beyond the 8-bit signal"),
    (lambda d: d["tables"]["frames"].append(dict(d["tables"]["frames"][0], frame_id="0x7777",
                                                  frame_name="Empty")), "has no signals"),
    (lambda d: next(f for f in d["tables"]["frames"] if f["frame_id"] == "0x1000").__setitem__(
        "payload_length", 4), "beyond the frame's payload_length 4"),
])
def test_semantic_warnings_never_block_loading(mutate, text):
    doc = _doc()
    mutate(doc)
    report = validate(doc)
    assert report.ok and report.config is not None, [str(i) for i in report.errors]
    assert any(text in w.message for w in report.warnings), [str(w) for w in report.warnings]


def test_unreadable_source_is_an_error_not_a_crash(tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text("{ not json", encoding="utf-8")
    report = validate(bad)
    assert not report.ok and report.errors[0].where == "source"
    assert not validate(tmp_path / "missing_dir_or_file").ok


def test_shipped_schema_matches_the_checker():
    schema = json.loads((ROOT / "app" / "resources" / "protocol_config.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["format"]["const"] == canonical.FORMAT
    assert schema["properties"]["schema_version"]["const"] == canonical.SCHEMA_VERSION
    assert set(schema["required"]) == {"format", "schema_version", "tables"}
