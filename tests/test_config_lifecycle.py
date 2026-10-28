"""Configuration lifecycle: candidate, preview diff, rollback history
(Plane.md Part C, step C4)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from app.decoder import canonical
from app.decoder.config_loader import load_config, read_source_tables
from app.decoder.lifecycle import ConfigHistory, diff_configs, prepare_candidate

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "app" / "resources" / "config_template"


def _doc():
    tables, _ = read_source_tables(TEMPLATE)
    return canonical.tables_to_canonical(tables)


def test_candidate_of_the_same_configuration_has_no_changes():
    active = load_config(TEMPLATE)
    c = prepare_candidate(TEMPLATE, active)
    assert c.can_activate and c.diff.identical
    assert c.diff.unchanged == len(active.all_signals)
    assert len(c.fingerprint) == 64


def test_diff_reports_signal_and_protocol_changes_by_stable_id():
    active = load_config(TEMPLATE)
    doc = _doc()
    var = doc["tables"]["variables"]
    var[0]["scale"] = 0.5                                   # modified
    removed = var.pop(1)                                    # removed
    doc["tables"]["protocol"][0]["profile_name"] = "Renamed"
    c = prepare_candidate(doc, active)
    assert c.can_activate and not c.diff.identical
    changed = {k: ch.changes for ch in c.diff.modified for k in [ch.key]}
    assert any("scale" in ch and ch["scale"][1] == 0.5 for ch in changed.values())
    assert any(name.startswith(removed["signal_name"]) for _fid, name in c.diff.removed)
    assert c.diff.protocol["profile_name"][1] == "Renamed"
    assert any("Protocol profile_name" in line for line in c.diff.summary_lines())


def test_first_load_lists_everything_as_added():
    new = load_config(TEMPLATE)
    d = diff_configs(None, new)
    assert len(d.added) == len(new.all_signals) and not d.removed


def test_a_bad_import_is_a_candidate_with_errors_never_an_exception(tmp_path):
    active = load_config(TEMPLATE)
    before = copy.deepcopy(active)
    bad = tmp_path / "broken.json"
    bad.write_text("{ not json", encoding="utf-8")
    c = prepare_candidate(bad, active)
    assert not c.can_activate and c.config is None and c.diff is None
    assert c.report.errors[0].where == "source"
    doc = _doc()
    doc["tables"]["variables"].append(copy.deepcopy(doc["tables"]["variables"][0]))  # duplicate
    c = prepare_candidate(doc, active)
    assert not c.can_activate and c.report.errors
    assert active == before                                 # the active one is untouched


def test_history_keeps_the_newest_and_skips_repeats(tmp_path):
    h = ConfigHistory(tmp_path / "hist", keep=2)
    a = _doc()
    first = h.record(a)
    assert first is not None and h.record(a) is None        # same as newest: not recorded twice
    b = copy.deepcopy(a)
    b["tables"]["variables"][0]["scale"] = 0.25
    c = copy.deepcopy(a)
    c["tables"]["variables"][0]["scale"] = 0.75
    h.record(b)
    h.record(c)
    entries = h.entries()
    assert [e.fingerprint for e in entries] == [canonical.fingerprint(c), canonical.fingerprint(b)]
    assert not first.path.exists()                          # pruned beyond keep
    assert len(list((tmp_path / "hist").glob("*.json"))) == 3   # 2 entries + index


def test_restoring_a_history_entry_gives_the_same_configuration(tmp_path):
    h = ConfigHistory(tmp_path / "hist")
    doc = canonical.import_config(TEMPLATE)
    entry = h.record(doc)
    restored = prepare_candidate(entry.path, None)
    assert restored.can_activate and restored.fingerprint == canonical.fingerprint(doc)
    assert load_config(entry.path) == load_config(TEMPLATE)


def test_damaged_history_index_starts_over_instead_of_failing(tmp_path):
    folder = tmp_path / "hist"
    folder.mkdir()
    (folder / "index.json").write_text("garbage", encoding="utf-8")
    h = ConfigHistory(folder)
    assert h.entries() == []
    assert h.record(_doc()) is not None and len(h.entries()) == 1
    assert json.loads((folder / "index.json").read_text(encoding="utf-8"))["entries"]
