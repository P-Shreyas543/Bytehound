"""Decoded signal log writer (.xlsx, two sheets, cycle-buffered wide format).

Output workbook
---------------
* ``Metadata`` – key/value rows describing the session (app, port, baud,
  config path, file names, start time, etc.).
* ``Data`` – one wide row per **complete poll cycle**. Columns are grouped
  per frame in ``FrameConfig.frames`` order. Each frame block starts with
  ``<FrameName>.elapsed_ms`` and ``<FrameName>.frame_id`` (the latter
  carries the ``0xNNNN`` literal so the frame is identifiable even after
  a column rename), followed by that frame's signal columns prefixed
  with ``<FrameName>.``. The next frame's block follows, and so on.

  Bitfield signals expand into one ``0``/``1`` column per defined bit
  (``<signal>.<bit_name>``) — no raw integer column.
  Enum signals keep their raw integer column and gain a sibling
  ``<signal>.label`` column with the decoded text.

  If two different frames define a signal with the same name, both
  columns are emitted in config order. Their header text is identical;
  internally each cell is independently addressable by column position
  so neither overwrites the other.

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
from ..decoder.types import BitfieldSpec, FrameConfig, SignalSpec

_LOG = logging.getLogger("bytehound.serial_logging.decoded")

ErrorCallback = Callable[[str], None]

# Internal slot keys for the per-frame buffer entry. Stored alongside the
# real column names so we can look up each frame's housekeeping column
# positions without re-formatting the prefix each time.
_SLOT_ELAPSED = "__elapsed_ms__"
_SLOT_FRAME_ID = "__frame_id__"


def _format_number(value: float | int) -> float | int:
    return value


def _signal_label(name: str, unit: str) -> str:
    return f"{name} ({unit})" if unit else name


def _bitfield_specs_for(config: FrameConfig, spec: SignalSpec) -> List[BitfieldSpec]:
    """Look up bitfield specs for *spec* using the same key fallback the decoder uses."""
    for name in (spec.source_name, spec.signal_name):
        if not name:
            continue
        specs = config.bitfields.get((spec.frame_id, name))
        if specs:
            return specs
    return []


def _is_enum_signal(config: FrameConfig, spec: SignalSpec) -> bool:
    for name in (spec.source_name, spec.signal_name):
        if name and (spec.frame_id, name) in config.enums:
            return True
    return False


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
            self._bit_columns_by_key,
            self._enum_label_col_by_key,
            self._block_by_frame,
            self._cycle_frame_ids,
        ) = self._build_columns()
        self._trigger_id: Optional[int] = (
            self._cycle_frame_ids[-1] if self._cycle_frame_ids else None
        )
        # Per-frame slot keyed by column POSITION (int), not name. Lets two
        # frames write into independently-positioned cells even if their
        # column headers happen to share the same text.
        self._cycle_buffer: Dict[int, Dict[int, Any]] = {}

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
            # Each frame has its own elapsed_ms and frame_id columns.
            if _SLOT_ELAPSED in block:
                slot[block[_SLOT_ELAPSED]] = elapsed_ms
            if _SLOT_FRAME_ID in block:
                slot[block[_SLOT_FRAME_ID]] = f"0x{decoded.frame_id:04X}"
            for signal in [*decoded.signals, *decoded.calculations]:
                key = (signal.frame_id, signal.signal_name)

                # Bitfield: one 0/1 cell per defined bit. No raw column.
                bit_cols = self._bit_columns_by_key.get(key)
                if bit_cols:
                    for bit_name, active in signal.bit_values.items():
                        pos = bit_cols.get(bit_name)
                        if pos is not None:
                            slot[pos] = 1 if active else 0
                    continue

                # Enum: raw value in the signal column, label in the sibling
                # `.label` column. Both written when available so unknown raw
                # values still appear in the raw column even if no label matches.
                label_pos = self._enum_label_col_by_key.get(key)
                if label_pos is not None:
                    raw_pos = self._column_by_key.get(key)
                    if raw_pos is not None and signal.raw_value is not None:
                        slot[raw_pos] = int(signal.raw_value)
                    if signal.enum_label is not None:
                        slot[label_pos] = signal.enum_label
                    continue

                # Scalar signal: write the scaled value as before.
                if signal.scaled_value is None:
                    continue
                pos = self._column_by_key.get(key)
                if pos is None:
                    continue
                slot[pos] = _format_number(signal.scaled_value)

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
        # Position-keyed merge: each frame writes into its own column slots,
        # so even when two frames share a header text they land in distinct
        # cells of the wide row.
        flat: Dict[int, Any] = {}
        for slot in self._cycle_buffer.values():
            flat.update(slot)
        self._data_ws.append([flat.get(i, "") for i in range(len(self._columns))])

    def _build_columns(
        self,
    ) -> Tuple[
        List[str],
        Dict[Tuple[int, str], int],
        Dict[Tuple[int, str], Dict[str, int]],
        Dict[Tuple[int, str], int],
        Dict[int, Dict[str, int]],
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

        # Every column in a frame's block carries a `<FrameName>.` prefix.
        # The block starts with elapsed_ms + frame_id housekeeping, then
        # signal/bit/enum columns. Slots are keyed by column POSITION so
        # duplicate header text from cross-frame collisions still maps to
        # independent cells.
        columns: List[str] = []
        column_by_key: Dict[Tuple[int, str], int] = {}
        bit_columns_by_key: Dict[Tuple[int, str], Dict[str, int]] = {}
        enum_label_col_by_key: Dict[Tuple[int, str], int] = {}
        block_by_frame: Dict[int, Dict[str, int]] = {}

        for frame_id in cycle_frame_ids:
            frame_name = (
                self._config.frame_names.get(frame_id)
                or (self._config.frames[frame_id].frame_name if frame_id in self._config.frames else "")
                or f"0x{frame_id:04X}"
            )
            prefix = f"{frame_name}."

            elapsed_pos = len(columns)
            columns.append(f"{prefix}elapsed_ms")
            frame_id_pos = len(columns)
            columns.append(f"{prefix}frame_id")
            block: Dict[str, int] = {
                _SLOT_ELAPSED: elapsed_pos,
                _SLOT_FRAME_ID: frame_id_pos,
            }

            for spec in self._config.signals_by_frame.get(frame_id, []):
                bit_specs = _bitfield_specs_for(self._config, spec)
                if bit_specs:
                    # Bitfield: emit one 0/1 column per bit; no raw column.
                    bit_cols: Dict[str, int] = {}
                    for bit in bit_specs:
                        pos = len(columns)
                        columns.append(f"{prefix}{spec.signal_name}.{bit.bit_name}")
                        bit_cols[bit.bit_name] = pos
                    bit_columns_by_key[(frame_id, spec.signal_name)] = bit_cols
                    continue

                sig_label = f"{prefix}{_signal_label(spec.signal_name, spec.unit)}"
                pos = len(columns)
                columns.append(sig_label)
                column_by_key[(frame_id, spec.signal_name)] = pos
                block[spec.signal_name] = pos

                if _is_enum_signal(self._config, spec):
                    # Enum: add a sibling `.label` column next to the raw value.
                    label_pos = len(columns)
                    columns.append(f"{prefix}{spec.signal_name}.label")
                    enum_label_col_by_key[(frame_id, spec.signal_name)] = label_pos

            for calc in self._config.calc_groups:
                if calc.frame_id is not None:
                    if calc.frame_id != frame_id:
                        continue
                elif frame_id not in frames_by_group.get(calc.group, []):
                    continue
                signal_name = f"{calc.group} {calc.stat}"
                calc_label = f"{prefix}{_signal_label(signal_name, calc.unit)}"
                pos = len(columns)
                columns.append(calc_label)
                column_by_key[(frame_id, signal_name)] = pos
                block[signal_name] = pos

            block_by_frame[frame_id] = block

        return (
            columns,
            column_by_key,
            bit_columns_by_key,
            enum_label_col_by_key,
            block_by_frame,
            cycle_frame_ids,
        )

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
