# Bytehound Performance Notes

## Harness

`scripts/perf_harness.py` exercises the headless RX pipeline (parser → decoder
→ logger) against a synthetic byte stream built from
`tests/fixtures/canonical_config`. Reports throughput, per-stage latency
percentiles, RSS, and GC counts.

Usage:

```powershell
python scripts\perf_harness.py --rate 1000 --duration 10
python scripts\perf_harness.py --scenarios 100,500,1000 --duration 5
python scripts\perf_harness.py --rate 1000 --no-decoded-logger
```

The harness deliberately skips the Qt half of the pipeline (`_flush_ui`,
plot redraw). Those need a windowed run to measure honestly and are tracked
manually for now.

## Baseline — pre-optimisation (master @ 4c02f58, Windows, Python 3.10)

All numbers from `python scripts\perf_harness.py --scenarios 100,500,1000
--duration 5` (loggers ON, both decoded.xlsx and raw.csv).

| Rate    | Stage  | Throughput | mean µs | p95 µs | p99 µs |
|---------|--------|------------|---------|--------|--------|
| 100 Hz  | parse  | 9268/s     | 107.90  | 214.32 | 214.32 |
| 100 Hz  | decode | 7865/s     | 123.71  | 276.20 | 421.90 |
| 100 Hz  | logger | 2317/s     | 411.57  | 1101.6 | 1668.5 |
| 500 Hz  | parse  | 11984/s    | 86.93   | 219.87 | 351.50 |
| 500 Hz  | decode | 9227/s     | 105.75  | 223.50 | 371.30 |
| 500 Hz  | logger | 2613/s     | 373.80  | 979.40 | 1365.9 |
| 1000 Hz | parse  | 16673/s    | 58.01   | 131.90 | 240.32 |
| 1000 Hz | decode | 11457/s    | 85.47   | 166.10 | 317.00 |
| 1000 Hz | logger | 3036/s     | 320.27  | 814.30 | 1196.0 |

Logger-isolation runs at 1 kHz:

| Config              | logger mean | logger p95 | logger p99 |
|---------------------|------------:|-----------:|-----------:|
| decoded + raw       |     320 µs  |     814 µs |    1196 µs |
| decoded only        |     416 µs  |    1232 µs |    1978 µs |
| raw only            |      53 µs  |     136 µs |     346 µs |
| neither             |       –     |       –    |       –    |

Top-line per-packet budget at 1 kHz (decoded + raw on):
`58 + 85 + 320 ≈ 463 µs/packet` mean → ~46% of one core just on the synchronous
RX pipeline. Tail latencies (p99) push >1 ms which is enough to stall the
worker thread between iterations.

## Findings

1. **DecodedLogger dominates.** `decoded` alone at 1 kHz costs **~416 µs mean
   / ~2 ms p99 per packet** — 5–8× the cost of decode itself. openpyxl
   write-only mode still allocates `Cell` objects per value on every
   `ws.append`. With the per-frame block layout we just introduced, each
   cycle row has frame-count × (elapsed + frame_id + signals) cells, all
   built on the GUI thread (in the real app the call happens inside
   `_handle_packet`).

2. **RawLogger is fine.** It's already async (daemon writer thread); the
   synchronous cost per `log()` is just timestamp formatting + `put_nowait`.

3. **Decode itself is reasonable.** ~90 µs mean per frame for the canonical
   config (which has bitfields + enums + calc groups exercised). Allocation
   of `DecodedSignal` dataclasses dominates here but it's an order of
   magnitude below the logger.

4. **GC pressure is visible but not catastrophic** — gen-0 deltas of ±400
   over a 5 s run. The decoded-logger row construction is the obvious
   churn source.

## Optimization plan (highest-impact first)

1. **DecodedLogger off the synchronous decode path. ✅ LANDED.**
   The openpyxl `Workbook` is now owned exclusively by a daemon writer
   thread spawned in `open()`. `log_frame` still does the cycle-buffer
   manipulation synchronously, but the trigger-frame emit now just
   `queue.put_nowait(row)`s the assembled row list — the expensive
   `ws.append` runs on the writer. `close()` signals stop and joins; the
   writer saves+closes the workbook before exiting so callers (tests,
   "Stop Logging" UI) still get a finalised file by the time `close()`
   returns. Errors from the writer thread are surfaced via the same
   `_pending_error` / `_pump_pending_error` pattern as `RawLogger`.

   **Measured delta (1 kHz, decoded-only, 5 s harness run):**

   | metric         | before | after | speedup |
   |----------------|-------:|------:|--------:|
   | logger mean    | 416 µs |  34 µs |  ~12x  |
   | logger p95     |1232 µs |  80 µs |  ~15x  |
   | logger p99     |1978 µs | 144 µs |  ~14x  |

   Combined parse + decode + logger budget at 1 kHz dropped from
   ~463 µs/packet to ~224 µs/packet — roughly **2x more RX headroom on
   the GUI/decoder thread**.

2. **Plot redraw audit** — `_redraw_plot` runs `np.fromiter` over every
   curve every tick even when no new sample arrived. Worth measuring against
   a real session; cheap to skip if the deque length hasn't changed since
   last redraw. (deferred to next pass)

3. **decode_frame allocation reduction** — pre-built status strings, skip
   per-signal `DecodedSignal(...)` for unchanged signals. Diminishing
   returns until #1 lands. (deferred)

4. **`_apply_decoded` calls `datetime.now()` twice per frame.** Cheap fix
   but only ~µs of savings. (deferred until needed)

5. **xlsx → streaming CSV with optional xlsx export on Stop.** Bigger
   refactor, biggest win, breaks the "decoded.xlsx" file expectation.
   Defer — #1 already brought the synchronous cost below decode itself.

## After-optimization sweep (loggers ON, both decoded + raw)

| Rate    | Stage  | Throughput | mean µs | p95 µs | p99 µs |
|---------|--------|------------|---------|--------|--------|
| 100 Hz  | parse  |  8465/s    |  95.11  | 164.35 | 164.35 |
| 100 Hz  | decode |  7787/s    | 114.87  | 200.50 | 523.40 |
| 100 Hz  | logger |  6632/s    |  95.25  | 184.50 | 207.70 |
| 500 Hz  | parse  | 12962/s    |  80.70  | 168.78 | 298.12 |
| 500 Hz  | decode | 10517/s    |  97.32  | 188.50 | 549.40 |
| 500 Hz  | logger | 11863/s    |  86.23  | 195.80 | 692.70 |
| 1000 Hz | parse  | 15185/s    |  65.07  | 150.60 | 235.23 |
| 1000 Hz | decode | 11244/s    |  86.08  | 168.00 | 289.70 |
| 1000 Hz | logger | 13572/s    |  72.91  | 158.90 | 334.10 |

Logger is no longer the hot stage — it's roughly tied with parse, which
means future wins must come from decode itself or from the Qt/plot half
of the pipeline (out of scope for this harness).

## Round 2 — plot redraw skip-when-unchanged. ✅ LANDED.

`_redraw_plot` previously rebuilt numpy arrays via `np.fromiter` and called
`setData` on every curve on every 60 Hz tick, even when no new sample had
arrived for that signal since the last redraw. With many curves and a
sparse mix of fast + slow signals, that's the dominant cost of the redraw.

Each curve now caches a `(len, last_x)` signature on the curve object
itself. On the next redraw, if the signature is unchanged we skip both
`np.fromiter` allocations AND the `setData` call. The bounded-deque ring
buffer makes a pure-length check unreliable (length pins at maxlen=1500
once saturated even as new samples push old ones off), so we combine
length with the rightmost timestamp — which increases monotonically with
every appended sample.

`oldest_x` (used for the live X-range anchor) is now computed from
`buf[0][0]` directly instead of by reading `x_values[0]` after
`np.fromiter`; this means the anchor still updates correctly when the
data is skipped, with no array allocation.

Cannot benchmark via the headless harness (plot is Qt-only). Logic
verification: the skip is conservative — output is identical to the
old code in every case where the cached signature mismatches, and where
it matches there's by construction no new sample to render. Theme
changes touch the pen via `setPen` (a separate path) and don't require
a `setData`, so the skip is safe across theme switches too.

## Round 2b — hide-aware history appends. ✅ LANDED.

`_apply_decoded` previously appended every "ok" signal's sample into
`_plot_history` on every packet, regardless of whether the Live Plot
dock was open or hidden. `_redraw_plot` already short-circuits when the
dock is hidden, so the appends were the only remaining per-packet cost
the plot was contributing when invisible.

Now: when `_plot_dock.isVisible()` is false, both the
`(datetime.now() - session_started).total_seconds()` call and the
deque appends are skipped. The deque cap is bounded
(`_plot_history_maxlen`), so re-opening after a hidden period fills
back in from re-open time — which matches the UX expectation that a
hidden panel doesn't need to keep buffering data the user can't see.

Savings scale with signal count: at 1 kHz with ~5 ok-status signals
per packet, this is ~5000 deque appends/sec + one `datetime.now()`/sec
that no longer fire while the dock is hidden. Worth it on low-spec
hardware where users routinely collapse panels to free pixels.

Tests still 116 green.

## Round 3 — decode_frame allocation reduction. ✅ LANDED.

Three focused changes to `app/decoder/frame_decoder.py`:

1. **`_lookup_enum` / `_decode_bitfield` fast paths.** Both helpers were
   building a 2-tuple keys list per signal call regardless of whether the
   spec was an enum/bitfield. Most signals are plain scalars, so the list
   was pure waste. Replaced with an early `if not config.enums: return`
   bail-out plus a try-source-first, fall-back-to-signal-name lookup that
   only does dict.get calls — no list allocation in the common path.
2. **`DecodedSignal` and `DecodedFrame` switched to `@dataclass(slots=True)`.**
   Python 3.10+ supports slots-on-dataclass natively. Tighter memory layout
   and faster instantiation; no API change.
3. **Dropped redundant `int(raw)` cast** at the `_decode_bitfield` call
   site (caller already gated on `isinstance(raw, int)`).

**Measured (decode-isolated, 1 kHz, 6 s harness run):**

| metric        | before | after | improvement |
|---------------|-------:|------:|------------:|
| decode mean   |  93 µs | 72 µs |        ~22% |
| decode p95    | 194 µs |143 µs |        ~26% |
| decode p99    | 298 µs |216 µs |        ~28% |

End-to-end at 1 kHz (parse + decode + logger, all on) is now
~218 µs/packet — down from ~463 µs at the start of this perf pass.
That's **>2x more headroom** on the synchronous RX path overall.

## Cumulative round-by-round summary (1 kHz harness, end-to-end with loggers on)

| Round | parse | decode | logger | total |
|-------|------:|-------:|-------:|------:|
| Baseline                  | 58 µs | 86 µs | 320 µs | 463 µs |
| #1 — DecodedLogger async  | 65 µs | 86 µs |  73 µs | 224 µs |
| #2 — Plot redraw skip     |   —   |   —   |   —    |   —    | (Qt-only, not measured here) |
| #2b — Hide-aware appends  |   —   |   —   |   —    |   —    | (Qt-only, not measured here) |
| #3 — decode_frame fastpath| 66 µs | 79 µs |  73 µs | 218 µs |

Tests: 116 green throughout.

## Still slow / next-up

* **Plot redraw: deque → numpy array.** The `np.fromiter` allocations
  still fire when a curve does grow. A ring-buffer numpy array per
  signal (pre-allocated, write-pointer wrap-around, sliced view passed
  to `setData`) would eliminate the per-tick allocation entirely. Bigger
  refactor; do once the skip guard is no longer enough.
* **Decode tail latency (p99 ~550 µs at 500 Hz)** — driven by per-signal
  `DecodedSignal` allocation and the calc-group list-comp. Worth a
  cProfile pass on `decode_frame` against a 5+ signal frame.
* **Hide-aware updates** — when the live-plot dock is collapsed or the
  Analysis Suite is fronted, skip pushing samples into invisible panels.
  Cheap to wire (the dock already exposes `.isVisible()`); benefit scales
  with how often the user keeps the plot hidden.
* **Console retention is already capped** at 3000 lines for the raw
  console and 5000 for the activity log via `setMaximumBlockCount`. No
  action needed there.

## Polling test coverage (this pass)

Added 9 new tests to `tests/test_polling_worker.py` for a total of 10:

| Test                                                       | Verifies |
|------------------------------------------------------------|----------|
| `test_priority_tx_preempts_polling`                        | Priority TX runs before any poll |
| `test_round_robin_cursor_visits_every_schedule`            | Cursor fairness when all due at once |
| `test_disabled_schedule_is_skipped`                        | toggle(False) entries are skipped without losing cursor position |
| `test_toggle_reenable_resets_next_run_to_full_interval`    | Re-enable waits a full interval (regression guard) |
| `test_disable_failed_schedule_marks_disabled_and_emits_once` | Build-time ValueError disables + reports exactly once |
| `test_boot_grace_suppresses_polling_until_first_rx_or_timeout` | No poll fires during boot-grace pre-RX |
| `test_first_rx_byte_clears_boot_grace_immediately`         | Boot grace lifts as soon as device proves alive |
| `test_stop_event_exits_run_loop_promptly`                  | run() exits in <0.5 s after stop() |
| `test_reset_metrics_zeroes_counters`                       | reset_metrics() clears and emits |
| `test_enqueue_priority_tx_emits_error_on_full_queue`       | 256-entry queue refuses overflow rather than growing |

Suite is 116 green (was 107). Runtime ~47 s.

## What was NOT covered in this pass

The original brief asked for several items that are deferred:

* **Qt-integrated UI flush / plot harness.** Needs a windowed run and a
  fake `QSerialPort` driver; the headless harness here only proves the
  RX pipeline. Hand-test the app at 1 kHz with a stress source before
  the next release.
* **Decoded-logger streaming-CSV variant.** Optimization #1 brought
  synchronous cost below decode itself, so the xlsx-vs-CSV refactor
  isn't load-bearing yet. Revisit if a >1 kHz device shows up.
* **`_apply_decoded` allocation reduction, console-cap, hide-aware
  redraw.** All low-µs wins on their own; bundle them when there's a
  motivating workload.
* **Polling cadence-drift integration test against a fake transport.**
  The new tests cover correctness; long-run drift measurement needs a
  fake serial that fakes RX in response to TX. Worth doing if the perf
  pass continues.
