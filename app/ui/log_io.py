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
    sigProgress = Signal(int)                # Progress percentage (0-100)
    error = Signal(str, str)                # (path, error_message)

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
            else:
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

    def _load_csv(self):
        """Parse a legacy _decoded.csv file (pre-xlsx Bytehound versions)."""
        import pandas as pd
        try:
            df = pd.read_csv(self._path, comment='#')
        except Exception as e:
            self.error.emit(self._path, f"Failed to parse CSV: {e}")
            return

        if df.empty:
            self.error.emit(self._path, "No data rows found in CSV.")
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

    def _load_xlsx(self):
        """Parse a .xlsx file. Supports three schemas using high-performance pandas."""
        import pandas as pd
        sheet_candidates, col_candidates, scale_mapping = self._get_schema_settings()
        try:
            xls = pd.ExcelFile(self._path)
            sheet = None
            for cand in sheet_candidates:
                if cand in xls.sheet_names:
                    sheet = cand
                    break
            if not sheet:
                sheet = 'Data' if 'Data' in xls.sheet_names else ('Record' if 'Record' in xls.sheet_names else xls.sheet_names[0])
            df = pd.read_excel(xls, sheet_name=sheet)
        except Exception as e:
            self.error.emit(self._path, f"Failed to parse Excel: {e}")
            return

        if df.empty:
            self.error.emit(self._path, "No data rows found.")
            return

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
