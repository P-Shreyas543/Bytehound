# Bytehound 1.2.5 — release notes

Changes since **v1.2.3** (2026-08-28), branch `production-hardening`.
(1.2.4 was built for a soak test and never published.)

---

## Full notes (GitHub release page)

### Long-duration logging — record for days or months

- **Sessions instead of one growing file.** Each recording is a session
  folder: a new segment every hour (configurable), so every workbook stays
  well inside Excel's limits. `session.json` records every segment, gap,
  event and integrity counter.
- **Logging survives unplugs and reconnects.** With Auto-Reconnect on, an
  unplug is recorded as a gap and the same session continues in a new
  segment.
- **Fixed-step log** (optional): one row exactly every step (e.g. 1 s) with
  the newest value of each signal and its age — independent of how busy the
  PC is.
- **Lossless raw capture** of every received byte (`.bhraw`); *Tools →
  Rebuild Decoded Log* regenerates any decoded log from it.
- **Crash-safe.** Logs are written as data arrives; after a crash or power
  cut the next start recovers the session.
- **`log.txt` in every session folder:** the application log of that
  recording (version, configuration, connection, every event), so a zipped
  session explains itself when shared.
- **Log CSVs open cleanly in Excel:** units such as °C display correctly
  and values are written without binary noise (25.9, not
  25.900000000000002).
- **New: Tools → Merge Session…** joins a session's hourly files into one
  workbook, or one workbook per day, for analysis. Runs in the background
  with progress and Cancel.
- Segment workbooks are compiled in a separate background process, so the
  window stays responsive while logging.

### Data integrity — know when something was lost

- Every received byte is accounted for: noise, broken frames and buffer
  overflow are counted (**Discarded**), serial driver errors are shown
  (**Driver errors**), frames with a bad CRC are kept in a rejected-frames
  file.
- **Sequence counters** (new optional *SequenceCounters* sheet): if your
  device sends a rolling counter, Bytehound detects frames lost *before*
  they reached the PC and reports them.
- Fixed several cases where received data could be lost silently (serial
  parser, TCP connections closing, write failures that were not reported).

### Configuration

- **Import preview:** loading a configuration shows errors, warnings and
  exactly what changes (signals added / removed / modified) before you
  activate it. A failed or cancelled import never changes the active one.
- **Restore Previous Configuration…** (File menu): the last 20 activated
  configurations can be brought back.
- **Activating a configuration while connected now takes effect
  immediately** (the app reconnects with it; previously the old decoding
  continued until a manual reconnect). While logging, the session continues
  in a new segment with the new configuration.
- **Validation warnings** for likely mistakes (signal beyond the frame's
  payload length, zero scale, min > max, bitfield bit beyond the signal).
- **Configuration fingerprint** recorded in every session and workbook, so
  each recording proves which configuration decoded it.
- **ValueRules sheet** (new, optional) and a per-signal **clamp_negative**
  column. Fixes: the decoder used to override signals named
  `Drive_Mode` / `Key_Switch` in frame 0x101 of *every* configuration; it
  now does so only for configurations written for it (Ather workbooks decode
  exactly as before).
- Configuration Editor saves are now crash-safe, and JSON configurations
  keep every sheet, column and value of the original exactly.

### Experiment configuration (new optional sheets)

- **Derived sheet:** values computed live from other signals — e.g.
  Power = `[CellVoltage] * [CellCurrent]` — and running totals such as
  **Ah** and **Wh**. They appear in the table, plot, logs and Analysis
  Suite. Formulas are arithmetic only (no code can run from a
  configuration); totals restart with each session and skip gaps.
- **Logging sheet:** the configuration says how its experiment is recorded
  (segment length, fixed step, stale rule) and can **merge the session
  automatically when logging stops** — event log, fixed-step log or both,
  into one workbook or one per day. Also in Logging Settings.
- **Expected frame rate** (Frames `expected_period_ms`): the Activity Log
  says once when a frame stops or slows down and once when it is back; the
  live plot marks its signals stale after 3 periods.

### Live plot

- Gaps (unplug, silent device) are shown as breaks in the line instead of a
  straight line across them.
- On/off, enum and bitfield signals are drawn as steps.
- A panel no longer draws a third unit against the wrong axis.
- A signal that stops arriving is drawn dashed with "(no data for N s)" in
  the legend; periods with a lost connection are shaded.

### Analysis Suite

- Opens months-long logging sessions quickly; exact statistics for any
  range; math channels on sessions.
- Loading shows progress (file, rows read) with Cancel; a workbook with a
  CSV beside it is loaded from the CSV (~100x faster); workbooks keep
  clock time.

### Reliability and security

- Update and issue-report links must use HTTPS; downloaded installers are
  re-verified before they run.
- Test-only packages are no longer bundled in the application.
- Portable (zip) copies show the correct version and no longer offer every
  release as an update.

### Verified

- 65-hour run on a real BMS (1.2.4 soak build) (RS485, 115,200 baud): 4.23 million frames,
  zero errors, every hourly segment closed and complete.
- The new configuration sheets on the real single-cell rig (charge /
  discharge run: Ah and Wh match current × time; automatic merge at stop).
- Automated test suite: 985 tests passing.

### Known limitations

- With many signals plotted at very high frame rates (thousands of frames
  per second) the live plot can make the window lag; data and logs are not
  affected. A fix is in progress.
- TCP/UDP connections are IPv4 only.
- The manual no longer mentions Modbus RTU: Bytehound reads framed serial
  protocols and Waveshare USB-CAN adapters (`crc16_modbus` is only the name
  of a CRC algorithm).
- Logs from v1.2.3 have elapsed time only; this version adds date and time
  to every row.

---

## Short notes (for `version.json` → shown by the in-app updater)

```
Long-duration logging, data-integrity checks, experiment configuration sheets.

- Recordings are now sessions split into hourly files; logging survives unplugs and reconnects
- Tools > Merge Session, and automatic merge when logging stops (event, fixed-step or both)
- New Derived sheet: Power, Ah, Wh computed live and logged
- Logging sheet: a configuration sets how its experiment is recorded
- Expected frame rate per frame: warns once when a frame stops or slows down
- Optional fixed-step log and lossless raw capture; crash-safe recording; log.txt in every session
- Log CSVs open cleanly in Excel (units such as degC, no float noise)
- Every received byte accounted for; optional sequence counters detect lost frames
- Import preview, restore previous configuration, configuration fingerprint in every log
- Live plot shows gaps as gaps and states as steps, marks stopped signals; Analysis Suite loads with progress
- Verified: 65 h on a real BMS, 4.23 M frames, zero errors
```

---

## Before publishing

1. `python build.py --release` from a committed tree (done for 1.2.5).
2. Owner hands-on check of the installer on this PC or another one.
3. Push, merge `production-hardening` → `master`, tag `v1.2.5`, upload
   installer + zip + `version.json`.
4. Soak status: the 65 h soak ran the 1.2.4 build; the 1.2.5 changes
   (configuration sheets, merge at stop, frame rate) passed the full test
   suite and a short real-device run, not a soak.
