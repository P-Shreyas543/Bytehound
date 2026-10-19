"""Part C step C5: config-driven value rules (decision 4) replace the
decoder's hard-coded frame 0x101 branch; the negative clamp is a
per-signal setting, on by default (decision 5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.decoder import canonical
from app.decoder.config_loader import ConfigError, load_config, read_source_tables
from app.decoder.frame_decoder import decode_frame

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "app" / "resources" / "config_template"
ATHER = ROOT / "configs" / "Ather_v1_0_1.xlsx"          # local device configuration
needs_ather = pytest.mark.skipif(not ATHER.exists(), reason="configs/Ather_v1_0_1.xlsx not present")


def _doc():
    tables, _ = read_source_tables(TEMPLATE)
    return canonical.tables_to_canonical(tables)


def _first_signal(doc):
    row = doc["tables"]["variables"][0]
    return int(row["id_or_address"], 16), row["signal_name"]


def _value(config, fid, name, payload):
    frame = decode_frame(config, fid, payload, {})
    return next(s for s in frame.signals if s.signal_name == name).scaled_value


def _rule(fid, name, **kw):
    row = {"id_or_address": f"0x{fid:X}", "signal_name": name, "source_byte": 7, "match_values": "6,7",
           "value_if_match": 1.0, "value_otherwise": 0.0, "enabled": True}
    row.update(kw)
    return row


def test_rule_sets_the_value_from_a_payload_byte():
    doc = _doc()
    fid, name = _first_signal(doc)
    doc["tables"]["value_rules"] = [_rule(fid, name, value_if_match=42.0, value_otherwise=-1.0)]
    cfg = load_config(doc)
    n = cfg.frames[fid].payload_length
    for last, expect in ((6, 42.0), (7, 42.0), (5, -1.0)):
        payload = bytes(n - 1) + bytes([last])
        assert _value(cfg, fid, name, payload) == expect
    short = bytes(7)                                       # no byte 7: the rule does not apply
    plain = load_config(_doc())
    assert _value(cfg, fid, name, short) == _value(plain, fid, name, short)


def test_hex_match_values():
    doc = _doc()
    fid, name = _first_signal(doc)
    doc["tables"]["value_rules"] = [_rule(fid, name, match_values="0x06 0x07")]
    cfg = load_config(doc)
    assert cfg.value_rules[(fid, name)].match_values == frozenset({6, 7})


@pytest.mark.parametrize("kw, text", [
    ({"signal_name": "Nope"}, "has no signal 'Nope'"),
    ({"source_byte": -1}, "source_byte must be >= 0"),
    ({"match_values": "300"}, "is not a byte"),
    ({"match_values": "on"}, "must be byte values"),
    ({"match_values": ""}, "match_values is empty"),
])
def test_bad_rules_are_errors(kw, text):
    doc = _doc()
    fid, name = _first_signal(doc)
    doc["tables"]["value_rules"] = [_rule(fid, name, **kw)]
    with pytest.raises(ConfigError, match=text):
        load_config(doc)


def test_duplicate_rule_is_an_error():
    doc = _doc()
    fid, name = _first_signal(doc)
    doc["tables"]["value_rules"] = [_rule(fid, name), _rule(fid, name, match_values="1")]
    with pytest.raises(ConfigError, match="already has a rule"):
        load_config(doc)


def _as_frame(fid_hex: str):
    doc = _doc()
    var = doc["tables"]["variables"][0]
    old = var["id_or_address"]
    for v in doc["tables"]["variables"]:
        if v["id_or_address"] == old and v is not var:
            v["enabled"] = False                       # keep just the one signal in the new frame
    var.update({"id_or_address": fid_hex, "signal_name": "Drive_Mode"})
    frame = next(f for f in doc["tables"]["frames"] if f["frame_id"] == old)
    doc["tables"]["frames"].append(dict(frame, frame_id=fid_hex, frame_name="Other"))
    return doc


def test_an_unrelated_config_with_frame_0x101_is_no_longer_overridden():
    """The old decoder rewrote any frame 0x101 Drive_Mode / Key_Switch from
    byte 0, in every configuration. With an explicit rule table (here: the
    rule disabled) the signal decodes exactly as the same signal in another
    frame: nothing is decided by frame number and name in the decoder."""
    doc = _as_frame("0x101")
    doc["tables"]["value_rules"] = [{"id_or_address": "0x101", "signal_name": "Drive_Mode", "source_byte": 0,
                                     "match_values": "7", "enabled": False}]
    cfg_101, cfg_102 = load_config(doc), load_config(_as_frame("0x102"))
    assert cfg_101.value_rules == {}
    for payload in (bytes([7]) + bytes(7), bytes([0x34, 0x12]) + bytes(6)):
        assert _value(cfg_101, 0x101, "Drive_Mode", payload) == _value(cfg_102, 0x102, "Drive_Mode", payload)


@needs_ather
def test_ather_workbook_is_migrated_to_explicit_rules_on_import():
    doc = canonical.import_config(ATHER)
    rules = {r["signal_name"]: r for r in doc["tables"]["value_rules"]}
    assert rules["Drive_Mode"]["match_values"] == "7" and rules["Key_Switch"]["match_values"] == "6,7"
    assert all(r["source_byte"] == 0 and r["id_or_address"] == "0x101" for r in rules.values())
    direct, via_doc = load_config(ATHER), load_config(doc)
    assert direct.value_rules == via_doc.value_rules and len(direct.value_rules) == 2
    for byte0, drive, key in ((7, 1.0, 1.0), (6, 0.0, 1.0), (3, 0.0, 0.0)):
        payload = bytes([byte0]) + bytes(7)
        assert _value(via_doc, 0x101, "Drive_Mode", payload) == drive
        assert _value(via_doc, 0x101, "Key_Switch", payload) == key


@needs_ather
def test_disabling_the_migrated_rules_decodes_the_raw_bits():
    doc = canonical.import_config(ATHER)
    for r in doc["tables"]["value_rules"]:
        r["enabled"] = False
    cfg = load_config(doc)
    assert cfg.value_rules == {}
    assert _value(cfg, 0x101, "Drive_Mode", bytes([4]) + bytes(7)) == 0.0   # bit 0 clear
    assert _value(cfg, 0x101, "Key_Switch", bytes([6]) + bytes(7)) == 1.0   # bit 1 set
    assert _value(cfg, 0x101, "Drive_Mode", bytes([6]) + bytes(7)) == 0.0   # bit 0 clear


@pytest.mark.parametrize("setting, expect", [(None, 0.0), (True, 0.0), (False, pytest.approx(-0.3))])
def test_negative_clamp_is_a_per_signal_setting(setting, expect):
    doc = _doc()
    fid, name = _first_signal(doc)
    row = doc["tables"]["variables"][0]
    row["offset"] = -0.3                                   # raw 0 -> -0.3, inside the clamp window
    row["min_value"] = 0.0
    if setting is not None:
        row["clamp_negative"] = setting
    cfg = load_config(doc)
    assert _value(cfg, fid, name, bytes(cfg.frames[fid].payload_length)) == expect


def test_new_columns_round_trip_through_every_format(tmp_path):
    doc = _doc()
    fid, name = _first_signal(doc)
    for i, row in enumerate(doc["tables"]["variables"]):   # a sheet column: every row has a value
        row["clamp_negative"] = i != 0
    doc["tables"]["value_rules"] = [_rule(fid, name)]
    for target in (tmp_path / "c.json", tmp_path / "c.xlsx", tmp_path / "csv"):
        canonical.export(doc, target)
        again = canonical.import_config(target)
        assert canonical.fingerprint(again) == canonical.fingerprint(doc), target
        assert load_config(target).value_rules == load_config(doc).value_rules
        assert not next(s for s in load_config(target).all_signals if s.signal_name == name).clamp_negative
