"""Application exit paths with a live logging session (task.md Phase 4).

Runs the real entry point (``app.main.main``) in a child process with
isolated settings. The child connects to a loopback device, records a
session that rotates every 2 s, and then either

* ``normal``: closes the main window (answering the "stop logging?" prompt
  with Yes), or
* ``kill``: ends itself with TerminateProcess / os._exit mid-session.

The parent then checks the exit code, that no Bytehound child process is
left behind, and the session on disk; for ``kill`` it runs crash recovery
and checks that recovery finished the session without altering any file
that was already complete.

  python tools/exit_check.py --mode normal --runs 5
  python tools/exit_check.py --mode kill --runs 3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CHILD = r'''
import os, sys, multiprocessing as mp
sys.path.insert(0, {root!r})
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from tools.bench_capture import _device_server

def main():
    from pathlib import Path
    from PySide6.QtCore import QSettings, QTimer
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, {ini!r})
    from PySide6.QtWidgets import QMessageBox
    import app.ui.main_window as mw
    from app.serial_io.serial_worker import SerialSettings
    from app.serial_logging.session import SessionSettings

    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    mw.MainWindow._check_and_recover_temp_logs = lambda self, *a, **k: None
    mw.MainWindow._popup_warning = lambda self, *a, **k: None
    mw.MainWindow._popup_critical = lambda self, *a, **k: None
    port_q, sent_q = mp.Queue(), mp.Queue()
    dev = mp.Process(target=_device_server, args=(port_q, 2000, 30.0, sent_q), daemon=True)
    dev.start()
    port = port_q.get(timeout=30)
    orig_init = mw.MainWindow.__init__

    def init(self, *a, **k):
        orig_init(self, *a, **k)

        def go():
            self._load_config_from_path(Path({template!r}), suppress_popups=True)
            self._session_settings_from_qsettings = lambda: SessionSettings(segment_seconds=2.0, fixed_step_s=0.1)
            assert self._attempt_connect(SerialSettings(port="127.0.0.1", connection_type="tcp",
                                                        host="127.0.0.1", port_num=port))
            assert self._start_logging_file(Path({session!r}))
            QTimer.singleShot(int({seconds} * 1000), finish)

        def finish():
            if {mode!r} == "normal":
                self.close()
                return
            if sys.platform == "win32":
                import ctypes
                k = ctypes.windll.kernel32
                k.GetCurrentProcess.restype = ctypes.c_void_p
                k.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
                k.TerminateProcess(k.GetCurrentProcess(), 99)
            os._exit(99)

        QTimer.singleShot(500, go)

    mw.MainWindow.__init__ = init
    import app.main
    return app.main.main([])

if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
'''


def _children_of(pid: int) -> list:
    """All live descendants of ``pid`` (Windows; [] elsewhere). A venv's
    python.exe is a launcher that starts the real interpreter as its child,
    so spawned helpers are grandchildren of the application process."""
    if sys.platform != "win32":
        return []
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-CimInstance Win32_Process | ForEach-Object { \"$($_.ProcessId) $($_.ParentProcessId)\" }"],
                         capture_output=True, text=True)
    parent_of = {}
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and all(x.isdigit() for x in parts):
            parent_of[int(parts[0])] = int(parts[1])
    found, frontier = set(), {pid}
    while frontier:
        nxt = {c for c, par in parent_of.items() if par in frontier and c not in found and c != pid}
        found |= nxt
        frontier = nxt
    return sorted(found)


def _alive(pid: int) -> bool:
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = ctypes.c_void_p
    h = k32.OpenProcess(0x00100000, False, pid)
    if not h:
        return False
    try:
        return k32.WaitForSingleObject(ctypes.c_void_p(h), 0) == 0x102
    finally:
        k32.CloseHandle(ctypes.c_void_p(h))


def _hashes(folder: Path) -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.iterdir() if p.is_file() and not p.name.endswith((".partial", ".json"))}


def run_once(mode: str, seconds: float) -> dict:
    from app.serial_logging.session import read_manifest, recover_session

    tmp = Path(tempfile.mkdtemp(prefix=f"bh_exit_{mode}_"))
    session = tmp / "session"
    script = tmp / "child.py"
    script.write_text(CHILD.format(root=str(ROOT), ini=str(tmp / "ini"), session=str(session),
                                   template=str(ROOT / "app" / "resources" / "config_template"),
                                   seconds=seconds, mode=mode), encoding="utf-8")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    proc = subprocess.Popen([sys.executable, str(script)], env=env, stdout=subprocess.DEVNULL,
                            stderr=open(tmp / "child.err", "w"))
    kids = []
    end = time.monotonic() + seconds + 120
    while proc.poll() is None and time.monotonic() < end:
        kids = sorted(set(kids) | set(_children_of(proc.pid)))
        time.sleep(0.5)
    if proc.poll() is None:
        proc.kill()
    code = proc.wait()
    deadline = time.monotonic() + 15
    while any(_alive(k) for k in kids) and time.monotonic() < deadline:
        time.sleep(0.5)
    left = [k for k in kids if _alive(k)]
    r = {"mode": mode, "exit_code": code, "children_seen": len(kids), "children_left": left,
         "stderr_tail": (tmp / "child.err").read_text(encoding="utf-8", errors="replace")[-600:],
         "folder": str(session), "problems": []}
    expected_code = 0 if mode == "normal" else 99
    if code != expected_code:
        r["problems"].append(f"exit code {code}, expected {expected_code}")
    if left:
        r["problems"].append(f"{len(left)} child process(es) left running: {left}")
    if not (session / "session.json").exists():
        r["problems"].append("no session.json")
        return r
    m = read_manifest(session)
    r["status_on_disk"] = m["status"]
    if mode == "normal":
        if m["status"] != "closed" or any(s["status"] != "closed" for s in m["segments"]):
            r["problems"].append(f"session {m['status']}, segments {[s['status'] for s in m['segments']]}")
    else:
        if m["status"] not in ("recording", "closing"):
            r["problems"].append(f"killed session says {m['status']}")
        done_before = {s["index"]: s for s in m["segments"] if s["status"] == "closed"}
        before = _hashes(session)
        recovered = recover_session(session)
        m2 = read_manifest(session)
        r["recovered"] = recovered
        r["status_after_recovery"] = m2["status"]
        after = _hashes(session)
        changed = sorted(n for n in before if n in after and before[n] != after[n])
        # A closed segment's files are final; recovery may only add files.
        closed_files = {f for s in done_before.values() for f in s["files"].values()}
        if any(n in closed_files for n in changed):
            r["problems"].append(f"recovery changed finished files: {changed}")
        if not recovered or m2["status"] != "recovered":
            r["problems"].append(f"recovery: {recovered}, status {m2['status']}")
        bad = [s["index"] for s in m2["segments"] if s["status"] not in ("closed", "recovered")]
        if bad:
            r["problems"].append(f"segments not finished after recovery: {bad}")
        r["segments"] = len(m2["segments"])
    if list(session.glob("*.partial")) and mode == "normal":
        r["problems"].append("temp .partial files left")
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["normal", "kill"], default="normal")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--seconds", type=float, default=7.0)
    args = ap.parse_args()
    failed = 0
    for i in range(args.runs):
        r = run_once(args.mode, args.seconds)
        ok = not r["problems"]
        failed += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {args.mode} run {i + 1}: exit {r['exit_code']}, "
              f"{r['children_seen']} child process(es), left {r['children_left']}, "
              f"disk status {r.get('status_on_disk')}"
              + (f", after recovery {r.get('status_after_recovery')} ({r.get('segments')} segments)"
                 if args.mode == "kill" else ""))
        for p in r["problems"]:
            print(f"     - {p}")
        if r["problems"] and r["stderr_tail"].strip():
            print("     stderr: " + r["stderr_tail"].strip().replace("\n", "\n             "))
        out = ROOT / "artifacts" / "exit_check"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"exit_{args.mode}_{time.strftime('%Y%m%d_%H%M%S')}_{i + 1}.json").write_text(
            json.dumps(r, indent=1), encoding="utf-8")
    return failed


if __name__ == "__main__":
    sys.exit(main())
