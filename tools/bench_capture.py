"""High-rate capture benchmark — no hardware needed.

A child process plays the device: a TCP server that streams valid frames for
the bundled ``config_template`` at a fixed rate. The real ``MainWindow`` runs
offscreen in this process, connects over TCP, and optionally logs. While it
runs we measure:

* GUI-thread stall: a 5 ms QTimer records how late each tick fires. Anything
  that holds the GIL or the Qt event loop shows up here (p50 / p99 / max).
* Packets shown: frames that reached ``_handle_packet`` vs frames sent.
* Packets dropped by the UI queue (``_backpressure_dropped_count``).
* Peak working set (RSS) of this process, and of the capture process if any.

QSettings are redirected to a temp ini so the user's real settings are never
touched.

Run:  python tools/bench_capture.py [--rate 2000] [--seconds 10] [--log]
"""

from __future__ import annotations

import argparse
import ctypes
import json
import multiprocessing as mp
import os
import socket
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TEMPLATE = ROOT / "app" / "resources" / "config_template"


# ---------------------------------------------------------------------------
# Device simulator (child process)
# ---------------------------------------------------------------------------

def _frames_for_template() -> list[bytes]:
    from app.decoder.config_loader import load_config
    from app.protocol.packet_builder import build_packet

    cfg = load_config(TEMPLATE)
    out = []
    for fid, frame in cfg.frames.items():
        length = getattr(frame, "payload_length", None) or max(
            (s.start_byte + s.byte_length for s in cfg.signals_by_frame.get(fid, [])), default=0
        )
        payload = bytes((i * 7 + fid) & 0xFF for i in range(length))
        out.append(build_packet(cfg.protocol, fid, payload))
    return out


def _device_server(port_q, rate: int, seconds: float, sent_q) -> None:
    frames = _frames_for_template()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port_q.put(srv.getsockname()[1])
    conn, _ = srv.accept()
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    tick = 0.01
    per_tick = max(1, rate // 100)
    sent = 0
    t0 = time.perf_counter()
    next_t = t0
    try:
        while time.perf_counter() - t0 < seconds:
            burst = b"".join(frames[(sent + i) % len(frames)] for i in range(per_tick))
            conn.sendall(burst)
            sent += per_tick
            next_t += tick
            delay = next_t - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
    except OSError:
        pass
    sent_q.put(sent)
    time.sleep(1.0)
    conn.close()
    srv.close()


# ---------------------------------------------------------------------------
# Memory helpers (Windows working set; ru_maxrss elsewhere)
# ---------------------------------------------------------------------------

def peak_rss_mb(pid: int | None = None) -> float:
    if sys.platform == "win32":
        class PMC(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ]
        k32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        k32.OpenProcess.restype = ctypes.c_void_p
        if pid is None:
            h = ctypes.c_void_p(k32.GetCurrentProcess())
            close = False
        else:
            h = ctypes.c_void_p(k32.OpenProcess(0x1000 | 0x0010, False, pid))
            close = True
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        ok = psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
        if close:
            k32.CloseHandle(h)
        return pmc.PeakWorkingSetSize / 1e6 if ok else float("nan")
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e3


# ---------------------------------------------------------------------------
# Benchmark driver
# ---------------------------------------------------------------------------

def run(rate: int, seconds: float, log: bool, mode: str) -> dict:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    tmp = Path(tempfile.mkdtemp(prefix="bh_bench_"))

    import PySide6.QtCore as QtCore
    real_qsettings = QtCore.QSettings

    class IsolatedQSettings(real_qsettings):
        def __init__(self, *args, **kwargs):
            if len(args) <= 2 and all(isinstance(a, str) for a in args) and not (
                args and (args[0].endswith(".ini") or "/" in args[0] or "\\" in args[0])
            ):
                super().__init__(str(tmp / "settings.ini"), real_qsettings.Format.IniFormat)
            else:
                super().__init__(*args, **kwargs)

    QtCore.QSettings = IsolatedQSettings
    IsolatedQSettings(str(tmp / "settings.ini"), real_qsettings.Format.IniFormat).setValue(
        "capture/mode", mode
    )

    from PySide6.QtWidgets import QApplication
    from app.ui import main_window as mw
    from app.serial_io.serial_worker import SerialSettings

    mw.MainWindow._check_and_recover_temp_logs = lambda self, *a, **k: None
    app = QApplication.instance() or QApplication([])

    w = mw.MainWindow()
    w.show()
    w._load_config_from_path(TEMPLATE, suppress_popups=True)

    def pump(sec: float) -> None:
        end = time.perf_counter() + sec
        while time.perf_counter() < end:
            app.processEvents()
            time.sleep(0.001)

    pump(1.0)

    port_q, sent_q = mp.Queue(), mp.Queue()
    dev = mp.Process(target=_device_server, args=(port_q, rate, seconds, sent_q), daemon=True)
    dev.start()
    port = port_q.get(timeout=30)

    settings = SerialSettings(port="127.0.0.1", connection_type="tcp", host="127.0.0.1", port_num=port)
    if not w._attempt_connect(settings):
        raise SystemExit("connect failed")
    if log:
        w._start_logging_file(tmp / "bench_log.xlsx")

    # GUI stall probe.
    lateness: list[float] = []
    state = {"last": time.perf_counter()}
    probe = QtCore.QTimer()
    probe.setInterval(5)
    probe.setTimerType(QtCore.Qt.TimerType.PreciseTimer)

    def on_probe() -> None:
        now = time.perf_counter()
        lateness.append(max(0.0, (now - state["last"]) * 1000.0 - 5.0))
        state["last"] = now

    probe.timeout.connect(on_probe)
    start_count = w._packet_count
    state["last"] = time.perf_counter()
    probe.start()
    app_loop_until = time.perf_counter() + seconds + 1.5
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(int((app_loop_until - time.perf_counter()) * 1000), loop.quit)
    loop.exec()
    probe.stop()

    sent = sent_q.get(timeout=10)
    shown = w._packet_count - start_count
    dropped = getattr(w, "_backpressure_dropped_count", 0)
    capture_pid = getattr(getattr(w, "_serial", None), "child_pid", None)

    t_stop = time.perf_counter()
    if log:
        w._stop_logging()
    stop_s = time.perf_counter() - t_stop
    capture_rss = peak_rss_mb(capture_pid) if capture_pid else None
    w._disconnect(reason="bench done")
    dev.join(timeout=5)
    w.close()
    pump(0.3)

    lat_sorted = sorted(lateness)

    def p(q: float) -> float:
        return lat_sorted[min(len(lat_sorted) - 1, int(q * len(lat_sorted)))] if lat_sorted else 0.0
    return {
        "mode": mode,
        "rate_fps": rate,
        "seconds": seconds,
        "log": log,
        "sent": sent,
        "shown": shown,
        "dropped_ui": dropped,
        "stall_p50_ms": round(statistics.median(lateness), 2) if lateness else 0.0,
        "stall_p99_ms": round(p(0.99), 2),
        "stall_max_ms": round(max(lateness), 2) if lateness else 0.0,
        "gui_peak_rss_mb": round(peak_rss_mb(), 1),
        "capture_peak_rss_mb": round(capture_rss, 1) if capture_rss else None,
        "stop_logging_s": round(stop_s, 2) if log else None,
        "out_dir": str(tmp),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=int, default=2000, help="frames per second sent by the device")
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--log", action="store_true", help="decoded logging on during the run")
    ap.add_argument("--mode", default="thread", choices=["thread", "process"])
    args = ap.parse_args()
    print(json.dumps(run(args.rate, args.seconds, args.log, args.mode)))
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
