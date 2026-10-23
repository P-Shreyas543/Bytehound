# Test sequences / pack cycler — plan (Part S)

Owner request 2026-10-23: automate TX from the app ("after 100 min do this,
then that"), with conditions such as *cell voltage >=* or *current <=*, so
Bytehound can run charge / rest / discharge cycles on a single cell or a
pack. Status words as in task.md §10 (PASS / FAIL / NOT RUN / BLOCKED).

## 1. Goal and non-goals

**Goal.** A *sequence* is an ordered list of steps defined in the
configuration (or a recipe file). Each step sends TX commands in order,
confirms the device applied them, then waits until an end condition is true
(voltage, current, temperature, Ah / Wh, time …) or a timeout. Loops give
cycles. Safety limits and a safe state protect the cell at every moment.
Every step and cycle is recorded in the session.

**Non-goals (v1).**
- Closed-loop control (PID, setting a current by regulating a PWM). Steps
  switch what the device offers (relays, set-points); regulation stays in
  the device.
- Replacing hardware protection. Software limits act within ~1 frame
  period (200 ms here) plus USB latency; the board's comparators, fuses and
  BMS remain the primary protection. The manual will say so.
- Webhook / phone notifications (the cycler's `webhook_notifier`) — later.

## 2. What exists and what is reused

| Source | Reuse | Change |
|---|---|---|
| `cycler-standalone: core/cycler_engine.py` (450 lines) — states, start / pause / resume / skip / stop / E-STOP, watchdog, journal | State machine and its transitions | Drive from decoded signals and TX commands of the active configuration, not the board's fixed frames |
| `core/cutoff_detector.py` — fixed cut-off types (V >=, V <=, I taper with arming delay, duration, capacity, temperature) | Taper arming delay, hold logic | Replaced by expressions over any signal |
| `core/safety_monitor.py` — limits, BMS faults, watchdog, shutdown | Rules and tests | Limits become expressions; watchdog uses `expected_period_ms` |
| `core/step_transition_controller.py` (673 lines) — board-specific ordered relay switching with echo verification and comparator reset pulses | The **pattern**: send → verify by echo → next; retries; abort to safe state | Becomes generic *actions* with `verify` (section 4.3); the board's order is written in the sequence |
| `core/state_journal.py` — crash journal, resume | As is, adapted | Lives in the session folder |
| `core/metrics_tracker.py`, `aging_analysis.py`, `dqv_analysis.py` | Per-step / per-cycle metrics; capacity fade; dQ/dV later | Inputs from Derived integrals / decoded signals |
| `core/preflight_checker.py` | Pre-start checks | Generic checks (section 6) |
| Recipes `config/recipes/*.json` (CCCV 5x / 15x, capacity test, DCIR pulse) | Ported as example sequences | — |
| Bytehound: `expressions.py` (Derived), `build_tx_command`, `enqueue_priority_tx`, `FrameRateMonitor`, SessionLog events, merge | Conditions, sending, silence detection, records | Comparison / `and` / `or` added to the expression language |

The 98 cycler tests run with their own conftest (never `--noconftest`).

## 3. Architecture

```
app/sequence/
  model.py       Sequence, Step, Action, Limit (frozen dataclasses)
  parse.py       Sequence / SequenceLimits sheets + recipe JSON → model; errors with row numbers
  conditions.py  compile "[CellVoltage] >= 4.2 and step_time > 60 s" (built on expressions.py)
  engine.py      pure state machine: feed(signals, t) / tick(t) → actions to send, events
  safety.py      limits, safe state, silence / disconnect rules (pure)
  metrics.py     per-step and per-cycle Ah, Wh, efficiency, fade
  journal.py     crash journal in the session folder
app/ui/
  sequence_runner.py   Qt glue: decoded frames → engine, engine actions → TX queue, timers
  sequence_panel.py    Tools → Run Sequence dock
```

The engine is **pure and clock-injected** (no Qt, no serial): every rule is
tested on a simulated clock and a simulated cell, fast and deterministic.
The runner only moves data in and out.

Engine states: `idle → preflight → running(step, phase) ⇄ paused →
finishing → done | aborted | faulted`. Phases inside a step:
`actions` (send + verify, one at a time) → `settle` → `waiting` (end
conditions) → next step.

## 4. Configuration

### 4.1 `Sequence` sheet (optional)

| Column | Example | Meaning |
|---|---|---|
| `step` | `3` | Order (integers, unique) |
| `name` | `CC/CV charge` | Label shown in the panel and logs |
| `type` | `charge` | `charge` / `discharge` / `rest` / `action` / `loop` — decides per-cycle bookkeeping |
| `actions` | see 4.3 | What to send at the start of the step, in order |
| `end_when` | `[CellVoltage] >= 4.2 or [CellCurrent] <= 0.18` | Step ends when true (held for `hold`) |
| `hold` | `3` | Samples the condition must stay true (default 3) |
| `timeout` | `120 min` | Required when `end_when` is set; units s / min / h |
| `on_timeout` | `next` | `next` or `abort` (default `abort`) |
| `loop_to`, `loop_count` | `2`, `5` | `loop` steps: go back to step 2, 5 times |
| `enabled`, `description` | | As in other sheets |

### 4.2 `SequenceLimits` sheet (optional, strongly recommended)

| Column | Example | Meaning |
|---|---|---|
| `name` | `Over-voltage` | Shown when it trips |
| `condition` | `[CellVoltage] > 4.25` | Checked on every sample, no hold |
| `applies` | `always` | `always` / `charge` / `discharge` / `rest` |
| `action` | `abort` | `abort` (safe state, stop) or `warn` |

Plus a fixed row set by the app: *no data for 3 × expected period* (uses
Frames `expected_period_ms`) and *connection lost* → abort.

**Safe state**: a `safe_state` row on the Sequence sheet (`type = safe`)
whose actions put everything off; sent on any abort and verified (4.3).

### 4.3 Actions

`Command: Field=value, Field=value; then; Command: …` — each part is one TX
command. Options per action, in brackets:

- `verify [0x6002.Charge Enable] == 1` — wait until the device's telemetry
  shows the change (default: the same-named signal of the command's frame,
  if one exists); re-send up to `retries` (default 3), else abort.
- `wait 500 ms` — settle time after the action.

**Fields not named keep their current value** (taken from the latest
received telemetry of that frame, as the Parameter Editor does), never the
field's default — otherwise "Discharge Load 3 = 1" would switch loads 1, 2,
4 off. If no current value is known, preflight fails.

Example (single-cell board, from the cycler's transition controller):

```
Cell Relay Control: Cell Select=1 [verify]; Cell Relay Control: Cell Enable=1 [verify; wait 500 ms];
Cell Charge Select: Max Charge Voltage=1, Max Charge Current 1=1 [verify];
Cell Charge Control: Charge Comparator Reset=1 [wait 100 ms]; Cell Charge Control: Charge Comparator Reset=0;
Cell Charge Control: Charge Enable=1 [verify]
```

### 4.4 Conditions

Built on `app/decoder/expressions.py` (no Python eval), extended with
`< <= > >= == !=`, `and`, `or`, `not`, and these variables:
`step_time`, `total_time` (seconds), `cycle`, `step_ah`, `step_wh`
(integrated over the step from Derived / current × voltage), and any
signal or Derived value in `[ ]`. Unit suffixes `s min h` on times.
A signal that is stale (older than 3 periods) makes a condition *unknown*:
end conditions wait, safety limits abort.

### 4.5 Recipe file

The same tables as a JSON or xlsx recipe (File → Load Sequence…), so a
recipe can change without editing the device configuration. A recipe is
checked against the active configuration (commands, fields, signals exist).

## 5. Safety rules (all must pass before release)

1. Any limit (4.2), E-STOP, Abort, connection loss, silence, app close,
   unhandled exception → **safe state** sent immediately, verified, re-sent
   every 1 s until verified or 10 attempts; then an alarm stays on screen.
2. Start needs a confirmation that shows steps, limits and the safe state.
3. Starting requires a passing preflight (6); E-STOP is always visible.
4. After a crash or restart: never resume by itself. The journal offers
   *Resume from step N* or *Discard*; resume first sends the safe state.
5. Pause = safe state + timer stopped; Resume re-runs the current step's
   actions.
6. End conditions need `hold` consecutive samples; limits act on one.
7. Every send, verify, retry, transition and trip goes to the Activity Log,
   `log.txt` and the session events.
8. Configuration activation, disconnect or Load Sequence while running →
   refused (or abort first, after a confirmation).

## 6. Preflight

Connected; telemetry fresh for every signal used; every command / field /
signal in the sequence exists; current values known for all command frames;
every condition step has a timeout; at least one limit on voltage and one
on temperature (warning if missing); safe state defined; logging on (offer
to start it); disk space for the expected run time.

## 7. Records and results

- Session events: `sequence_start`, `step_start` (name, cycle), `step_end`
  (reason, e.g. "CellVoltage reached 4.20 V after 1 h 02 min"), `limit`,
  `abort`, `done`.
- Event and fixed-step logs get `step`, `cycle`, `step_name` columns.
- `cycles.csv` (and a `Cycles` sheet in the merged workbook): per cycle —
  charge Ah / Wh / time, discharge Ah / Wh / time, coulombic and energy
  efficiency, end voltages, max temperature, capacity vs cycle 1.
- Analysis Suite: step / cycle boundaries as markers; filter by cycle.

## 8. UI — Tools → Run Sequence (dock)

Step table (current step highlighted, status per step), current condition
with its live value ("CellVoltage 4.13 V → ends at ≥ 4.20 V"), time in step
/ total, cycle *n of N*, last Ah / Wh, Start / Pause / Skip step / Abort,
red E-STOP. The panel can be closed; the sequence keeps running and the
status bar shows it.

## 9. Testing

- Unit: parsing errors per column; condition language (comparison, units,
  stale = unknown); action field merge with live values.
- Engine on simulated clock + **cell model** (OCV curve, internal
  resistance, CC/CV charger, loads, temperature): CCCV charge ends on taper,
  discharge ends on voltage, timeouts, loops 5×, hold vs noise, every abort
  path (limit, E-STOP, disconnect, silence, close, exception), safe-state
  verify / re-send / alarm, journal resume.
- GUI: runner with the test `Device` over TCP — full 2-cycle run, Pause /
  Resume / Skip / Abort; frames lost mid-step.
- Ported cycler tests where they apply.
- Frozen self-test `--selftest-sequence` (simulated cell).
- **HIL on the real rig, supervised**: 1 cycle, then the CCCV 5× recipe;
  pull the USB cable mid-charge (expect safe state on reconnect / relays
  off by board watchdog).

## 10. Phases

| Phase | Content | Exit criterion | Estimate |
|---|---|---|---|
| S0 | Owner decisions (section 11); confirm board echo / verify behaviour from the cycler code | Decisions recorded | — |
| S1 | `model`, `parse`, `conditions` (+ expression comparisons) | Unit tests PASS | 0.5 d |
| S2 | `engine` (actions, verify, settle, waiting, hold, timeout, loops) + cell model | Engine tests PASS on simulated clock | 1 d |
| S3 | `safety` + safe state + preflight | Every abort path tested | 0.5 d |
| S4 | Runner: TX queue, decoded frames, session events / columns, journal | GUI run with test Device PASS | 0.5 d |
| S5 | Panel UI | Manual check + GUI tests | 0.5 d |
| S6 | `metrics`, `cycles.csv`, merged `Cycles` sheet, Analysis markers | Tests PASS | 1 d |
| S7 | Experiment workbooks get Sequence + SequenceLimits (CCCV, capacity test); HIL supervised run | HIL 1 cycle + 5× PASS | 0.5 d + rig time |
| S8 | Docs (manual, instruction.md), frozen self-test, full suite, release notes | Full suite PASS | 0.5 d |

Total ≈ 5–6 days of work plus rig time. S1–S5 give a usable single-cell
sequencer; S6 adds the cycler results; pack extras (min / max / spread via
CalcGroups in conditions) work from S1 on because conditions take any
signal.

## 11. Decisions for the owner (before S1)

1. **Unnamed fields** keep the live value (recommended) — or use defaults?
2. **Where sequences live:** sheet in the configuration *and* loadable
   recipe files (recommended) — or only one of them?
3. **Pack hardware:** which device switches / sets the pack charger and load
   (the current board is single-cell)? The engine is generic; the actions
   and limits depend on it.
4. **Crash resume:** offer *Resume from step N* after a restart
   (recommended) — or always start over?
5. **Standalone Single-Cell Cycler:** keep maintaining it until Bytehound's
   sequencer matches it, then retire it (recommended)?
6. **Hardware watchdog:** does the board turn relays off by itself if it
   stops receiving commands / the PC disappears? If not, a USB unplug
   mid-charge leaves the charger on until reconnect — worth adding in
   firmware.

## 12. Risks

| Risk | Mitigation |
|---|---|
| PC sleep / USB suspend mid-run | Preflight warns; runner blocks Windows sleep while running (SetThreadExecutionState); board watchdog (11.6) |
| Wrong relay order damages the board | Order written explicitly in actions; verify each; examples from the cycler's proven controller |
| Noisy signal ends a step early | `hold` samples; taper arming delay as in the cycler |
| Stale telemetry looks fine | Stale = unknown; limits abort on silence |
| Long runs (days) | Session logging already soak-tested 65 h; journal every step |
