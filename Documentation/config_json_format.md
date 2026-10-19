# ByteHound configuration JSON format (`bytehound.protocol`, schema_version 1)

Reference for the canonical JSON configuration: what the Configuration
Editor saves, what *Restore Previous Configuration* keeps, and what
`Bytehound --validate` and the import preview check. Design and decisions:
[canonical_config_design.md](canonical_config_design.md).
Machine-readable schema: `app/resources/protocol_config.schema.json`
(shipped with the application).

## 1. Shape

```json
{
  "format": "bytehound.protocol",
  "schema_version": 1,
  "tables": {
    "protocol": [
      {"profile_name": "Default", "parser_type": "framed", "header_hex": "AA 55",
       "frame_id_size": 2, "crc_type": "crc16_modbus", "crc_size": 2, "enabled": true}
    ],
    "frames": [
      {"frame_id": "0x1000", "frame_name": "BMS Status", "payload_length": 8,
       "direction": "rxtx", "enabled": true}
    ],
    "variables": [
      {"id_or_address": "0x1000", "signal_name": "Pack Voltage", "data_type": "uint16",
       "count": 1, "start_index": 1, "byte_order": "little", "scale": 0.01,
       "offset": 0.0, "unit": "V", "min_value": 0.0, "max_value": 60.0, "enabled": true}
    ]
  },
  "extra_tables": {"readme": [{"text": "how to use"}]},
  "import": {
    "source_format": "xlsx", "source_name": "pack.xlsx",
    "source_sha256": "…", "imported_utc": "2026-10-19T10:15:23+00:00", "app_version": "1.2.4"
  }
}
```

| Key | Required | Meaning |
|---|---|---|
| `format` | yes | Always `"bytehound.protocol"`. Identifies the file; any other JSON is read as the older table format (§6). |
| `schema_version` | yes | `1`. Older versions are upgraded on load (§5); newer ones are refused with "update ByteHound". |
| `tables` | yes | One entry per configuration sheet, each a list of rows (§2). |
| `extra_tables` | no | Sheets the loader does not use (e.g. a `readme`), kept so nothing is lost in a round trip. Values are text. |
| `import` | no | Where the configuration came from. **Not** part of the fingerprint. |

## 2. Tables

The same tables as the Excel workbook (manual §5), using the sheet's column
names as written:

`protocol` (required) · `frames` · `variables` (or legacy `frame_config`;
one of them required) · `bitfields` · `enums` · `calc_groups` ·
`tx_commands` · `tx_command_fields` · `serial_defaults` ·
`polling_schedule` · `sequence_counters` · `value_rules`

- **One entry per sheet row, before expansion.** A `variables` row with
  `count: 8` stays one row; the loader expands it to 8 signals exactly as it
  does for Excel.
- Blank rows are dropped. Empty optional tables are omitted (an empty sheet
  holds no configuration); an empty `variables` table is kept because its
  presence changes how the loader reads `frame_config`.
- **Unknown columns** are kept per row under `"extensions": {"column": "text"}`.

A workbook written for the old built-in frame `0x101` rule (signals
`Drive_Mode` / `Key_Switch`) gets the equivalent explicit `value_rules`
rows when it is imported (Part C decision 4), so the document states what
the decoder does; decoded values are unchanged.

## 3. Values

A cell becomes a JSON number or `true`/`false` **only when that converts back
to exactly the same text**; otherwise it stays a string. This makes the
round trip Excel → JSON → Excel lossless.

| Column kind | Typed when | Stays text, e.g. |
|---|---|---|
| integer | plain decimal: `8` → `8` | `"08"`, `"0x10"`, `"1.0"` |
| float | `0.01` → `0.01`, `-40` → `-40.0` | `"1.0"`, `"1e-3"`, `"nan"` |
| boolean | exactly `TRUE` / `FALSE` | `"true"`, `"yes"` |
| text | never | — |
| empty cell | — | `""` |

Frame IDs (`frame_id`, `id_or_address`, …) are **hex strings**
(`"0x1000"`), as in the sheets. Numbers must be finite.

## 4. Fingerprint

`SHA-256` of the document **without** the `import` block, serialised with
sorted keys. The same configuration saved as `.xlsx`, a CSV folder or JSON
has the same fingerprint; any real change gives a different one. It is shown
by `Bytehound --validate` and the import preview, and recorded:

- `session.json → config.fingerprint` (and `config_changes[].fingerprint`
  after a configuration change while logging);
- `config_fingerprint` in every segment workbook's **Metadata** sheet.

`config.files_sha256` (hash of the copied files) is still recorded beside it.

## 5. Versions and migration

`app/decoder/canonical.py → MIGRATIONS` maps a version to a function that
upgrades a document one step. Loading applies them in order **in memory**;
the file on disk is never rewritten. A version newer than the application
understands is refused with a message to update ByteHound.

## 6. Compatibility

| Reads | Canonical JSON | Older table JSON (`{"protocol": [...], ...}`) | `.xlsx` / CSV folder |
|---|---|---|---|
| This version | yes | yes (unchanged path) | yes |
| ByteHound before C1 (≤ v1.2.3) | **no** | yes | yes |

The Configuration Editor now saves canonical JSON. To give a configuration
to someone on an older version, export `.xlsx` or CSV.

## 7. Saving

Every save (Configuration Editor JSON, `.xlsx`, CSV folder; the rollback
history) writes a temporary file, flushes it to disk and then replaces the
target, so a crash or full disk during a save leaves the previous file
intact. `.xlsx` exports write every cell as text (Excel may flag numbers
stored as text; the loader reads them correctly).

## 8. Validation

`Bytehound --validate <file>` and the import preview run three layers:

1. **Structure** (this document's rules) — errors.
2. **Loader rules** — types, duplicates, overlapping bytes, unknown frames
   or signals — errors (unchanged from earlier versions).
3. **Semantic checks** — warnings that never block loading: a signal past
   the frame's `payload_length`, scale 0 or non-finite, `min_value` >
   `max_value`, a bitfield bit beyond the signal width, a frame with no
   signals.
