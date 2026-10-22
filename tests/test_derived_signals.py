"""Derived sheet (next version, owner request 2026-10-23): values computed
from other signals (Power) and running integrals (Ah, Wh), live, in the
table/plot/logs, with a safe formula language."""

from __future__ import annotations

import csv
import struct
from pathlib import Path

import pytest

from app.decoder import canonical
from app.decoder.config_loader import ConfigError, load_config, read_source_tables
from app.decoder.expressions import ExpressionError, compile_expression
from app.decoder.frame_decoder import decode_frame, reset_integrals

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "app" / "resources" / "config_template"


def _doc(derived):
    tables, _ = read_source_tables(TEMPLATE)
    doc = canonical.tables_to_canonical(tables)
    doc["tables"]["derived"] = derived
    return doc


def _row(name, expression, unit="", kind="value", **kw):
    r = {"name": name, "expression": expression, "unit": unit, "kind": kind, "frame_id": "", "enabled": True,
         "description": ""}
    r.update(kw)
    return r


POWER = _row("Pack Power", "[Pack Voltage] * [Pack Current]", "W")
CHARGE = _row("Charge", "[Pack Current]", "Ah", "integral_hours")
ENERGY = _row("Energy", "[Pack Power]", "Wh", "integral_hours")


@pytest.fixture(scope="module")
def cfg():
    return load_config(_doc([POWER, CHARGE, ENERGY]))


def _payload(cfg, volts, amps):
    """0x1000 payload with Pack Voltage / Pack Current set (layout from the config)."""
    sigs = {s.signal_name: s for s in cfg.signals_by_frame[0x1000]}
    buf = bytearray(cfg.frames[0x1000].payload_length)
    for name, value in (("Pack Voltage", volts), ("Pack Current", amps)):
        s = sigs[name]
        raw = round((value - s.offset) / s.scale)
        fmt = {1: "b", 2: "h", 4: "i"}[s.byte_length]
        fmt = fmt if s.data_type in ("int", "sint") else fmt.upper()
        struct.pack_into(("<" if s.endianness == "little" else ">") + fmt, buf, s.start_byte, raw)
    return bytes(buf)


def _derived(frame, name):
    return next(c.scaled_value for c in frame.calculations if c.signal_name == name)


# ------------------------------------------------------------------ formulas

def test_formulas_are_safe_and_clear():
    e = compile_expression("[Pack Voltage] * [Pack Current] / 1000")
    assert e.refs == ["Pack Voltage", "Pack Current"]
    assert e.evaluate({"Pack Voltage": 50.0, "Pack Current": 4.0}) == pytest.approx(0.2)
    for bad, msg in (("__import__('os')", "allowed functions"), ("[a].__class__", "Attribute"),
                     ("open('x')", "allowed functions"), ("'text'", "only numbers"), ("x + 1", "unknown name"),
                     ("[a] +", "not a valid formula"), ("", "empty"), ("__ref0", "reserved")):
        with pytest.raises(ExpressionError, match=msg):
            compile_expression(bad)


# ------------------------------------------------------------------ configuration

def test_derived_rows_load_in_order_with_resolved_inputs(cfg):
    names = [d.name for d in cfg.derived]
    assert names == ["Pack Power", "Charge", "Energy"]
    power, charge, energy = cfg.derived
    assert power.inputs == ((0x1000, "Pack Voltage"), (0x1000, "Pack Current")) and power.frame_id == 0x1000
    assert charge.kind == "integral_hours" and energy.inputs == (("derived", "Pack Power"),)


@pytest.mark.parametrize("row, text", [
    (_row("X", "[No Such Signal]"), "unknown signal"),
    (_row("X", "[Later]"), "unknown signal"),                         # forward references are not allowed
    (_row("X", "[Pack Voltage]", kind="average"), "kind must be one of"),
    (_row("X", "[Pack Voltage] +"), "not a valid formula"),
    (_row("X", "1 + 2"), "uses no signal"),
    (_row("", "[Pack Voltage]"), "name is required"),
    (_row("X", "[Pack Voltage]", frame_id="0x7777"), "unknown frame"),
    (_row("X", "[0x2000.Pack Voltage]"), "has no signal"),
])
def test_bad_rows_are_explained(row, text):
    with pytest.raises(ConfigError, match=text):
        load_config(_doc([row, _row("Later", "[Pack Voltage]")]))


def test_duplicate_names_are_errors():
    with pytest.raises(ConfigError, match="already used"):
        load_config(_doc([POWER, dict(POWER)]))


def test_sheet_round_trips_through_every_format(cfg, tmp_path):
    doc = _doc([POWER, CHARGE, ENERGY])
    for target in (tmp_path / "c.json", tmp_path / "c.xlsx", tmp_path / "csv"):
        canonical.export(doc, target)
        assert load_config(target).derived == cfg.derived, target


# ------------------------------------------------------------------ decoding

def test_power_is_computed_live(cfg):
    frame = decode_frame(cfg, 0x1000, _payload(cfg, 51.2, 3.5), {}, t=0.0)
    assert _derived(frame, "Pack Power") == pytest.approx(51.2 * 3.5, rel=1e-3)
    sig = next(c for c in frame.calculations if c.signal_name == "Pack Power")
    assert sig.is_calculated and sig.unit == "W" and sig.group == "Derived"


def test_amp_hours_integrate_one_hour_exactly(cfg):
    state = {}
    payload = _payload(cfg, 50.0, 2.0)
    t = 0.0
    while t <= 3600.0 + 1e-9:                               # 5 Hz for one hour
        frame = decode_frame(cfg, 0x1000, payload, state, t=t)
        t += 0.2
    assert _derived(frame, "Charge") == pytest.approx(2.0, rel=1e-6)     # 2 A x 1 h
    assert _derived(frame, "Energy") == pytest.approx(100.0, rel=1e-3)   # 100 W x 1 h


def test_a_gap_is_not_integrated_and_a_reset_starts_from_zero(cfg):
    state = {}
    payload = _payload(cfg, 50.0, 2.0)
    for i in range(51):                                     # 10 s at 5 Hz
        frame = decode_frame(cfg, 0x1000, payload, state, t=i * 0.2)
    before = _derived(frame, "Charge")
    frame = decode_frame(cfg, 0x1000, payload, state, t=10.0 + 600.0)   # 10 min unplugged
    assert _derived(frame, "Charge") == pytest.approx(before)         # the gap adds nothing
    frame = decode_frame(cfg, 0x1000, payload, state, t=610.2)
    assert _derived(frame, "Charge") > before                         # integrating again after it
    reset_integrals(state)
    frame = decode_frame(cfg, 0x1000, payload, state, t=700.0)
    assert _derived(frame, "Charge") == 0.0


def test_without_timestamps_integrals_do_not_start(cfg):
    frame = decode_frame(cfg, 0x1000, _payload(cfg, 50.0, 2.0), {})
    names = {c.signal_name for c in frame.calculations}
    assert "Pack Power" in names and "Charge" not in names


# ------------------------------------------------------------------ logs

def test_event_and_fixed_step_logs_carry_the_derived_columns(cfg, tmp_path):
    from app.serial_logging.session import SessionLog, SessionSettings, read_manifest

    clock = {"wall": 1_800_000_000.0, "perf": 1000.0}
    s = SessionLog(tmp_path / "sess", cfg, SessionSettings(segment_seconds=3600, fixed_step_s=1.0),
                   config_source=None, clock=lambda: clock["wall"], perf=lambda: clock["perf"],
                   disk_free=lambda p: 500 * 1024 ** 3)
    s.start()
    state = {}
    for _ in range(60):
        f = decode_frame(cfg, 0x1000, _payload(cfg, 50.0, 2.0), state, t=clock["perf"])
        s.log_frame(f, clock["perf"])
        clock["wall"] += 0.5
        clock["perf"] += 0.5
        s.tick()
    s.stop()
    assert s.await_finished(60)
    seg = read_manifest(tmp_path / "sess")["segments"][0]
    for key, col in (("event_csv", "Pack Power (W)"), ("fixed_csv", "Charge (Ah)")):
        with (tmp_path / "sess" / seg["files"][key]).open(encoding="utf-8-sig", newline="") as fp:
            rows = list(csv.reader(fp))
        header = rows[0]
        idx = next(i for i, h in enumerate(header) if h.endswith(col))
        values = [float(r[idx]) for r in rows[1:] if r[idx] != ""]
        assert values, (key, col)
        if col.startswith("Charge"):
            assert values == sorted(values) and values[-1] == pytest.approx(2.0 * 29.5 / 3600, rel=0.05)
        else:
            assert values[-1] == pytest.approx(100.0, rel=1e-3)
