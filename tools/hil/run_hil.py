"""Hardware-in-the-loop test of ByteHound against a NUCLEO-G474RE running
firmware/nucleo_g474_bms_sim.

The board's own counters (frames sent per ID, injected noise / corrupted
frames, bytes sent, frames it received) are compared with what the
application's PollingWorker, parser, session logger and analysis code saw.
Any difference is a lost, duplicated or misclassified byte.

  python tools/hil/run_hil.py                 # every test, ~3 min
  python tools/hil/run_hil.py --ping          # is the board there?
  python tools/hil/run_hil.py --only stream_2000000 burst
  python tools/hil/run_hil.py --soak-minutes 60

Exit status is the number of failed tests. A JSON report is written to
artifacts/hil/ (``--report`` to change).
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication  # noqa: E402

from app.decoder.config_loader import load_config  # noqa: E402
from app.serial_io.serial_worker import WATCHDOG_TIMEOUT, PollingWorker, SerialSettings  # noqa: E402
from tools.hil import nucleo as hw  # noqa: E402

TELEMETRY = (0x1000, 0x2000, 0x3000, 0x4000)
STAT_KEY = {0x1000: "frames_1000", 0x2000: "frames_2000", 0x3000: "frames_3000", 0x4000: "frames_4000"}


# ---------------------------------------------------------------- plumbing
@dataclass
class Result:
    name: str
    ok: bool = True
    checks: List[str] = field(default_factory=list)
    data: Dict[str, object] = field(default_factory=dict)
    seconds: float = 0.0

    def check(self, cond: bool, label: str) -> bool:
        self.checks.append(("ok   " if cond else "FAIL ") + label)
        self.ok &= bool(cond)
        return bool(cond)


def pump(seconds: float, until: Optional[Callable[[], bool]] = None) -> bool:
    """Run the Qt event loop so the worker's queued signals are delivered."""
    app = QCoreApplication.instance()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if until is not None and until():
            return True
        time.sleep(0.002)
    app.processEvents()
    return until() if until is not None else True


class AppLink:
    """The application's serial stack on the board's port: PollingWorker
    with worker-side decoding, exactly as the main window runs it."""

    def __init__(self, port: str, baud: int, config, schedules=(), on_items=None) -> None:
        self.config = config
        self.worker = PollingWorker(SerialSettings(port=port, baud_rate=baud), config.protocol,
                                    list(schedules), decode_config=config)
        self.good: Dict[int, int] = {}
        self.good_bytes = 0
        self.rejected = 0
        self.rejected_bytes = 0
        self.seq: List[int] = []
        self.replies: Dict[int, bytes] = {}
        self.tx: List[bytes] = []
        self.tx_times: List[float] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.timeouts_fired = 0
        self.lost = 0
        self.integrity: dict = {}
        self._on_items = on_items
        w = self.worker
        w.packets_received.connect(self._on_packets)
        w.tx_recorded.connect(self._on_tx)
        w.warning_occurred.connect(self.warnings.append)
        w.error_occurred.connect(self.errors.append)
        w.device_timeout.connect(self._on_timeout)
        w.connection_lost.connect(self._on_lost)
        w.integrity_updated.connect(lambda s: setattr(self, "integrity", dict(s)))

    def _on_tx(self, b) -> None:
        self.tx.append(bytes(b))
        self.tx_times.append(time.monotonic())

    def _on_timeout(self) -> None:
        self.timeouts_fired += 1

    def _on_lost(self) -> None:
        self.lost += 1

    def _on_packets(self, items) -> None:
        for p, _decoded, _rx_perf in items:
            if not p.ok:
                self.rejected += 1
                self.rejected_bytes += len(p.raw)
                continue
            fid = p.frame_id
            if fid in TELEMETRY:
                self.good[fid] = self.good.get(fid, 0) + 1
                self.good_bytes += len(p.raw)
                if fid == 0x4000:
                    self.seq.append(struct.unpack_from("<I", p.payload)[0])
            else:
                self.replies[fid] = p.payload
        if self._on_items is not None:
            self._on_items(items)

    def open(self) -> "AppLink":
        self.worker.open()
        pump(0.3)
        return self

    def send(self, data: bytes) -> None:
        self.worker.enqueue_priority_tx(data)

    def board_stats(self, timeout: float = 3.0) -> Dict[str, int]:
        self.replies.pop(hw.ID_STATS_REPLY, None)
        self.send(hw.command(hw.ID_STATS))
        if not pump(timeout, lambda: hw.ID_STATS_REPLY in self.replies):
            raise TimeoutError("board did not answer GET_STATS through the app")
        return hw.parse_stats(self.replies[hw.ID_STATS_REPLY])

    def close(self) -> dict:
        snap = self.worker.integrity_snapshot()
        self.worker.close()
        pump(0.1)
        return snap


def prepare_board(port: str, baud: int) -> None:
    """Quiesce the board, move it to ``baud``, zero its counters, release the port."""
    with hw.open_any_baud(port) as n:
        if baud != 115200:
            n.set_baud(baud)
        n.reset_stats()
        time.sleep(0.05)


def restore_board(port: str) -> None:
    with hw.open_any_baud(port):
        pass


def check_seq(r: Result, seq: List[int], expected: int, allow_missing: int = 0) -> None:
    diffs_bad = sum(1 for a, b in zip(seq, seq[1:], strict=False) if b != a + 1)
    if allow_missing:
        r.check(all(b > a for a, b in zip(seq, seq[1:], strict=False)), "0x4000 sequence strictly increasing (no duplicates/reordering)")
        r.check(expected - len(seq) <= allow_missing,
                f"0x4000 frames missing {expected - len(seq)} <= corrupted {allow_missing}")
    else:
        r.check(diffs_bad == 0 and (not seq or seq[0] == 0),
                f"0x4000 sequence contiguous from 0 ({len(seq)} frames, {diffs_bad} gaps)")
        r.check(len(seq) == expected, f"0x4000 frames seen {len(seq)} == sent {expected}")


def seq_gaps(seq: List[int]) -> int:
    """Frames missing between consecutive received counters (32-bit wrap;
    a backward jump is a reset, not loss) — the tests' own count."""
    missing = 0
    for a, b in zip(seq, seq[1:], strict=False):
        d = (b - a) % (1 << 32)
        if 1 < d < (1 << 31):
            missing += d - 1
    return missing


def check_app_sequence(r: Result, link: "AppLink", snap: dict) -> None:
    """F12: the application's own gap count equals what the received
    sequence proves."""
    if "seq_missing" not in snap:
        r.check(False, "application did not report sequence counters (F12)")
        return
    expect = seq_gaps(link.seq)
    r.check(snap["seq_missing"] == expect,
            f"app detected {snap['seq_missing']} missing frames from the counter == {expect} in the sequence")


def check_accounting(r: Result, link: AppLink, snap: dict, st: Dict[str, int], *, injected: bool) -> None:
    for fid in TELEMETRY:
        got, sent = link.good.get(fid, 0), st[STAT_KEY[fid]]
        r.check(got == sent, f"0x{fid:04X} good frames app {got} == board {sent}")
    r.check(link.rejected == st["corrupted"], f"rejected frames app {link.rejected} == corrupted by board {st['corrupted']}")
    r.check(snap["discarded_bytes"] == st["noise_bytes"],
            f"discarded bytes app {snap['discarded_bytes']} == noise injected {st['noise_bytes']}")
    total = link.good_bytes + link.rejected_bytes + snap["discarded_bytes"]
    r.check(total == st["tx_bytes"], f"bytes accounted app {total} == sent by board {st['tx_bytes']}")
    r.check(snap["overflow_bytes"] == 0, f"parser overflow bytes {snap['overflow_bytes']} == 0")
    drv = snap.get("driver_errors") or {}
    r.check(not any(drv.values()), f"no driver errors {drv}")
    if not injected:
        r.check(snap["frames_rejected"] == 0, "no rejected frames on a clean line")
    r.check(st["rx_crc_errors"] == 0 and st["rx_overruns"] == 0 and st["rx_line_errors"] == 0,
            f"board RX clean (crc {st['rx_crc_errors']}, overrun {st['rx_overruns']}, line {st['rx_line_errors']})")
    check_app_sequence(r, link, snap)
    r.data.update(board=st, app_good=dict(link.good), app_rejected=link.rejected,
                  integrity={k: v for k, v in snap.items() if k != "driver_errors"})


# ------------------------------------------------------------------ tests
def t_ping(args, config) -> Result:
    r = Result("ping")
    with hw.open_any_baud(args.port) as n:
        v = n.ping()
        r.check(v.startswith("bh-sim-g474"), f"firmware answers: {v!r}")
        r.data["version"] = v
    return r


def _stream(name: str, args, config, baud: int, seconds: float, load: float,
            noise: int = 0, corrupt: int = 0, counter: bool = True) -> Result:
    r = Result(name)
    prepare_board(args.port, baud)
    cps = max(1, int(load * baud / 10 / hw.CYCLE_BYTES[counter]))
    if noise:
        cps = int(cps * 0.95)
    link = AppLink(args.port, baud, config).open()
    raw = Path(tempfile.mkdtemp(prefix="bh_hil_")) / "wire.bhraw"
    link.worker.start_raw_capture(raw, {"test": name})
    try:
        if noise or corrupt:
            link.send(hw.inject_cmd(noise, corrupt))
        link.send(hw.stream_cmd(cps, counter))
        pump(seconds)
        link.send(hw.stream_cmd(0, False))
        link.send(hw.inject_cmd(0, 0))
        pump(0.5)
        st = link.board_stats()
    finally:
        cap_err = link.worker.stop_raw_capture()
        snap = link.close()
        restore_board(args.port)
    r.data.update(baud=baud, cycles_per_s=cps, seconds=seconds, load=load)
    r.data["achieved_cycles_per_s"] = round(st["frames_1000"] / seconds, 1)
    check_accounting(r, link, snap, st, injected=bool(noise or corrupt))
    if counter:
        check_seq(r, link.seq, st["frames_4000"] if not corrupt else st["seq_next"],
                  allow_missing=st["corrupted"] if corrupt else 0)
    from app.serial_logging.raw_capture import iter_raw_capture
    rx_raw = sum(len(d) for direction, _t, d in iter_raw_capture(raw) if direction == 0)
    r.check(cap_err is None, f"raw capture wrote without error ({cap_err})")
    r.check(rx_raw == snap["parser_bytes_in"],
            f"raw capture RX bytes {rx_raw} == parser bytes in {snap['parser_bytes_in']}")
    r.check(not link.errors, f"no worker errors {link.errors[:3]}")
    return r


def t_burst(args, config) -> Result:
    """Back-to-back cycles with no pacing at 2 Mbaud: the line is 100 % busy."""
    r = Result("burst_2000000")
    baud, cycles = 2_000_000, args.burst_cycles
    prepare_board(args.port, baud)
    link = AppLink(args.port, baud, config).open()
    try:
        t0 = time.monotonic()
        link.send(hw.burst_cmd(cycles))
        pump(cycles * hw.CYCLE_BYTES[True] * 10 / baud * 1.5 + 2.0,
             lambda: link.good.get(0x4000, 0) >= cycles)
        dt = time.monotonic() - t0
        pump(0.3)
        st = link.board_stats()
    finally:
        snap = link.close()
        restore_board(args.port)
    r.data.update(cycles=cycles, seconds=round(dt, 2),
                  line_utilisation=round(st["tx_bytes"] * 10 / baud / dt, 3))
    r.check(st["frames_4000"] == cycles, f"board sent {st['frames_4000']} of {cycles} cycles")
    check_accounting(r, link, snap, st, injected=False)
    check_seq(r, link.seq, cycles)
    return r


def _polling(name: str, args, config, pipelined: bool) -> Result:
    """Configured poll schedule against the board. The default 100 ms TX
    gap cannot carry the template schedule (17 polls/s), which the worker
    must say; with a 20 ms gap every interval must be honoured."""
    r = Result(name)
    prepare_board(args.port, 115200)
    seconds = args.poll_seconds
    link = AppLink(args.port, 115200, config, config.polling_schedules).open()
    try:
        link.worker.set_pipelining(pipelined, depth=2)
        link.worker.set_polling_global(True)
        pump(5.0)                                     # past the 2.5 s boot grace
        r.check(any("polls/s" in w for w in link.warnings),
                f"default gap: worker warns the schedule will stretch ({link.warnings[:1]})")
        missed_stretched = link.worker.integrity_snapshot()["polls_missed"]
        r.check(missed_stretched > 0, f"default gap: skipped polls are counted ({missed_stretched})")
        link.worker.set_polling_global(False)
        pump(0.3)
        missed_before = link.worker.integrity_snapshot()["polls_missed"]
        tx_mark = len(link.tx_times)
        good_mark = dict(link.good)
        link.worker.set_pipelining(pipelined, depth=2, gap_ms=20)
        link.warnings.clear()
        link.worker.set_polling_global(True)
        pump(seconds)
        link.worker.set_polling_global(False)
        pump(0.4)
        st = link.board_stats()
    finally:
        snap = link.close()
        restore_board(args.port)
    polls = [(t, int.from_bytes(b[2:4], "little"))
             for t, b in zip(link.tx_times[tx_mark:], link.tx[tx_mark:], strict=True)
             if len(b) >= 4 and int.from_bytes(b[2:4], "little") in TELEMETRY]
    span = polls[-1][0] - polls[0][0] if len(polls) > 1 else 0.0
    sent = {fid: sum(1 for _t, f in polls if f == fid) for fid in TELEMETRY}
    r.data.update(polls_sent=sent, responses=dict(link.good), poll_timeouts=snap["poll_timeouts"],
                  span_s=round(span, 2))
    r.check(not link.warnings, f"20 ms gap: no stretch warning {link.warnings[:1]}")
    missed = snap["polls_missed"] - missed_before
    r.check(missed == 0, f"20 ms gap: no polls skipped ({missed})")
    import statistics
    jitter = {}
    for s in config.polling_schedules:
        ts = [t for t, f in polls if f == s.target_id]
        iv = [(b - a) * 1000 for a, b in zip(ts, ts[1:], strict=False)]
        if len(iv) > 2:
            jitter[f"0x{s.target_id:04X}"] = {"interval_ms": s.interval_ms, "mean": round(statistics.mean(iv), 1),
                                            "stdev": round(statistics.stdev(iv), 1),
                                            "max_late": round(max(iv) - s.interval_ms, 1)}
    r.data["jitter_ms"] = jitter
    r.checks.append(f"info jitter (ms): {jitter}")
    for s in config.polling_schedules:
        expect = span * 1000 / max(s.interval_ms, 1)
        got = link.good.get(s.target_id, 0) - good_mark.get(s.target_id, 0)
        r.check(abs(got - expect) <= 0.15 * expect + 2,
                f"0x{s.target_id:04X} responses {got} vs {expect:.0f} for {s.interval_ms} ms over {span:.1f}s")
        total = link.good.get(s.target_id, 0)
        r.check(total == st[STAT_KEY[s.target_id]], f"0x{s.target_id:04X} app {total} == board replies {st[STAT_KEY[s.target_id]]}")
    r.check(snap["poll_timeouts"] == 0, f"poll timeouts {snap['poll_timeouts']} == 0")
    r.check(st["rx_frames_ok"] >= len(polls), f"board received {st['rx_frames_ok']} frames >= {len(polls)} polls sent")
    r.check(st["rx_crc_errors"] == 0, f"board saw {st['rx_crc_errors']} bad-CRC requests")
    r.check(snap["frames_rejected"] == 0 and snap["discarded_bytes"] == 0, "clean RX on the app side")
    return r


def t_smoke(args, config) -> Result:
    """The existing end-to-end smoke script (decode, bitfields, enums, TX
    commands, voltage-limit round trip, polling cadence) against the board."""
    r = Result("smoke_headless")
    restore_board(args.port)
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    p = subprocess.run([sys.executable, str(ROOT / "tools" / "smoke" / "smoke_headless.py"), "--port", args.port,
                        "--boot-delay", "0.5", "--seconds", "12", "--tx-gap", "20"],
                       cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180)
    fails = [ln for ln in p.stdout.splitlines() if ln.startswith("[FAIL]")]
    oks = sum(1 for ln in p.stdout.splitlines() if ln.startswith("[ OK ]"))
    r.data.update(exit=p.returncode, passed=oks, failed=fails)
    r.check(p.returncode == 0, f"smoke_headless exit {p.returncode}: {oks} ok, {len(fails)} failed")
    for f in fails:
        r.checks.append("     " + f)
    restore_board(args.port)
    return r


def t_watchdog(args, config) -> Result:
    r = Result("watchdog")
    prepare_board(args.port, 115200)
    link = AppLink(args.port, 115200, config).open()
    try:
        fired = pump(WATCHDOG_TIMEOUT + 2.0, lambda: link.timeouts_fired > 0)
        r.check(fired, f"device_timeout after {WATCHDOG_TIMEOUT}s of silence")
        link.send(hw.stream_cmd(20, True))
        resumed = pump(2.0, lambda: link.good.get(0x4000, 0) >= 10)
        r.check(resumed, f"data resumes after silence ({link.good.get(0x4000, 0)} frames)")
        link.send(hw.stream_cmd(0, False))
        pump(0.3)
        r.check(link.lost == 0, "no connection_lost on a silent but connected device")
    finally:
        link.close()
        restore_board(args.port)
    return r


def _lost_bytes(link: "AppLink", snap: dict, st: Dict[str, int]) -> int:
    return st["tx_bytes"] - (link.good_bytes + link.rejected_bytes + snap["discarded_bytes"])


def t_reader_pause(args, config) -> Result:
    """task.md Phase 3: the worker stops reading for P seconds while the
    board streams at 2 Mbaud. The driver buffer the OS actually granted is
    not reported by pyserial, so it is measured: the longest pause with no
    loss bounds it from below, the first lossy pause from above."""
    r = Result("reader_pause_2000000")
    baud, load = 2_000_000, 0.8
    cps = int(load * baud / 10 / hw.CYCLE_BYTES[True])
    rate = cps * hw.CYCLE_BYTES[True]
    results = []
    for pause_s in args.pauses:
        prepare_board(args.port, baud)
        link = AppLink(args.port, baud, config).open()
        orig = link.worker._service_rx
        pending = {"s": 0.0}

        def paused(_orig=orig, _pending=pending):
            if _pending["s"]:
                d, _pending["s"] = _pending["s"], 0.0
                time.sleep(d)
            return _orig()

        link.worker._service_rx = paused
        try:
            link.send(hw.stream_cmd(cps, True))
            pump(2.0)
            pending["s"] = pause_s
            pump(pause_s + 3.0)
            link.send(hw.stream_cmd(0, False))
            pump(1.0)
            st = link.board_stats(timeout=10.0)
        finally:
            snap = link.close()
            restore_board(args.port)
        lost = _lost_bytes(link, snap, st)
        results.append({"pause_s": pause_s, "bytes_during_pause": int(rate * pause_s), "lost_bytes": lost,
                        "seq_missing": st["frames_4000"] - len(link.seq),
                        "app_seq_missing": snap.get("seq_missing"),
                        "driver_errors": snap.get("driver_errors")})
    import app.serial_io.serial_worker as sw
    r.data.update(baud=baud, bytes_per_s=rate, requested_rx_buffer=sw.RX_DRIVER_BUFFER, pauses=results)
    lossless = [x["pause_s"] for x in results if x["lost_bytes"] == 0]
    lossy = [x for x in results if x["lost_bytes"] > 0]
    r.data["effective_buffer_bytes_at_least"] = int(rate * max(lossless)) if lossless else 0
    r.data["effective_buffer_bytes_below"] = int(rate * lossy[0]["pause_s"]) if lossy else None
    for x in results:
        r.checks.append(f"info pause {x['pause_s']:>4.1f}s ({x['bytes_during_pause']:,} B unread): "
                        f"lost {x['lost_bytes']:,} B, seq missing {x['seq_missing']}")
    # Acceptance: a 2 s reader stall (GC, CPU load, AV scan) at the rated
    # 2 Mbaud must cost nothing. Longer pauses are measured, not assumed.
    for x in results:
        if x["pause_s"] <= 2.0:
            r.check(x["lost_bytes"] == 0, f"no loss across a {x['pause_s']} s reader pause")
    for x in lossy:
        r.check(x["seq_missing"] > 0, f"loss after a {x['pause_s']} s pause is visible as a sequence gap")
    for x in results:
        # F12: the application itself reports what the board proves was lost
        # (frames lost at the very end of a run leave no later counter, so
        # the app can only be <= the board's count, never more).
        r.check(x["app_seq_missing"] is not None and x["app_seq_missing"] <= x["seq_missing"]
                and (x["seq_missing"] == 0) == (x["app_seq_missing"] == 0),
                f"pause {x['pause_s']} s: app detected {x['app_seq_missing']} missing, board proves {x['seq_missing']}")
    return r


def _burn(stop) -> None:
    while not stop.is_set():
        pass


def t_cpu_load(args, config) -> Result:
    """Every core busy in other processes while streaming at 2 Mbaud."""
    import multiprocessing as mp
    n = os.cpu_count() or 4
    stop = mp.get_context("spawn").Event()
    burners = [mp.get_context("spawn").Process(target=_burn, args=(stop,), daemon=True) for _ in range(n)]
    for b in burners:
        b.start()
    try:
        time.sleep(1.0)
        res = _stream("cpu_load_2000000", args, config, 2_000_000, args.stream_seconds, 0.8)
    finally:
        stop.set()
        for b in burners:
            b.join(5)
            if b.is_alive():
                b.terminate()
    res.data["busy_processes"] = n
    return res


def t_shutdown_under_traffic(args, config) -> Result:
    """Close the connection while the board streams at 2 Mbaud with raw
    capture on: no error, the capture file is complete and parseable."""
    from app.serial_logging.raw_capture import iter_raw_capture
    r = Result("shutdown_under_traffic")
    baud = 2_000_000
    prepare_board(args.port, baud)
    link = AppLink(args.port, baud, config).open()
    raw = Path(tempfile.mkdtemp(prefix="bh_hil_")) / "wire.bhraw"
    link.worker.start_raw_capture(raw, {"test": "shutdown"})
    link.send(hw.stream_cmd(int(0.8 * baud / 10 / hw.CYCLE_BYTES[True]), True))
    pump(3.0)
    t0 = time.monotonic()
    snap = link.close()                       # board still streaming
    close_s = time.monotonic() - t0
    r.check(close_s < 3.0, f"close returned in {close_s:.2f} s")
    r.check(not link.worker.isRunning(), "worker thread stopped")
    r.check(not link.errors, f"no worker errors {link.errors[:2]}")
    try:
        rx = sum(len(d) for direction, _t, d in iter_raw_capture(raw) if direction == 0)
        r.check(rx == snap["parser_bytes_in"],
                f"raw capture complete: {rx} RX bytes == parser bytes in {snap['parser_bytes_in']}")
    except Exception as exc:
        r.check(False, f"raw capture unreadable after close: {exc}")
    restore_board(args.port)                   # finds the board at 2 Mbaud, stops it
    r.check(True, "board recovered and back at 115200")
    return r


def t_seq_wraparound(args, config, cfg_dir: Path) -> Result:
    """The 32-bit sequence counter wraps 0xFFFFFFFF -> 0 inside a logged
    session: every value is decoded unsigned, logged once, in order."""
    import pandas as pd
    from app.serial_logging.session import SessionLog, SessionSettings, read_manifest
    r = Result("seq_wraparound")
    baud, cycles = 921600, 4000
    start = 0xFFFFFFFF - 1999
    prepare_board(args.port, baud)
    out = Path(tempfile.mkdtemp(prefix="bh_hil_wrap_")) / "session"
    link = AppLink(args.port, baud, config).open()
    session = SessionLog(out, config, SessionSettings(segment_seconds=1.5, fixed_step_s=0.1), config_source=cfg_dir)
    try:
        session.start()
        link.worker.set_session_sink(session)
        link.send(hw.command(hw.ID_SET_SEQ, struct.pack("<I", start)))
        pump(0.2)
        link.send(hw.burst_cmd(cycles))
        pump(10.0, lambda: link.good.get(0x4000, 0) >= cycles)
        pump(0.5)
        for _ in range(3):
            session.tick()
            pump(0.6)
        link.worker.set_session_sink(None)
        session.stop()
        r.check(session.await_finished(120), "session finished")
    finally:
        snap = link.close()
        restore_board(args.port)
    r.check(snap.get("seq_missing") == 0 and snap.get("seq_resets") == 0,
            f"F12: wrap is not a gap or reset (missing {snap.get('seq_missing')}, resets {snap.get('seq_resets')})")
    expect = [(start + i) & 0xFFFFFFFF for i in range(cycles)]
    r.check(link.seq == expect, f"worker saw {len(link.seq)} counters, wrapping at 0xFFFFFFFF -> 0")
    logged = []
    for seg in read_manifest(out)["segments"]:
        ev = pd.read_csv(out / seg["files"]["event_csv"])
        col = next(c for c in ev.columns if c.endswith("HIL Seq"))
        logged += ev[col].dropna().astype("int64").tolist()
    r.check(logged == expect, f"event log holds the {cycles} values exactly once, in order, unsigned")
    r.check(min(logged) == 0 and max(logged) == 0xFFFFFFFF, "both ends of the 32-bit range present")
    return r


def t_device_reset(args, config) -> Result:
    """Hardware reset of the target mid-stream (the ST-LINK VCP stays up,
    as a BMS rebooting behind a USB-UART adapter would)."""
    r = Result("device_reset")
    cli = hw.programmer_cli()
    if cli is None:
        r.check(False, "STM32_Programmer_CLI not found")
        return r
    prepare_board(args.port, 115200)
    link = AppLink(args.port, 115200, config).open()
    try:
        link.send(hw.stream_cmd(100, True))
        pump(2.0)
        before = link.good.get(0x4000, 0)
        p = subprocess.run([str(cli), "-c", "port=SWD", "mode=HOTPLUG", "-hardRst"],
                           capture_output=True, text=True, timeout=30)
        r.check(p.returncode == 0, f"target reset via SWD (exit {p.returncode})")
        pump(1.0)
        seq_at_reset = len(link.seq)
        link.send(hw.stream_cmd(100, True))   # firmware boots with streaming off
        pump(2.0)
        after = link.seq[seq_at_reset:]
        link.send(hw.stream_cmd(0, False))
        pump(0.3)
        r.check(before > 100, f"frames before reset: {before}")
        r.check(len(after) > 100, f"frames after reset: {len(after)}")
        r.check(bool(after) and after[0] < 50, f"sequence restarted after reboot (first {after[:1]})")
        r.check(link.worker.isRunning(), "worker still running")
        r.check(link.lost == 0, "no connection_lost (port never went away)")
        snap = link.worker.integrity_snapshot()
        r.check(snap.get("seq_resets") == 1 and snap.get("seq_missing") == 0,
                f"F12: the reboot is a counter reset, not loss (resets {snap.get('seq_resets')}, "
                f"missing {snap.get('seq_missing')})")
        torn = snap["frame_bytes_rejected"] + snap["discarded_bytes"]
        r.check(torn <= 2 * hw.CYCLE_BYTES[True], f"bytes lost to the torn frame at reset: {torn}")
        r.data.update(before=before, after=len(after), torn_bytes=torn)
    finally:
        link.close()
        restore_board(args.port)
    return r


def _session(name: str, args, config, cfg_dir: Path, baud: int, seconds: float, load: float) -> Result:
    """Full logging path: session log (event + fixed-step CSV segments,
    rotation, raw capture), then the Analysis Suite's SessionSource on
    the result — all checked against the board's counters."""
    import pandas as pd
    from app.serial_logging.raw_capture import rebuild_decoded_log
    from app.serial_logging.session import SessionLog, SessionSettings, read_manifest
    from app.serial_logging.session_analysis import SessionSource

    r = Result(name)
    prepare_board(args.port, baud)
    out = Path(tempfile.mkdtemp(prefix="bh_hil_session_")) / "session"
    # The production path: the worker writes frames to the session on its
    # own thread (PollingWorker.set_session_sink).
    link = AppLink(args.port, baud, config).open()

    class Hooks:
        def start(self, path, metadata):
            link.worker.start_raw_capture(path, metadata)

        def stop(self):
            return link.worker.stop_raw_capture()

        def rotate(self, path, metadata):
            return link.worker.rotate_raw_capture(path, metadata)

    warnings: List[str] = []
    seg_s = max(5.0, seconds / 4)
    session = SessionLog(out, config, SessionSettings(segment_seconds=seg_s, fixed_step_s=0.1),
                         config_source=cfg_dir, raw_capture=Hooks(), on_warning=warnings.append,
                         on_error=warnings.append)
    cps = max(1, int(load * baud / 10 / hw.CYCLE_BYTES[True]))
    try:
        session.start()
        link.worker.set_session_sink(session)
        link.send(hw.stream_cmd(cps, True))
        t_end = time.monotonic() + seconds
        while time.monotonic() < t_end:
            pump(min(1.0, t_end - time.monotonic()))
            session.set_integrity(link.worker.integrity_snapshot())
            session.tick()
        link.send(hw.stream_cmd(0, False))
        pump(0.5)
        st = link.board_stats()
        session.set_integrity(link.worker.integrity_snapshot())
        link.worker.set_session_sink(None)
        session.stop()
        r.check(session.await_finished(300), "segment finishers done")
    finally:
        snap = link.close()
        restore_board(args.port)

    check_accounting(r, link, snap, st, injected=False)
    check_seq(r, link.seq, st["frames_4000"])
    r.check(snap.get("session_log_errors") == 0 and snap.get("parse_errors") == 0,
            f"no session-log or parser errors ({snap.get('session_log_errors')}, {snap.get('parse_errors')})")
    m = read_manifest(out)
    segs = m["segments"]
    r.check(len(segs) >= int(seconds // seg_s), f"{len(segs)} segments (rotation every {seg_s:.0f}s)")
    r.check(all(s["status"] == "closed" for s in segs), "every segment closed cleanly")
    r.check(not warnings, f"no session warnings {warnings[:2]}")

    # Event log: every 0x4000 frame the board sent is a row with its seq.
    seq_logged: List[int] = []
    fixed_rows = 0
    for s in segs:
        ev = pd.read_csv(out / s["files"]["event_csv"])
        cols = [c for c in ev.columns if c.endswith("HIL Seq")]
        if cols:
            col = ev[cols[0]].dropna().astype("int64")
            seq_logged += col[col.diff().fillna(1) != 0].tolist()
        fixed_rows += len(pd.read_csv(out / s["files"]["fixed_csv"]))
    r.check(seq_logged == list(range(st["frames_4000"])),
            f"event log holds seq 0..{st['frames_4000'] - 1} exactly once ({len(seq_logged)} distinct)")
    expect_fixed = seconds / 0.1
    r.check(abs(fixed_rows - expect_fixed) <= 0.03 * expect_fixed + 15,
            f"fixed-step rows {fixed_rows} (~{expect_fixed:.0f} at 0.1 s)")
    leftovers = list(out.glob("*.partial")) + list(out.glob("*.tmp_*"))
    r.check(not leftovers, f"no temp files left {[p.name for p in leftovers[:3]]}")

    # Analysis Suite data source over the same session.
    src = SessionSource(out, "event")
    src.ensure_caches()
    seq_sig = next((n for n in src.signals() if n.endswith("HIL Seq")), None)
    r.check(seq_sig is not None, f"analysis sees signal {seq_sig!r}")
    stats = src.stats(seq_sig, 0.0, src.duration + 1.0) if seq_sig else None
    r.check(stats is not None and stats.min == 0 and stats.max == st["frames_4000"] - 1,
            f"analysis min/max {getattr(stats, 'min', None)}/{getattr(stats, 'max', None)} == 0/{st['frames_4000'] - 1}")
    r.check(stats is not None and stats.n == st["frames_4000"],
            f"analysis sample count {getattr(stats, 'n', None)} == {st['frames_4000']}")
    win = src.window([seq_sig], 0.0, src.duration + 1.0, max_points=2000) if seq_sig else None
    r.check(win is not None, "analysis overview window renders")
    fixed = SessionSource(out, "fixed")
    fixed.ensure_caches()
    r.check(any(n.endswith("HIL Seq") for n in fixed.signals()), "analysis opens the fixed-step log")

    # Lossless raw capture: the segment files together hold every received
    # byte, and parsing them end to end yields every frame the board sent.
    # (A per-segment rebuild can lose the one frame split across a file
    # boundary.)
    from app.protocol.packet_parser import create_parser
    from app.serial_logging.raw_capture import iter_raw_capture
    raws = [out / s["files"]["raw"] for s in segs if s["files"].get("raw")]
    r.check(len(raws) == len(segs), f"{len(raws)} raw capture files for {len(segs)} segments")
    parser = create_parser(config.protocol)
    rx_bytes = good = 0
    for path in raws:
        for direction, _t, d in iter_raw_capture(path):
            if direction == 0:
                rx_bytes += len(d)
                parser.feed(d)
                good += sum(1 for p in parser.extract_all() if p.ok and p.frame_id in TELEMETRY)
    r.check(rx_bytes == snap["parser_bytes_in"],
            f"raw capture RX bytes {rx_bytes} == parser bytes in {snap['parser_bytes_in']} (no gap at rotation)")
    logged = sum(st[STAT_KEY[f]] for f in TELEMETRY)
    r.check(good == logged, f"frames parsed from raw capture {good} == {logged} sent")
    rebuilt = sum(rebuild_decoded_log(p, config, p.with_suffix(".rebuilt.xlsx")) for p in raws)
    r.check(logged - rebuilt <= len(raws) - 1,
            f"per-segment rebuild {rebuilt} frames, short by {logged - rebuilt} <= {len(raws) - 1} boundaries")

    # Order and timestamps across rotation boundaries; xlsx = CSV; export.
    from openpyxl import load_workbook
    times = []
    xlsx_ok = True
    for s in segs:
        ev = pd.read_csv(out / s["files"]["event_csv"], usecols=["time_utc"])
        times += pd.to_datetime(ev["time_utc"], utc=True, format="ISO8601").astype("int64").tolist()
        wb = load_workbook(out / s["files"]["event_xlsx"], read_only=True)
        xlsx_rows = sum(1 for _ in wb["Data"].iter_rows()) - 1
        wb.close()
        xlsx_ok &= xlsx_rows == s["rows"]["event"] == len(ev)
    r.check(all(b >= a for a, b in zip(times, times[1:], strict=False)),
            "event timestamps never go backwards, across every rotation")
    r.check(xlsx_ok, "each segment's .xlsx has exactly the rows of its CSV and the manifest")
    export = out.parent / "export.csv"
    n_export = src.export_range([seq_sig], 0.0, src.duration + 1.0, export)
    exported = pd.read_csv(export)
    ecol = next(c for c in exported.columns if c.endswith("HIL Seq"))
    ex = exported[ecol].dropna().astype("int64")
    ex = ex[ex.diff().fillna(1) != 0].tolist()
    r.check(ex == list(range(st["frames_4000"])),
            f"Analysis Suite export: {n_export} rows, every seq once ({len(ex)} distinct)")

    r.data.update(folder=str(out), segments=len(segs), fixed_rows=fixed_rows, baud=baud,
                  cycles_per_s=cps, seconds=seconds)
    return r


def t_gui(args, config, cfg_dir: Path) -> Result:
    """The real MainWindow on the board: connect, stream at 921600 baud,
    log a session (event + fixed-step, rotating), stop, then open it in the
    Analysis Suite. Measures how late the GUI event loop runs under load."""
    import pandas as pd
    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtWidgets import QInputDialog

    import app.ui.analysis_suite as asu
    import app.ui.main_window as mw
    from app.serial_logging.session import SessionSettings, read_manifest

    r = Result("gui_end_to_end")
    baud, seconds = 921600, args.gui_seconds
    tmp = Path(tempfile.mkdtemp(prefix="bh_hil_gui_"))
    # Never touch the user's real settings.
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp / "ini"))
    mw.MainWindow._check_and_recover_temp_logs = lambda self: None
    mw.MainWindow._popup_warning = lambda self, *a, **k: None
    mw.MainWindow._popup_critical = lambda self, *a, **k: None
    prepare_board(args.port, baud)

    win = mw.MainWindow()
    win.show()
    replies: Dict[int, bytes] = {}
    seq: List[int] = []
    # perf_counter: time.monotonic() moves in ~15.6 ms steps on Windows,
    # which quantised every lateness value by up to that much.
    lag = {"max": 0.0, "n": 0, "over_100": 0, "spikes": [], "all": []}
    last = [time.perf_counter()]

    def tick() -> None:
        now = time.perf_counter()
        late = now - last[0] - 0.02
        last[0] = now
        lag["n"] += 1
        lag["all"].append(max(0.0, late))
        lag["max"] = max(lag["max"], late)
        lag["over_100"] += late > 0.1
        if late > 0.1:
            lag["spikes"].append((round(now - lag.get("t0", now), 2), round(late * 1000)))

    probe = QTimer()
    probe.setInterval(20)
    probe.timeout.connect(tick)

    # While the event loop is stalled, sample what the GUI thread is doing.
    import collections
    import threading
    import traceback
    gui_ident = threading.get_ident()
    stall_stacks: collections.Counter = collections.Counter()
    sampling = threading.Event()

    def sampler() -> None:
        while not sampling.wait(0.05):
            if probe.isActive() and time.perf_counter() - last[0] > 0.3:
                frame = sys._current_frames().get(gui_ident)
                if frame is not None:
                    stack = traceback.extract_stack(frame)[-6:]
                    stall_stacks[" <- ".join(f"{Path(f.filename).name}:{f.lineno}:{f.name}"
                                             for f in reversed(stack))] += 1

    sampler_thread = threading.Thread(target=sampler, daemon=True)
    sampler_thread.start()

    def tap(items) -> None:
        for p, *_rest in items:
            if p.ok and p.frame_id == 0x4000:
                seq.append(struct.unpack_from("<I", p.payload)[0])
            elif p.ok and p.frame_id in (hw.ID_STATS_REPLY,):
                replies[p.frame_id] = p.payload

    folder = tmp / "session"
    cps = int(0.6 * baud / 10 / hw.CYCLE_BYTES[True])
    try:
        win._load_config_from_path(cfg_dir, suppress_popups=True)
        pump(0.5)
        win._session_settings_from_qsettings = lambda: SessionSettings(segment_seconds=seconds / 3,
                                                                       fixed_step_s=0.1)
        r.check(win._attempt_connect(SerialSettings(port=args.port, baud_rate=baud)), "MainWindow connects")
        win._serial.packets_received.connect(tap)
        r.check(win._start_logging_file(folder), "logging session starts")
        pump(0.3)
        probe.start()
        last[0] = lag["t0"] = time.perf_counter()
        win._serial.enqueue_priority_tx(hw.stream_cmd(cps, True))
        pump(seconds)
        win._serial.enqueue_priority_tx(hw.stream_cmd(0, False))
        pump(0.8)
        probe.stop()
        sampling.set()
        win._serial.enqueue_priority_tx(hw.command(hw.ID_STATS))
        r.check(pump(3.0, lambda: hw.ID_STATS_REPLY in replies), "board stats via the GUI's worker")
        st = hw.parse_stats(replies[hw.ID_STATS_REPLY])
        session = win._session_log
        win._stop_logging()
        r.check(session is not None and session.await_finished(300), "session finished")
        pump(0.5)
    finally:
        try:
            win._disconnect(reason="HIL done")
        finally:
            win.close()
            pump(0.5)
            restore_board(args.port)

    r.data.update(cycles_per_s=cps, frames_per_s=cps * 4, seconds=seconds,
                  gui_max_lag_ms=round(lag["max"] * 1000, 1), gui_ticks=lag["n"],
                  gui_ticks_late_over_100ms=lag["over_100"], gui_spikes=lag["spikes"],
                  gui_stall_stacks=stall_stacks.most_common(8), board=st)
    r.check(seq == list(range(st["frames_4000"])),
            f"GUI worker delivered seq 0..{st['frames_4000'] - 1} exactly once ({len(seq)})")
    # Release gate (agreed 2026-10-17): p99 <= 50 ms and max <= 250 ms at the
    # rated 3,000 frames/s; this test runs 3,250.
    ordered = sorted(lag["all"])
    p99 = ordered[min(len(ordered) - 1, int(0.99 * len(ordered)))] if ordered else 0.0
    r.data["gui_p99_lag_ms"] = round(p99 * 1000, 1)
    r.check(p99 <= 0.05, f"GUI event loop p99 lag {p99 * 1000:.0f} ms <= 50 ms ({lag['n']} ticks of 20 ms)")
    r.check(lag["max"] <= 0.25, f"GUI event loop max lag {lag['max'] * 1000:.0f} ms <= 250 ms "
                                f"({lag['over_100']} of {lag['n']} ticks > 100 ms)")
    m = read_manifest(folder)
    segs = m["segments"]
    r.check(m["status"] == "closed" and all(x["status"] == "closed" for x in segs),
            f"session closed cleanly, {len(segs)} segments")
    logged: List[int] = []
    for x in segs:
        ev = pd.read_csv(folder / x["files"]["event_csv"])
        col = next(c for c in ev.columns if c.endswith("HIL Seq"))
        v = ev[col].dropna().astype("int64")
        logged += v[v.diff().fillna(1) != 0].tolist()
    r.check(logged == list(range(st["frames_4000"])),
            f"GUI session event log holds every seq exactly once ({len(logged)})")
    integ = segs[-1].get("integrity", {})
    r.data["last_segment_integrity"] = integ

    # Analysis Suite opens the session the GUI just wrote.
    asu.AnalysisSuiteWindow._popup_warning = lambda self, *a, **k: None
    QInputDialog.getItem = staticmethod(lambda *a, **k: ("Event log", True))
    aw = asu.AnalysisSuiteWindow()
    try:
        aw._open_logging_session(str(folder))
        r.check(pump(60, lambda: len(aw._logs) == 1), "Analysis Suite opens the session")
        entry = next(iter(aw._logs.values()))
        param = next(p for p in entry.available_params() if p.endswith("HIL Seq"))
        full = entry.range_stats(param, 0.0, entry.source.duration + 1)
        r.check(full["n"] == st["frames_4000"] and full["max"] == st["frames_4000"] - 1,
                f"Analysis Suite stats n={full['n']} max={full['max']} match the board")
    finally:
        aw.close()
        pump(0.3)
    return r


# ------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=None, help="ST-LINK VCP (auto-detected)")
    ap.add_argument("--ping", action="store_true", help="only check the board answers")
    ap.add_argument("--only", nargs="*", help="run only these tests")
    ap.add_argument("--stream-seconds", type=float, default=10.0)
    ap.add_argument("--poll-seconds", type=float, default=8.0)
    ap.add_argument("--burst-cycles", type=int, default=20000)
    ap.add_argument("--session-seconds", type=float, default=30.0)
    ap.add_argument("--gui-seconds", type=float, default=30.0)
    ap.add_argument("--rx-buffer", type=int, default=None,
                    help="override the driver receive-buffer request (bytes) for experiments")
    ap.add_argument("--pauses", type=float, nargs="*", default=[1.0, 2.0, 4.0, 8.0, 16.0],
                    help="reader pauses (s) for the reader_pause test")
    ap.add_argument("--soak-minutes", type=float, default=0.0, help="extra session soak at 921600 baud")
    ap.add_argument("--report", type=Path, default=ROOT / "artifacts" / "hil")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    if args.rx_buffer:
        import app.serial_io.serial_worker as sw
        sw.RX_DRIVER_BUFFER = args.rx_buffer
    args.port = args.port or hw.find_port()
    if not args.port:
        print("No ST-LINK virtual COM port found. Is the NUCLEO plugged in?")
        return 1
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication(sys.argv)

    cfg_dir = hw.hil_config_dir(Path(tempfile.mkdtemp(prefix="bh_hil_cfg_")) / "config")
    config = load_config(cfg_dir)
    S = args.stream_seconds
    tests: Dict[str, Callable[[], Result]] = {
        "ping": lambda: t_ping(args, config),
        "stream_115200": lambda: _stream("stream_115200", args, config, 115200, S, 0.9),
        "stream_921600": lambda: _stream("stream_921600", args, config, 921600, S, 0.8),
        "stream_2000000": lambda: _stream("stream_2000000", args, config, 2_000_000, S, 0.8),
        "inject_noise_corrupt": lambda: _stream("inject_noise_corrupt", args, config, 921600, S, 0.6,
                                                noise=7, corrupt=13),
        "burst": lambda: t_burst(args, config),
        "polling_sequential": lambda: _polling("polling_sequential", args, config, False),
        "polling_pipelined": lambda: _polling("polling_pipelined", args, config, True),
        "watchdog": lambda: t_watchdog(args, config),
        "device_reset": lambda: t_device_reset(args, config),
        "session_analysis": lambda: _session("session_analysis", args, config, cfg_dir, 921600,
                                             args.session_seconds, 0.6),
        "gui_end_to_end": lambda: t_gui(args, config, cfg_dir),
        "reader_pause": lambda: t_reader_pause(args, config),
        "cpu_load": lambda: t_cpu_load(args, config),
        "shutdown_under_traffic": lambda: t_shutdown_under_traffic(args, config),
        "seq_wraparound": lambda: t_seq_wraparound(args, config, cfg_dir),
        "smoke_headless": lambda: t_smoke(args, config),
    }
    if args.soak_minutes:
        tests["soak"] = lambda: _session("soak", args, config, cfg_dir, 921600, args.soak_minutes * 60, 0.5)
    if args.ping:
        names = ["ping"]
    elif args.only:
        names = args.only
    else:
        names = list(tests)

    print(f"HIL on {args.port}: {', '.join(names)}")
    results: List[Result] = []
    for name in names:
        t0 = time.monotonic()
        try:
            res = tests[name]()
        except Exception as exc:
            res = Result(name)
            res.check(False, f"raised {type(exc).__name__}: {exc}")
            res.data["traceback"] = traceback.format_exc()
            try:
                restore_board(args.port)
            except Exception:
                pass
        res.seconds = round(time.monotonic() - t0, 1)
        results.append(res)
        print(f"\n[{'PASS' if res.ok else 'FAIL'}] {name} ({res.seconds}s)")
        for c in res.checks:
            print("   " + c)
        if "traceback" in res.data:
            print(res.data["traceback"])

    failed = [r.name for r in results if not r.ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed" + (f"; failed: {failed}" if failed else ""))
    if not args.ping:
        args.report.mkdir(parents=True, exist_ok=True)
        path = args.report / f"hil_{datetime.now():%Y%m%d_%H%M%S}.json"
        path.write_text(json.dumps({"port": args.port, "results": [vars(r) for r in results]},
                                   indent=2, default=str), encoding="utf-8")
        print(f"report: {path}")
    return len(failed)


if __name__ == "__main__":
    sys.exit(main())
