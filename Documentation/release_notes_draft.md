# Bytehound — release notes (DRAFT for review)

Changes since **v1.2.3** (2026-08-28), branch `production-hardening`.
Version number to confirm before publishing (see the end of this file).

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

- 65-hour run on a real BMS (RS485, 115,200 baud): 4.23 million frames,
  zero errors, every hourly segment closed and complete.
- Automated test suite: 949 tests (948 passing in the last full run; one
  timing-sensitive test failed once under load and passes when re-run).

### Known limitations

- With many signals plotted at very high frame rates (thousands of frames
  per second) the live plot can make the window lag; data and logs are not
  affected. A fix is in progress.
- TCP/UDP connections are IPv4 only.
- Logs from v1.2.3 have elapsed time only; this version adds date and time
  to every row.

---

## Short notes (for `version.json` → shown by the in-app updater)

```
Long-duration logging, data-integrity checks and safer configuration changes.

- Recordings are now sessions split into hourly files; logging survives unplugs and reconnects
- New: Tools > Merge Session joins a session into one workbook or one per day
- Optional fixed-step log and lossless raw capture; crash-safe recording
- Every received byte accounted for; optional sequence counters detect lost frames
- Import preview, restore previous configuration, configuration fingerprint in every log
- Activating a configuration while connected now takes effect immediately
- Live plot shows gaps as gaps and states as steps
- Fixes for silent data-loss cases and an override of frame 0x101 signals in every configuration
- Verified: 65 h on a real BMS, 4.23 M frames, zero errors
```

---

## Before publishing

1. **Version number.** The build tested in the 65 h soak was labelled 1.2.4
   but never published. Tags `v1.3.0` / `v1.3.1` already exist in this
   repository (the Single-Cell Cycler), so a Bytehound `1.3.x` tag would
   collide. Proposal: publish this as **1.2.4**.
2. The 65 h soak ran the C4 code; later changes (live-plot fixes, value
   rules, fingerprint, Merge Session) passed the full test suite and frozen
   self-tests but not a soak.
3. `python build.py --release` from a committed tree; tag; upload installer
   and zip.
