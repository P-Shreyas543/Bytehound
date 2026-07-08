"""Auto-extracted mixin."""

from __future__ import annotations
import time
from datetime import datetime
from collections import deque
from typing import Optional, List, Tuple, Deque

from ..decoder.frame_decoder import DecodedFrame, DecodedSignal, decode_frame
from ..protocol.packet_parser import ParsedPacket
from .logging_session import _format_number


class TelemetryPipelineMixin:
    """Mixin for MainWindow."""

    def _on_packets_received(self, batch: list) -> None:
        """Slot called by the worker's batch signal. Queues for the 60Hz UI timer.

        The underlying deque is bounded (maxlen=10_000) so a stalled Qt event
        loop cannot cause an OOM crash — oldest packets are silently dropped.
        """
        self._pending_packets.extend(batch)

    def _flush_ui(self) -> None:
        """Drain the pending packet queue and refresh the UI at 60 Hz.

        The session clock and rate label are updated on EVERY tick (even when
        no packets arrived) so the clock doesn't freeze during device timeouts.
        """
        try:
            self._flush_ui_inner()
        except Exception:
            # Never let a single bad batch kill the 60 Hz timer.
            import logging
            logging.getLogger("bytehound.ui").exception(
                "_flush_ui recovered from unexpected error"
            )

    def _flush_ui_inner(self) -> None:
        """Actual flush implementation, called by _flush_ui with protection."""
        # Update the session elapsed clock unconditionally (cheap string op).
        if self._session_started is not None and hasattr(self, '_session_clock_label'):
            elapsed = int((datetime.now() - self._session_started).total_seconds())
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            self._session_clock_label.setText(f"\u23f1 {h}:{m:02d}:{s:02d}")

        # --- Drain packet queue ---
        # Atomic swap: replace the shared deque with a fresh one so the worker
        # thread's extend() never races with our iteration.  CPython's GIL
        # makes a single attribute assignment atomic.
        pending = self._pending_packets
        self._pending_packets = deque(maxlen=10_000)
        if not pending:
            return

        self._staged_signals_for_ui = {}
        packets = list(pending)
        # Buffer all per-packet console rows so we can emit ONE
        # appendPlainText per flush instead of one per packet. At 1 kHz RX
        # this drops the Qt block-layout cost by ~50x.
        self._console_buffer: List[str] = []
        # Worker pushes (ParsedPacket, DecodedFrame|None) tuples; legacy
        # bare-ParsedPacket items are normalised here so _handle_packet
        # doesn't have to branch.
        for item in packets:
            if isinstance(item, tuple):
                packet, pre_decoded = item
            else:
                packet, pre_decoded = item, None
            try:
                self._handle_packet(packet, pre_decoded=pre_decoded)
            except Exception:
                import logging
                logging.getLogger("bytehound.ui").exception(
                    "_handle_packet raised on frame_id=0x%04X",
                    getattr(packet, 'frame_id', 0),
                )
        if self._console_buffer:
            sb = self._console.verticalScrollBar()
            at_bottom = sb.value() >= sb.maximum() - 4
            self._console.appendPlainText("\n".join(self._console_buffer))
            self._console_buffer.clear()
            if not at_bottom:
                sb.setValue(sb.value())
        if hasattr(self, "_pending_console_lines") and self._pending_console_lines:
            lines = self._pending_console_lines
            self._pending_console_lines = []
            sb = self._console.verticalScrollBar()
            at_bottom = sb.value() >= sb.maximum() - 4
            self._console.appendPlainText("\n".join(lines))
            if not at_bottom:
                sb.setValue(sb.value())
        # Counts label is rebuilt once per flush — the worker pushes the
        # authoritative wire-level counters via metrics_updated at ~10 Hz,
        # and _handle_packet only mutates the UI-side _packet_count. One
        # refresh per flush is plenty and saves ~50 string rebuilds/batch.
        self._refresh_counts_label()
        # Commit all staged model cell updates in ONE dataChanged per row.
        self._table_model.commit_staged()
        # Redraw the plot once for the entire batch.
        now = time.monotonic()
        if (now - self._plot_last_redraw) >= self._plot_redraw_interval_s:
            self._redraw_plot()
            self._plot_last_redraw = now
        # Invalidate the hover crosshair cache now that plot_history has changed
        if hasattr(self, "_hover_cache"):
            self._hover_cache.clear()

        # Update detail tabs and editors ONLY for the latest signals in the batch
        bf_dock = getattr(self, "_bitfields_dock", None)
        en_dock = getattr(self, "_enums_dock", None)
        bf_visible = bf_dock is None or bf_dock.isVisible()
        en_visible = en_dock is None or en_dock.isVisible()
        detail_tabs_visible = bf_visible or en_visible

        for signal in self._staged_signals_for_ui.values():
            if detail_tabs_visible:
                self._update_detail_tabs(signal, bf_visible=bf_visible, en_visible=en_visible)

            value_text = "-" if signal.scaled_value is None else _format_number(signal.scaled_value)
            for val_item in getattr(self, "_editor_value_items", {}).get(signal.signal_name, ()):
                val_item.setText(signal.display_value or value_text)

        self._staged_signals_for_ui.clear()

        # Packet rate readout in the plot toolbar — refreshed at most ~4 Hz
        # so the label doesn't flicker. Uses a 1-second sliding-sum window.
        if hasattr(self, "_rate_label"):
            now = time.monotonic()
            if not hasattr(self, "_rate_window"):
                self._rate_window: Deque[Tuple[float, int]] = deque()
                self._rate_last_redraw = now
            self._rate_window.append((now, len(packets)))
            # Drop entries older than 1 second.
            cutoff = now - 1.0
            while self._rate_window and self._rate_window[0][0] < cutoff:
                self._rate_window.popleft()
            if (now - self._rate_last_redraw) >= 0.25:
                hz = sum(c for _, c in self._rate_window)
                self._rate_label.setText(f"{hz} Hz")
                self._rate_last_redraw = now

    def _handle_packet(
        self,
        packet: ParsedPacket,
        pre_decoded: Optional[DecodedFrame] = None,
    ) -> None:
        if hasattr(self, "_polling_action") and not self._polling_action.isChecked():
            self._unsolicited_detected = True
        self._packet_count += 1
        now = time.perf_counter()
        if self._last_packet_perf is not None:
            self._delta_t_ms = (now - self._last_packet_perf) * 1000.0
        self._last_packet_perf = now
        # Buffer the console line. _flush_ui appends them all in one shot.
        # Skip the whole console pipeline when the dock is hidden: the
        # datetime.strftime + hex.upper formatting is ~10 µs per packet
        # which dominates the per-packet UI cost at 1 kHz. Same UX
        # contract as the plot — re-opening shows fresh content from
        # re-open time forward.
        if not packet.ok:
            # Worker is the single source of truth for the CRC error count
            # and pushes it via metrics_updated → _on_metrics_updated.
            return

        # Reset LED to green when data is flowing again after a timeout.
        if self._serial is not None:
            current_tooltip = self._led_label.toolTip()
            if current_tooltip == "Connected (No Data)":
                self._led_label.setStyleSheet("color: #66BB6A;")
                self._led_label.setToolTip("Connected")
                self._set_status("Connected")

        if self._config is None:
            return
        # The worker thread already decoded for us so the GUI thread doesn't
        # block on decode work. The rare worker-decode-error fallback path
        # goes through decode_frame here.
        if not hasattr(self, "_signal_state"):
            self._signal_state = {}
        decoded = pre_decoded if pre_decoded is not None else decode_frame(
            self._config, packet.frame_id, packet.payload, self._signal_state
        )
        self._apply_decoded(decoded)
        if self._decoded_logger:
            # Use the monotonic clock for elapsed_ms — wall-clock arithmetic
            # would skip or go backward if the system clock is corrected by
            # NTP during the session. Fall back to a freshly-sampled baseline
            # only if logging started before _log_started_perf was captured
            # (defensive — should not happen with the current Start path).
            if self._log_started_perf is not None:
                elapsed_ms = int((time.perf_counter() - self._log_started_perf) * 1000)
            else:
                t0 = self._log_started or self._session_started
                elapsed_ms = int((datetime.now() - t0).total_seconds() * 1000)
            self._decoded_logger.log_frame(decoded, elapsed_ms)

    def _add_signal_row(
        self,
        row: int,  # kept for API compatibility but ignored (model appends)
        frame_id: Optional[int],
        signal_name: str,
        group: str,
        start_byte: int,
        data_type: str,
        unit: str,
        is_calculated: bool = False,
    ) -> None:
        """Add a new row to the telemetry model (called for runtime-discovered signals)."""
        key = ("calc", signal_name) if is_calculated else (frame_id, signal_name)
        self._signal_unit_map[key] = unit
        self._table_model.add_row(
            key=key,
            frame_hex=f"0x{frame_id:04X}" if frame_id is not None else "-",
            group=group or "-",
            signal_name=signal_name,
            start_byte=str(start_byte),
            data_type=data_type or "-",
            unit=unit,
            is_calculated=is_calculated,
        )

    def _apply_decoded(self, decoded: DecodedFrame) -> None:
        if decoded.error is not None:
            # Decode-time issues (e.g. "no signals configured for frame_id …")
            # are surfaced in the console for the user to investigate. They are
            # NOT counted in the status-bar "Errors" tally — that field tracks
            # wire-level CRC failures only.
            self._console.appendPlainText(f"[decode] {decoded.error}")
            return
        for w in decoded.warnings:
            key = (w.frame_id, w.kind, w.offset if w.offset is not None else -1)
            if key in self._seen_decode_warnings:
                continue
            self._seen_decode_warnings.add(key)
            tail = f"  tail@byte{w.offset}: {w.extra_hex}" if w.extra_hex else ""
            self._log_activity(f"[DECODE WARN] {w.message}{tail}")
            self._console.appendPlainText(f"[decode warning] {w.message}")

        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        # Evaluate Auto-Pause / Triggered Logging if armed
        trigger_hit = False
        if self._plot_trigger is not None:
            trigger = self._plot_trigger
            op = trigger["op"]
            t_val = trigger["value"]
            for sig in [*decoded.signals, *decoded.calculations]:
                if sig.status == "ok" and sig.signal_name == trigger["param"]:
                    v = sig.scaled_value if sig.scaled_value is not None else sig.raw_value
                    if v is not None:
                        if (op == ">" and v > t_val) or \
                           (op == "<" and v < t_val) or \
                           (op == "==" and v == t_val) or \
                           (op == ">=" and v >= t_val) or \
                           (op == "<=" and v <= t_val) or \
                           (op == "!=" and v != t_val):
                            trigger_hit = True
                            break

        if trigger_hit:
            trigger_cfg = self._plot_trigger
            self._plot_trigger = None  # Disarm after triggering once

            if trigger_cfg.get("pause") and self._plot_live:
                self._set_plot_live(False, source="trigger")
                self._log_activity("[ACTION] Plot auto-paused by trigger")

            if trigger_cfg.get("log") and not self._raw_logger:
                self._on_toggle_logging()  # Start logging
                self._log_activity("[ACTION] Logging auto-started by trigger")

            # Update trigger button UI if it exists
            if hasattr(self, "_trigger_btn"):
                self._trigger_btn.setText("Trigger...")
                self._trigger_btn.setStyleSheet("")
                self._trigger_btn.setToolTip("Configure auto-pause trigger")

        # Evaluate Fault Alarms (check enum and bitfields for 'fault' or 'error')
        if not hasattr(self, "_fault_str_cache"):
            self._fault_str_cache = {}

        for sig in decoded.signals:
            if sig.status == "ok":
                fault_detected = False
                if sig.enum_label:
                    is_fault = self._fault_str_cache.get(sig.enum_label)
                    if is_fault is None:
                        is_fault = "fault" in sig.enum_label.lower() or "error" in sig.enum_label.lower()
                        self._fault_str_cache[sig.enum_label] = is_fault
                    if is_fault:
                        fault_detected = True
                elif sig.bit_values:
                    for bit_name, is_set in sig.bit_values.items():
                        if is_set:
                            is_fault = self._fault_str_cache.get(bit_name)
                            if is_fault is None:
                                is_fault = "fault" in bit_name.lower() or "error" in bit_name.lower()
                                self._fault_str_cache[bit_name] = is_fault
                            if is_fault:
                                fault_detected = True
                                break
                if fault_detected:
                    key = (sig.frame_id, sig.signal_name)
                    # Use a separate set to debounce fault notifications so we don't spam the UI
                    if not hasattr(self, "_seen_faults"):
                        self._seen_faults = set()
                    if key not in self._seen_faults:
                        self._seen_faults.add(key)
                        self._console.appendPlainText(f"[FAULT ALARM] {sig.signal_name}: {sig.display_value}")
                        self._log_activity(f"[ALARM] Fault detected on {sig.signal_name}: {sig.display_value}")

        plot_visible = getattr(self, "_plot_dock", None) is None or self._plot_dock.isVisible()
        if plot_visible:
            elapsed = (datetime.now() - self._session_started).total_seconds()
        for signal in [*decoded.signals, *decoded.calculations]:
            key = ("calc", signal.signal_name) if signal.is_calculated else (signal.frame_id, signal.signal_name)
            # If the key isn't in the model yet, add it (calculated / late-arriving signals)
            if self._table_model.row_for_key(key) is None:
                spec = next(
                    (s for s in self._config.all_signals
                     if s.frame_id == signal.frame_id and s.signal_name == signal.signal_name),
                    None,
                )
                self._add_signal_row(
                    0,  # ignored by model-backed version
                    None if signal.is_calculated else signal.frame_id,
                    signal.signal_name,
                    signal.group,
                    spec.start_byte if spec else 0,
                    spec.data_type if spec else "-",
                    signal.unit,
                    signal.is_calculated,
                )

            if signal.raw_value is None and not signal.is_calculated:
                continue

            raw_text = "-" if signal.raw_value is None else _format_number(signal.raw_value)
            value_text = "-" if signal.scaled_value is None else _format_number(signal.scaled_value)
            self._table_model.stage_live_cells(
                key,
                raw=raw_text,
                value=signal.display_value or value_text,
                status=self._status_text(signal),
                updated=timestamp,
            )

            if hasattr(self, "_staged_signals_for_ui"):
                self._staged_signals_for_ui[key] = signal

            if plot_visible and signal.scaled_value is not None and signal.status == "ok":
                self._plot_history[key].append(elapsed, signal.scaled_value)

    def _status_text(self, signal: DecodedSignal) -> str:
        if signal.enum_label:
            return f"{signal.status}: {signal.enum_label}"
        if signal.bit_values:
            active = [name for name, active_state in signal.bit_values.items() if active_state]
            return f"{signal.status}: {', '.join(active) if active else 'None'}"
        return signal.status
