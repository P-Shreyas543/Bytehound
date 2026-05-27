"""Auto-extracted mixin."""

from __future__ import annotations
import struct
from typing import Dict, List
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QTableWidgetItem, QPushButton, QSizePolicy
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtCore import QLocale, Qt


class ParameterEditorMixin:
    """Mixin for MainWindow."""

    def _populate_editor_table(self) -> None:
        self._editor_table.setRowCount(0)
        # Index: signal_name -> list of value-cell QTableWidgetItem refs.
        # _apply_decoded looks rows up by name on every decoded signal of
        # every packet; a linear scan over rowCount() was O(rows * packets *
        # signals_per_packet) per UI flush. A dict turns that into O(1).
        self._editor_value_items: Dict[str, List[QTableWidgetItem]] = {}
        if not self._config:
            return
        # Filter out signals on rx-only frames — direction='rx' means we are
        # never supposed to TX to that frame, so the Parameter Editor must
        # not even surface those signals as writable. Unknown frames default
        # to rxtx (auto-created entries) so they stay visible.
        frames = self._config.frames
        rw_signals = [
            s for s in self._config.all_signals
            if s.read_write in ("W", "RW")
            and (frames.get(s.frame_id) is None or frames[s.frame_id].is_tx_capable)
        ]
        if not rw_signals:
            # Nothing writable — insert a single informational row
            self._editor_table.insertRow(0)
            lbl = QTableWidgetItem("No writable signals defined in this config (all are read-only).")
            lbl.setFlags(Qt.ItemFlag.NoItemFlags)
            self._editor_table.setItem(0, 0, lbl)
            self._editor_table.setSpan(0, 0, 1, 4)
            return
        _INT_TYPES = {"uint8", "int8", "uint16", "int16", "uint32", "int32"}
        for s in rw_signals:
            row = self._editor_table.rowCount()
            self._editor_table.insertRow(row)
            self._editor_table.setItem(row, 0, QTableWidgetItem(f"0x{s.frame_id:04X}"))
            self._editor_table.setItem(row, 1, QTableWidgetItem(s.signal_name))

            curr_val = QTableWidgetItem("-")
            curr_val.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._editor_table.setItem(row, 2, curr_val)
            self._editor_value_items.setdefault(s.signal_name, []).append(curr_val)

            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(2, 1, 2, 1)
            inp = QLineEdit()
            inp.setPlaceholderText("enter value…")

            lo = s.min_value
            hi = s.max_value
            if s.data_type in _INT_TYPES:
                ilo = int(lo) if lo is not None else -2_147_483_648
                ihi = int(hi) if hi is not None else  2_147_483_647
                inp.setValidator(QIntValidator(ilo, ihi))
                inp.setToolTip(f"Integer  [{ilo} … {ihi}]")
            else:
                flo = lo if lo is not None else -1e18
                fhi = hi if hi is not None else  1e18
                _dv = QDoubleValidator(flo, fhi, 6)
                _dv.setLocale(QLocale(QLocale.Language.C))
                inp.setValidator(_dv)
                inp.setToolTip(f"Float  [{flo:g} … {fhi:g}]")

            btn = QPushButton("Write")
            btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda _, inp=inp, s=s: self._on_editor_write(s, inp.text()))
            # Allow pressing Enter in the input to trigger write
            inp.returnPressed.connect(lambda inp=inp, s=s: self._on_editor_write(s, inp.text()))
            layout.addWidget(inp)
            layout.addWidget(btn)
            self._editor_table.setCellWidget(row, 3, widget)

    def _on_editor_write(self, signal, text: str) -> None:
        if not self._serial or not self._serial.is_open:
            self._popup_warning("Write", "Not connected")
            return
        try:
            val = float(text)
            if signal.min_value is not None and val < signal.min_value:
                raise ValueError(f"Min value is {signal.min_value}")
            if signal.max_value is not None and val > signal.max_value:
                raise ValueError(f"Max value is {signal.max_value}")
        except ValueError as e:
            self._popup_warning("Invalid Input", str(e))
            return

        from ..protocol.packet_builder import build_packet

        try:
            # Step 1: reverse scale/offset → raw = (user_value - offset) / scale
            raw = (val - signal.offset) / signal.scale

            # Step 2: encode raw into bytes per data_type and byte_order
            byteorder: str = signal.endianness   # "little" | "big"
            dt: str = signal.data_type            # "uint8", "int16", "float32", etc.

            if "float" in dt:
                fmt = ("<" if byteorder == "little" else ">") + (
                    "f" if signal.byte_length == 4 else "d"
                )
                encoded = struct.pack(fmt, float(raw))
            elif "int" in dt:
                signed = dt.startswith("int")
                encoded = round(raw).to_bytes(signal.byte_length, byteorder, signed=signed)
            else:
                raise ValueError(f"Unsupported data_type for write: {dt!r}")

            if len(encoded) != signal.byte_length:
                raise ValueError(
                    f"Encoded value is {len(encoded)} bytes but signal expects {signal.byte_length}"
                )

            # Step 3: place encoded bytes at start_byte in a zero-padded payload
            payload = bytearray(signal.end_byte)
            payload[signal.start_byte:signal.end_byte] = encoded

            # Step 4: wrap in the full packet envelope (header + CRC + footer)
            pkt = build_packet(self._config.protocol, signal.frame_id, bytes(payload))

        except (OverflowError, struct.error, ValueError) as exc:
            self._popup_warning("Write Error", str(exc))
            return

        self._serial.enqueue_priority_tx(pkt)
        self._log_activity(
            f"Write: {signal.signal_name} = {val} {signal.unit}  "
            f"(raw=0x{pkt.hex().upper()})"
        )
