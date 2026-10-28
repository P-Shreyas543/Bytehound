"""GUI event-loop latency probe with stall diagnostics (task.md Phase 1).

Runs the real ``MainWindow`` offscreen under a combined load and measures
how late a 10 ms ``PreciseTimer`` fires on the GUI thread. Load:

* frames streamed at ``--rate`` frames/s, from a loopback TCP device in a
  child process (no hardware) or, with ``--port``, from the NUCLEO-G474RE
  HIL firmware at ``--baud``;
* a logging session (event log + fixed-step 0.1 s) rotating every
  ``--segment-seconds``, so segment finishing (xlsx compile, analysis
  cache) overlaps live traffic;
* the RX console dock visible and the telemetry views updating.

Diagnostics, all on ``time.perf_counter()`` (monotonic, sub-microsecond;
``time.monotonic()`` ticks in ~15.6 ms steps on Windows) relative to the
start of the run:

* every tick's lateness (p50/p95/p99/max, exceedances of 50/100/250 ms);
* for every stall above ``--stall-ms``: the GUI thread's stack, sampled
  every 10 ms by a watcher thread while the stall lasts, and the other
  threads' stacks once;
* garbage-collection pauses (``gc.callbacks``) per generation;
* segment open / close / finish events of the session;
* UI queue depth (``_pending_packets``) per tick;
* process CPU (all threads) and whole-system CPU per second, and the
  working set, to separate GUI-thread work from OS-level starvation.

The watcher only samples while the GUI is already late, so it does not
add work to the GUI thread in normal operation.

  python tools/gui_latency_probe.py --rate 3250 --seconds 60 --runs 3
  python tools/gui_latency_probe.py --port COM26 --baud 921600 --rate 3250

Writes one JSON per run to ``artifacts/gui_latency/`` and prints a summary.
QSettings go to a temp .ini: the user's real settings are never touched.
"""

from __future__ import annotations

import argparse
import collections
import ctypes
import gc
import json
import multiprocessing as mp
import os
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tools.bench_capture import _device_server, peak_rss_mb  # noqa: E402

TICK_MS = 10


def _percentile(sorted_vals: List[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


class _CpuMeter:
    """Process CPU (all threads) and system-wide busy fraction (Windows)."""

    def __init__(self) -> None:
        self._last = self._read()

    @staticmethod
    def _read():
        proc = time.process_time()
        if sys.platform != "win32":
            return time.perf_counter(), proc, None
        idle, kern, user = (ctypes.c_ulonglong() for _ in range(3))
        ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))
        return time.perf_counter(), proc, (idle.value, kern.value + user.value)

    def sample(self) -> Dict[str, float]:
        now = self._read()
        (t0, p0, s0), (t1, p1, s1) = self._last, now
        self._last = now
        dt = max(t1 - t0, 1e-6)
        out = {"proc_cpu_cores": round((p1 - p0) / dt, 3)}
        if s0 and s1:
            busy = (s1[1] - s0[1]) - (s1[0] - s0[0])
            total = s1[1] - s0[1]
            out["system_busy"] = round(busy / total, 3) if total else 0.0
        return out


def run_once(args, run_index: int) -> dict:
    import PySide6.QtCore as QtCore

    tmp = Path(tempfile.mkdtemp(prefix="bh_latency_"))
    import logging
    log_path = tmp / "probe.log"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s"))
    handler.setLevel(logging.WARNING)
    logging.getLogger().addHandler(handler)
    QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
    QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat, QtCore.QSettings.Scope.UserScope,
                             str(tmp / "ini"))

    from PySide6.QtWidgets import QApplication

    import app.serial_logging.session as session_mod
    import app.ui.main_window as mw
    from app.serial_io.serial_worker import SerialSettings
    from app.serial_logging.session import SessionSettings

    mw.MainWindow._check_and_recover_temp_logs = lambda self, *a, **k: None
    # The window loads the default configuration on its first event-loop
    # pass; the probe loads its own explicitly, so that deferred load must
    # not replace it (it did before 2026-10-19: config and plot setup lost).
    mw.MainWindow._load_default_config = lambda self, *a, **k: None
    mw.MainWindow._popup_warning = lambda self, *a, **k: None
    mw.MainWindow._popup_critical = lambda self, *a, **k: None
    app = QApplication.instance() or QApplication(sys.argv)

    t_origin = time.perf_counter()

    def rel() -> float:
        return round(time.perf_counter() - t_origin, 4)

    # --- session events (wrapped, timing only) ---------------------------
    events: List[dict] = []
    originals = {}
    for name in ("_open_segment", "_close_segment", "_finish_segment"):
        orig = getattr(session_mod.SessionLog, name)
        originals[name] = orig

        def wrapper(self, *a, __orig=orig, __name=name, **k):
            t0 = time.perf_counter()
            try:
                return __orig(self, *a, **k)
            finally:
                events.append({"t": round(t0 - t_origin, 4), "event": __name,
                               "thread": threading.current_thread().name,
                               "duration_ms": round((time.perf_counter() - t0) * 1000, 2)})
        setattr(session_mod.SessionLog, name, wrapper)

    # --- GC pauses ----------------------------------------------------------
    gc_events: List[dict] = []
    gc_start: Dict[int, float] = {}

    def on_gc(phase, info):
        tid = threading.get_ident()
        if phase == "start":
            gc_start[tid] = time.perf_counter()
        else:
            t0 = gc_start.pop(tid, None)
            if t0 is not None:
                dur = (time.perf_counter() - t0) * 1000
                if dur >= 1.0:
                    gc_events.append({"t": round(t0 - t_origin, 4), "gen": info.get("generation"),
                                      "ms": round(dur, 2), "collected": info.get("collected"),
                                      "gui_thread": tid == gui_ident})
    gui_ident = threading.get_ident()
    gc.callbacks.append(on_gc)

    # --- UI flush cost (timing only) -------------------------------------
    flushes: List[tuple] = []      # (t, packets in queue at start, duration ms)
    import app.ui.telemetry_pipeline as tp
    orig_flush = tp.TelemetryPipelineMixin._flush_ui_inner

    def timed_flush(self):
        n = len(getattr(self, "_pending_packets", ()) or ())
        t0 = time.perf_counter()
        try:
            return orig_flush(self)
        finally:
            dt = (time.perf_counter() - t0) * 1000
            if n or dt > 5:
                flushes.append((round(t0 - t_origin, 4), n, round(dt, 2)))
    tp.TelemetryPipelineMixin._flush_ui_inner = timed_flush

    w = mw.MainWindow()
    w.show()
    cfg_dir = Path(args.config) if args.config else ROOT / "app" / "resources" / "config_template"
    if args.port:
        from tools.hil import nucleo as hw
        cfg_dir = hw.hil_config_dir(tmp / "config")
    w._load_config_from_path(cfg_dir, suppress_popups=True)
    w._session_settings_from_qsettings = lambda: SessionSettings(
        segment_seconds=args.segment_seconds, fixed_step_s=0.1)
    if getattr(w, "_console_dock", None) is not None:
        w._console_dock.show()

    # --- live plot load (live_plot_plan.md L0 / M1) ----------------------
    redraws: List[float] = []            # duration of every _redraw_plot, ms
    orig_redraw = mw.MainWindow._redraw_plot
    plot_signals = 0
    if args.plot_grid:
        rows, cols = (int(v) for v in args.plot_grid.lower().split("x"))
        w._plot_dock.show()
        w._rebuild_plot_grid(rows, cols, restore=False)
        for i, sig in enumerate(w._config.all_signals):
            w._add_signal_to_panel(i % len(w._plot_panels), (sig.frame_id, sig.signal_name))
        plot_signals = sum(len(p.assigned_keys) for p in w._plot_panels)
        w._plot_window_seconds = args.plot_window or None

        def timed_redraw(self, __orig=orig_redraw):
            t0 = time.perf_counter()
            try:
                return __orig(self)
            finally:
                redraws.append((time.perf_counter() - t0) * 1000)
        mw.MainWindow._redraw_plot = timed_redraw

    def pump(sec: float) -> None:
        end = time.perf_counter() + sec
        while time.perf_counter() < end:
            app.processEvents()
            time.sleep(0.001)

    pump(1.0)
    if args.gc_freeze:
        # Experiment only: move every object alive after start-up out of the
        # collector's reach so full collections scan only new objects.
        gc.collect()
        gc.freeze()

    dev = None
    sent_q = None
    if args.port:
        from tools.hil import nucleo as hw
        with hw.open_any_baud(args.port) as n:
            if args.baud != 115200:
                n.set_baud(args.baud)
            n.reset_stats()
        settings = SerialSettings(port=args.port, baud_rate=args.baud)
    else:
        port_q, sent_q = mp.Queue(), mp.Queue()
        dev = mp.Process(target=_device_server, args=(port_q, args.rate, args.seconds, sent_q), daemon=True)
        dev.start()
        settings = SerialSettings(port="127.0.0.1", connection_type="tcp", host="127.0.0.1",
                                  port_num=port_q.get(timeout=30))
    if not w._attempt_connect(settings):
        raise SystemExit("connect failed")
    worker_warnings: List[tuple] = []
    # Batches emitted by the worker vs handled by the GUI slot: the
    # difference is the backlog waiting in Qt's posted-event queue.
    batch_count = {"emitted": 0, "handled": 0}

    def count_emitted(_batch):
        batch_count["emitted"] += 1
    w._serial.packets_received.connect(count_emitted, QtCore.Qt.ConnectionType.DirectConnection)
    orig_on_packets = w._on_packets_received

    def counted_on_packets(batch, __orig=orig_on_packets):
        batch_count["handled"] += 1
        return __orig(batch)
    w._serial.packets_received.disconnect(orig_on_packets)
    w._serial.packets_received.connect(counted_on_packets)
    w._serial.warning_occurred.connect(lambda m: worker_warnings.append((rel(), m)))
    w._serial.error_occurred.connect(lambda m: worker_warnings.append((rel(), "ERROR " + m)))
    if args.gui_logging:
        # A/B: log on the GUI thread as before the worker sink existed.
        type(w._serial).logs_sessions = False
    if not w._start_logging_file(tmp / "session"):
        raise SystemExit("logging did not start")

    # --- probe + watcher ----------------------------------------------------
    ticks: List[tuple] = []          # (t, lateness_ms, queue_depth)
    last = [time.perf_counter()]
    cpu = _CpuMeter()
    cpu_samples: List[dict] = []
    stalls: List[dict] = []
    current: Dict[str, object] = {}
    stop_watch = threading.Event()

    def on_tick() -> None:
        now = time.perf_counter()
        late = max(0.0, (now - last[0]) * 1000.0 - TICK_MS)
        last[0] = now
        depth = len(getattr(w, "_pending_packets", ()) or ())
        ticks.append((round(now - t_origin, 4), round(late, 2), depth,
                      batch_count["emitted"] - batch_count["handled"]))
        if current:
            current["end"] = round(now - t_origin, 4)
            current["lateness_ms"] = round(late, 1)
            stalls.append(dict(current))
            current.clear()

    worker_stalls: List[dict] = []
    progress = {"rx": None, "since": time.perf_counter(), "next": 0.0, "open": None}

    def worker_stack() -> str:
        # Never keep a frame object beyond this call: a retained frame keeps
        # its locals alive (CPython 3.10), e.g. the parser's memoryview of its
        # buffer, which then cannot be resized (observed: BufferError).
        if args.no_stacks:
            return "<stack sampling off>"
        frames = sys._current_frames()
        try:
            for fr in frames.values():
                st = traceback.extract_stack(fr)
                if any(f.name == "_run_loop" and f.filename.endswith("serial_worker.py") for f in st):
                    return " <- ".join(f"{Path(f.filename).name}:{f.lineno}:{f.name}" for f in reversed(st[-10:]))
            return "<worker thread not found>"
        finally:
            del frames

    pipeline: List[tuple] = []   # (t, rx_bytes, parser_in, frames_ok, batch, since_emit_s, gui_count, worker_id)

    def check_worker(now: float) -> None:
        if now < progress["next"]:
            return
        progress["next"] = now + 0.25
        worker = getattr(w, "_serial", None)
        rx = getattr(worker, "_rx_bytes", None)
        try:
            st = worker._parser.stats
            pipeline.append((round(now - t_origin, 2), rx, st.bytes_in, st.frames_ok,
                             len(worker._batch), round(time.monotonic() - worker._last_emit_time, 2),
                             w._packet_count, id(worker) % 100000))
        except Exception:
            pass
        if rx is None:
            return
        if rx != progress["rx"]:
            if progress["open"] is not None:
                progress["open"]["end"] = round(now - t_origin, 3)
                worker_stalls.append(progress["open"])
                progress["open"] = None
            progress["rx"], progress["since"] = rx, now
            return
        if now - progress["since"] > 1.0:
            if progress["open"] is None:
                progress["open"] = {"start": round(progress["since"] - t_origin, 3), "stacks": collections.Counter(),
                                    "batch": len(getattr(worker, "_batch", ()) or ()),
                                    "socket_waiting": None}
                try:
                    progress["open"]["socket_waiting"] = worker._serial.in_waiting if worker._serial else None
                except Exception as exc:
                    progress["open"]["socket_waiting"] = repr(exc)
            progress["open"]["stacks"][worker_stack()] += 1

    def watcher() -> None:
        next_cpu = time.perf_counter() + 1.0
        while not stop_watch.wait(0.01):
            now = time.perf_counter()
            check_worker(now)
            if now >= next_cpu:
                s = cpu.sample()
                s["t"] = round(now - t_origin, 3)
                s["rss_mb"] = round(peak_rss_mb(), 1)
                cpu_samples.append(s)
                next_cpu += 1.0
            behind = (now - last[0]) * 1000.0 - TICK_MS
            if behind < args.stall_ms:
                continue
            if args.no_stacks:
                if not current:
                    current.update(start=round(last[0] - t_origin, 4), gui_samples=collections.Counter(),
                                   other_threads={}, cpu_at_start=cpu_samples[-1] if cpu_samples else None)
                current["gui_samples"]["<stack sampling off>"] += 1
                continue
            frames = sys._current_frames()
            try:
                gui = frames.get(gui_ident)
                stack = "<no frame>" if gui is None else " <- ".join(
                    f"{Path(f.filename).name}:{f.lineno}:{f.name}" for f in reversed(traceback.extract_stack(gui)[-8:]))
                if not current:
                    current.update(start=round(last[0] - t_origin, 4), gui_samples=collections.Counter(),
                                   other_threads={
                                       threading._active.get(tid, None).name if threading._active.get(tid) else str(tid):
                                       " <- ".join(f"{Path(f.filename).name}:{f.lineno}:{f.name}"
                                                   for f in reversed(traceback.extract_stack(fr)[-4:]))
                                       for tid, fr in frames.items() if tid != gui_ident},
                                   cpu_at_start=cpu_samples[-1] if cpu_samples else None)
                current["gui_samples"][stack] += 1
            finally:
                del frames
                gui = None

    probe = QtCore.QTimer()
    probe.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
    probe.setInterval(TICK_MS)
    probe.timeout.connect(on_tick)
    watch = threading.Thread(target=watcher, name="LatencyWatcher", daemon=True)
    last[0] = time.perf_counter()
    probe.start()
    watch.start()
    if args.port:
        from tools.hil import nucleo as hw
        cps = max(1, args.rate // 4)
        w._serial.enqueue_priority_tx(hw.stream_cmd(cps, True))
    # Measure under the real event loop (exec), as the application runs;
    # a processEvents()+sleep pump would distort timer delivery.
    def run_loop(seconds: float) -> None:
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(int(seconds * 1000), loop.quit)
        loop.exec()

    t_load0 = rel()
    run_loop(args.seconds)
    t_load1 = rel()
    if args.port:
        w._serial.enqueue_priority_tx(hw.stream_cmd(0, False))
    run_loop(1.5)
    probe.stop()
    stop_watch.set()
    watch.join(1.0)

    plot_state = {
        "dock_visible": bool(w._plot_dock.isVisible()),
        "panels": len(w._plot_panels),
        "assigned": sum(len(p.assigned_keys) for p in w._plot_panels),
        "items_visible": sum(bool(p.plot_item.isVisible()) for p in w._plot_panels),
        "history_keys": [list(k) for k in list(w._plot_history)[:4]],
        "curves": sum(len(p.curves) for p in w._plot_panels),
        "points_in_curves": sum(len(c.getData()[0]) if c.getData()[0] is not None else 0
                                for p in w._plot_panels for c in p.curves.values()),
        "history_points": sum(len(w._plot_history[k]) for p in w._plot_panels for k in p.assigned_keys
                              if k in w._plot_history),
    } if args.plot_grid else None
    session = w._session_log
    t_stop0 = time.perf_counter()
    w._stop_logging()
    finished = session.await_finished(600) if session is not None else True
    stop_s = time.perf_counter() - t_stop0
    shown = w._packet_count
    w._disconnect(reason="latency probe done")
    w.close()
    pump(0.5)
    sent = sent_q.get(timeout=10) if sent_q is not None else None
    if dev is not None:
        dev.join(timeout=5)
    if args.port:
        from tools.hil import nucleo as hw
        with hw.open_any_baud(args.port):
            pass
    gc.callbacks.remove(on_gc)
    from app.serial_io.serial_worker import PollingWorker
    PollingWorker.logs_sessions = True
    logging.getLogger().removeHandler(handler)
    handler.close()
    tp.TelemetryPipelineMixin._flush_ui_inner = orig_flush
    mw.MainWindow._redraw_plot = orig_redraw
    for name, orig in originals.items():
        setattr(session_mod.SessionLog, name, orig)

    load = [lt for t, lt, _d, _b in ticks if t_load0 <= t <= t_load1]
    s = sorted(load)
    for st in stalls:
        st["gui_samples"] = st["gui_samples"].most_common(5)
    return {
        "run": run_index,
        "started": datetime.now().isoformat(timespec="seconds"),
        "source": f"serial {args.port} @ {args.baud}" if args.port else "tcp loopback",
        "rate_fps": args.rate,
        "seconds": args.seconds,
        "segment_seconds": args.segment_seconds,
        "tick_ms": TICK_MS,
        "samples": len(load),
        "p50_ms": round(_percentile(s, 0.50), 2),
        "p95_ms": round(_percentile(s, 0.95), 2),
        "p99_ms": round(_percentile(s, 0.99), 2),
        "max_ms": round(s[-1], 2) if s else 0.0,
        "over_50ms": sum(1 for v in load if v > 50),
        "over_100ms": sum(1 for v in load if v > 100),
        "over_250ms": sum(1 for v in load if v > 250),
        "max_queue_depth": max((d for _, _, d, _b in ticks), default=0),
        "max_posted_batch_backlog": max((b for _, _, _d, b in ticks), default=0),
        "backlog_at_worst_ticks": sorted(((lt, b) for _, lt, _d, b in ticks), reverse=True)[:5],
        "flush_max_ms": max((d for _, _, d in flushes), default=0.0),
        "flush_us_per_packet_p50": round(_percentile(sorted(d * 1000 / n for _, n, d in flushes if n >= 20), 0.5), 1),
        "flushes": flushes,
        "plot_grid": args.plot_grid,
        "plot_window_s": args.plot_window if args.plot_grid else None,
        "plot_signals": plot_signals,
        "plot_state": plot_state,
        "redraws": len(redraws),
        "redraw_p50_ms": round(_percentile(sorted(redraws), 0.50), 2) if redraws else None,
        "redraw_p99_ms": round(_percentile(sorted(redraws), 0.99), 2) if redraws else None,
        "redraw_max_ms": round(max(redraws), 2) if redraws else None,
        "frames_sent": sent,
        "frames_shown": shown,
        "session_finished": finished,
        "stop_logging_s": round(stop_s, 2),
        "stalls": stalls,
        "worker_stalls": [dict(ws, stacks=ws["stacks"].most_common(4)) for ws in worker_stalls]
        + ([dict(progress["open"], stacks=progress["open"]["stacks"].most_common(4), end=None)]
           if progress["open"] else []),
        "pipeline": pipeline,
        "worker_warnings": worker_warnings,
        "buffer_errors": sum(1 for _, m in worker_warnings if "BufferError" in m),
        "stack_sampling": not args.no_stacks,
        "gc_freeze": args.gc_freeze,
        "logging_thread": "gui" if args.gui_logging else "worker",
        "gc_gen2_max_ms": max((g["ms"] for g in gc_events if g["gen"] == 2), default=0.0),
        "log_file": str(log_path),
        "rx_bytes_final": getattr(getattr(w, "_serial", None), "_rx_bytes", None),
        "session_events": events,
        "gc_pauses": gc_events,
        "cpu": cpu_samples,
        "ticks": ticks if args.keep_ticks else None,
        "session_folder": str(tmp / "session"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rate", type=int, default=3250, help="frames per second")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--segment-seconds", type=float, default=10.0)
    ap.add_argument("--stall-ms", type=float, default=50.0, help="stack-sample stalls longer than this")
    ap.add_argument("--port", default=None, help="NUCLEO HIL firmware port (default: TCP loopback)")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--config", default=None)
    ap.add_argument("--no-stacks", action="store_true",
                    help="never sample thread stacks (rules out observer effects)")
    ap.add_argument("--gui-logging", action="store_true",
                    help="A/B: write the session on the GUI thread (pre-change behaviour)")
    ap.add_argument("--gc-freeze", action="store_true", help="experiment: gc.freeze() after start-up")
    ap.add_argument("--keep-ticks", action="store_true", help="store every tick in the JSON")
    ap.add_argument("--plot-grid", default=None, help="live plot grid, e.g. 2x4, with every config signal plotted")
    ap.add_argument("--plot-window", type=float, default=300.0, help="plot window in s (0 = All session)")
    ap.add_argument("--out", type=Path, default=ROOT / "artifacts" / "gui_latency")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    args.out.mkdir(parents=True, exist_ok=True)
    worst = 0.0
    for i in range(args.runs):
        r = run_once(args, i + 1)
        path = args.out / f"latency_{datetime.now():%Y%m%d_%H%M%S}_run{i + 1}.json"
        path.write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
        worst = max(worst, r["max_ms"])
        print(f"run {i + 1}: n={r['samples']} p50={r['p50_ms']} p95={r['p95_ms']} p99={r['p99_ms']} "
              f"max={r['max_ms']} ms  >50:{r['over_50ms']} >100:{r['over_100ms']} >250:{r['over_250ms']}  "
              f"stalls>{args.stall_ms:.0f}ms:{len(r['stalls'])}  queue_max={r['max_queue_depth']}  "
              f"posted_backlog_max={r['max_posted_batch_backlog']} worst(lat,backlog)={r['backlog_at_worst_ticks'][:2]}  "
              f"shown={r['frames_shown']}/{r['frames_sent']}  worker_stalls={len(r['worker_stalls'])}  "
              f"buffer_errors={r['buffer_errors']} gc2_max={r['gc_gen2_max_ms']}  -> {path.name}")
        if r["plot_grid"]:
            print(f"   plot {r['plot_grid']} ({r['plot_signals']} signals, window "
                  f"{r['plot_window_s'] or 'all'} s): redraws={r['redraws']} p50={r['redraw_p50_ms']} "
                  f"p99={r['redraw_p99_ms']} max={r['redraw_max_ms']} ms")
        for ws in r["worker_stalls"]:
            print(f"   WORKER not reading {ws['start']}..{ws.get('end')} s, batch={ws['batch']}, "
                  f"socket_waiting={ws['socket_waiting']}: {ws['stacks'][:2]}")
        for st in r["stalls"]:
            print(f"   stall {st['start']}..{st.get('end')} s ({st.get('lateness_ms')} ms): "
                  f"{st['gui_samples'][:2]}")
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
