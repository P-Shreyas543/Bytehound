# Bytehound C++ Migration Plan

> **Read §0 first.** It is the single checklist of everything planned, in
> progress, blocked or deliberately dropped, so nothing gets lost. The C++
> plan proper starts at *Objective* below.

## 0. Master status and roadmap (updated 2026-10-17)

Bytehound is used by BMS manufacturers and test labs that log continuously
for **days, months or years** at high frame rates. Every item is ticked only
when implemented, tested and verified; dropped items say why. Detailed
evidence for finished threading/memory work lives in [fix.md](fix.md).

### 0.0 Production-readiness closure pass ([task.md](../task.md)) — progress tracker

Started 2026-10-17 from `56b99d8`. Status per task.md: **PASS** (criterion
run and met, evidence named), **FAIL**, **OPEN**, **NOT RUN**, **BLOCKED**.
Updated after every phase. Release recommendation so far: **NOT READY**.

**Decisions taken with the project owner (2026-10-17)**

- GUI latency release gate: **p99 ≤ 50 ms and max ≤ 250 ms at the rated
  3,000 frames/s** (logging on, rotation). Above the rated rate the display
  may degrade; logging may not. (No document defined "rated frame rate" or
  whether 50 ms was a maximum.)
- Session logging moves off the GUI thread into the capture worker.

**Phase 1 — GUI stalls** — commit `5758cbe`

- [x] Diagnostic tool `tools/gui_latency_probe.py`: real MainWindow, loopback
      device or NUCLEO, logging + rotation; tick lateness on `perf_counter`
      (`time.monotonic` ticks in 15.6 ms steps on Windows), GC pauses,
      session events, UI-flush cost, queue depths, CPU, worker progress,
      worker log; optional stack sampling, A/B and `gc.freeze` switches
- [x] **Silent data loss found and fixed:** a retained frame kept the
      parser's memoryview alive → `BufferError` on every `feed()` → the
      worker dropped what it read while the session said "closed".
      Triggered by the probe's own stack sampler (2/3 runs; 0/5 without).
      Views now released before each parse returns; parser exceptions
      counted (`parse_errors`). Tests fail on the old code
- [x] UI flush bounded to 25 ms per tick (worst flush 832 → ~200 ms)
- [x] Session logging on the worker thread (`set_session_sink`), SessionLog
      locked, GUI callbacks via a queued relay. A/B: no change at 3,000
      fps; lower worst case at 5,000 fps in 2 of 3 pairs (small sample)
- [x] Stop Logging blocks the GUI ≤ 40 ms per wait (was 200 ms, for seconds)
- [x] Queue-saturation warning rate-limited (was a file write per batch)
- [x] Order-dependent test pollution from `56b99d8` fixed
- [x] **Gate run 2026-10-19 — PASS, 9 of 9 runs**, with a caveat.
      Loopback probe, 3,000 fps, logging + 10 s rotation, 60 s each, 6
      runs: p50 0.0–0.03 ms, p95 3.6–5.0 ms, **p99 5.9–14.1 ms, max
      37–158 ms**, 0 ticks > 250 ms (~5,900 samples of 10 ms per run).
      NUCLEO `gui_end_to_end`, 3,252 fps, 3 runs: **p99 10–11 ms, max
      39–49 ms**. Caveat: a batch of 5 on 2026-10-17 with the same logging
      architecture failed the max (284–632 ms); results depend on machine
      state, so this is evidence for the tested conditions, not a bound.
      (One HIL run on 2026-10-19 reported p99 58 ms, but its tick clock
      was `time.monotonic` — 15.6 ms steps — so the value is not usable;
      the HIL probe now uses `perf_counter`, as do the figures above.
      Earlier HIL figures, e.g. "p99 12 ms / max 43 ms", had the same
      flaw.)
- [ ] **4.5 s stall** (one HIL run, 2026-10-17): mechanism identified at
      5,000 fps (GIL saturation + gen-2 GC 41→420 ms + backlog) but not
      reproduced at the rated rate; **OPEN**
- Tested and rejected: Qt posted-event backlog as the cause; `gc.freeze()`
  (cuts GC pauses, not the stalls)

**Phase 2 — helper process** (`app/serial_logging/_isolated.py`) — commit `19174e1`

- [x] Timeout per job (10 min + 10 s/MB); hung helper terminated; next job
      gets a fresh helper
- [x] Crash: retried once in a fresh helper, then `HelperFailed` — never
      rerun inside the application
- [x] Jobs serialised (timeout = the job's own run); leftover `.partial`
      files removed on any failure
- [x] Unpicklable result, job exception, write failure → error returned,
      CSV kept, segment `closed_with_errors` with the reason in
      `session.json` (event-log compile errors were not recorded before)
- [x] No orphan helper when the application is killed mid-job (tested;
      no watchdog was needed)
- [x] Finishing backlog warning (≥ 3 segments waiting)
- [x] Stop Logging no longer says "saved" while finishing continues
- [x] `Bytehound.exe --selftest-finish` — **PASS in the frozen build**
      (PyInstaller 6.20.0, Python 3.10.11): separate helper pid, readable
      xlsx, analysis cache, no leftovers; `--selftest-capture` PASS
- [x] **Orphan helpers (found in Phase 3, fixed):** an *idle* helper
      outlived a crashed / killed application forever — 22 had piled up
      from test runs (pytest ends with `TerminateProcess`). The earlier
      orphan test was invalid (its script lacked the `__main__` guard, so
      it never had a real helper) and its "no watchdog needed" conclusion
      was wrong. Helpers now exit when the parent process ends; both the
      busy and idle tests fail without the watcher and pass with it
- [ ] GUI responsiveness *while* finishing fails — NOT RUN
- [ ] Application closed during finishing (non-daemon finishers keep the
      process alive until done) — NOT RUN

**Phase 3 — serial and end-to-end integrity** — commit `5312b3b`, firmware 1.1.0 (`SET_SEQ`)

- [x] Transport at 115,200 / 921,600 / 2,000,000 (existing `stream_*`),
      CPU load on every core (`cpu_load`), shutdown while streaming
      (`shutdown_under_traffic`): **PASS** — every byte accounted, raw
      capture complete, close < 3 s
- [ ] Device removal / USB reconnect — **NOT RUN** (needs a physical
      unplug; target reset is covered by `device_reset`)
- [x] Reader pauses at 2 Mbaud (`reader_pause`, 7 runs): pauses ≤ 2 s
      lossless in 6 of 7 runs, ≤ 4 s in 4 of 5; 8 s loses 0.5–1.3 MB,
      16 s loses everything; one run lost data at 1 s (unexplained, not
      reproduced in 6 attempts). Every loss showed as a sequence gap.
      **FAIL** for "no unexplained loss" until the 1-run case is explained
- [x] **Requested vs effective buffer:** pyserial does not report the
      granted size. Measured: request 4 KB, 64 KB, 4 MiB or 64 MiB makes
      no difference at 0.25 s / 1 s pauses → buffering is upstream of the
      requested driver buffer on the ST-LINK VCP. F16's earlier claim was
      based on a flawed experiment and is corrected
- [x] Deterministic frames, all stages: board sent = worker received =
      decoded = event log (once, in order) = Analysis Suite stats and
      export = per-segment .xlsx rows; timestamps never backwards across
      rotations; noise and corruption counted exactly; 32-bit wraparound
      0xFFFFFFFF → 0 logged once, unsigned (`seq_wraparound`) — **PASS**
- [x] **F12 implemented (2026-10-19, owner: "go ahead as recommended")**
      without waiting for Part C: an optional, backward-compatible
      `sequence_counters` table (CSV or xlsx sheet; documented in
      instruction.md §5.12) marks a counter signal (bits, step). The worker
      tracks it after decode: gap / repeat / reset (half-range rule, as in
      RFC 1982). Totals in integrity (`seq_missing`, `seq_gaps`,
      `seq_repeats`, `seq_resets`, per frame) → session.json per segment;
      every event in `seg_NNNN_sequence.csv`; a warning on the first gap
      (≤ 1 per 10 s). **Verified on the NUCLEO:** the app's count equals the
      board-proven loss exactly — reader pause 8 s: 18,791 = 18,791; 16 s:
      37,631 = 37,631; noise/corruption: 588 = 588; clean streams 0; the
      32-bit wrap is neither gap nor reset; a reboot is 1 reset, 0 missing.
      Over TCP / UDP to the Pi: 0 = 0. Capture-process mode: counters in
      integrity (tested), events not written to the CSV (documented)
- [x] **Re-test 2026-10-19 (owner request):** NUCLEO clean 2 Mbaud 3/3
      (≈1.6 MB each, byte-exact, app 0 missing). Pi over the Ethernet
      cable **10/10**; over Wi-Fi 9/10 — `udp_stream_5000` lost 152 cycles
      in one gap (whole datagrams: 10,336 B = 152 × 68 never reached the
      parser), **detected by F12 exactly (152 = 152)**; repeated 3× with 0
      loss. Wi-Fi UDP datagram loss: 1 of 5 runs; Ethernet UDP: 0 of 4.
      UDP has no retransmission — this is the network, and the app now
      reports it
- [ ] FTDI / CH340 / CP2102 — **BLOCKED** (no adapters)

**Phase 4 — rotation, polling, shutdown** — commit `75286bb`

- [x] **Two silent-loss defects found and fixed:**
      - the segment's event logger had no `on_error`: a write error (disk
        full) disabled it with no report and every later frame was
        dropped while session.json said `closed`. Now the session's error
        handler fires (the GUI stops logging and says why) and the
        segment is `closed_with_errors` with the reason
      - the fixed-step writer's death was noticed only when the segment
        closed (up to an hour) and rows kept queueing into it (up to 1M
        in memory); now reported at the next tick and dropped + counted
- [x] Next segment cannot be opened at rotation: raised (GUI stops logging
      with a message, as before) and now recorded in session.json events
- [x] Crash during rotation is recovered; recovery leaves a closed session
      byte-for-byte untouched; an existing session is never overwritten
      (existing test)
- [x] Fixed-rate polling: start-to-start intervals (F20); warning exact at
      the capacity boundary (10.0/s at 100 ms: none; 10.1/s: warns);
      re-enable waits one interval; **missed-poll accounting added**
      (`polls_missed` in integrity) — and fixed: time with polling off was
      counted as missed. NUCLEO: default gap → 50 polls counted missed;
      20 ms gap → 0 missed. Jitter at 100 ms: mean 99–100 ms, stdev 31–35
      ms, worst 56 ms late (timed at the GUI's TX signal, so it overstates
      wire jitter)
- [x] Application exit, real entry point `app.main.main` with a live
      session rotating every 2 s (`tools/exit_check.py`): **normal close
      5/5 — exit 0, session closed, no process left** (descendants
      tracked: a venv `python.exe` is a launcher, helpers are
      grandchildren); **killed mid-session 5/5 — no process left,
      recovery → `recovered`, no finished file changed**
- [x] Test harness without the forced exit (`BYTEHOUND_TEST_NORMAL_EXIT=1`):
      GUI subset (19 tests) exits 0 in 3/3; **full suite 669 passed, exit
      0, no fatal error (1 run)**. The original crash was intermittent
      (~2 of 6 runs), so one clean run does not prove it gone: the
      workaround stays until several clean normal-exit runs are recorded
- [ ] Frozen exe closed normally / killed — NOT RUN (Phase 5)

**Phase 5 — packaging**

- [x] Frozen build from `75286bb`: `python -m PyInstaller --noconfirm
      --distpath <scratch> --workpath <scratch> Bytehound.spec` (the
      documented step; `build.py` not used because it rewrites
      version.json and may auto-commit). Python 3.10.11, PyInstaller
      6.20.0, `Bytehound.exe` sha256 `9a368cde…bcd653`, 278 MB; `dist/`
      untouched
- [x] Frozen CLI: `--selftest-finish` PASS, `--selftest-capture` PASS,
      `--validate` template → 0, broken config → 1, missing path → 1
- [x] Frozen windowed GUI launch + normal close 3/3: window in 3.1–3.6 s,
      exit 0, no process left (user settings backed up and restored)
- [ ] Connect / log / rotate inside the frozen GUI — **NOT RUN** (needs UI
      automation; the helper and capture paths are covered by the
      self-tests)
- [ ] Clean Windows machine — **BLOCKED**

**TCP / UDP on a real network** (Raspberry Pi 4-class, Debian 13, as the
device; `tools/hil/net_device.py` + `tools/hil/net_hil.py`)

- [x] **10/10 over the direct Ethernet cable and 10/10 over Wi-Fi**: TCP
      at 1,000 and 5,000 cycles/s (20,000 frames/s) byte-exact with raw
      capture; peer close delivers every frame first (F15); drop +
      reconnect keeps the sequence complete; 300 TX commands intact
      (F13); UDP at 1,000 / 5,000 cycles/s and 60 KB datagrams (F4) with
      0 cycles lost; ICMP port unreachable does not end the session (F14)
- [ ] **Limitation found:** the TCP and UDP transports are IPv4-only
      (`AF_INET`); a device reachable only over IPv6 (e.g. a link-local
      Ethernet port) cannot be used. Not fixed — scope decision
- [ ] **Behaviour to document:** manual TX commands are spaced by the
      poll TX-gap floor (100 ms → at most 10 commands/s); the TX queue
      holds 256 and drops the excess with a warning. Correct, but a
      script sending many writes will lose commands unless the gap is
      lowered
- Lab note: the Pi's `netplan-eth0` profile is DHCP; on a direct cable it
  fails every ~45 s and NetworkManager wipes eth0's addresses. Tests used
  a temporary static profile (removed afterwards)

**Phase 6 — soak and security**

- [x] Manual review: no `shell=True`, no `pickle`/`yaml` load of untrusted
      data; updates over HTTPS with sha256 (missing hash refused)
- [x] **Fixed (`07b2d6b`):** update installer downloaded to a fixed name
      in %TEMP% and launched later without re-checking (CWE-377/367) →
      private random directory + re-hash right before launch
- [ ] **Open (Low):** math-channel `eval` with `__builtins__=None` and
      `np` in scope is not a sandbox. Input is only the user's own
      expressions from their own registry settings, so exploiting it
      needs code execution as that user already. Recommended: AST
      allow-list before eval (needs a compatibility review of existing
      expressions)
- [x] **pip-audit 2.10.1** (installed into .venv only, approved
      2026-10-19; no existing package changed): `requirements.txt` → **no
      known vulnerabilities**. Installed environment: pillow 12.2.0 (25),
      setuptools 65.5.0 (8), pip 26.1.1 (4), soupsieve 2.8.4 (2). In the
      frozen build: pillow and pip **not shipped**; setuptools' advisories
      are in `package_index` / sdist code, which is not shipped (only
      `pkg_resources` was); soupsieve (CSS-selector ReDoS) shipped but is
      unreachable (the app never uses bs4 / `read_html`)
- [x] **Found and fixed:** the release bundled **pytest, _pytest, pluggy,
      bs4, soupsieve and pkg_resources** (pulled in by pandas' optional
      test helpers). Excluded in `Bytehound.spec`; frozen self-tests and
      GUI launch re-verified; bundle 278 → 277 MB, window 3.1 → 2.6 s.
      Recommended for the build machine anyway: upgrade setuptools and
      pip
- [x] **Bandit 1.9.4** on `app/`: 0 High, 4 Medium, 78 Low. Medium: B307
      (math-channel eval, above) and 3× B310 (urlopen without a scheme
      check — the installer URL comes from the remote manifest) → **fixed:
      HTTPS required** for manifest, installer and issue-report URLs (still
      listed by Bandit, which does not see the check). Low: 72× try/except/
      pass, 2× except/continue (code quality, not addressed in this pass),
      subprocess use (reviewed: installer launch, fixed argv, no shell)
- [ ] Scoped mypy — NOT RUN (no project configuration)
- [x] **Soak — PASS for the tested configuration (analysed 2026-10-22):**
      **65.3 h** (2026-10-19 10:06 → 10-22 03:24 UTC), app 1.2.4 installer
      build (app code = C4 commit), real BMS over **RS485 serial, COM3 @
      115,200 baud** (not CAN — corrected), config
      `Blue01_M_4836_RS485_config.xlsx` (framed AA 55, **crc none**, 9
      frames, 67 signals; validates with no warnings; no frame 0x1F0, so the
      C2 0x1F0 question does not apply). Load: **18.0 frames/s** in every
      segment (light: ~370 B/s). Results: **66/66 segments `closed`**, 0
      gaps, 0 events, session closed by Stop (last heartbeat 8 s before),
      **4,231,307 frames, 0 rejected / discarded / parse errors / driver
      errors / missed polls / log errors / dropped rows**; read-loop gap max
      **47 ms**; segment joins 8–19 ms; 470,146 log rows, timestamps never
      backwards, largest row gap **0.534 s** (cadence 0.5 s) → no stall in
      65 h; every file present with the recorded size and SHA-256; CSV and
      sampled xlsx row counts = manifest; analysis caches + summary present.
      **Raw capture re-parsed independently: 4,231,314 frames, 0 bad** — the
      decoded log holds the same (470,146 cycles × 9 frames). **Finding
      (Low):** the per-segment integrity counters come from the periodic
      snapshot (~10/s via the GUI thread), so they lag the exact rotation /
      stop moment by a fraction of a second; here 124 bytes (~6 frames,
      ~0.3 s) are uncounted in the counters — not missing from the raw
      capture or the log. Fix candidate: take a fresh snapshot at rotation
      and stop. **NOT MEASURED:** memory / handle trend (no Task Manager
      figures or `bytehound.log` in the hand-over), UI responsiveness during
      the run. **Limits:** one configuration, low frame rate, CRC off (a
      corrupted value with intact framing would not be detectable)

**Part C — canonical configuration (started 2026-10-19)**

- [x] Owner decision: design document first, then build
- [x] Requirements taken verbatim from the original protocol specification
      (§2–§5, §9–§12), not from memory
- [x] Inventory: 4 input forms (xlsx, CSV folder, table JSON, YAML), 11
      tables, regression corpus of **23 configurations that all load**
      (template, fixture, 9 root workbooks, 12 MultiCellBMSConfig LFP/NMC
      workbooks; parsers framed / waveshare variable / waveshare 20-byte)
- [x] Problems found for the design: duplicate helper copy (dead code),
      Ather `0x101` branch, silent negative clamp, **non-atomic Config
      Editor JSON save**, file-based (not canonical) fingerprint, config
      swap while connected not restarting the worker (to be verified, C0)
- [x] **Design for review:**
      [Documentation/canonical_config_design.md](canonical_config_design.md)
      — canonical JSON v1 (pre-expansion, typed, stable ids, extensions
      preserved), validation, fingerprint, import/export/migration,
      lifecycle, clean-ups, tests, steps C0–C6
- [x] **Owner decisions 1–5 (2026-10-19): all as proposed** — hex frame
      IDs; in-house validation + shipped schema; auto-reconnect on
      activation while connected; generic value rules replace the Ather
      branch (with migration); clamp becomes a per-signal setting, default on
- [x] **C0 baseline:** `tests/test_config_corpus.py` + fixtures from
      `tools/make_decode_golden.py` — all 23 configurations, 5 deterministic
      payloads per frame (incl. the Ather 0x101 trigger bytes 6 / 7 and 8
      values at the negative clamp), **1,150 frame decodes pinned**; any
      later change to a decoded value fails the suite. Config swap while
      connected **verified**: the worker keeps decoding with the old
      configuration (old frames 0x1000… vs the window's 0x6000…); the
      interactive path shows a "Reconnect required" toast, the programmatic
      path nothing. Fixed by decision 3 in C4
- [x] **C1 canonical model** (`app/decoder/canonical.py`): typed tables,
      source column names, unknown columns → `extensions`, unknown sheets →
      `extra_tables`, `import` metadata, fingerprint (SHA-256 without
      `import`), atomic save; `load_config` and the new shared
      `read_source_tables` accept canonical JSON (file or dict); legacy table
      JSON unchanged. Shape revised from the nested proposal for
      losslessness (design §3 "Revision during C1"). **Proof:** all 23
      configurations decode identically to the C0 baseline via canonical
      JSON (in memory and saved), round trip byte-for-byte lossless incl.
      `readme` sheets; 64 tests (`tests/test_canonical_config.py`)
- [x] **C2 validation** (`app/decoder/validation.py`): structure checks
      (in-house, decision 2) + every loader rule (errors, unchanged) + new
      semantic **warnings** that never block loading (signal beyond
      `payload_length`, zero / non-finite scale, min > max, bitfield bit
      beyond the signal width, frame without signals). New rules are
      warnings because the corpus already contains one such problem: frame
      `0x1F0` declares `payload_length 3` but defines signals up to byte 4
      in **Blue01_M_CAN_4836, DB_48100 and the_energy_company_4850** —
      **finding for the configuration owner** (those signals can only
      decode if the device sends longer frames); files left unchanged.
      JSON Schema shipped as `app/resources/protocol_config.schema.json`.
      `Bytehound --validate` now prints the fingerprint and the warnings
      (existing output lines kept). 40 tests; corpus pinned: 0 errors, the
      6 known warnings and no others
- [x] **C3 export / migration / atomic saves:** `canonical.export` → canonical
      `.json`, `.xlsx` (one sheet per table, every cell text) or a CSV folder,
      all atomic; migration registry (upgrades on load, never in place; newer
      versions refused with "update ByteHound"). **Config Editor** saves (JSON,
      xlsx, CSV) now go through these — previously plain writes that a crash
      could truncate. **Proof:** all 23 configurations exported to xlsx and to
      CSV and re-imported give the identical canonical document and
      fingerprint, and decode as the baseline (46 round trips). Behaviour
      notes: Config Editor JSON is now canonical (an *older* ByteHound cannot
      read it; xlsx / CSV exports stay readable everywhere); empty optional
      sheets are not carried (an empty sheet holds no configuration; an
      empty `variables` table is kept because its presence matters to the
      loader); xlsx cells are text (Excel may flag numbers stored as text)
- [x] **C4 lifecycle** (`app/decoder/lifecycle.py`, UI in
      `app/ui/config_loader.py`): Import Config / recent / welcome-page loads
      now build a **candidate** (import + validate + diff against the active
      config by stable id `(frame, signal)`, plus protocol fields and other
      tables) and show a **preview** — errors block activation, warnings and
      the change list inform — and activate only on **Activate**. A failed or
      cancelled import never changes the active config. **Rollback:** every
      activated config is kept as canonical JSON (last 20, deduplicated,
      atomic) in app data; File → *Restore Previous Configuration…* goes
      through the same preview. **Decision 3:** activating while connected
      restarts the capture worker with the new config — fixes the C0 finding
      (the worker kept decoding with the old config; the app only showed a
      "Reconnect required" toast). While logging, `SessionLog.change_config`
      records a gap, copies the config as `config_N/`, tags every segment
      with the config it used, keeps the fixed-step grid (no tick lost or
      repeated) and the offline rebuild decodes each segment with its own
      config. Startup/preset loads stay direct (no preview). Tests: 7
      service, 1 session, 2 GUI end to end (TCP device: worker replaced and
      decoding with the new config, 2 segments `config` / `config_2`, gap,
      history entry; cancel / invalid leave everything unchanged). Tests use
      a temp history folder (conftest), never the user's app data
- [x] **C5 clean-ups** (first implementation discarded at the owner's
      request, then re-implemented on the owner's go-ahead the same day):
      (1) **dead code** — 151 lines / 12 shadowed duplicate loader helpers
      (incl. a half-written `_parse_protocol`) removed; the 12 live
      functions are bytecode-identical before/after. (2) **Decision 4** —
      the decoder's hard-coded frame `0x101` branch is replaced by an
      optional **`value_rules`** table. **Bug demonstrated on the old code:**
      a voltage-like signal named `Drive_Mode` in frame 0x101 of *any*
      configuration decoded as 1.0 / 0.0 instead of 0.07 / 46.6 V (same
      signal in 0x102). Migration: a config with no rules whose 0x101 has
      those names gets the equivalent rows (loader, every path; shown
      explicitly in the canonical document on import); Ather decodes
      identically (corpus baseline passes and **fails with the migration
      disabled**). (3) **Decision 5** — `clamp_negative` per-signal column
      in `variables`, default TRUE (values unchanged). Validation warns on a
      rule past `payload_length`; preview diff covers `value_rules`; schema,
      `instruction.md` §5.13, manual (Sheet 12, Variables column), JSON doc
      updated. 16 new tests (13 failed on the old code); Ather-specific
      tests skip without `configs/`
- [x] **C6 fingerprint / docs / packaging:** the canonical content
      fingerprint is recorded in `session.json → config.fingerprint`, in
      each `config_changes[]` entry and as `config_fingerprint` in every
      segment workbook's Metadata sheet (same config as xlsx / CSV / JSON →
      same fingerprint; `files_sha256` kept beside it). Reference doc
      `Documentation/config_json_format.md`; user manual updated (5f119b8).
      Schema file ships in the frozen build (`_internal/app/resources/`,
      checked). **Portable-zip v0.0.0 fixed** (§0.11): `find_version_file`
      falls back to the bundled `version.json`; frozen portable build now
      titles "v1.2.4" with no version.json beside the exe (was v0.0.0);
      frozen `--selftest-finish` OK

**Defect found by the full suite during C3 (2026-10-19), fixed:** helper
timeout race. When a helper job hit its timeout but finished its atomic
rename before the kill landed, the segment was marked
`closed_with_errors` ("did not finish") while a complete `.xlsx` sat next
to it — manifest and disk disagreed (`test_helper_timeout_…` failed 1 of
867). Fix: `run_isolated` keeps the result of a job that completed while
being stopped; on a real timeout the job's final output is removed with
its `.partial`, so a failed segment never carries a complete-looking file.
New test `test_job_that_finishes_while_being_stopped_keeps_its_result`
(fails without the fix, passes with it); the session timeout test now uses
jobs that really hang instead of racing a 0.1 ms timeout against real ones.

**Release v1.2.4 built (2026-10-22, not yet published)** — `python build.py
--release` from a clean tree at 49b7c0e (+ the sha commit 80a8a3d):
`installer_output/Bytehound_Setup_1.2.4.exe` 65.2 MB, SHA-256
`0af060db…` = `version.json`; `dist/Bytehound_1.2.4.zip` 110.3 MB. Release
exe checked: title v1.2.4, start/close, `--selftest-merge`, `--selftest-finish`,
`--selftest-capture`, `--validate` PASS, no leftover processes. The installer
itself was not run here (same AppId as the copy installed on this PC — it
would replace it). Release notes in `version.json` (short) and
`Documentation/release_notes_draft.md` (full). Soak evidence covers the C4
code (65 h); later changes covered by the full suite (937) and frozen
self-tests only. Publishing (push, tag, upload) is the owner's step.

**Session merge for analysis (2026-10-22, owner request)** —
`tools/merge_session.py <session> [--split day] [--kind fixed] [--csv]`
joins a session's hourly segment CSVs in order and compiles one workbook (or
one per local calendar day, cut exactly at midnight on each row's
timestamp) with the app's own compiler (Metadata + Data, `Data_2` past
Excel's row limit); a configuration change starts a new part instead of
mixing columns; recorded gaps listed in Metadata; session folder never
modified. 5 tests. Applied to the 65 h soak: 4 day workbooks, rows 60,424 /
172,800 / 172,798 / 64,124 = 470,146 (all rows). **In the app (done
2026-10-22): Tools → Merge Session…** — folder picker, options dialog (log,
one workbook / per day, keep CSV, output folder; warns when a single workbook
passes one Excel sheet or gets slow to open), merge in a **child process**
(no GUI / capture stall through the GIL) with progress and Cancel (checked
per segment, every 10,000 rows and inside the xlsx compiler; a cancelled or
failed merge removes everything it wrote). Logic moved to
`app/serial_logging/session_merge.py`; the CLI tool is a thin wrapper. 14
tests (incl. the real child process, cancel, refusals). **Frozen build
verified (commit d1a2071, PyInstaller):** `Bytehound.exe --selftest-merge`
PASS (merge in a child of the exe, xlsx with every row), together with
`--selftest-finish`, `--selftest-capture`, `--validate` (Ather, value-rule
migration) PASS, GUI start/close OK, no leftover processes, portable title
from the bundled version.json. The menu dialog itself was not clicked in
the frozen build (same code path as the self-test below the dialog). Also converted for the owner: an unfinished
v1.2.3 single-file log (`EKF_SoC_Cycles.xlsx.tmp_data`, 341,319 rows,
~47.4 h) compiled to xlsx with the app's recovery compiler — all rows
present.

**Repository reorganisation (2026-10-19, owner request)** — industry-standard
layout, no behaviour change:
- **Device configurations are local only:** every customer / device
  `.xlsx` / `.dbc` (10 root files + `MultiCellBMSConfig/`) moved to
  `configs/`, which is git-ignored; files stay on disk, git stops tracking
  them (history still contains earlier versions). Tests that use them read
  `configs/` and **skip** when it is absent (checked: without the folder 90
  passed, 12 skipped, 0 failed; with it everything runs). Corpus ids are
  computed relative to `configs/`, so the 23 decode baselines keep their
  names. The config-change session test now uses the tracked fixture
  instead of Blue01, so it always runs. `build.py` takes the Ather preset
  from `configs/`.
- **Scripts:** 13 hardware smoke scripts → `tools/smoke/` (each now puts
  the repository root on `sys.path`, so they run from the root as
  `python tools/smoke/<name>.py`; config paths → `configs/`); generators,
  validator and doc-anchor checker → `tools/`.
- **Docs:** 12 loose `.md` files (this tracker, `instruction.md`, specs)
  → `Documentation/`; 45 relative links rewritten and checked (0 broken); README gains *Repository layout* and *Device
  configurations* sections; stale cycler section replaced (the cycler
  lives on branch `cycler-standalone`).
- **Firmware:** `MCU_BMS_SLIP`, `MCU_BMS_Simulator`,
  `MCU_S32K312_Simulator` → `firmware/`; 11 Eclipse workspace-state files
  (`.workspace/.metadata`, the cause of the "Filename too long" worktree
  failure) untracked and ignored.
- **Removed:** `build_cycler.py` (pointed at the removed cycler); caches
  and temp files deleted at the owner's choice (`build/`, `__pycache__`,
  `.pytest_cache`, `.ruff_cache`, `.coverage`, `debug.log`, ~36 MB).
  Kept at the owner's choice: `installer_output/`, `scratch/`,
  `artifacts/`, `logs/`.

**Closure — scope traceability (Parts C, D, E, G, F12)**

Scope taken from the checklists in this file (§0.5–0.9), not from the part
names. "Critical" = needed for trustworthy long-duration logging with the
existing configuration formats; the rest is product scope. **Every
not-done item needs an owner scope decision before release.**

| ID | Expected (summary of the checklist) | Status | Evidence / where | Depends on | Critical? |
|---|---|---|---|---|---|
| C | Versioned canonical JSON config + schema; in-house validation (overlaps, bounds, duplicates, circular calcs); fingerprint in every log; CSV/xlsx/JSON/YAML import → canonical, lossless export; import preview + rollback; remove dead `config_loader.py` copy; move Ather branch out of the decoder; document negative clamp; CRC set limited to what exists | **PASS — 9 of 9** (C1–C6: canonical JSON + schema, validation, fingerprint in every log, lossless import/export, preview + rollback, dead code removed, Ather branch → value rules, clamp setting, CRC unchanged) | §0.5, §0.0 C-steps | — | No for the current formats (existing loaders work and are tested); **yes** for the protocol spec's acceptance |
| D | Protocol Studio: config management, model/view signal editor, frame layout view, decoder test bench (`.bhraw` replay) | **NOT RUN** (0 of 4) | §0.6 | C | No |
| E | Spec regression tests (CRC vectors, framing, byte order, bitfields, round-trips, migrations); full pytest + smoke + frozen check; docs (JSON format, import, session format, long-run guide); known limitations | **Partial**: full pytest (671 passed), frozen self-tests, long-run lab guide, hardware plan, limitations list (§0.11 + this section) **PASS**; spec regression tests / JSON docs **NOT RUN** (need C) | §0.7, this section | C | Partial: the done half is; the C half follows C |
| G | Menus/shortcuts (8), responsiveness (3), visual quality (5), interaction (6), verification (2) | **Partial**: responsiveness — segment finishing off the GUI, logging on the worker, bounded flush, card re-polish, console limit, stop-wait, latency gate **PASS** at 3,000 fps (9/9, caveat in Phase 1); "nothing slow on the GUI thread" for config load / import / export **NOT RUN**; budgets in CI **NOT RUN** (probe exists, not wired to CI); menus, visual, interaction, screenshot review **NOT RUN** (0 of 21) | §0.9, Phase 1 | — | Responsiveness: **yes** (done for logging); the rest: No |
| F12 | The application detects frames lost on the wire/device from a sequence counter declared in the config (gaps, repeats, resets per frame ID) | **PASS** — implemented with an optional `sequence_counters` table (no Part C needed); app count = board-proven loss on the NUCLEO (18,791 / 37,631 / 588 / 0) and over TCP/UDP (0 = 0) | `app/decoder/sequence.py`, worker `_check_sequence`, session `log_sequence_event`; tests/test_sequence_counters.py; run_hil / net_hil checks | — (Part C will fold the table into the canonical schema) | Yes — done |

Release recommendation from this pass: **NOT READY** — open: scope
decision for C / D / E-spec / G; 4.5 s stall OPEN; 1-of-7 unexplained
reader-pause loss; adapter matrix (FTDI / CH340 / CP2102), clean-machine
packaged test and 24 h soak BLOCKED on hardware/time; frozen GUI workflow
NOT RUN.

### 0.1 Release blockers (current Python release, v1.2.3)

From the production check — must be fixed before shipping:

- [x] Connection dialog ignored the saved baud (config default won) — fixed,
      `test_connection_dialog_qsettings_wins_over_config_defaults` passes
- [x] Ruff lint findings (90) — fixed; `ruff check app tests` clean
- [ ] `installer_url` (`Bytehound_Setup_1.2.3.exe`) returns HTTP 404 — upload
      the installer to the Cloudflare worker. (Homepage, `version.json` and
      `LICENSE` return 200; `report_issue` is POST-only and answers 422 to an
      empty POST, i.e. it is live.)
- [ ] `dist/Bytehound` has no `Bytehound.exe`; `Bytehound_1.2.3.zip` is from
      2026-09-12 and predates all fixes — rebuild with `build.py`, rebuild the
      installer, update `sha256` in `version.json`
- [ ] Decide which branch ships: the release fixes are on `Migration_To_C++`
      together with the threading/memory rework below

### 0.2 Done — threading, capture and memory (details in fix.md)

- [x] Lossless raw wire capture (`.bhraw`) while logging, written by the
      capture worker; **Tools → Rebuild Decoded Log** regenerates the decoded
      log from it (byte-identical rows to the live log, tested)
- [x] `TimeSeriesBuffer` rewritten (contiguous, zero-copy, no duplicate
      cache): 200 signals × 100k samples 682 → 360 MB, full read 34.5 → 0.4 ms
- [x] Plot history = one memory budget shared by all signals (default 512 MB)
- [x] Table cells formatted once per 60 Hz flush, not per packet
- [x] Atomic `.xlsx` saves (`.partial` + rename) — no half-written logs
- [x] Benchmark harness `tools/bench_capture.py` (TCP loopback, no hardware);
      vs 11b7527 at 6000 fps: all frames shown instead of 72–77 %, 110–145 MB
      less memory; median GUI stall at 1000 fps 10.5 → 0.01 ms
- [x] Capture-in-a-separate-process implemented, tested, works in the frozen
      build (`Bytehound.exe --selftest-capture`) — **but slower than the
      thread at ≥3000 fps**, so it is opt-in/experimental; thread is default
- [x] `app/main.py` imports the GUI lazily (cheap child processes, faster
      `--validate`)
- [x] Full `pytest` on the final state: 565 passed, 0 failed (run twice)

### 0.3 Part A — Long-duration logging (highest risk for BMS labs)

Today one decoded `.xlsx` per session is compiled from a temp CSV on Stop.
Excel caps a sheet at 1,048,576 rows (~29 h at 10 Hz); a month is ~26 M rows
and the compile at Stop would take hours. **Decided: hourly CSV segments,
each also converted to `.xlsx` when it closes.**

- [x] Session folder with `seg_NNNN_event.csv/.xlsx`, `seg_NNNN.bhraw`,
      optional `seg_NNNN_fixed.csv/.xlsx` and `seg_NNNN_rejected.csv`; rotated
      every hour (Logging Settings: 15 min – 24 h) and before any file reaches
      1,000,000 rows — `app/serial_logging/session.py`
- [x] `session.json` manifest: app version, config fingerprint + config copy,
      start/end wall time, per-segment time range / rows / status / SHA-256;
      rewritten atomically after every rotation
- [x] Each closed segment converted to `.xlsx` in the background (≤1 M rows
      by construction); never blocks capture or the next segment
- [x] Absolute timestamps (UTC + local, ISO 8601 with offset) in rows, not
      only elapsed ms — anchored to the monotonic clock per segment, so no
      jumps on NTP/DST and a fresh anchor every hour
- [x] Disk guard: warn below 10 GB free, stop logging cleanly below 2 GB
      (both configurable); never delete data automatically; free space in the
      logging status label; events recorded in the manifest
- [x] Crash / power-loss recovery per segment on next launch (default folder
      and every recently used session folder); manifest fixed
- [x] **Behaviour change:** logging continues across auto-reconnects (new
      segment, gap recorded) instead of stopping — a USB glitch at 3 a.m.
      must not end a month-long log. Found and fixed on the way: after an
      auto-reconnect Auto-Fetch stayed **off** (and per-target / pipelining
      choices were lost with the old worker), so a polled BMS went silent;
      the exact polling setup is now restored. Stop Logging stays usable
      during the gap. End-to-end test: `tests/test_session_gui.py`
- [x] Soak test `tools/soak_session.py` (time-compressed, real files and
      threads): 3 simulated days, 73 segments, 518,400 cycles, 259,202
      fixed-step rows — all rows present, grid unbroken, every segment
      closed and hashed, no temp files. **It found a handle leak** (finished
      segment threads were retained: +2 OS handles per segment, ~1,300 per
      month); fixed, and now flat: 265 handles on days 1–3, memory
      43.7 → 44.2 MB. Regression test added. A real multi-week run on lab
      hardware is still needed (see 0.11)
- [x] **Tools → Rebuild Decoded Log** accepts a session's `session.json` and
      rebuilds every segment from its `.bhraw` (rows match the live log, tested)

### 0.4 Part B — Analysis Suite for months of data

Was: the whole log read into pandas / float64 arrays (a month at 200 signals
≈ 40 GB in memory, ≈ 31 GB of CSV) — it could not open. Session CSVs did not
open at all (no `elapsed_ms` column). Now `app/serial_logging/session_analysis.py`
+ `SessionEntry` in `app/ui/log_io.py`.

- [x] **File → Open Logging Session…** (Ctrl+Shift+O), or pick a
      `session.json` in Load Logs: event log, fixed-step log, or both; works
      on a session that is still recording (closed segments). Sessions are
      restored from saved workspaces and the Recent menu
- [x] Per-segment **analysis cache** at segment close (`seg_NNNN_*_analysis.npz`,
      lossless, compressed): row times, every signal at full resolution, and
      10 s / 60 s / 600 s bucket aggregates (n, mean, M2, min, max) + quantile
      sketch. Plus a **session summary** (`<kind>_summary.npz`: 600 s level
      merged across segments + all sketches), extended as each segment closes.
      Missing caches/summary (older or recovered sessions) are built on
      first open, with progress. *(Was planned as per-second / per-minute;
      1 s would cost ~18 GB per month at 200 signals.)*
- [x] Multi-resolution plotting: full resolution when the view holds
      ≤ 400k rows, otherwise a min/max envelope at the finest level that fits
      the plot width (spikes stay visible); reloads in the background after a
      pan/zoom without changing the user's zoom
- [x] Statistics: **all exact for any range** — min / max / mean / std / n
      by a hierarchical bucket merge (600 s → 60 s → 10 s buckets, full
      resolution for the edges; Chan merge for std); median / P5 / P95 by
      bracketed streaming selection over full-resolution data (memory
      bounded). 30 days × 10 Hz: 3.8 s on the statistics thread, and the
      panel never blocks the GUI while it computes. (`≈` estimate only as a
      fallback if bracketing fails.) Cursors and hover read full-resolution
      values, never envelope points
- [x] Wall-clock axis (session start time feeds the existing Wall-clock
      toggle); disconnect gaps and empty buckets drawn as gaps
- [x] Export of session curves = **full resolution** for the visible range
      (never the envelope), streamed per segment, CSV or CSV + `.xlsx` split
      into ≤ 1 M-row sheets
- [x] Legacy single `.xlsx` / `.csv` logs open as before; single session
      segment CSVs (event / fixed) now open too
- [x] Measured (`tools/bench_session_analysis.py`, 30 days × 10 Hz × 10
      signals = 25.9 M rows, 720 segments): reopen 67 ms, overview **16 ms**,
      zoom 1 day 106 ms / 1 h 11 ms / 2 min 0.3 ms, exact whole-session stats
      39 ms, cursor read 2.3 ms (cold). Targets: overview < 5 s ✅, zoom < 1 s ✅.
      One-time summary build for a 30-day session without one: 7.5 s
      (normally avoided — the logger extends it per segment)
- [x] Tests: `tests/test_session_analysis.py` (windows, envelopes, gaps, stats
      on both paths, values, export, fixed-step, incremental summary — all
      against brute force on the CSVs), `tests/test_analysis_session.py`
      (end to end through the Analysis Suite window)
- [x] Math channels on sessions: computed from full-resolution data of the
      visible range (gaps when zoomed out — never maths on an envelope);
      `integral()` on a session starts at the view's left edge (status bar
      says so). Shared evaluator; `integral()` is now gap-safe
- [x] Smoothing / normalising: one helper for build and updates (fixes an
      existing bug where an offset change or zoom dropped the smoothing);
      smoothing is not applied to a zoomed-out envelope
- [x] Exact long-range percentiles (see Statistics above)
- [ ] **Needs real lab logs:** measure analysis-cache disk use (~7 % of the
      CSV on smooth synthetic data, 0.32 GB for 25.9 M rows × 10 signals;
      noisy data compresses less). Sizing method documented in
      `Documentation/long_run_lab_guide.md` §2

### 0.5 Part C — Canonical protocol configuration (protocol spec, phases 2–4)

Design (from the audit): the in-memory model already exists (`types.py`
dataclasses) and every format funnels into the same "tables of rows". The
canonical JSON is the typed, structured, **pre-array-expansion** form of
those tables, compiled to `FrameConfig` through the existing loader — so
live decode, Protocol Studio and the test bench share one decoder and
decoding is unchanged by construction. This JSON is also the C++ "JSON
Configuration Contract" (Phase 1 below); the Python app is the converter that
turns customers' Excel/CSV profiles into it.

Status per item (2026-10-19; steps C0–C6 in §0.0 have the evidence):

- [x] Versioned canonical JSON + documented schema — C1 (8cfe737), schema
      file C2, reference `Documentation/config_json_format.md` (C6)
- [x] Structural + semantic validation in-house (no `jsonschema` dependency):
      overlaps, bounds, duplicates, invalid scaling, missing frames, circular
      calc references — C2 (4fe6e7d). Circular calc references cannot occur:
      calculation groups take inputs only from decoded signals, never from
      other calculations (`frame_decoder._calculate_groups`)
- [x] JSON load/save, migrations, deterministic fingerprint (SHA-256 of
      canonical JSON) recorded in every log and session manifest — C1, C3
      (migration registry), C6 (d009450: session.json + workbook metadata)
- [x] CSV / xlsx / legacy-table-JSON / YAML import → canonical; export back
      without loss; document anything a format cannot hold — C1, C3 (46
      export round trips identical); limits in config_json_format.md §6
- [x] Import preview (errors, warnings, added / modified / removed signals),
      explicit confirm; a failed import never replaces the active config;
      previous config kept for rollback — C4 (4a92459)
- [x] Remove dead duplicate helpers in `config_loader.py` (lines 327–476: an
      older copy incl. a broken `_parse_protocol`; Python uses the later copy)
      — C5 (re-implemented): done
- [x] Move the Ather-specific branch in `frame_decoder.py` (frame `0x101`,
      `Drive_Mode`, `Key_Switch`) out of the generic decoder into
      configuration — decode output must stay identical (regression test)
      — C5: `value_rules` + migration, decode unchanged
- [x] Document or configure the silent clamp of small negatives to 0 when
      `min_value >= 0` (`frame_decoder.py`) — C5: `clamp_negative` column
- [x] CRC stays limited to `crc16_modbus`, `crc16_ccitt`, `crc32`, `none` —
      no invented parameters; schema covers exactly what is implemented
      (unchanged by C1–C6; the schema does not enumerate CRC types beyond
      the loader's own check)

### 0.6 Part D — Protocol Studio (protocol spec, phase 5)

Builds on the existing Config Editor / Wizard (`config_editor.py`,
`config_wizard.py`, today `QTableWidget` over raw rows).

- [ ] Configuration management: open, import, save, save as, export,
      validate, revert, name/version, dirty state
- [ ] Model/view signal editor (`QAbstractTableModel` + delegates) with
      validation feedback
- [ ] Frame layout view: byte/bit map, overlaps, out-of-bounds, CRC config
- [ ] Decoder test bench: hex frames, `.bhraw` replay, raw / engineering
      values, CRC status, expected-value comparison — same decoder as live

### 0.7 Part E — Hardening and release

- [ ] Spec regression tests: CRC vectors, partial / concatenated / noisy
      frames, byte order, signed ints, bitfields, scaling, round-trips,
      failed-import rollback, migrations, decoder equivalence
- [ ] Full pytest, smoke tests, frozen-build check including templates and
      schemas in the package
- [ ] Docs: JSON format, import workflow, session/segment format, long-run
      operating guide for labs (disk sizing, rotation, recovery)
- [ ] Known limitations and required hardware validation listed

### 0.8 Part F — Zero frame loss on the serial path (BMS-critical)

Goal: **every byte the PC receives is either decoded into a frame or
accounted for**, every gap is recorded with a reason, and frames lost
*before* reaching the PC are detected where the protocol allows it. Nothing
is ever discarded silently. Audit of the current code (2026-10-16) found
these loss points:

| # | Where | What happens today | Fix |
|---|---|---|---|
| F1 | `serial_worker.py` `_reset_rx_state_for_polling_start` | Starting Auto-Fetch calls `reset_input_buffer()` and resets the parser — frames already in the OS buffer are **thrown away** | Drain and decode them (`_drain_pending_rx` already does this) instead of discarding; count them as "pre-poll frames" |
| F2 | `_run_loop` polling gate `not backpressured` | When the GUI falls behind, **polling stops** → the device is not asked → gaps in the log | Never pause polling for UI load; the UI decimates/coalesces instead. Logging and raw capture never depend on GUI speed |
| F3 | Parser resync / `_trim_if_overflow` | Noise bytes skipped while hunting for a header, and >1 MB unmatched buffers, are dropped **without being counted** (only a log line) | Per-parser `discarded_bytes` counter + reason; byte accounting `rx_bytes = framed_bytes + discarded_bytes + buffered_bytes` checked in tests and shown in the UI |
| F4 | `UdpSocketWrapper` `recv(4096)` | Datagrams > 4096 B error out (WSAEMSGSIZE) / truncate | Receive up to 64 KiB per datagram |
| F5 | TCP/UDP sockets | OS default receive buffer → **UDP drops under bursts** | Set `SO_RCVBUF` large (e.g. 4 MiB), verify the granted size, warn if smaller |
| F6 | `open()` purge | `reset_input_buffer()` on connect drops pre-connect bytes | Keep (no session yet), but log the byte count purged |
| F7 | Serial driver / USB-UART FIFO overrun | Invisible today | Windows: poll `ClearCommError` (`CE_OVERRUN`, `CE_RXOVER`, `CE_FRAME`, `CE_RXPARITY`) via ctypes and count/log each; elsewhere use what pyserial exposes |
| F8 | Worker thread scheduling | Normal priority — CPU load elsewhere can starve reads | Raise the capture thread priority (`QThread.TimeCriticalPriority` / highest), keep `timeBeginPeriod(1)`, recommend power plan + USB selective-suspend off in the lab guide |
| F9 | Bad-CRC / malformed frames | Counted, but not in the decoded log (bytes only in `.bhraw`) | Write rejected frames with reason to a per-segment `rejected.csv`; counts in the manifest |
| F10 | Decoded-log queue full (100k) | Drops rows (raw capture keeps bytes, rebuild recovers) | Raw capture on for every logging session (already); decoded drops counted in the manifest and the UI badge; rebuild offered automatically on Stop if any were dropped |
| F11 | Reconnect | Logging stops on unplug (Part A fixes) | Continue the session; record the gap (start/end, reason) in the manifest |
| F12 | Frames lost on the wire / in the device | Undetectable without protocol help | **Done 2026-10-19:** optional `sequence_counters` table marks a counter (bits, step); gaps, repeats and resets counted per frame ID, in integrity / session.json and `seg_NNNN_sequence.csv` (instruction.md §5.12) |
| F13 | `TcpSocketWrapper.write` / UDP write | `socket.send()` may write only part of a buffer — **the rest of a TX command was lost** without an error | Send until every byte is out (with timeout), else raise |
| F14 | UDP on Windows | An ICMP "port unreachable" (device rebooting) arrives as `WSAECONNRESET` on the next read → treated as an unplug → **session ended** | Ignore the notice for UDP and keep reading |
| F15 | `TcpSocketWrapper` on peer close | Raised "closed by remote peer" while bytes already received sat in its buffer → **the device's last frames were lost**, more the busier the PC (found by the stress test under load) | Deliver every buffered byte first, then report the close |
| F16 | Serial driver receive buffer / reader stalls (NUCLEO rig) | A reader stall at 2 Mbaud loses data upstream (USB bridge / driver) with **no driver error flag** | Request 4 MiB (kept: harmless, may help other drivers — unverified). **Correction 2026-10-19:** the earlier evidence that the request fixes it was a flawed experiment. Rigorous `run_hil.py reader_pause` (single pause, full accounting): on the ST-LINK VCP the request size makes no measurable difference (4 KB…64 MB all lossless at 1 s); pauses ≤ 4 s lossless in 4 of 5 runs, 8 s loses 0.5–1.3 MB, 16 s loses everything; one run of 7 lost data at 1 s (unexplained). The app cannot prevent upstream loss: keep the reader from stalling (F17, Part G) and detect loss (F12). `rx_service_gap_max_ms` shows how long data waited unread |
| F17 | TX gap wait (found on the NUCLEO rig) | Every command / poll **slept up to 110 ms with reads blocked** to honour the TX gap — 20 kB unread at 2 Mbaud per command | The gap wait keeps draining RX; poll responses read during the wait still end it; pipelined drains match in-flight polls |
| F18 | Raw capture at segment rotation (found on the NUCLEO rig) | Rotation stopped the capture, then started the next one: **~70 ms of received bytes missing from the `.bhraw` files at every rotation** (1,971 frames over 3 rotations). Also a race: a record being written while the file closed was dropped | `rotate()` swaps to the next file before the segment closes, under a lock shared with every record; per-segment gauges (`buffered_bytes`, `rx_service_gap_max_ms`) recorded as values, not deltas |
| F19 | Poll schedule vs TX gap (found on the NUCLEO rig) | The template schedule (100/200/500 ms) needs 17 polls/s, the default 100 ms gap allows 10 → **every interval silently ran ~1.7× long** (0x1000 at 268 ms) | Warning when polling starts, with the fix (lower the TX gap or lengthen intervals) |
| F20 | Poll scheduling (found on the NUCLEO rig) | The next poll was due one interval after the previous one *finished*, so every period was stretched by the wait for its turn, the TX gap and the round trip: **0x1000 at 100 ms ran 10–25 % slow** even when the link had capacity (45–54 polls in 6 s instead of 60) | Fixed-rate: next = previous due time + interval; a schedule already late is realigned to now (no catch-up burst). Both modes now 61–62 in 6 s |

Progress (each with a test that fails on the old code):
F1 ✅ F2 ✅ F3 ✅ F4 ✅ F5 ✅ F6 ✅ F7 ✅ F8 ✅ F9 ✅ F10 ✅ F11 ✅
F12 ✅ F13 ✅ F14 ✅ F15 ✅ F16 ✅ F17 ✅ F18 ✅ F19 ✅ F20 ✅ — tests in `tests/test_polling_worker.py`
(`test_polling_start_delivers_waiting_frames_instead_of_discarding`,
`test_polling_continues_while_gui_is_backpressured`) and
`tests/test_frame_loss.py`. The UDP burst test shows the old code really
lost datagrams to the OS.

Done when:

- [x] F1–F11 and F13–F20 implemented, each with a regression test that
      fails on the old code (F16–F20: verified by running the new tests
      against the previous `app/` code — all fail there)
- [x] **Hardware-in-the-loop rig: NUCLEO-G474RE** —
      `firmware/nucleo_g474_bms_sim` (bare-metal, VS Code build / flash /
      debug with the CubeIDE toolchain) and `tools/hil/run_hil.py`. The
      board counts every frame and byte it sends (sequence counter, noise
      and CRC-error injection, any baud); the test compares with what the
      app saw. 13 tests, all passing on 2026-10-17, also with the full unit
      suite loading the CPU at the same time:
      streaming at 115,200 / 921,600 / 2,000,000 baud (2,354 cycles/s =
      9,400 frames/s at 2 Mbaud: every byte accounted, sequence contiguous,
      raw capture = parser input), noise + corruption (17,488 noise bytes
      and 2,354 corrupted frames counted exactly), burst at 100 % line
      rate, sequential and pipelined polling, watchdog, target reset
      mid-stream, session logging + fixed-step + rotation + Analysis
      Suite stats against the board, the real MainWindow end to end at
      3,250 frames/s (GUI event loop worst 43–152 ms late over 7 runs,
      one 4.5 s stall — see 0.11; Part G's 50 ms budget not yet met),
      `smoke_headless.py`.
      Found F16–F20 and the Part G items below
- [x] F12 (sequence-counter gap detection) — optional `sequence_counters`
      table, verified on hardware (see §0.0 Phase 3); Part C will fold the
      table into the canonical schema
- [x] Integrity counters per segment in `session.json`: bytes, frames OK,
      rejected, discarded + overflow + escape-layer bytes, driver error flags
      (`driver_*`), poll timeouts, bytes purged at connect, decoded-log drops,
      rejected frames; disconnect gaps listed per session. (Sequence gaps
      with F12)
- [x] Status-bar integrity indicators: `Discarded: N B`, `Driver errors: N`,
      amber warning badge with the reason, logging status with free disk
      space (now actually visible — it was hidden). A dedicated live
      integrity panel (all counters, per segment) moves to Part G
- [x] Stress test (`test_stress_every_byte_and_frame_accounted`, TCP + UDP):
      30,000 frames as fast as possible with noise, random splits and
      corrupted CRCs through a real worker into a session — raw capture
      byte-identical, every byte accounted, every valid frame in the decoded
      log exactly once, every corrupted one in the rejected file, rebuild
      finds the same frames. Passes repeatedly under heavy CPU load (after
      the F15 fix it found)
- [x] Hardware validation plan written:
      `Documentation/hardware_validation_plan.md` (H1–H11: baud sweep on FTDI /
      CH340 / CP2102, 24 h endurance, unplug, power cycle, PC load, disk full,
      crash, ≥ 14-day soak, live serial smoke; pass criteria). Requires a
      configurable baud rate and a rolling counter in the simulator sketch
- [ ] **Needs lab hardware:** run H1–H11 and record results. The NUCLEO
      rig covers the simulator side on the ST-LINK VCP (H1/H2 at all three
      bauds for minutes, H5 reset, H11); still needed: FTDI / CH340 / CP2102
      adapters, 24 h and multi-week runs (`run_hil.py --soak-minutes`),
      unplug, disk full, crash, a real BMS
- [x] Lab guide: `Documentation/long_run_lab_guide.md` (PC preparation —
      power plan, sleep, USB selective suspend, adapter power saving,
      updates, antivirus exclusions; disk sizing; settings; status-bar
      indicators; after the test; crash recovery; troubleshooting)

### 0.9 Part G — UI/UX to industry standard (no glitches, no lag)

BMS manufacturers judge the tool by its polish. Target: behaves like
established measurement software (Vector CANalyzer/CANape, NI, PCAN-View) —
predictable menus, instant response, no visual glitches, readable at any DPI.

**Menus and commands** (today: File / Edit / View / Device / Tools / Help
exist; gaps below)

- [ ] File: New / Open / Open Recent ▸ / Save / Save As / Import ▸ /
      Export ▸ / Close Session / Exit — recent configs and sessions (the
      handler `_on_load_recent_config` exists but is not in the menu)
- [ ] Edit: Copy / Copy Table / Select All / Find (Ctrl+F) / Clear; Undo/Redo
      in editors
- [ ] View: every dock toggle, Full Screen (F11), Zoom In/Out/Reset, Theme ▸,
      Reset Layout
- [ ] Device: Connect / Disconnect, Start/Stop Polling, Start/Stop Logging,
      Logging Mode ▸ (event / fixed-step, Part H), Send Command…
- [ ] Tools: Protocol Studio, Analysis Suite, Rebuild Decoded Log, Decoder
      Test Bench, **Preferences** (one dialog with pages, replacing scattered
      Logging / Plot / Connect settings)
- [ ] Help: User Guide (F1), Keyboard Shortcuts, Check for Updates, Report
      Issue, Diagnostics, About
- [ ] Standard shortcuts everywhere (Ctrl+O/S/Shift+S/Q, F5 connect, Ctrl+L
      logging, Space pause) listed in Help → Keyboard Shortcuts; mnemonics
      on every menu; no non-standard separators in the menu bar itself
- [ ] Analysis Suite uses the same menu conventions as the main window

**Responsiveness (measured, not assumed)**

- [ ] Nothing slow on the GUI thread: config load, import, validation,
      exports, log conversion, session open — all background with progress +
      cancel
- [ ] Budgets enforced by the benchmark harness and a GUI-stall probe in CI:
      input-to-response < 100 ms, live update ≤ 100 ms behind data, no GUI
      stall > 50 ms at the rated frame rate during logging
- [ ] Zero flicker: no widget rebuilds on value updates, no style re-polish
      per update (the profile showed 6.4k polish/unpolish calls), no layout
      jumps when values change width (fixed-width numeric fonts/columns)
  - [x] Telemetry cards re-polish only when their state changes (was
        ~1,000 polish passes/s at 3,250 frames/s on the HIL rig)
- [x] Segment finishing (xlsx compile, analysis cache) runs in a helper
      process (`app/serial_logging/_isolated.py`): on a thread it held the
      GIL and the GUI lagged 150–800 ms for ~3 s after every rotation
- [x] RX console limited to 400 lines/s with a "N frames not shown" line
      (formatting and laying out every frame was most of the GUI thread's
      time at high rates); logs and raw capture keep every frame
- [x] GUI-stall probe with stack sampling in `run_hil.py gui_end_to_end`
      (records what the GUI thread was doing whenever it is > 300 ms late)

**Visual quality**

- [ ] One typography scale (font family, sizes, weights) and one spacing
      scale used by every window; tabular (monospace-digit) numbers in tables,
      cards, cursors
- [ ] Consistent icon set and colour semantics: OK / warning / fault /
      stale / disconnected the same everywhere (table, cards, plots, status)
- [ ] Light and dark themes both complete; high-DPI 100–200 %, 4K and
      multi-monitor (moving windows between DPIs) without blur or clipping
- [ ] Startup: exactly one window, no tiny floating window, no focus
      stealing; layout state versioned, corrupt layouts reset safely
- [ ] Number display: configured precision and units consistently in
      table, cards, plots, cursors, exports

**Interaction quality**

- [ ] Recoverable problems shown as toasts / status messages / the warning
      badge — modal dialogs only for decisions; audit the ~88 popup sites
- [ ] Every error message says what happened and what to do next
- [ ] Destructive actions confirm (clear data, overwrite file, stop a
      long log); long operations are cancellable
- [ ] Empty states with guidance (no config, not connected, no data yet)
- [ ] Keyboard-only operation and accessible names on all controls;
      sensible tab order in every dialog
- [ ] State remembered: window layouts, last config, column widths, plot
      selections, Analysis Suite session

**Verification**

- [ ] Screenshot review set (light/dark × 100/150/200 % DPI) for main window,
      every dialog, Analysis Suite, Protocol Studio
- [ ] UI walkthrough checklist run before each release

### 0.10 Part H — Fixed-step logging (sample on an exact time grid)

Labs often need one row every 0.1 s / 1 s exactly, regardless of when or how
often the BMS sends each frame (e.g. to align with a cycler or climate
chamber log). Today the decoded log is event-driven (one row per poll cycle).

- [x] Logging mode: **Event** (current) or **Fixed step**; both can run
      together into separate files of the same session
- [x] Step 10 ms – 60 s in Logging Settings (Preferences consolidation and a
      step choice in the Start Logging dialog come with Part G)
- [x] Driftless timing: row *n* is stamped at `t0 + n × step` on the
      monotonic receive clock. **Design change:** rows are derived from each
      frame's receive timestamp rather than generated by a timer in the
      worker — the values are then exact by construction (newest value at or
      before each tick), independent of GUI load, and identical in thread
      and process capture modes. A stall only delays when rows are written;
      late ticks are emitted on catch-up, never skipped
- [x] Value policy per row: latest value of every signal (sample-and-hold),
      plus per-signal **age** (ms since the value arrived) and a **stale**
      flag when older than N steps (configurable, default 3); option to leave
      stale cells blank instead of holding
- [x] Rows written even when nothing arrived (all stale) so the grid is
      complete; disconnects shown as stale rows + gap in the manifest
- [x] Same session folder, segments, rotation, `.xlsx` per segment, disk
      guard and crash recovery as Part A
- [x] Analysis Suite opens fixed-step logs natively (File → Open Logging
      Session → Fixed-step log / Both)
- ~~Metrics: tick jitter p50/p99/max~~ — row times are exact by
  construction, so there is no tick jitter to measure. (What can lag is
  *writing*: bounded by the 1 s quiet margin, plus any GUI stall.)
- [x] Tests: grid exactness over a simulated week (no drift), hold/age/stale
      behaviour, catch-up after a stall, grid continuity across rotations and
      across a disconnect gap (`tests/test_session_log.py`)
- [x] Test: fixed-step values equal the event log's values at the same instants

### 0.11 Known gaps and follow-ups (don't lose these)

- **[FIXED in C6]** Portable zip shows v0.0.0 (found 2026-10-19, pre-existing since the
  spec was added):** the frozen app reads `version.json` beside the exe,
  but the spec bundles it into `_internal\`. The installer copies it next
  to the exe, so installed copies are fine; a zip from `build.py` is not —
  title "v0.0.0" and the updater treats every release as newer. Fix: fall
  back to `sys._MEIPASS` (or copy it in `build.py`). Soak zip had it
  copied by hand.
- **Needs lab hardware / real data (cannot be done in software):**
  `Documentation/hardware_validation_plan.md` H1–H11 (incl.
  `smoke_headless.py` phases 2–10 on the simulator, 24 h per baud rate,
  ≥ 14-day soak); analysis-cache disk use on real logs.
- **Capture process follow-up:** to beat the thread it must send compact
  numpy batches (columnar) instead of pickled `DecodedFrame` objects.
- [x] **Tests no longer touch real user settings:** `conftest.py` redirects
  every `QSettings(org, app)` (module-level and function-local imports) to a
  per-run temp `.ini`; `tests/test_settings_isolation.py`. Two suites can
  run at once.
- [x] **Test process exit crash (code 139)**, intermittent, pre-existing:
  access violation in the interpreter's final teardown after all tests
  pass. Destroying leftover widgets first made it *abort* instead (seen
  2026-10-17), and so did `os._exit` (its DLL-detach step). Now
  `pytest_unconfigure` ends the process with `TerminateProcess` and pytest's
  own status once every report is written (verified: full suite 637 passed
  → exit 0; pass → 0, failure → 1, nothing collected → 5; JUnit XML still
  written). Still to check: the app's own exit path for the same pattern.
- [ ] **8 PytestUnraisableExceptionWarnings** in a full run, reported under
  `test_main.py` but allocated by
  `test_logging.py::test_recover_temp_files_never_deletes_on_catastrophic_failure`
  (it makes `Workbook.save` raise, leaving openpyxl's write-only generator
  open). Test-induced, pre-existing; close the workbook in that error path
  or in the test.
- [ ] **One unexplained 4.5 s GUI stall** in one of eight `gui_end_to_end`
  runs after the lag fixes (the first run after segment finishing moved to
  the helper process; first spawn?). Not reproduced since; the stall sampler will name the
  code if it recurs.
- [x] **Polling below the configured rate** (10–25 %): completion-relative
  scheduling, fixed as F20.
- [x] **Stale scripts:** `smoke_headless.py` and the other device scripts
  (`smoke_*.py`, `test_com10_full.py`, `s32k144_validator.py`) unpacked
  worker batches as 2-tuples (they are 3-tuples since rx timestamps) and
  saw no frames at all; `smoke_headless.py` also expected `Cell Voltage 1`
  instead of the loader's `Cell Voltage_1`. Fixed; only `smoke_headless.py`
  was re-run (on the NUCLEO), the others need their own devices.
- [ ] **Test suite takes ~31–37 min**, mostly GUI/theme tests — profile with
  `pytest --durations=30` and speed up the slowest.
- [x] **Smoke tooling in the repo:** `tools/smoke_launch.py` (offscreen
  launch smoke, isolated settings) next to `tools/bench_capture.py`,
  `tools/soak_session.py`, `tools/bench_session_analysis.py`.
- [x] `RawLogger`: **kept** as a library API (covered by tests, used by
  `smoke_headless.py`); the app itself logs through sessions + `.bhraw`.
- Dropped on purpose (see fix.md): float32 plot storage (uint32 counters
  lose precision), blocking serial reads (USB-CDC tuning, needs hardware),
  QThread pool consolidation, shared time column, numpy columnar decode.

### 0.12 Order of work

1. Commit the fix.md work; new branch for the rest.
2. **Part F (zero frame loss)** — smallest changes with the biggest risk
   reduction; must land before long runs are trusted.
3. **Part A (long-duration logging)** together with **Part H (fixed-step
   logging)** — they share the session/segment writer.
4. **Part B (Analysis Suite)**.
5. **Part G (UI/UX)** — responsiveness items alongside each part; the menu /
   Preferences / visual pass once A, B and H have added their commands.
6. Parts C → D (protocol configuration, Protocol Studio), then E.
7. Release: 0.1 blockers, frozen build, hardware validation, UI walkthrough.

### 0.13 How this feeds the C++ migration

| Python work | C++ plan section it defines |
|---|---|
| Canonical JSON + validator + fingerprint | Phase 1 *JSON Configuration Contract* — the Python app converts Excel/CSV profiles to it, so the C++ app stays JSON-only as planned |
| Session folder + CSV segments + `.bhraw` | Phase 3 *Logging* — same on-disk format, so both apps write and read the same sessions; `.xlsx` per segment is Python-only |
| Multi-resolution Analysis Suite | Phase 6 *Analysis Suite Rewrite* |
| `tools/bench_capture.py` numbers | Phase 0 baseline and the performance gates |
| `.bhraw` captures + rebuild | Golden fixtures for byte-for-byte parity tests |
| Part F byte/frame accounting + integrity counters | Phase 2 *Transport* completion criteria and the reliability gates — the C++ worker must report the same counters |
| Part H fixed-step logger in the capture worker | Phase 3 *Logging* — driftless grid logging is a C++ requirement too |
| Part G UI/UX standards and budgets | Phases 4–5 and the performance gates |
| Process-mode result | Evidence for the Phase 2 design: worker thread + batched immutable snapshots; avoid per-object serialisation across boundaries |

### 0.14 Part I — Live plot review ([live_plot_plan.md](live_plot_plan.md))

Owner request 2026-10-19. Scope: the Live Plot dock (not the Analysis
Suite, not the XY plot). Phases L0 baseline → L1 correctness → L2
performance → L3 UX (owner picks).

- [x] **L0 baseline (2026-10-19)** — tools: `tools/plot_bench.py` (offline,
      synthetic history) and `tools/gui_latency_probe.py --plot-grid`.
      **M1 FAIL — the live plot breaks the GUI latency gate at 3,000
      frames/s:** 15 template signals on a 2×4 grid, 5-min window, 3 × 60 s:
      p99 84.7 / 82.8 / 88.6 ms (gate ≤ 50), max 133.8 / 135.9 / 256.6 ms
      (gate ≤ 250; one run over), 112–149 ticks > 50 ms; redraw p50 ≈ 11
      ms, p99 ≈ 48–50 ms, max 78–112 ms. No data lost (all 180,000 frames
      shown). Stacks: pyqtgraph `PlotDataItem._getDisplayDataset` inside
      `setData` (finite check of x, clip, peak min/max) over every point in
      the window on every redraw. The Phase 1 gate PASS (9/9) was measured
      with an **empty plot**, so this load had never been measured. **A/B
      on the code before the P1–P5 fixes (5a0d61e): same failure** (p99
      79.6 / 107.7 ms, redraw p50 10.4 / 12.3 ms) — pre-existing, not
      caused by P1–P5. **M3 FAIL — "All session" after hours:**
      `plot_bench` 64 signals × 10 Hz: redraw with new data 16 / 23 / **177**
      ms median at 0.1 / 1 / 8 h of history (whole history re-sent each
      redraw); the 5-min window stays 15–23 ms at any history length.
      **M2 PASS:** dropping old samples when the budget is full costs ≤ 2.4
      ms (8 h, one signal). **M4:** hover readout cold 0.1 / 0.4 / 10.5 ms
      (max 16 ms at 8 h) — acceptable. M5 visual: offscreen screenshots in
      L1 only; DPI / theme review NOT RUN. **Probe defect found and fixed:**
      the window's deferred default-config load replaced the probe's
      configuration after setup (plot emptied; in `--port` mode the HIL
      config was replaced by the bundled template — earlier hardware
      latency runs decoded with the template, figures still meaningful)
- [x] **L1 correctness (P1–P5) done:** P1 — a sample arriving more than
      5× the signal's usual interval (and ≥ 0.5 s) after the previous one
      stores a NaN break point right after the last sample; curves draw with
      `connect="finite"`, so unplugs / silent devices / reconnects show as
      gaps (break placed immediately after the last sample so a step curve
      never holds an old state into the gap — caught on the first
      screenshot, fixed and pinned by a test). P2 — boolean / enum /
      bitfield signals drawn with `stepMode="right"`. P3 — adding a third
      unit to a panel is refused with a message; a saved layout holding one
      leaves that signal undrawn and says so in the Activity Log (never
      drawn against the second unit's axis). P4 — when the display queue
      evicts points under load, every history is marked to break before its
      next sample. Hover readout shows `–` anywhere inside a gap. P5 — three
      manual passages corrected (512 MB shared budget, Plot Settings
      description) + "Reading the live plot" notes. **Evidence:** 15 new
      tests; 10 failed on the old code for exactly these reasons and pass
      now; existing plot / buffer tests unchanged and passing; offscreen
      screenshot: Pack Voltage breaks at the 8–12 s outage, BMS State drawn
      as steps ending at its last sample
- [~] **L2 performance (2026-10-22) — PARTIAL: gate met on a quiet PC, not
      under background load.** Changes: (1) curves drawn at screen
      resolution — `peak_decimate` keeps min/max per bucket and every gap
      (0.28 ms for 180k samples), pyqtgraph gets ~2 points per pixel
      column; Explore re-reduces the visible range shortly after pan/zoom,
      so zooming in shows every sample; (2) the live X range is moved only
      when it shifts ≥ 1 pixel (setXRange cascaded through all 8 linked
      panels' layout on every redraw — the 302 ms stall); (3) redraws paced
      by one pixel of time (10–30 per s) and ≤ 4× their own cost; (4)
      `app/gc_tuning.refreeze()` on configuration activation: long-lived
      objects frozen out of full collections (gen-2 pauses 40–58 ms → 23–37
      ms), previous configuration freed (tested). **Probe, 3,000 fps, 15
      signals, 5-min window, 3 × 60 s:** before L2 p99 83–89 / max 134–257;
      after: p99 **38.9** / 50.2 / 82.9 ms, max 130 / 262 / 177 ms, redraw
      p50 4.9 / 6.9 / 13.7 ms — the spread follows background load (system
      busy 22 / 32 / 47 %; the app uses ~1 core: capture thread and GUI share
      Python's GIL). Same load with no plot: p99 21 ms. 12 new tests.
      Further options (not done): incremental (cached) reduction per curve;
      capture process mode. Real BMS rates (18 fps in the soak) are ~170×
      lighter than this load
- [ ] L3 UX (U1–U5; owner chooses)

## Objective

Migrate Bytehound from Python/PySide6 to a native C++20 and Qt 6 desktop application with **performance, deterministic timing, and UI responsiveness as the primary goals**. Preserve configurable protocol decoding, serial/TCP/UDP I/O, CAN support, command transmission, polling, logging, live plotting, Analysis Suite, configuration tooling, and Windows packaging.

The migrated app must start cleanly, maintain predictable telemetry timing under load, stay responsive under high-rate telemetry, and never create the unwanted tiny floating `Bytehound` window seen during startup.

## Performance-First Rules

1. Serial receive, parsing, decoding, polling, logging, Excel/CSV loading, and export never run on the UI thread.
2. No unbounded queue, log document, or chart history is permitted.
3. Incoming data is processed immediately by workers; UI presentation is coalesced at a fixed rate.
4. Every subsystem has measured latency, throughput, memory, and queue-depth metrics.
5. A feature is not complete until it passes its performance budget as well as functional tests.

## Performance Execution Order

### 1. Worker-Owned Receive Pipeline

- Keep serial/TCP/UDP receive, stream parsing, frame decoding, and calculations in the telemetry worker.
- Emit decoded batches or immutable latest-value snapshots, never a Qt signal for every packet.

### 2. Fixed-Rate UI Coalescing

- Process UI updates every 50–100 ms (10–20 FPS) by default.
- Prefer a lower, stable UI update rate over attempting to paint every incoming packet.
- Keep receive/decode timing independent from UI frame timing.

### 3. Latest-Value-Only Widget Updates

- Retain only the latest update for each signal during an UI interval.
- Update tables, cards, parameter editors, TX readbacks, detail tabs, and plots only when their displayed value changed.
- Do not reapply stylesheets or call `setText()` when text is unchanged.

### 4. Bounded, Decimated Plotting

- Keep only the required visible-window history for live drawing.
- Downsample large series to display-resolution min/max points.
- Redraw charts at 10–20 FPS.
- Reuse plot widgets and curve objects; never rebuild a plot because a value, visibility flag, or colour changed.

### 5. Bounded Text Documents

- Cap the raw console and activity log at 500–2,000 lines.
- Append batched text at the UI update interval.
- Skip console formatting entirely while its dock is hidden.

### 6. Analysis Suite as a Background, Cached Pipeline

- Load logs in workers and show a reduced preview first.
- Cache parsed numeric columns and use decimated arrays only for drawing.
- Preserve full-resolution arrays for statistics and export.
- Update only the affected curve when a log, offset, visibility state, or parameter changes.

### 7. Remove Packet-Handler Allocation and Formatting Work

The packet hot path must avoid per-packet timestamps formatted as strings, repeated list/dictionary scans, stylesheet updates, unchanged widget writes, axis-range recalculation, and unnecessary array allocations.

### 8. Profile Every Change

Measure packet decoding, UI flush, packet handling, live redraw, Analysis Suite rebuild, and Excel/CSV loading. Keep before/after timing results with each performance change.

## Target Stack

| Area | Target |
|---|---|
| Language | C++20 |
| UI | Qt 6 Widgets |
| Charts | Qt Charts or QCustomPlot; choose after performance benchmark |
| Serial | Qt Serial Port |
| TCP / UDP | Qt Network |
| Runtime configuration | Versioned JSON schema validated with Qt Core APIs |
| CAN / Waveshare | Existing protocol implementation ported into a dedicated transport adapter |
| Build | CMake + Ninja/MSVC |
| Tests | Catch2 or GoogleTest + Qt Test |
| Installer | Existing Inno Setup flow, updated for the C++ executable |

## Architecture

```text
UI thread
  MainWindow / dock layout / tables / plots / Analysis Suite
       ↑ batched immutable telemetry snapshots
Telemetry worker thread
  transport read → parser → decoder → polling scheduler → TX priority queue
       ↓ bounded logging queue
Logger worker thread
  raw CSV / decoded CSV output
```

Rules:

- The UI thread must never parse packets, decode frames, read files, write logs, or rebuild charts for every packet.
- Workers communicate using bounded queues and batched Qt signals.
- UI updates are coalesced to 10–30 FPS, regardless of incoming packet rate.
- File loading, Analysis Suite processing, and export run outside the UI thread.

## Phase 0 — Measure the Current Baseline First

1. Record supported configuration schemas and wire formats from `instruction.md`.
2. Add golden test fixtures for framed serial, SLIP, HDLC, COBS, Waveshare CAN, CRC variants, TX commands, and polling.
3. Capture current acceptance screenshots and log-output examples.
4. Benchmark startup time, memory, packet throughput, packet-to-UI latency, TX scheduling jitter, UI frame rate, log throughput, and Analysis Suite load/render time.
5. Keep Python as the reference implementation until every C++ subsystem passes equivalent tests.

## Phase 1 — Pure Core Library

Create a Qt-independent `bytehound-core` library containing:

- Versioned JSON configuration types and validation.
- JSON as the only runtime configuration source.
- Packet builder and stream parsers.
- CRC implementations.
- Frame decoding, enums, bitfields, calculations, and warnings.
- TX command encoding and boolean bit packing.

Completion criteria:

- Golden packet/config tests match current Python outputs byte-for-byte.
- No GUI or filesystem code is allowed in protocol/decoder hot paths.
- Parser/decode benchmarks establish per-packet timing budgets before UI work begins.

### JSON Configuration Contract

- One human-readable `.json` file is the complete and only configuration format.
- Include `schema_version`, protocol, frames, signals, bitfields, enums, calculation groups, TX commands, serial defaults, and polling schedules.
- Validate the complete document before starting a connection; show one actionable validation report instead of runtime popups.
- Preserve comments/user notes through explicit JSON fields, not spreadsheet formatting.
- The C++ application contains no Excel/CSV configuration import, export, parsing, or spreadsheet dependency.
- Never parse XLSX or CSV in the application.

## Phase 2 — Transport and Scheduler

Implement `TelemetryWorker` using `QThread` or a worker `QObject` moved to a thread:

- `QSerialPort`, `QTcpSocket`, and `QUdpSocket` adapters.
- Bounded priority TX queue.
- Fair round-robin polling.
- Boot grace period, watchdog, disconnect detection, retry/backoff, metrics.
- Decode packets in the worker and emit batches of latest values.

Completion criteria:

- Sustains the target device baud rate without UI involvement.
- Queue overflow is counted and surfaced, never causes unbounded memory growth.
- Priority TX preempts polling within a defined, tested latency budget.
- Polling intervals are measured for average error, worst-case error, and jitter.

## Phase 3 — Logging

Implement a dedicated logger worker with bounded queues:

- Raw packet CSV logging.
- Decoded wide-format CSV log output.
- Crash-safe temporary files and recovery.
- Rate-limited flushes and explicit shutdown drain handling.

Completion criteria:

- Logging cannot block serial receive or the UI.
- Long tests do not grow the console/activity document or memory indefinitely.
- Backpressure is measurable; a slow disk cannot silently increase memory or delay polling.

## Phase 4 — Main Qt UI

Rebuild the main UI with model/view components:

- `QAbstractTableModel` for telemetry; only changed rows emit `dataChanged`.
- Dock widgets for plots, bitfields, enums, TX commands, editor, console, and activity log.
- Fixed-rate UI update timer that applies latest telemetry snapshots.
- Bounded console and activity buffers.
- Lazy creation of optional panels, editors, and Analysis Suite.

### Mandatory Startup Window Fix

The screenshots show a blank, tiny top-level `Bytehound` window caused by restoring a floating dock/layout state during startup.

The C++ app must:

1. Create all docks docked and hidden/visible in a known default layout.
2. Restore only validated geometry after the main window is shown.
3. Never restore a floating dock automatically at startup.
4. Version the saved layout schema; discard incompatible or corrupt layouts.
5. Provide **View → Reset Layout** to clear settings deliberately.
6. Use non-modal status/toast feedback for recoverable startup events.
7. Avoid any `show()` call on a dock while applying saved state.

Completion criteria:

- Repeated cold starts create exactly one top-level application window.
- No blank, floating, modal, or focus-stealing startup windows.
- Main window becomes interactive before optional configuration, dashboard, and log-recovery work completes.

## Phase 5 — High-Performance Live Plotting

- Retain full telemetry only when needed for logging; retain a bounded display history for live plots.
- Downsample to pixel-appropriate min/max data before drawing.
- Redraw at 15–30 FPS maximum.
- Recompute axis ranges at a low fixed rate, never per packet.
- Do not recreate curves/widgets when data merely changes.

Completion criteria:

- UI remains interactive at sustained high packet rates.
- Multi-signal plots remain smooth during long sessions.
- Plot redraw time stays inside its frame budget; dropped redraws are preferable to blocking telemetry.

## Phase 6 — Analysis Suite Rewrite

- Parse logs in background workers.
- Cache loaded files and precompute numeric columns once.
- Render decimated plot data; retain source arrays for export/statistics.
- Update only changed curves when toggling a log, offset, or parameter.
- Debounce statistics, auto-fit, crosshair, and cursor updates.
- Use non-modal status feedback for recoverable file/export errors.

Completion criteria:

- Large logs load without freezing the app.
- Pan/zoom, cursor readout, overlay, export, and statistics remain responsive.
- Analysis operations publish progress and remain cancellable.

## Phase 7 — Configuration Tools and Feature Parity

Port:

- Configuration editor and protocol wizard.
- JSON configuration editor with schema-aware validation and formatting.
- Built-in JSON presets and JSON template generation.
- Parameter editor and TX commands.
- Diagnostics, user guide, updater wiring, reporting, and theme support.

Each feature moves only after a testable core API exists.

## Phase 8 — Packaging and Release

1. Build signed Windows binaries with CMake presets.
2. Package using Inno Setup.
3. Migrate settings under a new C++ application/version namespace, with safe import of compatible user settings only.
4. Run hardware smoke tests against the MCU simulators and real COM devices.
5. Release a beta alongside the Python version, then switch only after parity and performance gates pass.

## Performance, Timing, and Reliability Gates

| Metric | Gate |
|---|---|
| Startup | Main window visible in under 1 second on the release reference PC; configuration loads asynchronously afterward |
| Startup windows | Exactly one top-level Bytehound window |
| UI rate | Coalesced updates at 20–30 FPS; no UI work per incoming packet |
| Packet-to-worker latency | Measure and publish p50/p95/p99 from received byte to decoded frame |
| Packet-to-UI latency | Latest value visible within 100 ms at normal load; stale updates may be discarded rather than queued |
| Priority TX latency | Command leaves the worker queue within one worker iteration; timing verified under polling load |
| Polling jitter | Track and enforce a defined maximum jitter per configured interval |
| Parser/decode cost | Bounded benchmark per packet/frame; no heap-heavy work in the hot path |
| Memory | Bounded UI queues, console buffers, and display histories |
| Serial | No UI-thread I/O or decode work |
| Logging | Async and bounded; never blocks telemetry worker |
| Analysis Suite | Background loading, decimated plotting, cancellable long operations, responsive pan/zoom |
| Layout | Corrupt/stale settings fall back to a safe docked layout |

## Delivery Sequence

1. `bytehound-core` with parity tests.
2. Transport/scheduler/logger benchmark executable.
3. Main UI with live telemetry and startup-layout fix.
4. Live plotting and TX/editor parity.
5. Analysis Suite.
6. Config wizard/editor, installer, hardware validation, beta release.

## Migration Safety

- Do not remove the Python application until the C++ version passes the same configuration, packet, logging, and hardware tests.
- Keep test fixtures and expected decoded outputs shared between both implementations.
- Use feature flags during beta so users can fall back to the Python build if a protocol/configuration edge case is found.
- Convert existing profiles to JSON outside the C++ application before beta deployment, then compare protocol/decoder output against the original profiles during validation.
- Store every new raw and decoded session as CSV only; the C++ application has no XLSX logging dependency.

## Current Python Production Baseline

The `single_cell_cycler` Python application remains the validated production baseline while migration planning continues. Its release package includes the serial reconnect watchdog, rotating asynchronous logs, webhook retries, BMS alert identity, and tested PySide6 plot/metrology surfaces.
