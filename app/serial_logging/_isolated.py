"""Run heavy pure-Python work in a helper process.

Finishing a session segment (compiling the .xlsx with openpyxl, building
the analysis cache) is seconds to minutes of CPU-bound Python. On a thread
it holds the GIL and the GUI stalls for hundreds of milliseconds at a time
while it runs (measured on the NUCLEO HIL rig: 150-800 ms event-loop lag
for ~3 s after every rotation). In a separate process it costs the GUI
nothing.

One spawned worker is shared by the whole application and started on first
use. Jobs run one at a time, so a job's timeout measures its own run and
not the wait behind another job.

Failure handling (task.md Phase 2):

* the job raises - the exception propagates to the caller;
* the helper dies (crash, killed, out of memory) - the job is retried once
  in a fresh helper, then ``HelperFailed`` is raised. It is *not* rerun in
  the application: an input that crashes the helper would take the live
  application, and its recording session, down with it;
* the job exceeds ``timeout`` - the helper is terminated and
  ``TimeoutError`` is raised; the next job gets a fresh helper;
* no helper can be started at all (spawn not possible here) - the job runs
  in-process, slower to the GUI but not lost.

A helper does not outlive the application, even when the application is
killed in the middle of a job (tests/test_isolated.py checks this on
Windows; no extra watchdog was needed).

On any failure the caller's ``leftovers`` (temp files the job may have half
written) are deleted, so an incomplete output never looks finished.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

_LOG = logging.getLogger(__name__)

_lock = threading.Lock()        # guards _pool
_job_lock = threading.Lock()    # one job at a time
_pool: Optional[ProcessPoolExecutor] = None
_enabled = True

# Generous per-job limit for segment finishing: 10 minutes plus 10 s per MB
# of input (a full 1,000,000-row hourly segment, ~120 MB of CSV, gets about
# 30 minutes; measured compile rates are well inside that).
BASE_TIMEOUT_S = 600.0
TIMEOUT_S_PER_MB = 10.0


class HelperFailed(RuntimeError):
    """The helper process died twice running the same job."""


def set_enabled(enabled: bool) -> None:
    """Tests and tools that must stay single-process can turn this off."""
    global _enabled
    _enabled = enabled


def timeout_for(*paths: Path) -> float:
    """Time limit for a job reading ``paths``."""
    size = 0
    for p in paths:
        try:
            size += os.path.getsize(p)
        except OSError:
            pass
    return BASE_TIMEOUT_S + TIMEOUT_S_PER_MB * size / 1e6


def _get_pool() -> ProcessPoolExecutor:
    global _pool
    with _lock:
        if _pool is None:
            _pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
        return _pool


def _discard_pool(pool: ProcessPoolExecutor, *, kill: bool) -> None:
    """Forget ``pool``; with ``kill`` terminate its worker first (a hung job).

    ProcessPoolExecutor has no public way to stop a running job on Python
    3.10, so the worker processes are terminated directly.
    """
    global _pool
    with _lock:
        if _pool is pool:
            _pool = None
    if kill:
        for proc in list(getattr(pool, "_processes", {}).values()):
            try:
                proc.terminate()
                proc.join(5)
            except Exception:
                pass
    try:
        pool.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass


def helper_pids() -> list:
    """PIDs of the live helper processes (diagnostics and tests)."""
    with _lock:
        pool = _pool
    if pool is None:
        return []
    return [p.pid for p in getattr(pool, "_processes", {}).values() if p.is_alive()]


def _remove(paths: Iterable[Path]) -> None:
    for p in paths:
        try:
            Path(p).unlink(missing_ok=True)
        except OSError as exc:
            _LOG.warning("Could not remove leftover %s: %s", p, exc)


def run_isolated(fn: Callable[..., Any], *args: Any, timeout: Optional[float] = None,
                 leftovers: Iterable[Path] = ()) -> Any:
    """``fn(*args)`` in the helper process (see the module docstring for
    failures). ``fn`` and its arguments must be picklable (module-level
    function, plain data and paths)."""
    leftovers = list(leftovers)
    if not _enabled:
        return fn(*args)
    with _job_lock:
        try:
            for attempt in (1, 2):
                try:
                    pool = _get_pool()
                    future = pool.submit(fn, *args)
                except Exception as exc:  # no process can be started here
                    _LOG.warning("Helper process unavailable (%s); running %s in-process", exc, fn.__name__)
                    return fn(*args)
                try:
                    return future.result(timeout=timeout)
                except FutureTimeout:
                    _LOG.error("Helper job %s exceeded %.0f s; terminating the helper", fn.__name__, timeout)
                    _discard_pool(pool, kill=True)
                    raise TimeoutError(f"{fn.__name__} did not finish within {timeout:.0f} s") from None
                except BrokenProcessPool as exc:
                    _discard_pool(pool, kill=True)
                    if attempt == 2:
                        raise HelperFailed(f"helper process died twice running {fn.__name__}: {exc}") from exc
                    _LOG.warning("Helper process died (%s); retrying %s in a fresh helper", exc, fn.__name__)
        except BaseException:
            _remove(leftovers)
            raise
    raise AssertionError("unreachable")  # pragma: no cover


def shutdown() -> None:
    """Stop the helper process (waits for work in progress)."""
    global _pool
    with _lock:
        pool, _pool = _pool, None
    if pool is not None:
        pool.shutdown(wait=True)
