"""Auto-extracted mixin."""

from __future__ import annotations
import time
from datetime import datetime
from collections import deque
from typing import Optional, List, Tuple, Deque

from ..decoder.frame_decoder import DecodedFrame, DecodedSignal, decode_frame
from ..protocol.packet_parser import ParsedPacket
from .config_loader import format_display_data_type
from .logging_session import _format_number

# Most RX lines the console shows per second; the rest are counted, not drawn.
CONSOLE_LINES_PER_SECOND = 400
# Most GUI-thread time one UI flush spends on queued packets. The rest stay
# queued for the next tick: draining a large backlog in one call stalled
# the event loop for 0.1-1.5 s at 5,000 frames/s (tools/gui_latency_probe.py).
# Display only: the session log is written on arrival, before this queue.
FLUSH_BUDGET_S = 0.025


class TelemetryPipelineMixin:
    """Mixin for MainWindow."""

    BACKPRESSURE_HIGH_WATERMARK = 4000
    BACKPRESSURE_LOW_WATERMARK = 1000

    # ------------------------------------------------------------------
    # Session / log clocks. Everything runs on time.perf_counter(), the
    # clock the worker stamps each read with, so plot X values and log
    # elapsed_ms reflect when bytes arrived, not when the UI got to them.
    # ------------------------------------------------------------------

    def _reset_session_clock(self) -> None:
        self._session_started = datetime.now()
        self._session_started_perf = time.perf_counter()
        # Gap times are on this clock: a new clock starts without them (U2).
        if hasattr(self, "_clear_plot_gaps"):
            self._clear_plot_gaps()

    def _session_elapsed_s(self, t_perf: Optional[float] = None) -> float:
        start = getattr(self, "_session_started_perf", None)
        if start is None:
            self._reset_session_clock()
            start = self._session_started_perf
        return (time.perf_counter() if t_perf is None else t_perf) - start

    def _log_elapsed_ms(self, t_perf: Optional[float] = None) -> int:
        now = time.perf_counter() if t_perf is None else t_perf
        if getattr(self, "_log_started_perf", None) is not None:
            return int((now - self._log_started_perf) * 1000)
        return int(self._session_elapsed_s(now) * 1000)

    @staticmethod
    def _unpack_item(item) -> Tuple[ParsedPacket, Optional[DecodedFrame], Optional[float]]:
        """Worker items are (packet, decoded, rx_perf); older callers send
        (packet, decoded) or a bare packet."""
        if isinstance(item, tuple):
            if len(item) >= 3:
                return item[0], item[1], item[2]
            return item[0], item[1], None
        return item, None, None

    def _log_batch(self, batch: list) -> list:
        """Write a batch to the decoded log as soon as it arrives.

        Logging used to happen in the 60 Hz UI flush, after the bounded
        pending-packet queue: whenever the UI fell behind, the dropped packets
        were missing from the log too. Frames decoded here are passed on so
        the flush doesn't decode them again.
        """
        session = getattr(self, "_session_log", None)
        config = getattr(self, "_config", None)
        if session is None or config is None:
            return batch
        if getattr(getattr(self, "_serial", None), "logs_sessions", False):
            # The capture worker already wrote these frames on its thread.
            return batch
        out = []
        for item in batch:
            packet, decoded, rx_perf = self._unpack_item(item)
            t = rx_perf if rx_perf is not None else time.perf_counter()
            if getattr(packet, "ok", False) and packet.frame_id is not None:
                if decoded is None:
                    if not hasattr(self, "_signal_state"):
                        self._signal_state = {}
                    decoded = decode_frame(config, packet.frame_id, packet.payload, self._signal_state, t=t)
                session.log_frame(decoded, t)
            elif not getattr(packet, "ok", True):
                # Rejected frames (CRC / framing) are evidence, not noise: keep
                # them per segment with the reason (Plane.md F9).
                session.log_rejected(packet.raw, packet.frame_id, packet.error or "", t)
            out.append((packet, decoded, rx_perf))
        return out

    def _plot_redraw_due(self, now: float) -> bool:
        """When the live plot redraws (L2):

        * at most 30 times a second;
        * no more often than one pixel column of time: in a 5-minute window
          a pixel is ~0.3 s of data, so 30 redraws a second recomputed the
          same pixels ~10 times (capped at 10 redraws a second, so the
          newest point never lags by more than 0.1 s);
        * never more often than four times the last redraw's cost, so a
          heavy plot (many signals, hours of "All session") uses at most
          ~25 % of the GUI thread.
        """
        cost = getattr(self, "_plot_redraw_cost_s", 0.0)
        pixel = min(getattr(self, "_plot_pixel_time_s", 0.0), 0.1)
        interval = max(self._plot_redraw_interval_s, pixel, 4.0 * cost)
        return (now - self._plot_last_redraw) >= interval

    def _on_packets_received(self, batch: list) -> None:
        """Slot called by the worker's batch signal. Queues for the 60Hz UI timer.

        The underlying deque is bounded (maxlen=10_000) so a stalled Qt event
        loop cannot cause an OOM crash. When near capacity, backpressure throttling
        is signaled to the worker to pause autonomous polling.
        """
        batch = self._log_batch(batch)
        current_len = len(self._pending_packets)
        space_left = (self._pending_packets.maxlen - current_len) if self._pending_packets.maxlen else 10_000
        if len(batch) > space_left:
            dropped = len(batch) - space_left
            self._backpressure_dropped_count = getattr(self, "_backpressure_dropped_count", 0) + dropped
            # The oldest queued points are evicted: break every line there
            # rather than joining across the skipped points (live plot P4).
            for buf in getattr(self, "_plot_history", {}).values():
                buf.mark_break()
            # Once saturated this fired for every batch, and each log line was
            # a file write + flush on the GUI thread (seen in stall stacks).
            now = time.monotonic()
            if now - getattr(self, "_last_saturation_log", 0.0) >= 5.0:
                self._last_saturation_log = now
                import logging
                logging.getLogger("bytehound.ui").warning(
                    "UI event queue saturated: display skipped %d packets so far "
                    "(the session log is unaffected)", self._backpressure_dropped_count
                )

        self._pending_packets.extend(batch)

        # PuTTY-inspired backpressure signaling to the worker
        if len(self._pending_packets) >= self.BACKPRESSURE_HIGH_WATERMARK:
            if hasattr(self, "_serial") and self._serial is not None:
                if not getattr(self, "_ui_backpressured", False):
                    self._ui_backpressured = True
                    self._serial.set_backpressure(True)

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
            elapsed = int(self._session_elapsed_s())
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            self._session_clock_label.setText(f"\u23f1 {h}:{m:02d}:{s:02d}")

        # --- Drain packet queue ---
        # Atomic swap: replace the shared deque with a fresh one so the worker
        # thread's extend() never races with our iteration.  CPython's GIL
        # makes a single attribute assignment atomic.
        pending = self._pending_packets
        self._pending_packets = deque(maxlen=10_000)

        # Release backpressure once queue has been drained
        if getattr(self, "_ui_backpressured", False):
            if hasattr(self, "_serial") and self._serial is not None:
                self._ui_backpressured = False
                self._serial.set_backpressure(False)

        if not pending:
            return

        self._staged_signals_for_ui = {}
        packets = list(pending)
        # Buffer all per-packet console rows so we can emit ONE
        # appendPlainText per flush instead of one per packet. At 1 kHz RX
        # this drops the Qt block-layout cost by ~50x.
        self._console_buffer: List[str] = []
        console_dock = getattr(self, "_console_dock", None)
        console_visible = console_dock is not None and console_dock.isVisible()
        show_from = len(packets)
        if console_visible:
            # perf_counter → wall clock, once per flush
            wall_offset = time.time() - time.perf_counter()
            # Nobody reads thousands of lines a second, and formatting and
            # laying them out was most of the GUI thread's time at high
            # rates. Show the newest lines within budget and say how many
            # were skipped; logs and the raw capture keep every frame.
            now = time.monotonic()
            dt = now - getattr(self, "_console_last_flush", now - 1.0)
            self._console_last_flush = now
            budget = max(1, min(CONSOLE_LINES_PER_SECOND, int(CONSOLE_LINES_PER_SECOND * dt)))
            show_from = max(0, len(packets) - budget)
        # Worker pushes (ParsedPacket, DecodedFrame|None, rx_perf) tuples;
        # shorter legacy items are normalised so _handle_packet doesn't branch.
        deadline = time.perf_counter() + FLUSH_BUDGET_S
        processed = len(packets)
        for index, item in enumerate(packets):
            if index & 31 == 0 and index and time.perf_counter() > deadline:
                processed = index
                break
            packet, pre_decoded, rx_perf = self._unpack_item(item)
            if console_visible and index >= show_from and hasattr(packet, "raw"):
                ts = datetime.fromtimestamp(
                    (rx_perf if rx_perf is not None else time.perf_counter()) + wall_offset
                )
                self._console_buffer.append(
                    f"{ts.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}, RX, {packet.raw.hex(' ').upper()}"
                )
            try:
                self._handle_packet(packet, pre_decoded=pre_decoded, rx_perf=rx_perf)
            except Exception:
                import logging
                logging.getLogger("bytehound.ui").exception(
                    "_handle_packet raised on frame_id=0x%04X",
                    getattr(packet, 'frame_id', 0),
                )
        if processed < len(packets):
            # Out of budget: keep the rest, in order, ahead of anything newer.
            rest = deque(packets[processed:], maxlen=10_000)
            rest.extend(self._pending_packets)
            self._pending_packets = rest
        hidden = min(show_from, processed) if console_visible else 0
        if hidden:
            self._console_buffer.insert(0, (
                f"… {hidden} frames not shown (console limited to {CONSOLE_LINES_PER_SECOND}/s; "
                "logs and raw capture keep every frame)"
            ))
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
        # Format the newest value per row once, then commit all staged model
        # cell updates in ONE dataChanged per row.
        self._stage_table_cells()
        self._table_model.commit_staged()
        # Redraw the plot once for the entire batch.
        now = time.monotonic()
        if self._plot_redraw_due(now):
            t0 = time.perf_counter()
            self._redraw_plot()
            self._plot_redraw_cost_s = time.perf_counter() - t0
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
            disp_val = signal.display_value or value_text
            for val_item in getattr(self, "_editor_value_items", {}).get(signal.signal_name, ()):
                val_item.setText(disp_val)
            for tx_val_lbl in getattr(self, "_tx_current_value_labels", {}).get(signal.signal_name, ()):
                tx_val_lbl.setText(f"Current: {disp_val}")
            if hasattr(self, "_cards_view") and self._cards_view is not None:
                self._cards_view.update_signal_value(signal.signal_name, signal.scaled_value if signal.scaled_value is not None else "-", getattr(signal, "status", "ok"))

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
        rx_perf: Optional[float] = None,
    ) -> None:
        if hasattr(self, "_polling_action") and not self._polling_action.isChecked():
            self._unsolicited_detected = True
        self._packet_count += 1
        now = time.perf_counter()
        if self._last_packet_perf is not None:
            self._delta_t_ms = (now - self._last_packet_perf) * 1000.0
        self._last_packet_perf = now
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
        if not hasattr(self, "_latest_payload_by_frame"):
            self._latest_payload_by_frame = {}
        if packet.frame_id is not None:
            self._latest_payload_by_frame[packet.frame_id] = bytes(packet.payload)
            monitor = getattr(self, "_rate_monitor", None)
            if monitor:
                monitor.note(packet.frame_id, rx_perf if rx_perf is not None else now)
        if not hasattr(self, "_signal_state"):
            self._signal_state = {}
        decoded = pre_decoded if pre_decoded is not None else decode_frame(
            self._config, packet.frame_id, packet.payload, self._signal_state, t=rx_perf
        )
        # The decoded log was already written on arrival (_log_batch)
        self._apply_decoded(decoded, rx_perf=rx_perf)

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
        byte_length: int = 1,
        is_boolean: bool = False,
    ) -> None:
        """Add a new row to the telemetry model (called for runtime-discovered signals)."""
        key = ("calc", signal_name) if is_calculated else (frame_id, signal_name)
        self._signal_unit_map[key] = unit

        start_byte_str = "-" if is_calculated else str(start_byte)
        if is_calculated:
            data_type_str = "float"
        else:
            data_type_str = format_display_data_type(data_type, byte_length, is_boolean)

        self._table_model.add_row(
            key=key,
            frame_hex=f"0x{frame_id:04X}" if frame_id is not None else "-",
            group=group or "-",
            signal_name=signal_name,
            start_byte=start_byte_str,
            data_type=data_type_str,
            unit=unit,
            is_calculated=is_calculated,
        )

    def _apply_decoded(self, decoded: DecodedFrame, rx_perf: Optional[float] = None) -> None:
        if decoded.error is not None:
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

            if trigger_cfg.get("log") and not getattr(self, "_logging", False):
                started = self._start_logging_auto()
                if not started:
                    self._plot_trigger = trigger_cfg
                    return
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
                    if not hasattr(self, "_seen_faults"):
                        self._seen_faults = set()
                    if key not in self._seen_faults:
                        self._seen_faults.add(key)
                        self._console.appendPlainText(f"[FAULT ALARM] {sig.signal_name}: {sig.display_value}")
                        self._log_activity(f"[ALARM] Fault detected on {sig.signal_name}: {sig.display_value}")

        # History is recorded even while the Live Plot dock is hidden, so the
        # graph has no holes for the time it was tabbed away or collapsed.
        # Only the redraw is skipped when hidden.
        elapsed = self._session_elapsed_s(rx_perf)
        pending_cells = self.__dict__.setdefault("_pending_table_cells", {})
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
                    signal.frame_id,
                    signal.signal_name,
                    signal.group,
                    spec.start_byte if spec else 0,
                    spec.data_type if spec else "-",
                    signal.unit,
                    signal.is_calculated,
                    byte_length=spec.byte_length if spec else 1,
                    is_boolean=spec.is_boolean if spec else False,
                )

            if signal.raw_value is None and not signal.is_calculated:
                continue

            # Only the newest value per row is shown, so formatting waits for
            # the 60 Hz flush (_stage_table_cells) instead of running for
            # every packet.
            pending_cells[key] = signal

            if hasattr(self, "_staged_signals_for_ui"):
                self._staged_signals_for_ui[key] = signal

            if signal.scaled_value is not None and signal.status == "ok":
                self._plot_history[key].append(elapsed, signal.scaled_value)

    def _stage_table_cells(self) -> None:
        """Format and stage the newest decoded value for each table row."""
        pending = getattr(self, "_pending_table_cells", None)
        if not pending:
            return
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        for key, signal in pending.items():
            raw_text = "-" if signal.raw_value is None else _format_number(signal.raw_value)
            value_text = "-" if signal.scaled_value is None else _format_number(signal.scaled_value)
            if signal.is_calculated:
                table_value = value_text
            else:
                table_value = signal.display_value or value_text
                if signal.unit and table_value.endswith(f" {signal.unit}"):
                    table_value = table_value[: -len(f" {signal.unit}")].strip()
            self._table_model.stage_live_cells(
                key,
                raw=raw_text,
                value=table_value,
                status=self._status_text(signal),
                updated=timestamp,
            )
        pending.clear()

    def _status_text(self, signal: DecodedSignal) -> str:
        if signal.bit_values:
            active = [name for name, active_state in signal.bit_values.items() if active_state]
            return f"{signal.status}: {', '.join(active) if active else 'None'}"
        return signal.status
