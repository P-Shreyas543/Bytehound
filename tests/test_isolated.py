"""The helper process that runs segment finishing off the GUI's GIL."""

from __future__ import annotations

import os

import pytest

from app.serial_logging import _isolated


def _pid() -> int:
    return os.getpid()


def _boom() -> None:
    raise ValueError("bad input")


@pytest.fixture(autouse=True)
def _enabled():
    _isolated.set_enabled(True)
    yield
    _isolated.set_enabled(True)


def test_runs_in_another_process_and_reuses_it():
    first = _isolated.run_isolated(_pid)
    assert first != os.getpid()
    assert _isolated.run_isolated(_pid) == first


def test_exceptions_from_the_function_propagate():
    with pytest.raises(ValueError, match="bad input"):
        _isolated.run_isolated(_boom)


def test_disabled_runs_in_process():
    _isolated.set_enabled(False)
    assert _isolated.run_isolated(_pid) == os.getpid()


def test_falls_back_in_process_when_no_helper_can_start(monkeypatch):
    def no_pool():
        raise OSError("spawn blocked")

    monkeypatch.setattr(_isolated, "_get_pool", no_pool)
    assert _isolated.run_isolated(_pid) == os.getpid()


def test_compile_failure_in_helper_keeps_the_csv(tmp_path, monkeypatch):
    """finalize_temp_log must report, not raise, when the helper fails, so
    the CSV fallback still runs."""
    from app.serial_logging import decoded_logger as dl

    data = tmp_path / "seg.tmp_data"
    meta = tmp_path / "seg.tmp_meta"
    data.write_text("a,b\n1,2\n", encoding="utf-8")
    meta.write_text("{}", encoding="utf-8")

    def broken(*_a, **_k):
        raise RuntimeError("helper result could not be unpickled")

    monkeypatch.setattr(_isolated, "run_isolated", broken)
    exc = dl.finalize_temp_log(data, meta, tmp_path / "seg.xlsx", {}, keep_csv=True, isolate=True)
    assert isinstance(exc, RuntimeError)
    assert (tmp_path / "seg.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"


# ---------------------------------------------------------------------------
# Failure handling (task.md Phase 2)
# ---------------------------------------------------------------------------

import subprocess  # noqa: E402
import sys  # noqa: E402
import textwrap  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

from tests import isolated_jobs as jobs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


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
    h = k32.OpenProcess(0x00100000, False, pid)        # SYNCHRONIZE
    if not h:
        return False
    try:
        return k32.WaitForSingleObject(ctypes.c_void_p(h), 0) == 0x102   # WAIT_TIMEOUT
    finally:
        k32.CloseHandle(ctypes.c_void_p(h))


def test_hung_job_times_out_kills_the_helper_and_cleans_up(tmp_path):
    first = _isolated.run_isolated(jobs.pid)
    partial = tmp_path / "out.xlsx.partial"
    t0 = time.monotonic()
    with pytest.raises(TimeoutError):
        _isolated.run_isolated(jobs.sleep_then_write, 120, str(partial), timeout=2.0, leftovers=[partial])
    assert time.monotonic() - t0 < 20
    assert not partial.exists()                       # no half-written output left
    assert not _alive(first)                          # the hung helper was terminated
    second = _isolated.run_isolated(jobs.pid)         # and the next job gets a fresh one
    assert second not in (first, os.getpid())


def test_job_that_finishes_while_being_stopped_keeps_its_result(tmp_path, monkeypatch):
    """The timeout fires, but the job completes before the kill lands: its
    output is whole, so it is returned rather than reported as a timeout
    (found by the full suite: a segment marked failed beside a complete
    .xlsx)."""
    target = tmp_path / "out.xlsx"
    real_discard = _isolated._discard_pool

    def late_kill(pool, *, kill):
        deadline = time.monotonic() + 30
        while not target.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(1.0)                               # the result reaches the parent
        real_discard(pool, kill=kill)

    monkeypatch.setattr(_isolated, "_discard_pool", late_kill)
    assert _isolated.run_isolated(jobs.write_and_return, str(target), timeout=0.0001) == str(target)
    assert target.read_text(encoding="utf-8") == "whole"


def test_helper_crash_is_retried_once_in_a_fresh_helper(tmp_path):
    marker = tmp_path / "crashed"
    pid = _isolated.run_isolated(jobs.crash_once, str(marker))
    assert marker.exists() and pid != os.getpid()


def test_helper_that_keeps_dying_raises_and_never_runs_in_the_app(tmp_path):
    partial = tmp_path / "out.npz.partial"
    with pytest.raises(_isolated.HelperFailed):
        _isolated.run_isolated(jobs.crash, str(partial), leftovers=[partial])
    assert not partial.exists()
    assert _isolated.run_isolated(jobs.pid) != os.getpid()   # still usable afterwards


def test_unpicklable_result_is_an_error_not_a_hang():
    with pytest.raises(Exception) as info:
        _isolated.run_isolated(jobs.unpicklable_result, timeout=60)
    assert not isinstance(info.value, TimeoutError)
    assert _isolated.run_isolated(jobs.pid) != os.getpid()


def test_job_exception_keeps_the_same_helper():
    first = _isolated.run_isolated(jobs.pid)
    with pytest.raises(ValueError):
        _isolated.run_isolated(jobs.boom)
    assert _isolated.run_isolated(jobs.pid) == first


def test_timeout_scales_with_input_size(tmp_path):
    small, big = tmp_path / "a.csv", tmp_path / "b.csv"
    small.write_bytes(b"x")
    big.write_bytes(b"x" * 5_000_000)
    assert _isolated.timeout_for(small) == pytest.approx(_isolated.BASE_TIMEOUT_S, abs=0.1)
    assert _isolated.timeout_for(big) == pytest.approx(_isolated.BASE_TIMEOUT_S + 50.0, abs=0.1)
    assert _isolated.timeout_for(tmp_path / "missing.csv") == _isolated.BASE_TIMEOUT_S


def test_helper_exits_when_the_application_is_killed_mid_job(tmp_path):
    """No orphan: the helper is busy with a 120 s job when its parent dies."""
    script = tmp_path / "parent.py"
    pidfile = tmp_path / "helper.pid"
    script.write_text(textwrap.dedent(f"""
        import os, sys, threading, time
        sys.path.insert(0, {str(ROOT)!r})
        from app.serial_logging import _isolated
        from tests import isolated_jobs

        if __name__ == "__main__":   # spawn re-imports this script in the helper
            threading.Thread(target=_isolated.run_isolated,
                             args=(isolated_jobs.sleep_then_write, 120, {str(tmp_path / 'p')!r}),
                             daemon=True).start()
            for _ in range(300):
                pids = _isolated.helper_pids()
                if pids and os.path.exists({str(tmp_path / 'p')!r}):
                    break
                time.sleep(0.1)
            assert pids[0] != os.getpid()
            open({str(pidfile)!r}, "w").write(str(pids[0]))
            os._exit(9)          # abrupt: no atexit, no shutdown
    """), encoding="utf-8")
    # Output discarded: a surviving helper would hold a captured pipe open.
    subprocess.run([sys.executable, str(script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=120)
    helper = int(pidfile.read_text())
    deadline = time.monotonic() + 15
    while _alive(helper) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not _alive(helper), "helper outlived its killed parent"


def test_selftest_finish_passes_in_this_environment():
    """The check the frozen build runs (Bytehound.exe --selftest-finish)."""
    from app.serial_logging.selftest import selftest_finish

    assert selftest_finish(rows=200) == 0


def test_write_failure_in_the_helper_keeps_the_csv(tmp_path):
    """The helper cannot write the .xlsx (here: a directory is in the way,
    as with a permission or disk error): the error comes back and the
    streamed CSV is preserved, nothing is presented as finished."""
    from app.serial_logging import decoded_logger as dl

    data, meta = tmp_path / "seg.tmp_data", tmp_path / "seg.tmp_meta"
    data.write_text("a,b\n1,2\n", encoding="utf-8")
    meta.write_text("{}", encoding="utf-8")
    target = tmp_path / "seg.xlsx"
    target.mkdir()                                   # blocks the save
    exc = dl.finalize_temp_log(data, meta, target, {}, keep_csv=True, isolate=True)
    assert exc is not None and not isinstance(exc, TimeoutError)
    assert (tmp_path / "seg.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"
    assert not list(tmp_path.glob("*.partial"))


def test_idle_helper_exits_when_the_application_is_killed(tmp_path):
    """No orphan when the application dies after finishing work: an idle
    helper used to wait for its next job forever (found: one leftover
    helper per pytest run, which ends with TerminateProcess)."""
    script = tmp_path / "parent_idle.py"
    pidfile = tmp_path / "helper.pid"
    script.write_text(textwrap.dedent(f"""
        import os, sys
        sys.path.insert(0, {str(ROOT)!r})
        from app.serial_logging import _isolated
        from tests import isolated_jobs

        if __name__ == "__main__":   # spawn re-imports this script in the helper
            helper = _isolated.run_isolated(isolated_jobs.pid)    # helper started, now idle
            assert helper != os.getpid() and _isolated.helper_pids() == [helper]
            open({str(pidfile)!r}, "w").write(str(helper))
            if sys.platform == "win32":
                import ctypes
                k = ctypes.windll.kernel32
                k.GetCurrentProcess.restype = ctypes.c_void_p
                k.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
                k.TerminateProcess(k.GetCurrentProcess(), 9)
            os._exit(9)
    """), encoding="utf-8")
    # Output discarded: a surviving helper would hold a captured pipe open.
    subprocess.run([sys.executable, str(script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=120)
    helper = int(pidfile.read_text())
    deadline = time.monotonic() + 15
    while _alive(helper) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not _alive(helper), "idle helper outlived its killed parent"
