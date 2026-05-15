"""Decoded signal log writer (.xlsx, two sheets, cycle-buffered wide format).

Output workbook
---------------
* ``Metadata`` – key/value rows describing the session (app, port, baud,
  config path, file names, start time, etc.).
* ``Data`` – one wide row per **complete poll cycle**. Each frame in the
  config gets its own column block:
  ``<frame>.elapsed_ms | <frame>.frame_id | <frame>.<signal 1> | …``.
  Frames are emitted in the order they appear in ``FrameConfig.frames``.

Cycle Buffer pattern
--------------------
Frames arrive one at a time and each is stashed in an in-memory buffer
keyed by ``frame_id``. When the **trigger frame** (the last frame in the
config order) arrives, the buffer is checked: if every configured frame
has been seen since the previous emit, one wide row is appended to the
Data sheet. The buffer is **always cleared on trigger arrival** so a
later cycle never carries stale values forward; incomplete cycles are
dropped silently.

Persistence trade-off
---------------------
openpyxl write-only mode streams rows into the workbook in memory but
only persists to disk on :meth:`close`. A crash before Stop Logging
loses the decoded workbook; the raw CSV (streamed) is unaffected and can
be replayed to regenerate the decoded values.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from openpyxl import Workbook

from ..decoder.frame_decoder import DecodedFrame
from ..decoder.types import FrameConfig

_LOG = logging.getLogger("bytehound.serial_logging.decoded")

ErrorCallback = Callable[[str], None]

# Internal slot keys for the per-frame buffer entry. Stored alongside the
# real column names so we can look up the elapsed_ms / frame_id columns
# without re-formatting the frame label each time.
_SLOT_ELAPSED = "__elapsed_ms__"
_SLOT_FRAME_ID = "__frame_id__"


def _format_number(value: float | int) -> float | int:
    return value


def _signal_label(name: str, unit: str) -> str:
    return f"{name} ({unit})" if unit else name


class DecodedLogger:
    METADATA_SHEET = "Metadata"
    DATA_SHEET = "Data"

    def __init__(
        self,
        path: str | Path,
        config: FrameConfig,
        *,
        flush_interval: float = 0.5,
        metadata: Mapping[str, str] | None = None,
        on_error: ErrorCallback | None = None,
    ) -> None:
        self.path = Path(path)
        self._config = config
        self._workbook: Optional[Workbook] = None
        self._data_ws = None
        self._metadata = dict(metadata) if metadata else {}
        self._on_error = on_error
        self._disabled = False

        (
            self._columns,
            self._column_by_key,
            self._block_by_frame,
            self._cycle_frame_ids,
        ) = self._build_columns()
        self._trigger_id: Optional[int] = (
            self._cycle_frame_ids[-1] if self._cycle_frame_ids else None
        )
        self._cycle_buffer: Dict[int, Dict[str, Any]] = {}

        # Kept for API compatibility; xlsx output cannot flush incrementally.
        self._flush_interval = float(flush_interval)

    def __enter__(self) -> "DecodedLogger":
        self.open()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def open(self) -> None:
        if self._disabled:
            return
        if self._workbook is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)

        wb = Workbook(write_only=True)
        meta_ws = wb.create_sheet(title=self.METADATA_SHEET)
        meta_ws.append(["Key", "Value"])
        for key in sorted(self._metadata):
            value = str(self._metadata[key]).replace("\n", " ").strip()
            meta_ws.append([key, value])

        data_ws = wb.create_sheet(title=self.DATA_SHEET)
        data_ws.append(self._columns)

        self._workbook = wb
        self._data_ws = data_ws

    def close(self) -> None:
        if self._workbook is None:
            return
        try:
            self._workbook.save(self.path)
        except Exception as exc:
            self._handle_error("save", exc)
        finally:
            try:
                self._workbook.close()
            except Exception:
                pass
            self._workbook = None
            self._data_ws = None
            self._cycle_buffer.clear()

    def set_flush_interval(self, seconds: float) -> None:
        try:
            self._flush_interval = max(0.0, float(seconds))
        except (TypeError, ValueError):
            self._flush_interval = 0.5

    def log_frame(
        self,
        decoded: DecodedFrame,
        elapsed_ms: int,
        timestamp: datetime | None = None,
    ) -> None:
        if self._disabled:
            return
        try:
            if self._workbook is None:
                self.open()
            if self._data_ws is None:
                return

            block = self._block_by_frame.get(decoded.frame_id)
            if block is None:
                # Frame not represented in the schema — nothing to do.
                return

            slot = self._cycle_buffer.setdefault(decoded.frame_id, {})
            slot[block[_SLOT_ELAPSED]] = elapsed_ms
            slot[block[_SLOT_FRAME_ID]] = f"0x{decoded.frame_id:04X}"
            for signal in [*decoded.signals, *decoded.calculations]:
                if signal.scaled_value is None:
                    continue
                col = self._column_by_key.get((signal.frame_id, signal.signal_name))
                if col is None:
                    continue
                slot[col] = _format_number(signal.scaled_value)

            if self._trigger_id is not None and decoded.frame_id == self._trigger_id:
                self._maybe_emit_row()
                # Always clear so the next cycle starts fresh — no stale carry-over.
                self._cycle_buffer.clear()
        except Exception as exc:
            self._handle_error("write", exc)

    def _maybe_emit_row(self) -> None:
        """Emit the cycle row only when every configured frame is present."""
        if self._data_ws is None:
            return
        if not all(fid in self._cycle_buffer for fid in self._cycle_frame_ids):
            return
        flat: Dict[str, Any] = {}
        for slot in self._cycle_buffer.values():
            flat.update(slot)
        self._data_ws.append([flat.get(col, "") for col in self._columns])

    def _build_columns(
        self,
    ) -> Tuple[
        List[str],
        Dict[Tuple[int, str], str],
        Dict[int, Dict[str, str]],
        List[int],
    ]:
        # Cycle frames = configured frames that have at least one signal,
        # in the order they appear in FrameConfig.frames (insertion order).
        cycle_frame_ids = [
            fid
            for fid in self._config.frames.keys()
            if self._config.signals_by_frame.get(fid)
        ]

        # Map each calc group name to the frame ids that contribute signals
        # to it, used to fan calc_groups (with no explicit frame_id) into the
        # right per-frame blocks.
        frames_by_group: Dict[str, List[int]] = {}
        for spec in self._config.all_signals:
            if not spec.group:
                continue
            frames = frames_by_group.setdefault(spec.group, [])
            if spec.frame_id not in frames:
                frames.append(spec.frame_id)

        columns: List[str] = []
        column_by_key: Dict[Tuple[int, str], str] = {}
        block_by_frame: Dict[int, Dict[str, str]] = {}

        for frame_id in cycle_frame_ids:
            label = self._config.frame_names.get(frame_id) or f"0x{frame_id:04X}"
            elapsed_col = f"{label}.elapsed_ms"
            frame_id_col = f"{label}.frame_id"
            columns.extend([elapsed_col, frame_id_col])
            block: Dict[str, str] = {
                _SLOT_ELAPSED: elapsed_col,
                _SLOT_FRAME_ID: frame_id_col,
            }

            for spec in self._config.signals_by_frame.get(frame_id, []):
                sig_label = _signal_label(spec.signal_name, spec.unit)
                col = f"{label}.{sig_label}"
                columns.append(col)
                column_by_key[(frame_id, spec.signal_name)] = col
                block[spec.signal_name] = col

            for calc in self._config.calc_groups:
                if calc.frame_id is not None:
                    if calc.frame_id != frame_id:
                        continue
                elif frame_id not in frames_by_group.get(calc.group, []):
                    continue
                signal_name = f"{calc.group} {calc.stat}"
                calc_label = _signal_label(signal_name, calc.unit)
                col = f"{label}.{calc_label}"
                columns.append(col)
                column_by_key[(frame_id, signal_name)] = col
                block[signal_name] = col

            block_by_frame[frame_id] = block

        return columns, column_by_key, block_by_frame, cycle_frame_ids

    def _handle_error(self, context: str, exc: Exception) -> None:
        if self._disabled:
            return
        self._disabled = True
        try:
            if self._workbook is not None:
                self._workbook.close()
        except Exception:
            pass
        self._workbook = None
        self._data_ws = None
        self._cycle_buffer.clear()
        _LOG.error("DecodedLogger %s error", context, exc_info=True)
        if self._on_error is not None:
            self._on_error(f"Decoded log {context} error for {self.path.name}: {exc}")
