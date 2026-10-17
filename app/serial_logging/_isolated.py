"""Run heavy pure-Python work in a helper process.

Finishing a session segment (compiling the .xlsx with openpyxl, building
the analysis cache) is seconds to minutes of CPU-bound Python. On a thread
it holds the GIL and the GUI stalls for hundreds of milliseconds at a time
while it runs (measured on the NUCLEO HIL rig: 150-800 ms event-loop lag
for ~3 s after every rotation). In a separate process it costs the GUI
nothing.

One spawned worker is shared by the whole application and started on first
use. If a process cannot be used (spawn blocked, worker crashed) the call
runs in-process instead, so the work is never lost, only slower to the GUI.
"""

from __future__ import annotations

import logging
import multiprocessing
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from typing import Any, Callable, Optional

_LOG = logging.getLogger(__name__)

_lock = threading.Lock()
_pool: Optional[ProcessPoolExecutor] = None
_enabled = True


def set_enabled(enabled: bool) -> None:
    """Tests and tools that must stay single-process can turn this off."""
    global _enabled
    _enabled = enabled


def _get_pool() -> ProcessPoolExecutor:
    global _pool
    with _lock:
        if _pool is None:
            _pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
        return _pool


def _drop_pool(pool: ProcessPoolExecutor) -> None:
    global _pool
    with _lock:
        if _pool is pool:
            _pool = None
    try:
        pool.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass


def run_isolated(fn: Callable[..., Any], *args: Any) -> Any:
    """``fn(*args)`` in the helper process; exceptions raised by ``fn``
    propagate. ``fn`` and its arguments must be picklable (module-level
    function, plain data and paths)."""
    if not _enabled:
        return fn(*args)
    try:
        pool = _get_pool()
        future = pool.submit(fn, *args)
    except Exception as exc:  # spawn not possible here
        _LOG.warning("Helper process unavailable (%s); running %s in-process", exc, fn.__name__)
        return fn(*args)
    try:
        return future.result()
    except BrokenProcessPool as exc:
        _LOG.warning("Helper process died (%s); running %s in-process", exc, fn.__name__)
        _drop_pool(pool)
        return fn(*args)


def shutdown() -> None:
    """Stop the helper process (waits for work in progress)."""
    global _pool
    with _lock:
        pool, _pool = _pool, None
    if pool is not None:
        pool.shutdown(wait=True)
