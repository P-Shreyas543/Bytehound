# Canonical protocol configuration — design for review (Part C)

Status: **Approved 2026-10-19** (decisions in §9). Implementation tracked in `Plane.md` §0.0 Part C.
Source of requirements: the "ByteHound — Production Refactoring and Protocol
Configuration" specification (§2–§5, §9–§12) and `Plane.md` §0.5. Facts below
were taken from the repository on 2026-10-19 (commit `44f5f9e`).

Items marked **DECISION** need the owner's answer before they are built.

---

## 1. Goals and non-goals

**Goals** (spec §2, §3, §12):

1. JSON becomes the canonical internal representation of a protocol
   configuration, versioned and documented.
2. Excel and CSV stay supported as import / export formats; every existing
   configuration keeps loading and decodes exactly as today.
3. Validation (structural + semantic) with row-level, actionable errors.
4. Safe lifecycle: preview, explicit confirmation, atomic save, rollback,
   consistent snapshot per decoding session, fingerprint in every recording.

**Non-goals for Part C** (later parts): the Protocol Studio UI (Part D), the
decoder test bench (Part D), a full UI pass (Part G). Part C delivers the
model, validation, conversion and lifecycle services that Part D will use.

---

## 2. What exists today (verified)

### Input forms (`app/decoder/config_loader.py::load_config`)

| Form | How it is recognised | Notes |
|---|---|---|
| Excel workbook | `.xlsx` / `.xlsm` file | one sheet per table; sheet names normalised by alias |
| CSV folder | a directory | one `*.csv` per table, file stem = table name |
| Table JSON | `.json` file | a mapping `{table_name: [row, …]}` (what the Config Editor saves today) |
| YAML | `.yaml` / `.yml` | same mapping shape |
| Python dict | in-memory | same mapping shape (tests, wizard) |

All four are funnelled into the same **"tables of string rows"** and then
parsed into the in-memory model `FrameConfig` (`app/decoder/types.py`).

### Tables and the in-memory model

| Table | Required | Model |
|---|---|---|
| `protocol` | yes (one enabled row) | `ProtocolConfig` — header, frame-id size/order, length size/meaning/order, CRC type/size/order/coverage, footer, escape mode, parser type, TX pad, inter-frame delay, raw-log format |
| `frames` | with `variables` | `FrameDefinition` — id, name, payload length, direction, description |
| `variables` (preferred) / `frame_config` (legacy) | one of them | `SignalSpec` — byte offset, length, bit offset/length, type, byte order, scale, offset, unit, group, R/W, min/max, description; `count` + `start_index` expand one row into `Name_1 … Name_N` |
| `bitfields`, `enums`, `calc_groups` | no | `BitfieldSpec`, enum map, `CalcGroupSpec` |
| `tx_commands`, `tx_command_fields` | no | `TxCommandSpec` + `TxCommandFieldSpec` |
| `serial_defaults`, `polling_schedule` | no | `SerialDefaults`, `PollingScheduleSpec` |
| `sequence_counters` | no | `SequenceCounterSpec` (F12, added 2026-10-19) |

### Regression corpus (all load today)

23 configurations: the template, `tests/fixtures/canonical_config`, 9
workbooks in the repository root (Ather, Blue01, DB_48100, Experiment 1/6,
MultiCell, frame_config, single cell, the energy company) and 12 workbooks
under `MultiCellBMSConfig/LFP` and `/NMC`. They cover the `framed`,
`waveshare_can_variable_length` and `waveshare_can_20_bytes` parsers and the
`none` / `crc16_modbus` CRC settings.

### Known problems (Part C checklist)

- `config_loader.py` contains **two copies** of the helper functions (the
  first at lines ~333–483, the second from ~484); the first copy includes a
  broken `_parse_protocol` (line ~469). Python binds the later copy. Dead
  code to remove.
- `frame_decoder.py` hard-codes **Ather-specific** handling of frame
  `0x101` (`Drive_Mode = 1 if payload[0] == 7`, `Key_Switch = 1 if
  payload[0] in (6, 7)`) in the generic decoder.
- `frame_decoder.py` **silently clamps** an engineering value in −0.5…0 to
  0 when `min_value >= 0`.
- The Config Editor saves JSON with a plain `open()` + `json.dump`: **not
  atomic** (a crash mid-save truncates the file).
- The recording fingerprint (`session.json → config.files_sha256`) hashes the
  *files* copied into the session, so the same protocol saved as CSV and as
  xlsx gets different fingerprints.
- Loading a new config while connected replaces `MainWindow._config`, but the
  running worker keeps decoding with the config it was started with (it holds
  its own reference). Logged rows then use the new config's columns with the
  old decoder's frames until reconnect. **To be verified** before it is
  called a defect (step C0 below).

---

## 3. Canonical JSON v1

### Principles

- **Pre-expansion form:** one entry per *sheet row* (a `count: 8` cell
  voltage row stays one entry). The loader's existing expansion produces the
  `FrameConfig` — so live decode, import and future Protocol Studio share one
  decoder, and decoding is unchanged by construction.
- **Typed values:** numbers are JSON numbers, booleans are booleans, absent
  optional values are omitted (not `""`). Byte strings (header, footer,
  static TX payloads) are hex strings `"AA 55"`.
- **Frame IDs:** hex strings `"0x1000"` as in the sheets (human-readable,
  diff-friendly). **DECISION 1:** hex strings (proposed) or integers.
- **Stable signal identifiers:** each signal entry gets an `id`
  (`"<frame_id>/<signal_name>"`, e.g. `"0x2000/Cell Voltage"`), used for
  diffs, previews and later the Protocol Studio. Renaming a signal changes its
  id — the preview shows it as removed + added unless the user maps it.
- **Explicit defaults:** every default the loader applies today is written
  out on save, so a file means the same thing to every reader.
- **Nothing is dropped:** columns the loader does not know are preserved per
  entry under `"extensions": {"<column>": "<text>"}` and written back on
  export (spec §3 "preserve unknown extension fields").

### Shape (abbreviated)

```json
{
  "format": "bytehound.protocol",
  "schema_version": 1,
  "protocol": {
    "profile_name": "Default", "parser_type": "framed",
    "header": "AA 55", "footer": "EE",
    "frame_id": {"size": 2, "byte_order": "little"},
    "length": {"size": 1, "meaning": "payload_only", "byte_order": "little"},
    "crc": {"type": "crc16_modbus", "size": 2, "byte_order": "little", "coverage": "header_to_payload"},
    "escape_mode": "none", "tx_pad_length": null, "inter_frame_delay_ms": 10, "raw_log_format": "hex"
  },
  "frames": [
    {"id": "0x1000", "name": "BMS Status", "payload_length": 8, "direction": "rxtx", "description": "…"}
  ],
  "signals": [
    {"id": "0x1000/Pack Voltage", "frame": "0x1000", "name": "Pack Voltage",
     "data_type": "uint16", "byte_order": "little", "start_byte": 0, "count": 1, "start_index": 1,
     "scale": 0.01, "offset": 0.0, "unit": "V", "group": "", "read_write": "R",
     "min_value": 0, "max_value": 60, "description": "Total pack voltage", "enabled": true}
  ],
  "bitfields": [], "enums": [], "calc_groups": [],
  "tx_commands": [{"name": "Set Voltage Limit", "frame": "0x2000", "payload_hex": "", "fields": [ … ]}],
  "serial_defaults": {"baud_rate": 115200, "data_bits": 8, "stop_bits": 1, "parity": "N", "timeout_ms": 100},
  "polling_schedule": [], "sequence_counters": [],
  "import": {"source_format": "xlsx", "source_name": "Ather_v1_0_1.xlsx", "source_sha256": "…",
             "imported_utc": "…", "app_version": "…", "notes": []}
}
```

The full field list (every current column ↔ JSON key, type, default) is
generated from the loader during step C1 and kept in
`Documentation/config_json_format.md`, so it cannot drift from the code.

### Validation

- **Structural:** a JSON Schema document (draft 2020-12) is published with
  the app for tools and documentation. In the app, structure is checked by
  in-house code with the same rules — **no new dependency** (`jsonschema` is
  not installed; spec §11 "do not add unnecessary dependencies").
  **DECISION 2:** in-house checker (proposed) vs adding `jsonschema`.
- **Semantic** (existing rules kept, new ones marked *new*): exactly one
  enabled protocol; known parser / CRC / data types; frame ids fit
  `frame_id.size`; signals inside `payload_length` (*new* when the length
  is known); no overlapping signals in a frame (existing for bytes; *new*
  for bit fields); duplicate names; finite, non-zero `scale` (*new*);
  `min ≤ max`; bitfield index within the signal width (*new*); enum
  duplicates; calc-group and counter references; TX field ranges. Derived
  signals today are only `calc_groups` (no expressions), so "circular
  derived-signal references" cannot occur yet; the check is added with the
  first expression feature.
- Every error names the table, row / entry id and field; warnings
  (e.g. a frame with no signals) never block loading.

### Fingerprint

SHA-256 of the canonical serialisation: keys sorted, no insignificant
whitespace, UTF-8, the `import` block excluded (so re-importing the same
protocol from CSV or xlsx gives the same fingerprint). Recorded in
`session.json` and in every log's metadata next to the existing file hashes.

---

## 4. Import, export, migration

- **Import** = the existing readers (xlsx, CSV folder, table JSON, YAML) →
  tables → canonical JSON. Column aliases and sheet-name aliases already in
  the loader are kept; an import report lists the mapping used, unknown
  columns kept as extensions, and defaults applied.
- **Ambiguous columns:** the loader today accepts a fixed alias list; the
  spec asks for a mapping UI where mapping is ambiguous. Part C reports
  ambiguity (two columns that map to the same field, or none for a required
  field) as an import *error* with the candidates; the interactive mapping
  dialog is part of Part D.
- **Export** canonical → CSV folder, xlsx (the template's sheet names and
  column order) and canonical JSON. Round trip proven by test: import →
  export → import gives an identical canonical document for the whole
  corpus. Not representable in CSV/xlsx: nothing in v1 (extensions are
  columns); xlsx cell formatting and comments in a source workbook are not
  preserved (documented).
- **Migration:** a file with `"format": "bytehound.protocol"` is canonical;
  anything else is legacy and goes through import. A registry of
  `schema_version` upgrades (v1 → v2 …) runs on load, never in place: the
  original file is kept, the upgraded document is saved alongside only when
  the user saves.

---

## 5. Lifecycle (spec §5)

1. Load / import into a **candidate** — the active configuration is not
   touched.
2. Validate; build a **preview**: errors, warnings, inferred mappings, and a
   diff against the active configuration (added / modified / removed /
   unchanged signals, by stable id).
3. **Explicit confirm** to activate (errors block it).
4. **Atomic save** (temp file + `os.replace`, the pattern already used for
   `session.json` and workbooks).
5. **Rollback:** the previous active configuration is kept (last N
   canonical documents in the user's app-data folder) and can be restored.
6. **Consistent snapshot:** a configuration is immutable once active;
   decoding sessions take a reference at start. **DECISION 3:** activating a
   new configuration while connected — (a) require disconnect, (b) reconnect
   automatically with the new configuration (proposed), or (c) refuse while
   *logging* only. Today it is replaced without restarting the worker (see
   §2).
7. **Dirty state** and the fingerprint are exposed for the UI (Part D).

---

## 6. Decoder clean-ups (Part C checklist)

- Remove the dead duplicate helpers in `config_loader.py` (proven unused by
  the full suite + corpus equivalence before and after).
- **Ather branch — DECISION 4.** Options: (a) a generic, config-driven
  *raw-value rule* (e.g. a `value_rules` table: frame, signal, source byte,
  matching values → output value) and migrate the Ather workbook to it;
  (b) keep the behaviour but only when the config opts in by name; (c) leave
  as is and document. The spec says not to hard-code protocol-specific
  branches, so (a) is proposed — but it is a new feature and changes how
  that customer's file must be written (an automatic migration would add the
  rule when importing a workbook that matches the Ather frame layout).
- **Negative clamp — DECISION 5.** Options: (a) make it an explicit
  per-signal setting, default **on** for backward compatibility (proposed);
  (b) keep and document; (c) remove (changes decoded values for existing
  users).
- CRC: unchanged — `crc16_modbus`, `crc16_ccitt`, `crc32`, `none`; no
  parameters invented; the schema enumerates exactly what is implemented.

---

## 7. Tests (spec §9)

- **Corpus equivalence:** for all 23 configurations, the `FrameConfig` built
  via canonical JSON equals the one built directly, and decoding a fixed set
  of generated payloads per frame gives identical results (old vs new path).
- JSON round trip; CSV / xlsx export → re-import identity.
- Schema and semantic validation: one test per rule, valid and invalid.
- Failed import never replaces the active configuration; rollback restores
  the previous one; atomic save survives an exception mid-write.
- Migration: v1 documents load; a synthetic "v0" proves the registry.
- Existing decoder tests (byte order, signed, bitfields, scaling, CRC
  vectors, framing, noise) keep passing unchanged.

---

## 8. Plan (each step: full suite + corpus equivalence before commit)

| Step | Content |
|---|---|
| C0 | Baseline: corpus equivalence harness against the current loader; verify the config-swap-while-connected behaviour (§2) |
| C1 | Canonical model: tables ↔ canonical JSON (pre-expansion), defaults, extensions, fingerprint; generated format reference |
| C2 | Validation: structural + new semantic rules; JSON Schema document |
| C3 | Import / export / migration; round-trip tests; atomic save in the Config Editor |
| C4 | Lifecycle service: candidate, preview diff, confirm, rollback, snapshot; activation per DECISION 3 |
| C5 | Clean-ups: dead code; Ather per DECISION 4; clamp per DECISION 5 |
| C6 | Fingerprint into session.json / logs; documentation; packaging includes the schema |

---

## 9. Decisions (answered by the owner on 2026-10-19: all as proposed)

| # | Decision |
|---|---|
| 1 | Frame IDs are hex strings (`"0x1000"`) |
| 2 | Structural validation in-house; JSON Schema document shipped for tools |
| 3 | Activating a configuration while connected reconnects automatically with it (a logging session records a gap and continues in a new segment) |
| 4 | Ather `0x101` branch → generic config-driven value rules + automatic migration on import (decoded values unchanged) |
| 5 | Negative clamp → explicit per-signal setting, default on (decoded values unchanged) |

The original options:

1. Frame IDs in JSON: hex strings (proposed) or integers.
2. Structural validation: in-house (proposed) or add `jsonschema`.
3. Activating a new configuration while connected: (a) require disconnect,
   (b) automatic reconnect with the new configuration (proposed), (c) refuse
   only while logging.
4. Ather `0x101` branch: (a) generic config-driven value rules + automatic
   migration (proposed), (b) opt-in by name, (c) leave and document.
5. Negative clamp: (a) explicit per-signal setting, default on (proposed),
   (b) keep and document, (c) remove.
