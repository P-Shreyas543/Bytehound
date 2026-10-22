"""Garbage-collector tuning for the GUI (live plot L2, 2026-10-22).

A full (generation-2) collection walks every container object in the
process: the Qt / pyqtgraph object graph, the loaded configuration and
everything created at start-up. Those objects live for the whole run, yet
every full collection scanned them again — 40-80 ms pauses that stop every
Python thread, including the capture worker. Measured at 3,000 frames/s with
15 signals plotted: p99 GUI latency 50-60 ms, and 48 ms with them frozen.

``refreeze()`` collects once and then moves every surviving object into the
permanent generation, so later collections only look at objects created
since. It is called when a configuration is activated: unfreezing first lets
the previous configuration (and anything else no longer referenced) be
freed, so nothing accumulates across configuration changes.
"""

from __future__ import annotations

import gc
import logging
import time

_LOG = logging.getLogger("bytehound.gc")


def refreeze() -> None:
    t0 = time.perf_counter()
    gc.unfreeze()
    gc.collect()
    gc.freeze()
    _LOG.debug("gc refreeze: %d objects frozen in %.1f ms", gc.get_freeze_count(),
               (time.perf_counter() - t0) * 1000)
