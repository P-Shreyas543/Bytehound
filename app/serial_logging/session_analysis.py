"""Fast, exact analysis of long logging sessions (Plane.md Part B).

A month of 10 Hz data from 200 signals is ~31 GB of CSV — far too much to
read for every zoom or statistic. Each closed segment therefore gets a
lossless, compressed **analysis cache** next to its CSV::

    seg_NNNN_event_analysis.npz
      t                     row times, seconds since the session start (float64)
      c/<signal>            full-resolution values (float64, NaN = no value)
      L10/b, L60/b, L600/b  bucket index (bucket = floor(t / L))
      L10/<signal>/{n,mean,m2,min,max}   per-bucket count, mean, sum of squared
                            deviations (for exact merged std), min, max
      q/<signal>            101 quantiles of the segment (for long-range
                            percentile estimates) and q/<signal>/n

Arrays are read lazily, one signal at a time. :class:`SessionSource` serves:

* :meth:`window` — data to draw a time range: full resolution when it is small
  enough, otherwise a per-bucket min/max envelope (spikes stay visible);
* :meth:`value_at` — the full-resolution value at a time (cursors, hover);
* :meth:`stats` — min / max / mean / std / n that are **exact** for any range
  (bucket aggregates are exact, edge buckets read full resolution), with
  median / P5 / P95 exact for ranges up to :data:`FULL_RES_LIMIT` rows and
  estimated from per-segment quantiles (``approx_percentiles``) beyond that;
* :meth:`export_range` — full-resolution CSV (and .xlsx) of any range.
"""

from __future__ import annotations

import csv
import logging
import math
import threading
import zipfile
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .session import read_manifest

_LOG = logging.getLogger("bytehound.serial_logging.session_analysis")

LEVELS = (10, 60, 600)        # summary bucket sizes in seconds
FULL_RES_LIMIT = 400_000      # rows: up to this a window / stats use full resolution
QUANTILES = np.linspace(0, 100, 101)
_CACHE_SUFFIX = "_analysis.npz"
_SUMMARY_SUFFIX = "_summary.npz"
_AGG_KEYS = ("n", "mean", "m2", "min", "max")
_NON_SIGNAL = {"time_utc", "time_local", "tick", "elapsed_s", "stale_signals"}


# ---------------------------------------------------------------------------
# Building the per-segment cache
# ---------------------------------------------------------------------------

def _is_signal_column(name: str) -> bool:
    return not (
        name in _NON_SIGNAL
        or name.endswith(".elapsed_ms")
        or name.endswith(".frame_id")
        or name.endswith(".age_ms")
        or name.endswith(".label")
    )


def _parse_times(series, session_start: float) -> np.ndarray:
    import pandas as pd
    ts = pd.to_datetime(series, utc=True, errors="coerce", format="ISO8601")
    epoch = ts.astype("int64").to_numpy(dtype=np.float64) / 1e9
    epoch[ts.isna().to_numpy()] = np.nan
    return epoch - session_start


def _bucket_aggregates(t: np.ndarray, y: np.ndarray, level: int) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """Per-bucket n / mean / m2 / min / max of ``y`` (NaN ignored)."""
    b = np.floor(t / level).astype(np.int64)
    uniq, start = np.unique(b, return_index=True)
    valid = ~np.isnan(y)
    yz = np.where(valid, y, 0.0)
    n = np.add.reduceat(valid.astype(np.int64), start)
    s = np.add.reduceat(yz, start)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(n > 0, s / np.maximum(n, 1), np.nan)
    dev = np.where(valid, y - np.repeat(mean, np.diff(np.append(start, len(y)))), 0.0)
    m2 = np.add.reduceat(dev * dev, start)
    mn = np.fmin.reduceat(np.where(valid, y, np.inf), start)
    mx = np.fmax.reduceat(np.where(valid, y, -np.inf), start)
    mn[n == 0] = np.nan
    mx[n == 0] = np.nan
    return uniq, {"n": n, "mean": mean, "m2": m2, "min": mn, "max": mx}


def build_segment_cache(csv_path: Path, session_start_epoch: float, out_path: Optional[Path] = None) -> Path:
    """Read one segment CSV and write its analysis cache (atomic)."""
    import pandas as pd

    csv_path = Path(csv_path)
    out = Path(out_path) if out_path else csv_path.with_name(csv_path.stem + _CACHE_SUFFIX)
    df = pd.read_csv(csv_path, low_memory=False)
    if "time_utc" in df.columns:
        t = _parse_times(df["time_utc"], session_start_epoch)
    elif "elapsed_s" in df.columns:
        t = pd.to_numeric(df["elapsed_s"], errors="coerce").to_numpy(dtype=np.float64)
    else:
        raise ValueError(f"{csv_path.name}: no time_utc / elapsed_s column")
    keep = ~np.isnan(t)
    order = np.argsort(t[keep], kind="stable")
    t = t[keep][order]
    arrays: Dict[str, np.ndarray] = {"t": t}
    names: List[str] = []
    for col in df.columns:
        if not _is_signal_column(str(col)):
            continue
        y = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=np.float64)[keep][order]
        if y.size and np.all(np.isnan(y)):
            continue
        name = str(col)
        names.append(name)
        arrays[f"c/{name}"] = y
        for level in LEVELS:
            b, agg = _bucket_aggregates(t, y, level) if t.size else (np.zeros(0, np.int64), {})
            arrays[f"L{level}/b"] = b
            for k, v in agg.items():
                arrays[f"L{level}/{name}/{k}"] = v
        finite = y[~np.isnan(y)]
        arrays[f"q/{name}"] = np.percentile(finite, QUANTILES) if finite.size else np.full(101, np.nan)
        arrays[f"q/{name}/n"] = np.array([finite.size], dtype=np.int64)
    if t.size == 0:
        for level in LEVELS:
            arrays[f"L{level}/b"] = np.zeros(0, np.int64)
    arrays["signals"] = np.array(names, dtype=object)
    tmp = out.with_name(out.name + ".partial")
    with tmp.open("wb") as fp:
        np.savez_compressed(fp, **arrays)
    tmp.replace(out)
    return out


# ---------------------------------------------------------------------------
# Reading a session
# ---------------------------------------------------------------------------

@dataclass
class SegmentInfo:
    index: int
    csv: Path
    cache: Path
    t0: float          # seconds since session start
    t1: float
    rows: int


@dataclass
class Window:
    x: np.ndarray
    y: Dict[str, np.ndarray]
    level: int         # 0 = full resolution, else bucket size in seconds
    t0: float
    t1: float


@dataclass
class RangeStats:
    n: int
    min: float
    max: float
    mean: float
    std: float
    median: float
    p5: float
    p95: float
    approx_percentiles: bool


def _iso_to_epoch(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    return datetime.fromisoformat(str(text)).timestamp()


class SessionSource:
    """Read-only, thread-safe access to one session's data at any scale.

    Reads come from three places, cheapest first:

    * the session summary (``<kind>_summary.npz``): the coarsest bucket level
      merged across all segments plus every segment's quantile sketch — one
      file serves a whole-session overview and long-range percentiles;
    * per-segment caches: finer bucket levels and full-resolution rows, only
      for the segments a request overlaps;
    * an in-memory LRU of arrays already read.
    """

    def __init__(self, folder: Path, kind: str = "event", *, cache_capacity: int = 64) -> None:
        self.folder = Path(folder)
        self.kind = kind
        self.manifest = read_manifest(self.folder)
        start = _iso_to_epoch(self.manifest.get("started_utc"))
        if start is None:
            raise ValueError(f"{self.folder}: manifest has no start time")
        self.start_epoch = start
        self.segments: List[SegmentInfo] = []
        for seg in self.manifest.get("segments", []):
            name = seg.get("files", {}).get(f"{kind}_csv")
            if not name or not (self.folder / name).exists():
                continue
            csv_path = self.folder / name
            t0 = (_iso_to_epoch(seg.get("started_utc")) or start) - start
            t1e = _iso_to_epoch(seg.get("ended_utc"))
            t1 = (t1e - start) if t1e is not None else t0
            self.segments.append(SegmentInfo(
                int(seg["index"]), csv_path, csv_path.with_name(csv_path.stem + _CACHE_SUFFIX),
                t0, t1, int((seg.get("rows") or {}).get(kind, 0)),
            ))
        self.gaps: List[Tuple[float, float]] = []
        for gap in self.manifest.get("gaps", []):
            g0, g1 = _iso_to_epoch(gap.get("start_utc")), _iso_to_epoch(gap.get("end_utc"))
            if g0 is not None and g1 is not None:
                self.gaps.append((g0 - start, g1 - start))
        self.summary_path = self.folder / f"{kind}{_SUMMARY_SUFFIX}"
        self._lock = threading.Lock()
        self._lru: "OrderedDict[Tuple[int, str], np.ndarray]" = OrderedDict()
        self._capacity = cache_capacity
        self._signals: Optional[List[str]] = None
        self._summary: Dict[str, np.ndarray] = {}
        self._summary_keys: Optional[set] = None
        self._summary_segments: List[int] = []

    # -- caches --------------------------------------------------------------

    def missing_caches(self) -> List[SegmentInfo]:
        return [s for s in self.segments if not s.cache.exists()]

    def ensure_caches(self, progress: Optional[Callable[[int, int], None]] = None) -> None:
        """Build analysis caches for segments that have none (older or
        recovered sessions), then the session summary. Writes next to the
        CSVs; ``progress(done, total)`` covers both steps."""
        todo = self.missing_caches()
        for i, seg in enumerate(todo):
            build_segment_cache(seg.csv, self.start_epoch, seg.cache)
            if progress:
                progress(i + 1, len(todo) + 1)
        self._fix_segment_bounds()
        self.ensure_summary()
        if progress:
            progress(len(todo) + 1, len(todo) + 1)

    def _fix_segment_bounds(self) -> None:
        """Use the actual first/last row time where the manifest is vague
        (recovered or still-open segments); complete entries are trusted."""
        for seg in self.segments:
            if seg.cache.exists() and (seg.rows <= 0 or seg.t1 <= seg.t0):
                t = self._array(seg, "t")
                if t.size:
                    seg.t0 = min(seg.t0, float(t[0]))
                    seg.t1 = max(seg.t1, float(t[-1]))
                    seg.rows = int(t.size)

    def _arrays(self, seg: SegmentInfo, keys: Sequence[str]) -> Dict[str, np.ndarray]:
        """Several arrays of one segment cache, opening the file at most once."""
        out: Dict[str, np.ndarray] = {}
        missing: List[str] = []
        with self._lock:
            for key in keys:
                arr = self._lru.get((seg.index, key))
                if arr is None:
                    missing.append(key)
                else:
                    self._lru.move_to_end((seg.index, key))
                    out[key] = arr
        if missing:
            try:
                with np.load(seg.cache, allow_pickle=True) as z:
                    files = set(z.files)
                    loaded = {k: (z[k] if k in files else np.zeros(0)) for k in missing}
            except (OSError, zipfile.BadZipFile, ValueError) as exc:
                raise OSError(f"Cannot read {seg.cache.name}: {exc}") from exc
            with self._lock:
                for k, arr in loaded.items():
                    self._lru[(seg.index, k)] = arr
                while len(self._lru) > self._capacity:
                    self._lru.popitem(last=False)
            out.update(loaded)
        return out

    def _array(self, seg: SegmentInfo, key: str) -> np.ndarray:
        return self._arrays(seg, [key])[key]

    # -- session summary -----------------------------------------------------

    def ensure_summary(self) -> None:
        """Load the session summary, extending it with segments added since
        it was written, or build it. Persisted when the folder is writable."""
        have = [s for s in self.segments if s.cache.exists()]
        wanted = [s.index for s in have]
        existing: Dict[str, np.ndarray] = {}
        if self.summary_path.exists():
            try:
                with np.load(self.summary_path, allow_pickle=True) as z:
                    existing = {k: z[k] for k in z.files}
            except (OSError, zipfile.BadZipFile, ValueError):
                existing = {}
        done = [int(i) for i in existing.get("segments", np.zeros(0, np.int64)).tolist()]
        if done == wanted:
            self._set_summary(existing)
            return
        if done and done == wanted[:len(done)]:
            new = [s for s in have if s.index not in set(done)]
            base = existing
        else:
            new, base = have, {}
        merged = self._summarise(new, base)
        self._set_summary(merged)
        try:
            tmp = self.summary_path.with_name(self.summary_path.name + ".partial")
            with tmp.open("wb") as fp:
                np.savez_compressed(fp, **merged)
            tmp.replace(self.summary_path)
        except OSError as exc:
            _LOG.warning("Session summary not saved (%s); kept in memory", exc)

    def _set_summary(self, data: Dict[str, np.ndarray]) -> None:
        with self._lock:
            self._summary = data
            self._summary_segments = [int(i) for i in data.get("segments", np.zeros(0)).tolist()]

    def _summarise(self, segs: List[SegmentInfo], base: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        level = LEVELS[-1]
        names: List[str] = [str(n) for n in base.get("signals", np.zeros(0, dtype=object)).tolist()]
        for s in segs:
            for n in self._array(s, "signals").tolist():
                if n not in names:
                    names.append(n)
        out: Dict[str, np.ndarray] = {
            "signals": np.array(names, dtype=object),
            "segments": np.concatenate([base.get("segments", np.zeros(0, np.int64)),
                                        np.array([s.index for s in segs], dtype=np.int64)]),
        }
        per_seg: List[Dict[str, np.ndarray]] = []
        for s in segs:
            keys = [f"L{level}/b"]
            for n in names:
                keys += [f"L{level}/{n}/{k}" for k in _AGG_KEYS] + [f"q/{n}", f"q/{n}/n"]
            per_seg.append(self._arrays(s, keys))
        nseg_old = len(base.get("segments", []))
        for n in names:
            parts = []
            if f"S/{n}/b" in base:
                parts.append({k: base[f"S/{n}/{k}"] for k in ("b",) + _AGG_KEYS})
            for a in per_seg:
                b = a[f"L{level}/b"]
                if a[f"L{level}/{n}/n"].size:
                    parts.append({"b": b, **{k: a[f"L{level}/{n}/{k}"] for k in _AGG_KEYS}})
            merged = _merge_bucket_sets(parts)
            for k, v in merged.items():
                out[f"S/{n}/{k}"] = v
            q_old = base.get(f"Q/{n}", np.full((nseg_old, 101), np.nan))
            qn_old = base.get(f"Q/{n}/n", np.zeros(nseg_old, np.int64))
            q_new = np.array([a[f"q/{n}"] if a[f"q/{n}"].size else np.full(101, np.nan) for a in per_seg]).reshape(-1, 101)
            qn_new = np.array([int(a[f"q/{n}/n"][0]) if a[f"q/{n}/n"].size else 0 for a in per_seg], dtype=np.int64)
            out[f"Q/{n}"] = np.vstack([q_old.reshape(-1, 101), q_new]) if q_new.size or q_old.size else np.zeros((0, 101))
            out[f"Q/{n}/n"] = np.concatenate([qn_old, qn_new])
        return out

    def _summary_array(self, key: str) -> np.ndarray:
        with self._lock:
            arr = self._summary.get(key)
        return arr if arr is not None else np.zeros(0)

    # -- metadata --------------------------------------------------------------

    def signals(self) -> List[str]:
        if self._signals is None:
            names = [str(n) for n in self._summary_array("signals").tolist()]
            if not names:
                for seg in self.segments:
                    if seg.cache.exists():
                        for n in self._array(seg, "signals").tolist():
                            if n not in names:
                                names.append(n)
            self._signals = names
        return list(self._signals)

    @property
    def duration(self) -> float:
        return max((s.t1 for s in self.segments), default=0.0)

    def _overlapping(self, t0: float, t1: float) -> List[SegmentInfo]:
        return [s for s in self.segments if s.t1 >= t0 and s.t0 <= t1 and s.cache.exists()]

    def rows_in(self, t0: float, t1: float) -> int:
        total = 0.0
        for s in self._overlapping(t0, t1):
            span = max(s.t1 - s.t0, 1e-9)
            frac = (min(s.t1, t1) - max(s.t0, t0)) / span
            total += s.rows * max(0.0, min(1.0, frac))
        return int(total)

    # -- bucket aggregates ---------------------------------------------------

    def _buckets(self, param: str, level: int, lo_b: int, hi_b: int) -> Dict[str, np.ndarray]:
        """Merged aggregates of buckets lo_b..hi_b (inclusive) at ``level``."""
        if level == LEVELS[-1] and self._summary_segments:
            b = self._summary_array(f"S/{param}/b")
            sel = (b >= lo_b) & (b <= hi_b)
            return {"b": b[sel], **{k: self._summary_array(f"S/{param}/{k}")[sel] for k in _AGG_KEYS}}
        parts = []
        for s in self._overlapping(lo_b * level, (hi_b + 1) * level):
            a = self._arrays(s, [f"L{level}/b"] + [f"L{level}/{param}/{k}" for k in _AGG_KEYS])
            b = a[f"L{level}/b"]
            if a[f"L{level}/{param}/n"].size == 0:
                continue
            sel = (b >= lo_b) & (b <= hi_b)
            parts.append({"b": b[sel], **{k: a[f"L{level}/{param}/{k}"][sel] for k in _AGG_KEYS}})
        return _merge_bucket_sets(parts)

    # -- drawing -----------------------------------------------------------------

    def choose_level(self, t0: float, t1: float, max_points: int = 4000) -> int:
        if self.rows_in(t0, t1) <= FULL_RES_LIMIT:
            return 0
        for level in LEVELS:
            if (t1 - t0) / level <= max_points:
                return level
        return LEVELS[-1]

    def window(self, params: Sequence[str], t0: float, t1: float, *, max_points: int = 4000,
               level: Optional[int] = None) -> Window:
        """Data to draw [t0, t1]. ``level`` 0 = full resolution; otherwise a
        min/max envelope per bucket (two points per bucket). Gaps (empty
        buckets, disconnects) are NaN so curves drawn with
        ``connect='finite'`` break there."""
        if level is None:
            level = self.choose_level(t0, t1, max_points)
        if level == 0:
            xs, ys = [], {p: [] for p in params}
            for s in self._overlapping(t0, t1):
                a = self._arrays(s, ["t"] + [f"c/{p}" for p in params])
                t = a["t"]
                i0, i1 = np.searchsorted(t, t0, "left"), np.searchsorted(t, t1, "right")
                i0, i1 = max(0, i0 - 1), min(t.size, i1 + 1)
                if xs:
                    xs.append(np.array([np.nan]))
                    for p in params:
                        ys[p].append(np.array([np.nan]))
                xs.append(t[i0:i1])
                for p in params:
                    col = a[f"c/{p}"]
                    ys[p].append(col[i0:i1] if col.size else np.full(i1 - i0, np.nan))
            x = np.concatenate(xs) if xs else np.zeros(0)
            y = {p: (np.concatenate(v) if v else np.zeros(0)) for p, v in ys.items()}
            x, y = _break_gaps(x, y, self.gaps)
            return Window(x, y, 0, t0, t1)

        lo_b, hi_b = math.floor(t0 / level) - 1, math.floor(t1 / level) + 1
        per = {p: self._buckets(p, level, lo_b, hi_b) for p in params}
        all_b = np.unique(np.concatenate([per[p]["b"] for p in params])) if params else np.zeros(0, np.int64)
        if all_b.size == 0:
            return Window(np.zeros(0), {p: np.zeros(0) for p in params}, level, t0, t1)
        y: Dict[str, np.ndarray] = {}
        for p in params:
            mn = np.full(all_b.size, np.nan)
            mx = np.full(all_b.size, np.nan)
            idx = np.searchsorted(all_b, per[p]["b"])
            mn[idx] = per[p]["min"]
            mx[idx] = per[p]["max"]
            env = np.empty(all_b.size * 2)
            env[0::2], env[1::2] = mn, mx
            y[p] = env
        x = np.empty(all_b.size * 2)
        x[0::2] = all_b * level + level * 0.25
        x[1::2] = all_b * level + level * 0.75
        jumps = np.nonzero(np.diff(all_b) > 1)[0]
        if jumps.size:
            cut = (jumps + 1) * 2
            x = np.insert(x, cut, np.nan)
            for p in params:
                y[p] = np.insert(y[p], cut, np.nan)
        return Window(x, y, level, t0, t1)

    # -- values ----------------------------------------------------------------

    def value_at(self, param: str, t: float) -> float:
        """Full-resolution value at ``t`` (linear between rows; NaN outside
        the data, inside a gap, or before the first row)."""
        if any(g0 < t < g1 for g0, g1 in self.gaps):
            return float("nan")
        for s in self.segments:
            if s.t0 - 1e-6 <= t <= s.t1 + 1e-6 and s.cache.exists():
                a = self._arrays(s, ["t", f"c/{param}"])
                ts, ys = a["t"], a[f"c/{param}"]
                if ts.size == 0 or ys.size == 0 or t < ts[0] or t > ts[-1]:
                    return float("nan")
                ok = ~np.isnan(ys)
                if not ok.any():
                    return float("nan")
                return float(np.interp(t, ts[ok], ys[ok]))
        return float("nan")

    # -- statistics ------------------------------------------------------------

    def stats(self, param: str, t0: float, t1: float) -> Optional[RangeStats]:
        """Statistics of ``param`` over [t0, t1] (see module docstring)."""
        if self.rows_in(t0, t1) <= FULL_RES_LIMIT:
            vals = self._full_res(param, t0, t1)
            if vals.size == 0:
                return None
            p5, med, p95 = np.percentile(vals, [5, 50, 95])
            return RangeStats(int(vals.size), float(vals.min()), float(vals.max()), float(vals.mean()),
                              float(vals.std()), float(med), float(p5), float(p95), False)
        agg = self._exact_aggregate(param, t0, t1, right_open=False, levels=tuple(reversed(LEVELS)))
        if agg is None or agg[0] == 0:
            return None
        n, mean, m2, mn, mx = agg
        guesses = self._approx_percentiles(param, t0, t1, (5, 50, 95))
        exact = self._exact_percentiles(param, t0, t1, int(n), (5, 50, 95), guesses, mn, mx)
        if exact is not None:
            p5, med, p95 = exact
            return RangeStats(int(n), mn, mx, mean, math.sqrt(m2 / n), med, p5, p95, False)
        p5, med, p95 = guesses
        return RangeStats(int(n), mn, mx, mean, math.sqrt(m2 / n), med, p5, p95, True)

    def _exact_percentiles(self, param: str, t0: float, t1: float, n: int, qs: Sequence[float],
                           guesses: Sequence[float], vmin: float, vmax: float,
                           max_passes: int = 6) -> Optional[Tuple[float, ...]]:
        """Exact percentiles (numpy's linear definition) of a range too large
        to hold in memory.

        Each needed rank gets a value bracket around its sketch estimate; one
        streaming pass over the segments counts values below each bracket and
        keeps only the distinct values (with counts) inside it, from which the
        rank is selected exactly. A bracket that misses is widened and the
        pass repeated. Memory stays bounded by the distinct values inside the
        brackets. Returns None if a bracket still misses after ``max_passes``.
        """
        if n <= 0:
            return None
        spread = max(vmax - vmin, 1e-12)
        targets = []
        for q, g in zip(qs, guesses, strict=True):
            h = (n - 1) * q / 100.0
            k = int(math.floor(h))
            guess = g if math.isfinite(g) else (vmin + vmax) / 2
            targets.append({"k": k, "k1": min(k + 1, n - 1), "frac": h - k,
                            "lo": guess - spread * 0.002, "hi": guess + spread * 0.002})
        segs = self._overlapping(t0, t1)
        for _ in range(max_passes):
            below = [0] * len(targets)
            uniq: List[List[np.ndarray]] = [[] for _ in targets]
            cnts: List[List[np.ndarray]] = [[] for _ in targets]
            for s in segs:
                a = self._arrays(s, ["t", f"c/{param}"])
                t, y = a["t"], a[f"c/{param}"]
                if y.size == 0:
                    continue
                v = y[(t >= t0) & (t <= t1)]
                v = v[~np.isnan(v)]
                for i, tg in enumerate(targets):
                    below[i] += int((v < tg["lo"]).sum())
                    inside = v[(v >= tg["lo"]) & (v <= tg["hi"])]
                    if inside.size:
                        u, c = np.unique(inside, return_counts=True)
                        uniq[i].append(u)
                        cnts[i].append(c)
            results: List[Optional[float]] = []
            retry = False
            for i, tg in enumerate(targets):
                if uniq[i]:
                    u_all, inv = np.unique(np.concatenate(uniq[i]), return_inverse=True)
                    c_all = np.zeros(u_all.size, np.int64)
                    np.add.at(c_all, inv, np.concatenate(cnts[i]))
                    cum = np.cumsum(c_all)
                else:
                    u_all, cum = np.zeros(0), np.zeros(0, np.int64)
                total_inside = int(cum[-1]) if cum.size else 0
                vals = []
                for r in (tg["k"], tg["k1"]):
                    rel = r - below[i]
                    if 0 <= rel < total_inside:
                        vals.append(float(u_all[int(np.searchsorted(cum, rel, "right"))]))
                    else:
                        vals.append(None)
                if None in vals:
                    retry = True
                    width = (tg["hi"] - tg["lo"]) * 8
                    if below[i] > tg["k"]:
                        tg["lo"] -= width
                    if below[i] + total_inside <= tg["k1"]:
                        tg["hi"] += width
                    results.append(None)
                else:
                    results.append(vals[0] + tg["frac"] * (vals[1] - vals[0]))
            if not retry:
                return tuple(results)  # type: ignore[arg-type]
        return None

    def _exact_aggregate(self, param: str, t0: float, t1: float, *, right_open: bool,
                         levels: Tuple[int, ...]) -> Optional[Tuple[float, float, float, float, float]]:
        """(n, mean, m2, min, max) over [t0, t1] (or [t0, t1) if right_open),
        exact: whole buckets of the coarsest level inside the range, finer
        levels for the edges, full-resolution rows for what is left."""
        if t1 < t0:
            return None
        if not levels:
            v = self._full_res(param, t0, t1, right_open=right_open)
            if v.size == 0:
                return None
            m = float(v.mean())
            return float(v.size), m, float(((v - m) ** 2).sum()), float(v.min()), float(v.max())
        level = levels[0]
        first = math.ceil(t0 / level)
        last = math.floor(t1 / level) - 1       # buckets [first*L, (last+1)*L) lie inside
        if last < first:
            return self._exact_aggregate(param, t0, t1, right_open=right_open, levels=levels[1:])
        parts = []
        mid = self._buckets(param, level, first, last)
        ok = mid["n"] > 0 if mid["n"].size else np.zeros(0, bool)
        if ok.any():
            parts.append((mid["n"][ok].astype(float), mid["mean"][ok], mid["m2"][ok],
                          float(np.nanmin(mid["min"][ok])), float(np.nanmax(mid["max"][ok]))))
        for edge in (
            self._exact_aggregate(param, t0, first * level, right_open=True, levels=levels[1:]),
            self._exact_aggregate(param, (last + 1) * level, t1, right_open=right_open, levels=levels[1:]),
        ):
            if edge is not None and edge[0] > 0:
                parts.append((np.array([edge[0]]), np.array([edge[1]]), np.array([edge[2]]), edge[3], edge[4]))
        if not parts:
            return None
        n = np.concatenate([p[0] for p in parts])
        means = np.concatenate([p[1] for p in parts])
        m2s = np.concatenate([p[2] for p in parts])
        total = float(n.sum())
        mean = float((n * means).sum() / total)
        m2 = float(m2s.sum() + (n * (means - mean) ** 2).sum())    # Chan et al. merge
        return total, mean, m2, min(p[3] for p in parts), max(p[4] for p in parts)

    def _approx_percentiles(self, param: str, t0: float, t1: float, qs: Sequence[float]) -> Tuple[float, ...]:
        """Percentile estimates from per-segment quantile sketches, weighting
        each segment by the share of it inside the range."""
        q = self._summary_array(f"Q/{param}")
        qn = self._summary_array(f"Q/{param}/n")
        index_pos = {i: k for k, i in enumerate(self._summary_segments)}
        sets: List[Tuple[np.ndarray, int]] = []
        for s in self._overlapping(t0, t1):
            k = index_pos.get(s.index)
            if k is None or k >= len(qn):
                qs_seg, n_seg = self._array(s, f"q/{param}"), self._array(s, f"q/{param}/n")
                if not qs_seg.size or not n_seg.size:
                    continue
                row, cnt = qs_seg, int(n_seg[0])
            else:
                row, cnt = q[k], int(qn[k])
            frac = (min(s.t1, t1) - max(s.t0, t0)) / max(s.t1 - s.t0, 1e-9)
            sets.append((row, int(cnt * max(0.0, min(1.0, frac)))))
        return _merged_quantiles(sets, qs)

    def _full_res(self, param: str, t0: float, t1: float, *, right_open: bool = False) -> np.ndarray:
        out: List[np.ndarray] = []
        for s in self._overlapping(t0, t1):
            a = self._arrays(s, ["t", f"c/{param}"])
            t, y = a["t"], a[f"c/{param}"]
            if y.size == 0:
                continue
            sel = (t >= t0) & ((t < t1) if right_open else (t <= t1))
            v = y[sel]
            out.append(v[~np.isnan(v)])
        return np.concatenate(out) if out else np.zeros(0)

    # -- export --------------------------------------------------------------

    def export_range(self, params: Sequence[str], t0: float, t1: float, path: Path,
                     *, xlsx: bool = False, cancelled: Callable[[], bool] = lambda: False,
                     progress: Optional[Callable[[int], None]] = None) -> int:
        """Write every full-resolution row in [t0, t1] to CSV (UTC time,
        elapsed seconds, the chosen signals). With ``xlsx`` an .xlsx is also
        produced (split into sheets of at most 1,000,000 rows). Returns rows."""
        from .decoded_logger import compile_csv_to_xlsx
        from .session import iso_utc

        path = Path(path)
        segs = self._overlapping(t0, t1)
        rows = 0
        with path.open("w", newline="", encoding="utf-8") as fp:
            w = csv.writer(fp)
            w.writerow(["time_utc", "elapsed_s", *params])
            for i, s in enumerate(segs):
                if cancelled():
                    break
                a = self._arrays(s, ["t"] + [f"c/{p}" for p in params])
                t = a["t"]
                sel = (t >= t0) & (t <= t1)
                ts = t[sel]
                vals = [a[f"c/{p}"][sel] if a[f"c/{p}"].size else np.full(ts.size, np.nan) for p in params]
                for k in range(ts.size):
                    w.writerow([iso_utc(self.start_epoch + ts[k]), f"{ts[k]:.3f}",
                                *("" if not np.isfinite(v[k]) else repr(float(v[k])) for v in vals)])
                rows += int(ts.size)
                if progress:
                    progress(int(100 * (i + 1) / max(1, len(segs))))
        if xlsx and not cancelled():
            exc = compile_csv_to_xlsx(path, {"session": self.folder.name, "range_s": f"{t0:.3f}-{t1:.3f}"},
                                      path.with_suffix(".xlsx"))
            if exc is not None:
                raise exc
        return rows


def _merge_bucket_sets(parts: List[Dict[str, np.ndarray]]) -> Dict[str, np.ndarray]:
    """Merge per-segment bucket aggregates; a bucket split across segments is
    combined exactly (counts add, means/M2 by Chan et al., min/max)."""
    parts = [p for p in parts if p["b"].size]
    if not parts:
        return {"b": np.zeros(0, np.int64), **{k: np.zeros(0) for k in _AGG_KEYS}}
    b = np.concatenate([p["b"] for p in parts])
    n = np.concatenate([p["n"] for p in parts]).astype(np.float64)
    mean = np.concatenate([p["mean"] for p in parts])
    m2 = np.concatenate([p["m2"] for p in parts])
    mn = np.concatenate([p["min"] for p in parts])
    mx = np.concatenate([p["max"] for p in parts])
    uniq, inv = np.unique(b, return_inverse=True)
    if uniq.size == b.size:
        order = np.argsort(b)
        return {"b": b[order], "n": n[order].astype(np.int64), "mean": mean[order], "m2": m2[order],
                "min": mn[order], "max": mx[order]}
    tot = np.zeros(uniq.size)
    np.add.at(tot, inv, n)
    meanz = np.where(n > 0, mean, 0.0)
    s = np.zeros(uniq.size)
    np.add.at(s, inv, n * meanz)
    with np.errstate(invalid="ignore", divide="ignore"):
        gmean = np.where(tot > 0, s / np.maximum(tot, 1), np.nan)
    dev = np.where(n > 0, meanz - gmean[inv], 0.0)
    gm2 = np.zeros(uniq.size)
    np.add.at(gm2, inv, np.where(n > 0, m2, 0.0) + n * dev * dev)
    gmin = np.full(uniq.size, np.inf)
    gmax = np.full(uniq.size, -np.inf)
    np.fmin.at(gmin, inv, mn)
    np.fmax.at(gmax, inv, mx)
    gmin[~np.isfinite(gmin)] = np.nan
    gmax[~np.isfinite(gmax)] = np.nan
    return {"b": uniq, "n": tot.astype(np.int64), "mean": gmean, "m2": gm2, "min": gmin, "max": gmax}


def _break_gaps(x: np.ndarray, y: Dict[str, np.ndarray], gaps: Iterable[Tuple[float, float]]):
    """Insert NaN at recorded disconnect gaps so lines do not bridge them."""
    if x.size == 0:
        return x, y
    cuts = []
    for g0, g1 in gaps:
        i = int(np.searchsorted(x, g0, "right"))
        if 0 < i < x.size and x[i] >= g1 - 1e-9:
            cuts.append(i)
    if not cuts:
        return x, y
    x = np.insert(x, cuts, np.nan)
    return x, {p: np.insert(v, cuts, np.nan) for p, v in y.items()}


def _merged_quantiles(sets: List[Tuple[np.ndarray, int]], qs: Sequence[float]) -> Tuple[float, ...]:
    """Estimate quantiles of the union of segments from each segment's 101
    quantiles, weighting segments by sample count."""
    pts, wts = [], []
    for q, n in sets:
        if n <= 0 or np.all(np.isnan(q)):
            continue
        pts.append(q)
        wts.append(np.full(q.size, n / q.size))
    if not pts:
        return tuple(float("nan") for _ in qs)
    p = np.concatenate(pts)
    w = np.concatenate(wts)
    order = np.argsort(p)
    p, w = p[order], w[order]
    cw = np.cumsum(w) / w.sum() * 100
    return tuple(float(np.interp(q, cw, p)) for q in qs)
