"""Custom QAbstractTableModel for the main telemetry data table.

This model separates data storage from rendering, enabling the MainWindow
to batch-update multiple rows in a single model transaction rather than
re-painting the entire table on every packet received.

Column layout mirrors `_COLUMNS` in main_window.py:
    0  Frame      (frame_id as hex)
    1  Group
    2  Variable   (signal name)
    3  Start B.   (start byte)
    4  Data Type
    5  Raw        <<< live-updated
    6  Value      <<< live-updated
    7  Unit
    8  Status     <<< live-updated
    9  Updated    <<< live-updated
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
)
from PySide6.QtGui import QFont

# Columns that are populated once from config and never change.
_STATIC_COLS = {0, 1, 2, 3, 4, 7}
# Columns updated on every decoded frame.
_LIVE_COLS = {5, 6, 8, 9}

COLUMNS = (
    ("Frame",     100),
    ("Group",      90),
    ("Variable",  190),
    ("Start B.",   60),
    ("Data Type",  75),
    ("Raw",        95),
    ("Value",      95),
    ("Unit",       70),
    ("Status",    190),
    ("Updated",   110),
)
COLUMN_HEADERS = [c[0] for c in COLUMNS]
NUM_COLS = len(COLUMNS)

# Alignment per column index
_ALIGN: Dict[int, Qt.AlignmentFlag] = {
    3: Qt.AlignmentFlag.AlignRight  | Qt.AlignmentFlag.AlignVCenter,
    5: Qt.AlignmentFlag.AlignRight  | Qt.AlignmentFlag.AlignVCenter,
    6: Qt.AlignmentFlag.AlignRight  | Qt.AlignmentFlag.AlignVCenter,
    8: Qt.AlignmentFlag.AlignCenter,
}

# Foreground hint stored alongside each row for the "Status" column —
# kept as a plain string so the _StatusBadgeDelegate can paint over it.
_COL_STATUS = 8


class TelemetryTableModel(QAbstractTableModel):
    """Read-only model storing telemetry rows as plain lists of strings.

    Internal storage
    ----------------
    ``_rows``      – list of ``list[str]``  (one per signal, all columns)
    ``_row_index`` – ``dict[(frame_id, signal_name), int]``  for O(1) lookup
    ``_is_calc``   – ``dict[int, bool]``  whether a row is a calculated signal
    ``_key_at``    – ``list[tuple[int, str]]``  reverse map row → key
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: List[List[str]] = []
        self._row_index: Dict[Tuple[int, str], int] = {}
        self._is_calc: Dict[int, bool] = {}
        self._key_at: List[Tuple[int, str]] = []
        self._mono_font = QFont("Consolas", 10)
        # Staged (silent) updates accumulated during a 16ms batch;
        # maps row-index → (raw, value, status, updated) so that
        # only the *last* update for each row fires a single dataChanged.
        self._staged: Dict[int, Tuple[str, str, str, str]] = {}

    # ------------------------------------------------------------------
    # QAbstractTableModel required overrides
    # ------------------------------------------------------------------

    # B008: QModelIndex() in the default is the standard Qt-Python idiom and
    # matches the C++ Qt method signatures (`const QModelIndex &parent = QModelIndex()`).
    # An invalid QModelIndex is immutable for our purposes, so the "shared
    # mutable default" concern that B008 normally catches doesn't apply.
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # type: ignore[override]  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # type: ignore[override]  # noqa: B008
        return 0 if parent.isValid() else NUM_COLS

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            if 0 <= section < NUM_COLS:
                return COLUMN_HEADERS[section]
        return None

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if row >= len(self._rows) or col >= NUM_COLS:
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            return self._rows[row][col]

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return _ALIGN.get(col)

        if role == Qt.ItemDataRole.FontRole:
            return self._mono_font

        # UserRole on col 1 → is_calculated flag (for filter logic)
        if role == Qt.ItemDataRole.UserRole and col == 1:
            return self._is_calc.get(row, False)

        # UserRole on col 2 → (frame_id, signal_name) key tuple (for plot/context-menu)
        if role == Qt.ItemDataRole.UserRole and col == 2:
            if row < len(self._key_at):
                return self._key_at[row]

        return None

    def flags(
        self, index: QModelIndex | QPersistentModelIndex
    ) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    # ------------------------------------------------------------------
    # Public mutation API
    # ------------------------------------------------------------------

    def reset_from_config(
        self,
        rows: List[Dict[str, Any]],
    ) -> None:
        """Repopulate the entire model from a list of row descriptors.

        Each dict must have keys matching COLUMN_HEADERS (case-sensitive),
        plus optional ``is_calculated`` (bool) and ``key`` (tuple[int,str]).

        Call this when a new config is loaded.
        """
        self.beginResetModel()
        self._rows.clear()
        self._row_index.clear()
        self._is_calc.clear()
        self._key_at.clear()

        for i, descriptor in enumerate(rows):
            row_data = [str(descriptor.get(h, "-")) for h in COLUMN_HEADERS]
            self._rows.append(row_data)
            key: Tuple[int, str] = descriptor["key"]
            self._row_index[key] = i
            self._key_at.append(key)
            self._is_calc[i] = bool(descriptor.get("is_calculated", False))

        self.endResetModel()

    def update_live_cells(
        self,
        key: Tuple[int, str],
        raw: str,
        value: str,
        status: str,
        updated: str,
    ) -> bool:
        """Immediately update the four live columns and emit dataChanged.

        Use this for low-frequency one-shot updates (e.g. log replay).
        For high-frequency batched updates, prefer ``stage_live_cells`` +
        ``commit_staged`` to avoid emitting dozens of signals per row per
        flush cycle.

        Returns True if the key was found, False otherwise.
        """
        row = self._row_index.get(key)
        if row is None:
            return False
        data = self._rows[row]
        data[5] = raw
        data[6] = value
        data[8] = status
        data[9] = updated
        tl = self.index(row, 5)
        br = self.index(row, 9)
        self.dataChanged.emit(tl, br, [Qt.ItemDataRole.DisplayRole])
        return True

    def stage_live_cells(
        self,
        key: Tuple[int, str],
        raw: str,
        value: str,
        status: str,
        updated: str,
    ) -> bool:
        """Silently write to ``_rows`` WITHOUT emitting dataChanged.

        If the same key is staged multiple times inside one flush cycle, the
        last write wins and only ONE dataChanged will be emitted when
        ``commit_staged()`` is called — eliminating per-packet Qt signal
        overhead when many packets update the same row.

        Returns True if the key was found.
        """
        row = self._row_index.get(key)
        if row is None:
            return False
        data = self._rows[row]
        data[5] = raw
        data[6] = value
        data[8] = status
        data[9] = updated
        self._staged[row] = (raw, value, status, updated)
        return True

    def commit_staged(self) -> None:
        """Emit one dataChanged per affected row and clear the staged set.

        Call this once at the end of each 16ms batch flush — not per packet.
        """
        if not self._staged:
            return
        for row in self._staged:
            tl = self.index(row, 5)
            br = self.index(row, 9)
            self.dataChanged.emit(tl, br, [Qt.ItemDataRole.DisplayRole])
        self._staged.clear()

    def add_row(
        self,
        key: Tuple[int, str],
        frame_hex: str,
        group: str,
        signal_name: str,
        start_byte: str,
        data_type: str,
        unit: str,
        is_calculated: bool = False,
    ) -> int:
        """Append a new row (for signals discovered at runtime, not in config).

        Returns the new row index.
        """
        row = len(self._rows)
        self.beginInsertRows(QModelIndex(), row, row)
        row_data = [frame_hex, group, signal_name, start_byte, data_type,
                    "-", "-", unit, "-", "-"]
        self._rows.append(row_data)
        self._row_index[key] = row
        self._key_at.append(key)
        self._is_calc[row] = is_calculated
        self.endInsertRows()
        return row

    def clear_live_columns(self) -> None:
        """Reset all live columns to '-' (used by the Clear action)."""
        if not self._rows:
            return
        for row in self._rows:
            row[5] = "-"
            row[6] = "-"
            row[8] = "-"
            row[9] = "-"
        tl = self.index(0, 5)
        br = self.index(len(self._rows) - 1, 9)
        self.dataChanged.emit(tl, br, [Qt.ItemDataRole.DisplayRole])

    # ------------------------------------------------------------------
    # Convenience accessors (used by MainWindow for context-menu / copy)
    # ------------------------------------------------------------------

    def row_count(self) -> int:
        return len(self._rows)

    def cell_text(self, row: int, col: int) -> str:
        if 0 <= row < len(self._rows) and 0 <= col < NUM_COLS:
            return self._rows[row][col]
        return ""

    def key_for_row(self, row: int) -> Optional[Tuple[int, str]]:
        if 0 <= row < len(self._key_at):
            return self._key_at[row]
        return None

    def row_for_key(self, key: Tuple[int, str]) -> Optional[int]:
        return self._row_index.get(key)

    def is_calculated_row(self, row: int) -> bool:
        return self._is_calc.get(row, False)

    def group_for_row(self, row: int) -> str:
        return self.cell_text(row, 1)

    def signal_name_for_row(self, row: int) -> str:
        return self.cell_text(row, 2)
