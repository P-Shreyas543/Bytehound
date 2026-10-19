# Live Plot review plan

**Status:** PLAN — not started (owner request, 2026-10-19). Tracked in
[Plane.md](Plane.md) as Part I.

**Scope:** the Live Plot dock — `app/ui/plot_orchestration.py` (grid,
redraw, axes, modes), `app/ui/plot_panel.py` (panel state, history
buffer), and the feed in `app/ui/telemetry_pipeline.py`. Not in scope: the
Analysis Suite and the XY plot (separate reviews).

Rule for this work (as for the rest of the closure pass): every finding is
either **confirmed** (code or test proves it) or **to verify**; nothing is
fixed without a test that fails first; results are reported with evidence.

---

## 1. How the live plot works today (read from the code)

- **Samples:** every decoded signal with status `ok` is appended to its own
  `TimeSeriesBuffer` during the GUI flush. X = seconds since the session
  started on the worker's receive clock (`perf_counter`, the time the bytes
  arrived, not when the GUI processed them); Y = the scaled value.
- **Redraw:** at most 30 times a second, from the 60 Hz UI flush. A curve
  whose data did not change is skipped. Curves use clip-to-view, automatic
  peak downsampling and no antialiasing.
- **Memory:** one shared budget (default 512 MB, Plot Settings) divided
  between all plotted signals; more signals means less history each. The
  oldest samples are dropped in batches when a buffer reaches its share.
- **Modes:** *Live* (sliding window, or the whole session) and *Explore*
  (panning stops the scrolling); Y scaling fit / loose / expand / manual;
  a second Y axis for a second unit; hover readout; trigger.

## 2. Findings

### Confirmed by reading the code

| # | Finding | Why it matters |
|---|---|---|
| P1 | **No line break at gaps.** A reconnect, a silent device or a configuration change is drawn as a straight line from the last point before to the first point after. | Looks like a smooth change in a BMS value that never happened. |
| P2 | **Booleans, enums and states are drawn as ramps.** No step mode: a 0 → 1 switch is a sloped line between two samples. | At low rates the switch time looks wrong by up to one sample interval. |
| P3 | **A third unit in one panel uses the wrong axis.** Any signal whose unit differs from the first is drawn against the right axis, which is labelled with the *second* unit. | A °C trace read off a V axis. |
| P4 | **Points skipped under load vanish silently.** When the GUI queue saturates, display points are dropped (counted as *Dropped*, logs unaffected) and the line is joined across them. | Same as P1, during overload. |
| P5 | **Manual is wrong about history size.** The manual (§7) says a 6,000-sample ring buffer per signal; the code uses the shared 512 MB budget. | Users plan long sessions on wrong numbers. |

### To verify / measure

| # | Question | How |
|---|---|---|
| M1 | Redraw cost with many signals: GUI frame time at 3,000 frames/s with 8 panels × 8 signals, sliding window and "All session". | Extend `tools/gui_latency_probe.py`; gate = the Phase 1 latency gate (p99 ≤ 50 ms, max ≤ 250 ms). |
| M2 | Cost of dropping old samples when the budget is full (the copy runs on the GUI thread). | Probe after the budget fills; worst single flush. |
| M3 | "All session" after 1 h and 8 h: is the whole history re-sent on every change? | Profile `setData` size and time per redraw. |
| M4 | Hover readout and legend with many signals. | Probe with the mouse moving over a full grid. |
| M5 | Visual: theme switch, 125–200 % display scaling, right-axis alignment after resizing, legend overlap. | Screenshots at each setting (offscreen and real). |

### UX — owner chooses

| # | Proposal |
|---|---|
| U1 | Show when a signal goes **stale** (stops updating): faded tail or marker. |
| U2 | Shade **recorded gaps** (unplug, config change) on the time axis. |
| U3 | More than two units in a panel: a third axis, or a clear warning (fixes P3 visibly). |
| U4 | Clearer Live / Explore state, a "Back to live" button, and Δt / ΔY cursor measurements like the Analysis Suite. |
| U5 | Export the visible window as PNG or CSV. |

## 3. Phases

| Phase | Content | Exit criteria |
|---|---|---|
| **L0 Baseline** | Measure M1–M5; screenshots of today's behaviour; no code change. | Numbers and screenshots recorded in Plane.md. |
| **L1 Correctness** | P1 (break the line at gaps: recorded gaps, and silence longer than a few expected intervals), P2 (step drawing for boolean / enum / bitfield signals), P3, P4, P5 (manual). | One failing-then-passing test per item; latency gate unchanged; before/after screenshots. |
| **L2 Performance** | Only what L0 shows is over budget. | Gate met at 3,000 frames/s on the NUCLEO; full suite green. |
| **L3 UX** | The U-items the owner selects. | Per item: test + screenshot; manual updated. |

Hardware check at the end of L1 and L2: NUCLEO at 2 Mbaud (3,000 frames/s)
and a real BMS, 30 minutes each, plot visibly correct across an unplug and
a configuration change.

Rough effort: L0 half a day; L1 one to two days; L2 depends on L0; L3 per
item.
