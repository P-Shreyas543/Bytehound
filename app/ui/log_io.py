"""Background log-file loader and ``LogEntry`` dataclass for the Analysis Suite.

Extracted from analysis_suite.py to isolate disk I/O (csv/xlsx parsing,
column normalisation, test-name derivation) from the main window class.
This module has no dependency on any other ``analysis_*`` module, so it
is safe to import from anywhere without forming cycles.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from PySide6.QtCore import QThread, Signal


# ═══════════════════════════════════════════════════════════════════════
# Data model
# ═══════════════════════════════════════════════════════════════════════
@dataclass
class LogEntry:
    """One loaded test-log file."""
    id: str = ""
    path: str = ""
    name: str = ""
    color: str = "#1f77b4"
    visible: bool = True
    time_offset: float = 0.0
    start_timestamp: Optional[float] = None  # POSIX epoch of first sample
    elapsed: np.ndarray = field(default_factory=lambda: np.zeros(0))
    columns: dict[str, np.ndarray] = field(default_factory=dict)

    def available_params(self) -> list[str]:
        return [name for name in self.columns.keys() if not _is_time_like_param(name)]


def _is_time_like_param(name: str) -> bool:
    """Return True for columns that represent time axes rather than data."""
    norm = re.sub(r'\s+', ' ', (name or '').strip().lower())
    if norm in {
        '', 'time', 'timestamp', 'elapsed', 'elapsed (s)', 'time (s)',
        'elapsed time', 'elapsed time (s)',
    }:
        return True
    return norm.startswith('timestamp ') or norm.startswith('elapsed ')


def _test_name_from_path(path: str) -> str:
    """Extract a human-readable test name from the log filename."""
    base = os.path.splitext(os.path.basename(path))[0]
    # Strip DynoLog_ prefix and _YYYYMMDD_HHMMSS suffix
    base = re.sub(r'^DynoLog_', '', base)
    base = re.sub(r'_\d{8}_\d{6}$', '', base)
    return base or os.path.basename(path)


# File-path → LogEntry cache so re-toggling a parameter does not re-read disk.
_CSV_CACHE: dict[str, LogEntry] = {}


# ═══════════════════════════════════════════════════════════════════════
# Background loader thread
# ═══════════════════════════════════════════════════════════════════════
class LogLoaderThread(QThread):
    """Loads one .xlsx (Bytehound decoded or Dyno) or _decoded.csv log in a
    background thread."""
    sigFinished = Signal(str, str, object)   # (log_id, path, LogEntry or None)
    sigProgress = Signal(int)                # Progress percentage (0-100); -1 = unknown
    sigStatus = Signal(str)                  # what the loader is doing, for the progress dialog
    sigCancelled = Signal(str)               # (path) stopped by requestInterruption()
    error = Signal(str, str)                # (path, error_message)

    # Rows between progress reports / cancel checks while reading a workbook.
    _XLSX_CHUNK = 2000

    def __init__(self, path: str, log_id: str, color: str, parent=None):
        super().__init__(parent)
        self._path = path
        self._log_id = log_id
        self._color = color

    def run(self):
        try:
            ext = os.path.splitext(self._path)[1].lower()
            if ext == ".csv":
                self._load_csv()
                return
            twin = os.path.splitext(self._path)[0] + ".csv"
            if os.path.isfile(twin) and os.path.getsize(twin) > 0:
                # Session segments (and merged sessions saved with their CSV)
                # keep the same rows as CSV: ~100x faster to read than xlsx.
                self.sigStatus.emit(f"Reading {os.path.basename(twin)} (the CSV saved with this workbook)…")
                self._load_csv(source=twin)
                return
            self._load_xlsx()
        except Exception as exc:
            self.error.emit(self._path, str(exc))

    def _get_schema_settings(self):
        from PySide6.QtCore import QSettings
        from .analysis_theme import APP_ORG, APP_NAME
        s = QSettings(APP_ORG, APP_NAME)

        sheets_raw = s.value("import/sheet_names", "Data,Record")
        sheet_candidates = [x.strip() for x in str(sheets_raw).split(",") if x.strip()]

        cols_raw = s.value("import/elapsed_cols", "Elapsed (s),elapsed_ms")
        col_candidates = [x.strip() for x in str(cols_raw).split(",") if x.strip()]

        scales_raw = s.value("import/elapsed_scales", "Elapsed (s): 1.0\nelapsed_ms: 0.001")
        scale_mapping = {}
        for line in str(scales_raw).split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                try:
                    scale_mapping[k.strip()] = float(v.strip())
                except ValueError:
                    pass

        return sheet_candidates, col_candidates, scale_mapping

    def _load_csv(self, source: Optional[str] = None):
        """Parse a CSV log: a session segment / merged session, or a legacy
        _decoded.csv. ``source`` is the file to read when it is not
        ``self._path`` (the CSV twin of a workbook); the entry keeps
        ``self._path`` so the user sees the file they opened."""
        import pandas as pd
        self.sigProgress.emit(-1)
        if source is None:
            self.sigStatus.emit(f"Reading {os.path.basename(self._path)}…")
        try:
            df = pd.read_csv(source or self._path, comment='#')
        except Exception as e:
            self.error.emit(self._path, f"Failed to parse CSV: {e}")
            return

        if df.empty:
            self.error.emit(self._path, "Log file contains no recorded data (empty sheet). Please verify data was received during logging.")
            return

        first_ts_posix: float | None = None
        sheet_candidates, col_candidates, scale_mapping = self._get_schema_settings()

        elapsed_col = None
        elapsed_scale = 1.0
        for col in col_candidates:
            if col in df.columns:
                elapsed_col = col
                elapsed_scale = scale_mapping.get(col, 1.0)
                break

        if self._finish_session_layout(df):
            return

        if elapsed_col:
            elapsed_arr = (pd.to_numeric(df[elapsed_col], errors='coerce').fillna(0) * elapsed_scale).to_numpy(dtype=np.float64)
        elif "elapsed_ms" in df.columns:
            elapsed_arr = (pd.to_numeric(df["elapsed_ms"], errors='coerce').fillna(0) / 1000.0).to_numpy(dtype=np.float64)
        elif "timestamp" in df.columns:
            ts_series = pd.to_datetime(df["timestamp"], errors='coerce')
            valid_ts = ts_series.dropna()
            if valid_ts.empty:
                self.error.emit(self._path, "No valid timestamps found.")
                return
            first_ts = valid_ts.iloc[0]
            first_ts_posix = first_ts.timestamp()
            elapsed_arr = (ts_series - first_ts).dt.total_seconds().fillna(0).to_numpy(dtype=np.float64)
        else:
            self.error.emit(self._path, f"No configured time column (checked {col_candidates}) or timestamp column found.")
            return

        data_columns = [c for c in df.columns if c not in {"timestamp", "elapsed_ms"} and not _is_time_like_param(c)]
        if not data_columns:
            self.error.emit(self._path, "No data columns found in CSV.")
            return

        columns: dict[str, np.ndarray] = {}
        for col in data_columns:
            arr = pd.to_numeric(df[col], errors='coerce').to_numpy(dtype=np.float64)
            if not np.all(np.isnan(arr)):
                columns[col] = arr

        if not columns:
            self.error.emit(self._path, "No numeric columns found in CSV.")
            return

        entry = LogEntry(
            id=self._log_id,
            path=self._path,
            name=_test_name_from_path(self._path),
            color=self._color,
            start_timestamp=first_ts_posix,
            elapsed=elapsed_arr,
            columns=columns,
        )
        _CSV_CACHE[self._path] = entry
        self.sigProgress.emit(100)
        self.sigFinished.emit(self._log_id, self._path, entry)

    def _finish_session_layout(self, df) -> bool:
        """A session log (segment or merged session; CSV or workbook): time
        from ``time_utc`` (clock time available) or ``elapsed_s``, frame-block
        bookkeeping columns dropped. Returns False if ``df`` is not one."""
        import pandas as pd
        if "time_utc" not in df.columns and "elapsed_s" not in df.columns:
            return False
        from ..serial_logging.session_analysis import _is_signal_column
        self.sigStatus.emit(f"Preparing {os.path.basename(self._path)}…")
        first_ts_posix: float | None = None
        if "time_utc" in df.columns:
            ts = pd.to_datetime(df["time_utc"], utc=True, errors="coerce", format="ISO8601")
            valid = ts.dropna()
            if valid.empty:
                self.error.emit(self._path, "No valid time_utc values found.")
                return True
            first_ts_posix = valid.iloc[0].timestamp()
            elapsed_arr = (ts - valid.iloc[0]).dt.total_seconds().to_numpy(dtype=np.float64)
        else:
            elapsed_arr = pd.to_numeric(df["elapsed_s"], errors='coerce').to_numpy(dtype=np.float64)
        data_columns = [c for c in df.columns if _is_signal_column(str(c))]
        columns: dict[str, np.ndarray] = {}
        for col in data_columns:
            arr = pd.to_numeric(df[col], errors='coerce').to_numpy(dtype=np.float64)
            if not np.all(np.isnan(arr)):
                columns[str(col)] = arr
        if not columns:
            self.error.emit(self._path, "No numeric columns found.")
            return True
        entry = LogEntry(
            id=self._log_id, path=self._path, name=_test_name_from_path(self._path),
            color=self._color, start_timestamp=first_ts_posix, elapsed=elapsed_arr, columns=columns,
        )
        _CSV_CACHE[self._path] = entry
        self.sigProgress.emit(100)
        self.sigFinished.emit(self._log_id, self._path, entry)
        return True

    def _read_xlsx_streaming(self):
        """Read the data sheet(s) row by row (read-only mode): progress every
        ``_XLSX_CHUNK`` rows against the row count the workbook's Metadata
        records (sessions and merged sessions), cancellable, converted in
        chunks to keep memory down. Returns a DataFrame, or None if
        cancelled."""
        import pandas as pd
        from openpyxl import load_workbook

        sheet_candidates, _cols, _scales = self._get_schema_settings()
        name = os.path.basename(self._path)
        self.sigStatus.emit(f"Opening {name}…")
        wb = load_workbook(self._path, read_only=True, data_only=True)
        try:
            names = wb.sheetnames
            matching: list[str] = []
            for cand in sheet_candidates:
                matching = [s for s in names if s == cand or s.startswith(f"{cand}_")]
                if matching:
                    break
            if not matching:
                matching = ([s for s in names if s == "Data" or s.startswith("Data_")]
                            or [s for s in names if s == "Record" or s.startswith("Record_")]
                            or [names[0]])
            total = None
            if "Metadata" in names:
                for row in wb["Metadata"].iter_rows(values_only=True):
                    if row and str(row[0]).strip() == "rows" and len(row) > 1:
                        try:
                            total = int(str(row[1]).strip())
                        except ValueError:
                            total = None
                        break
            header = None
            chunks = []
            buf: list = []
            done = 0
            for sheet in matching:
                rows = wb[sheet].iter_rows(values_only=True)
                first = next(rows, None)
                if first is None:
                    continue
                if header is None:
                    header = [str(c) if c is not None else "" for c in first]
                for row in rows:
                    buf.append(row)
                    done += 1
                    if done % self._XLSX_CHUNK == 0:
                        if self.isInterruptionRequested():
                            return None
                        chunks.append(pd.DataFrame(buf, columns=header))
                        buf = []
                        if total:
                            self.sigProgress.emit(min(99, int(100 * done / total)))
                            self.sigStatus.emit(f"Reading {name}: {done:,} of {total:,} rows")
                        else:
                            self.sigStatus.emit(f"Reading {name}: {done:,} rows")
            if buf:
                chunks.append(pd.DataFrame(buf, columns=header))
            if header is None:
                return pd.DataFrame()
            return pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame(columns=header)
        finally:
            wb.close()

    def _load_xlsx(self):
        """Parse a .xlsx file. Supports multi-sheet datasets (Data, Data_2, Data_3...) using high-performance pandas."""
        import pandas as pd
        sheet_candidates, col_candidates, scale_mapping = self._get_schema_settings()
        try:
            df = self._read_xlsx_streaming()
        except Exception as e:
            self.error.emit(self._path, f"Failed to parse Excel: {e}")
            return
        if df is None:
            self.sigCancelled.emit(self._path)
            return

        if df.empty:
            self.error.emit(self._path, "Log file contains no recorded data (empty sheet). Please verify data was received during logging.")
            return
        if self._finish_session_layout(df):
            return
        self.sigStatus.emit(f"Preparing {os.path.basename(self._path)}…")

        headers = [str(c) if c else "" for c in df.columns]

        elapsed_col = None
        elapsed_scale = 1.0
        frame_block_elapsed_cols = set()
        frame_block_id_cols = set()

        for h in headers:
            if h.endswith(".elapsed_ms"):
                frame_block_elapsed_cols.add(h)
                elapsed_col = h  # LAST one wins (trigger frame)
                elapsed_scale = 1e-3
            elif h.endswith(".frame_id"):
                frame_block_id_cols.add(h)

        if not elapsed_col:
            for col in col_candidates:
                if col in headers:
                    elapsed_col = col
                    elapsed_scale = scale_mapping.get(col, 1.0)
                    break

        if not elapsed_col:
            for h in headers:
                if h == "Elapsed (s)":
                    elapsed_col = h
                    elapsed_scale = 1.0
                    break
                if h == "elapsed_ms":
                    elapsed_col = h
                    elapsed_scale = 1e-3
                    break

        if not elapsed_col:
            elapsed_arr = np.zeros(len(df), dtype=np.float64)
        else:
            elapsed_arr = (pd.to_numeric(df[elapsed_col], errors='coerce').ffill().fillna(0) * elapsed_scale).to_numpy(dtype=np.float64)

        columns: dict[str, np.ndarray] = {}
        skip_cols = frame_block_elapsed_cols | frame_block_id_cols | {elapsed_col}

        for h in headers:
            if h in skip_cols or _is_time_like_param(h):
                continue
            arr = pd.to_numeric(df[h], errors='coerce').to_numpy(dtype=np.float64)
            columns[h] = arr

        entry = LogEntry(
            id=self._log_id,
            path=self._path,
            name=_test_name_from_path(self._path),
            color=self._color,
            elapsed=elapsed_arr,
            columns=columns,
        )
        _CSV_CACHE[self._path] = entry
        self.sigProgress.emit(100)
        self.sigFinished.emit(self._log_id, self._path, entry)


# ═══════════════════════════════════════════════════════════════════════
# Math channels
# ═══════════════════════════════════════════════════════════════════════
def math_components(expr: str) -> list[str]:
    """Signal names referenced as ``[name]`` in a math-channel expression."""
    return re.findall(r'\[(.*?)\]', expr)


def eval_math_expression(expr: str, data, x: np.ndarray) -> np.ndarray:
    """Evaluate a math-channel expression over arrays sharing the time axis
    ``x``. ``diff``/``deriv`` = d/dt; ``integral``/``cumsum`` = trapezoidal
    running integral. NaN samples (gaps) are skipped: an interval with a
    NaN end contributes nothing instead of turning everything after it NaN.
    """
    def diff_func(y):
        if len(x) <= 1:
            return np.zeros_like(y)
        return np.gradient(y, x)

    def integral_func(y):
        if len(x) <= 1:
            return np.zeros_like(y)
        dt = np.diff(x)
        y_avg = 0.5 * (y[:-1] + y[1:])
        integrand = np.where(np.isfinite(y_avg) & np.isfinite(dt), y_avg * dt, 0.0)
        return np.insert(np.cumsum(integrand), 0, 0.0)

    py_expr = re.sub(r'\[(.*?)\]', r'data["\1"]', expr)
    return eval(  # noqa: S307 - restricted namespace, user's own expressions
        py_expr,
        {
            "__builtins__": None,
            "np": np,
            "diff": diff_func,
            "deriv": diff_func,
            "derivative": diff_func,
            "integral": integral_func,
            "int": integral_func,
            "cumsum": integral_func,
        },
        {"data": data},
    )


# ═══════════════════════════════════════════════════════════════════════
# Logging sessions (folders of rotated segments) — Plane.md Part B
# ═══════════════════════════════════════════════════════════════════════
def entry_value_at(entry, param: str, t: float, x: Optional[np.ndarray] = None) -> float:
    """Value of ``param`` at plot time ``t`` for any loaded log.

    Session entries answer from full-resolution data even when the plot shows
    a min/max envelope; ordinary logs interpolate their arrays.
    """
    if getattr(entry, "is_session", False):
        return entry.value_at(param, t)
    if x is None:
        x = entry.elapsed + entry.time_offset
    if len(x) == 0 or param not in entry.columns:
        return float("nan")
    return float(np.interp(t, x, entry.columns[param]))


class _SessionColumns:
    """``entry.columns``-compatible view: keys are every signal of the
    session, values are arrays for the entry's current view."""

    def __init__(self, entry: "SessionEntry") -> None:
        self._entry = entry

    def __contains__(self, key) -> bool:
        return key in self._entry.signal_set

    def __iter__(self):
        return iter(self._entry.signals)

    def __len__(self) -> int:
        return len(self._entry.signals)

    def keys(self):
        return list(self._entry.signals)

    def __getitem__(self, key: str) -> np.ndarray:
        if key not in self._entry.signal_set:
            raise KeyError(key)
        self._entry.ensure([key])
        return self._entry.view.y.get(key, np.zeros(0))

    def get(self, key: str, default=None):
        return self[key] if key in self else default


class SessionEntry:
    """A logging session presented like a :class:`LogEntry`.

    ``elapsed`` / ``columns`` hold the data of the current view only: full
    resolution when zoomed in, a min/max envelope when zoomed out. Gaps are
    NaN (draw with ``connect='finite'``). Values, statistics and exports go
    to full resolution through :attr:`source`.
    """

    is_session = True
    keeps_gaps = True

    def __init__(self, source, *, id: str, path: str, name: str, color: str) -> None:
        from ..serial_logging.session_analysis import Window

        self.source = source
        self.id = id
        self.path = path
        self.name = name
        self.color = color
        self.visible = True
        self.time_offset = 0.0
        self.start_timestamp: Optional[float] = source.start_epoch
        self.signals = [s for s in source.signals() if not _is_time_like_param(s)]
        self.signal_set = set(self.signals)
        self.columns = _SessionColumns(self)
        self.view = Window(np.zeros(0), {}, 0, 0.0, source.duration)
        self.loading = False
        self.math: dict[str, str] = {}

    def set_math_channels(self, defs: dict[str, str]) -> None:
        """Math channels for a session are evaluated on full-resolution data
        of the current view; when zoomed out (envelope) they are NaN.
        ``integral`` therefore integrates from the left edge of the view."""
        self.math = {k: v for k, v in defs.items() if k not in self.source.signals()}
        base = [s for s in self.source.signals() if not _is_time_like_param(s)]
        self.signals = base + [m for m in self.math if m not in base]
        self.signal_set = set(self.signals)
        for name in self.math:
            self.view.y.pop(name, None)

    def _real_params(self, params) -> list[str]:
        out: list[str] = []
        for p in params:
            for q in (math_components(self.math[p]) if p in self.math else [p]):
                if q in self.source.signals() and q not in out:
                    out.append(q)
        return out

    def _with_math(self, window, params):
        for p in params:
            if p not in self.math:
                continue
            if window.level == 0 and window.x.size:
                try:
                    window.y[p] = np.asarray(eval_math_expression(self.math[p], window.y, window.x), dtype=float)
                    continue
                except Exception:
                    pass
            window.y[p] = np.full(window.x.size, np.nan)
        return window

    @property
    def elapsed(self) -> np.ndarray:
        return self.view.x

    def available_params(self) -> list[str]:
        return list(self.signals)

    def plan(self, t0: float, t1: float, px: int) -> tuple[float, float, int]:
        """Range to load (with margin for smooth panning) and its level."""
        span = max(t1 - t0, 1e-3)
        lo = max(0.0, t0 - span * 0.5)
        hi = min(self.source.duration, t1 + span * 0.5)
        return lo, hi, self.source.choose_level(lo, hi, max_points=max(1000, px * 2))

    def covers(self, t0: float, t1: float, level: int) -> bool:
        v = self.view
        return v.x.size > 0 and v.t0 <= max(0.0, t0) and v.t1 >= min(self.source.duration, t1) and v.level == level

    def load(self, params, t0: float, t1: float, level: int):
        params = list(params)
        w = self.source.window(self._real_params(params), t0, t1, level=level)
        return self._with_math(w, params)

    def apply(self, window) -> None:
        self.view = window

    def ensure(self, params) -> None:
        """Make sure ``params`` are in the current view (same range/level)."""
        missing = [p for p in params if p not in self.view.y]
        if not missing:
            return
        v = self.view
        if v.x.size == 0 and not v.y:
            lo, hi = 0.0, self.source.duration
            level = self.source.choose_level(lo, hi)
        else:
            lo, hi, level = v.t0, v.t1, v.level
        wanted = sorted(set(v.y) | set(missing))
        w = self.source.window(self._real_params(wanted), lo, hi, level=level)
        self.view = self._with_math(w, wanted)

    def value_at(self, param: str, t: float) -> float:
        if param in self.math:
            v = self.view
            if v.level == 0 and param in v.y and v.x.size:
                ok = np.isfinite(v.x) & np.isfinite(v.y[param])
                if ok.any():
                    return float(np.interp(t - self.time_offset, v.x[ok], v.y[param][ok]))
            return float("nan")
        return self.source.value_at(param, t - self.time_offset)

    def range_stats(self, param: str, x0: float, x1: float) -> Optional[dict]:
        if param in self.math:
            return None   # math channels: no full-session statistics (view-only)
        st = self.source.stats(param, x0 - self.time_offset, x1 - self.time_offset)
        if st is None:
            return None
        return {"min": st.min, "p5": st.p5, "max": st.max, "mean": st.mean, "median": st.median,
                "p95": st.p95, "std": st.std, "n": st.n, "approx": st.approx_percentiles}


class SessionLoaderThread(QThread):
    """Opens a logging session folder (building missing analysis caches)."""
    sigFinished = Signal(str, str, object)
    sigProgress = Signal(int)
    sigStatus = Signal(str)
    error = Signal(str, str)

    def __init__(self, folder: str, log_id: str, color: str, kind: str = "event", parent=None):
        super().__init__(parent)
        self._folder = folder
        self._log_id = log_id
        self._color = color
        self._kind = kind

    def run(self):
        from ..serial_logging.session_analysis import SessionSource
        try:
            src = SessionSource(self._folder, kind=self._kind)
            if not src.segments:
                self.error.emit(self._folder, f"This session has no {self._kind} log segments.")
                return
            missing = len(src.missing_caches())
            name = os.path.basename(os.path.normpath(self._folder))
            self.sigStatus.emit(f"Opening session {name}: {len(src.segments)} segment(s)"
                                + (f", building {missing} analysis cache(s)" if missing else "") + "…")

            def caches(done, total):
                self.sigProgress.emit(int(100 * done / max(total, 1)))
                self.sigStatus.emit(f"Session {name}: analysis caches {done} of {total}")
            src.ensure_caches(caches)
            name = os.path.basename(os.path.normpath(self._folder))
            if self._kind != "event":
                name += f" ({self._kind}-step)" if self._kind == "fixed" else f" ({self._kind})"
            entry = SessionEntry(src, id=self._log_id, path=self._folder + f"#{self._kind}",
                                 name=name, color=self._color)
            entry.ensure([])
            entry.cache_built = missing
            self.sigProgress.emit(100)
            self.sigFinished.emit(self._log_id, entry.path, entry)
        except Exception as exc:
            self.error.emit(self._folder, str(exc))


class SessionWindowThread(QThread):
    """Loads a new view window for one session entry off the GUI thread."""
    sigDone = Signal(str, object)

    def __init__(self, entry: SessionEntry, params, t0: float, t1: float, level: int, parent=None):
        super().__init__(parent)
        self._entry, self._params, self._t0, self._t1, self._level = entry, list(params), t0, t1, level

    def run(self):
        try:
            w = self._entry.load(self._params, self._t0, self._t1, self._level)
        except Exception as exc:
            w = exc
        self.sigDone.emit(self._entry.id, w)
