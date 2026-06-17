"""Detail-tabs / group-filter methods extracted from MainWindow.

DetailTabsMixin holds the methods that maintain the bitfield/enum detail
tables (row upsert + per-tick refresh) and the group-filter row-visibility
logic shared by both detail tables. Designed to be mixed into MainWindow.
"""

from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

from ..decoder.frame_decoder import DecodedSignal


class DetailTabsMixin:
    """MainWindow mixin holding detail-tab + group-filter methods."""

    def _update_detail_tabs(
        self,
        signal: DecodedSignal,
        *,
        bf_visible: bool = True,
        en_visible: bool = True,
    ) -> None:
        """Refresh the Bitfields / Enums dock rows for *signal*.

        Each branch is gated on the caller-supplied visibility flag so a
        hidden dock pays no QTableWidgetItem allocations. The caller
        (``_apply_decoded``) reads the flags once per packet and forwards
        them; that keeps the visibility check off the inner loop's hot
        per-signal path even when the call IS made.
        """
        if bf_visible and signal.bit_values:
            group = self._signal_group_map.get((signal.frame_id, signal.signal_name), "")
            bf_selected = (
                self._bitfield_group_combo.selected_groups()
                if hasattr(self, "_bitfield_group_combo") else set()
            )
            bf_row_visible = self._row_visible_for_group(bf_selected, group)
            for bit_name, active in signal.bit_values.items():
                key = (f"0x{signal.frame_id:04X}", signal.signal_name, bit_name)
                self._upsert_detail_row(
                    self._bitfield_table,
                    self._bitfield_row_index,
                    key,
                    [f"0x{signal.frame_id:04X}", signal.signal_name, bit_name, "ON" if active else "OFF"],
                    last_values=self._bitfield_last_values,
                )
                row = self._bitfield_row_index.get("\x1f".join(key))
                if row is not None:
                    self._bitfield_table.setRowHidden(row, not bf_row_visible)
        if en_visible and signal.enum_label:
            group = self._signal_group_map.get((signal.frame_id, signal.signal_name), "")
            en_selected = (
                self._enum_group_combo.selected_groups()
                if hasattr(self, "_enum_group_combo") else set()
            )
            en_row_visible = self._row_visible_for_group(en_selected, group)
            key = (f"0x{signal.frame_id:04X}", signal.signal_name)
            self._upsert_detail_row(
                self._enum_table,
                self._enum_row_index,
                key,
                [
                    f"0x{signal.frame_id:04X}",
                    signal.signal_name,
                    "" if signal.raw_value is None else str(signal.raw_value),
                    signal.enum_label,
                ],
                last_values=self._enum_last_values,
            )
            row = self._enum_row_index.get("\x1f".join(key))
            if row is not None:
                self._enum_table.setRowHidden(row, not en_row_visible)

    def _upsert_detail_row(
        self,
        table: QTableWidget,
        row_index: Dict[str, int],
        key: tuple[str, ...],
        values: list[str],
        last_values: Optional[Dict[str, tuple[str, ...]]] = None,
    ) -> None:
        """Insert-or-update a row in *table*, looked up via *row_index* in O(1).

        *row_index* maps the joined-key string to the table row number. The
        caller is responsible for clearing it whenever ``table.setRowCount(0)``
        runs (see :meth:`_on_clear`).

        When *last_values* is supplied, the row's previous value tuple is
        cached there and unchanged updates short-circuit before touching Qt —
        critical at 100 Hz where most bitfield bits stay stable packet-to-packet.
        """
        key_text = "\x1f".join(key)
        values_tuple = tuple(values)
        if last_values is not None and last_values.get(key_text) == values_tuple:
            return
        row = row_index.get(key_text)
        if row is not None and row < table.rowCount():
            # Update existing items in place instead of allocating new
            # QTableWidgetItems every packet. Falls back to setItem only if
            # an item happens to be missing.
            for col, value in enumerate(values):
                item = table.item(row, col)
                if item is None:
                    table.setItem(row, col, QTableWidgetItem(value))
                elif item.text() != value:
                    item.setText(value)
            first = table.item(row, 0)
            if first is not None:
                first.setData(Qt.ItemDataRole.UserRole, key_text)
            if last_values is not None:
                last_values[key_text] = values_tuple
            return
        row = table.rowCount()
        table.insertRow(row)
        for col, value in enumerate(values):
            table.setItem(row, col, QTableWidgetItem(value))
        table.item(row, 0).setData(Qt.ItemDataRole.UserRole, key_text)
        row_index[key_text] = row
        if last_values is not None:
            last_values[key_text] = values_tuple

    def _populate_group_selector(self) -> None:
        if self._config is None:
            return
        groups = sorted({signal.group for signal in self._config.all_signals if signal.group})
        self._group_combo.set_groups(groups)

        has_groups = len(groups) > 0
        if hasattr(self, "_group_label"):
            self._group_label.setVisible(has_groups)
        if hasattr(self, "_group_combo"):
            self._group_combo.setVisible(has_groups)
        if hasattr(self, "_table"):
            self._table.setColumnHidden(1, not has_groups)

        # Refresh the per-(frame,signal) → group lookup used by the dock filters.
        self._signal_group_map = {
            (s.frame_id, s.signal_name): (s.group or "")
            for s in self._config.all_signals
        }
        # Each dock combo lists only groups whose signals actually belong to
        # that dock — listing groups that can never produce a row is noise.
        bitfield_keys = set(self._config.bitfields.keys())
        enum_keys = set(self._config.enums.keys())
        bitfield_groups = sorted({
            s.group for s in self._config.all_signals
            if s.group and (s.frame_id, s.signal_name) in bitfield_keys
        })
        enum_groups = sorted({
            s.group for s in self._config.all_signals
            if s.group and (s.frame_id, s.signal_name) in enum_keys
        })
        # Independent combos in each dock — both reset to "All" on config load.
        # After that they behave independently of the main combo.
        if hasattr(self, "_bitfield_group_combo"):
            self._bitfield_group_combo.set_groups(bitfield_groups)
        has_bf_groups = len(bitfield_groups) > 0
        if hasattr(self, "_bitfield_group_label"):
            self._bitfield_group_label.setVisible(has_bf_groups)
        if hasattr(self, "_bitfield_group_combo"):
            self._bitfield_group_combo.setVisible(has_bf_groups)

        if hasattr(self, "_enum_group_combo"):
            self._enum_group_combo.set_groups(enum_groups)
        has_en_groups = len(enum_groups) > 0
        if hasattr(self, "_enum_group_label"):
            self._enum_group_label.setVisible(has_en_groups)
        if hasattr(self, "_enum_group_combo"):
            self._enum_group_combo.setVisible(has_en_groups)

    def _row_visible_for_group(self, selected: set, group: str) -> bool:
        return (not selected) or (group in selected)

    def _apply_bitfield_group_filter(self) -> None:
        selected = self._bitfield_group_combo.selected_groups()
        self._bitfield_table.setUpdatesEnabled(False)
        try:
            for key_text, row in self._bitfield_row_index.items():
                parts = key_text.split("\x1f")
                if len(parts) < 2:
                    continue
                try:
                    frame_id = int(parts[0], 16)
                except ValueError:
                    continue
                group = self._signal_group_map.get((frame_id, parts[1]), "")
                self._bitfield_table.setRowHidden(
                    row, not self._row_visible_for_group(selected, group)
                )
        finally:
            self._bitfield_table.setUpdatesEnabled(True)

    def _apply_enum_group_filter(self) -> None:
        selected = self._enum_group_combo.selected_groups()
        self._enum_table.setUpdatesEnabled(False)
        try:
            for key_text, row in self._enum_row_index.items():
                parts = key_text.split("\x1f")
                if len(parts) < 2:
                    continue
                try:
                    frame_id = int(parts[0], 16)
                except ValueError:
                    continue
                group = self._signal_group_map.get((frame_id, parts[1]), "")
                self._enum_table.setRowHidden(
                    row, not self._row_visible_for_group(selected, group)
                )
        finally:
            self._enum_table.setUpdatesEnabled(True)

    def _apply_group_filter(self) -> None:
        selected_groups = self._group_combo.selected_groups()   # empty set = All
        search_text = ""
        if hasattr(self, "_search_input"):
            search_text = self._search_input.text().lower()

        show_calcs = self._show_calcs_check.isChecked()
        n = self._table_model.row_count()
        # Suppress per-row repaints — a single update at the end is 50x cheaper
        # for tables with 500+ signals.
        self._table.setUpdatesEnabled(False)
        try:
            for row in range(n):
                row_group   = self._table_model.group_for_row(row)
                row_name    = self._table_model.signal_name_for_row(row).lower()
                is_calculated = self._table_model.is_calculated_row(row)

                # Empty selected_groups means "All"
                if selected_groups:
                    visible = row_group in selected_groups
                else:
                    visible = True
                if is_calculated and not show_calcs:
                    visible = False
                if search_text and search_text not in row_name:
                    visible = False

                self._table.setRowHidden(row, not visible)
        finally:
            self._table.setUpdatesEnabled(True)

