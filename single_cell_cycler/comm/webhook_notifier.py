"""Remote Lab Webhook Notification Dispatcher (IMP-13).

Provides asynchronous, non-blocking webhook notifications for Discord, Slack, and Microsoft Teams.
Notifies laboratory engineers on Test Start, Safety Trips, and Test Completion.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("SingleCellCycler.WebhookNotifier")

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "webhook_settings.json"


class NotificationEvent(Enum):
    TEST_STARTED = "TEST_STARTED"
    STEP_COMPLETED = "STEP_COMPLETED"
    CYCLE_COMPLETED = "CYCLE_COMPLETED"
    TEST_PAUSED = "TEST_PAUSED"
    TEST_RESUMED = "TEST_RESUMED"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    SAFETY_TRIP = "SAFETY_TRIP"
    TEST_COMPLETED = "TEST_COMPLETED"
    PING = "PING"


@dataclass
class WebhookSettings:
    url: str = ""
    enabled: bool = False
    notify_test_started: bool = True
    notify_step_completed: bool = True
    notify_cycle_completed: bool = True
    notify_safety_trip: bool = True
    notify_test_completed: bool = True
    notify_test_paused_resumed: bool = True
    notify_emergency_stop: bool = True
    operator_tag: str = "Shreyas P"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "enabled": self.enabled,
            "notify_test_started": self.notify_test_started,
            "notify_step_completed": self.notify_step_completed,
            "notify_cycle_completed": self.notify_cycle_completed,
            "notify_safety_trip": self.notify_safety_trip,
            "notify_test_completed": self.notify_test_completed,
            "notify_test_paused_resumed": self.notify_test_paused_resumed,
            "notify_emergency_stop": self.notify_emergency_stop,
            "operator_tag": self.operator_tag,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WebhookSettings:
        return cls(
            url=data.get("url", ""),
            enabled=data.get("enabled", False),
            notify_test_started=data.get("notify_test_started", True),
            notify_step_completed=data.get("notify_step_completed", True),
            notify_cycle_completed=data.get("notify_cycle_completed", True),
            notify_safety_trip=data.get("notify_safety_trip", True),
            notify_test_completed=data.get("notify_test_completed", True),
            notify_test_paused_resumed=data.get("notify_test_paused_resumed", True),
            notify_emergency_stop=data.get("notify_emergency_stop", True),
            operator_tag=data.get("operator_tag", "Shreyas P"),
        )

    def save(self, path: Path = CONFIG_PATH) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Could not save webhook config: {exc}")

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> WebhookSettings:
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return cls.from_dict(data)
        except Exception as exc:
            logger.warning(f"Could not load webhook config: {exc}")
        return cls()


def _format_duration(seconds: float) -> str:
    s = int(max(0.0, seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m:02d}m {sec:02d}s"
    elif m > 0:
        return f"{m}m {sec:02d}s"
    else:
        return f"{seconds:.1f}s"


def build_universal_payload(
    event: NotificationEvent,
    title: str,
    description: str,
    fields: List[Dict[str, str]],
    color: int,
) -> Dict[str, Any]:
    """Construct multi-platform payload compatible with Discord, Slack, and generic webhooks."""
    # Discord format (embeds)
    discord_embed = {
        "title": title,
        "description": description,
        "color": color,
        "fields": [{"name": f["name"], "value": f["value"], "inline": True} for f in fields],
        "footer": {"text": "Bytehound Single-Cell BMS Cycler"},
        "timestamp": datetime.now().isoformat(),
    }

    # Slack format (attachments/blocks)
    slack_attachment = {
        "color": f"#{color:06x}",
        "title": title,
        "text": description,
        "fields": [{"title": f["name"], "value": f["value"], "short": True} for f in fields],
        "footer": "Bytehound Single-Cell BMS Cycler",
        "ts": int(time.time()),
    }

    return {
        # Discord native fields — used by Discord webhooks
        "content": f"**[Bytehound Lab Alert]** {title}",
        "embeds": [discord_embed],
        # Slack plain-text fallback — only Slack reads "text"; Discord ignores it
        "text": f"[Bytehound Lab Alert] {title} — {description}",
    }


class WebhookNotifier:
    """Non-blocking background thread notifier sending HTTP POST payloads to webhook endpoints."""

    def __init__(self, settings: Optional[WebhookSettings] = None):
        self.settings = settings or WebhookSettings.load()
        self._queue: queue.Queue = queue.Queue(maxsize=100)
        self._thread: Optional[threading.Thread] = None
        self._is_running = True

        self._start_worker()

    def _start_worker(self) -> None:
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def _worker_loop(self) -> None:
        while self._is_running:
            try:
                url, payload = self._queue.get(timeout=0.5)
                self._post_http(url, payload)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as exc:
                logger.error(f"Unexpected worker error: {exc}")

    def _post_http(self, url: str, payload: Dict[str, Any], timeout_s: float = 4.0) -> Tuple[bool, str]:
        """Synchronously dispatch HTTP POST request with short timeout."""
        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_data,
                headers={
                    "Content-Type": "application/json",
                    # Discord's Cloudflare WAF blocks non-browser User-Agents (error 1010).
                    # Using a standard browser UA string bypasses the bot protection.
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                status = resp.status
                if 200 <= status < 300:
                    logger.info(f"Webhook notification delivered successfully (HTTP {status}).")
                    return True, f"HTTP {status} OK"
                else:
                    msg = f"Webhook returned unexpected status HTTP {status}"
                    logger.warning(msg)
                    return False, msg
        except urllib.error.HTTPError as exc:
            msg = f"HTTP Error {exc.code}: {exc.reason}"
            logger.warning(f"Webhook dispatch failed: {msg}")
            return False, msg
        except urllib.error.URLError as exc:
            msg = f"Network Error: {exc.reason}"
            logger.warning(f"Webhook dispatch failed: {msg}")
            return False, msg
        except Exception as exc:
            msg = f"Error: {exc}"
            logger.warning(f"Webhook dispatch failed: {msg}")
            return False, msg

    def send_ping(self) -> Tuple[bool, str]:
        """Synchronously test configured webhook endpoint."""
        if not self.settings.url:
            return False, "No Webhook URL configured."
        operator = self.settings.operator_tag or "Shreyas P"
        payload = build_universal_payload(
            event=NotificationEvent.PING,
            title="🔔 Webhook Ping Test",
            description=f"Diagnostic test signal dispatched from Bytehound Cycler workstation by **{operator}**.",
            fields=[
                {"name": "Status", "value": "✅ Online"},
                {"name": "Operator", "value": operator},
                {"name": "Time", "value": datetime.now().strftime("%H:%M:%S")},
                {"name": "Workstation", "value": "Bytehound BMS Lab"},
            ],
            color=0x38BDF8,  # Sky blue
        )
        return self._post_http(self.settings.url, payload, timeout_s=4.0)

    def notify_test_started(
        self,
        cell_id: int,
        recipe_name: str,
        chemistry: str,
        steps_count: int,
    ) -> None:
        if not self.settings.enabled or not self.settings.notify_test_started or not self.settings.url:
            return
        payload = build_universal_payload(
            event=NotificationEvent.TEST_STARTED,
            title=f"▶ Test Started: Cell {cell_id}",
            description=f"Automated test profile commenced on channel **Cell {cell_id}**.",
            fields=[
                {"name": "Recipe", "value": recipe_name},
                {"name": "Chemistry", "value": chemistry},
                {"name": "Total Steps", "value": str(steps_count)},
                {"name": "Operator", "value": self.settings.operator_tag or "Lab Technician"},
            ],
            color=0x22C55E,  # Emerald Green
        )
        self._enqueue(payload)

    def notify_safety_trip(
        self,
        cell_id: int,
        trip_reason: str,
        voltage_v: float,
        current_a: float,
        temp_c: float,
    ) -> None:
        if not self.settings.enabled or not self.settings.notify_safety_trip or not self.settings.url:
            return
        payload = build_universal_payload(
            event=NotificationEvent.SAFETY_TRIP,
            title=f"🛑 SAFETY TRIP ALERT: Cell {cell_id}",
            description=f"CRITICAL: The hardware cycler safety interlock tripped on **Cell {cell_id}**! De-energization dispatched.",
            fields=[
                {"name": "Trip Reason", "value": trip_reason},
                {"name": "Cell Voltage", "value": f"{voltage_v:.3f} V"},
                {"name": "Current", "value": f"{current_a:+.3f} A"},
                {"name": "Peak Temperature", "value": f"{temp_c:.1f} °C"},
            ],
            color=0xEF4444,  # Red / Danger
        )
        self._enqueue(payload)

    def notify_test_completed(
        self,
        cell_id: int,
        recipe_name: str,
        cycles_count: int,
        final_cap_mah: float,
        energy_wh: float,
        duration_s: float,
    ) -> None:
        if not self.settings.enabled or not self.settings.notify_test_completed or not self.settings.url:
            return
        hours = duration_s / 3600.0
        payload = build_universal_payload(
            event=NotificationEvent.TEST_COMPLETED,
            title=f"✓ Test Completed: Cell {cell_id}",
            description=f"Battery qualification cycling completed on **Cell {cell_id}**.",
            fields=[
                {"name": "Recipe", "value": recipe_name},
                {"name": "Cycles Completed", "value": str(cycles_count)},
                {"name": "Final Capacity", "value": f"{final_cap_mah:.1f} mAh"},
                {"name": "Total Energy", "value": f"{energy_wh:.2f} Wh"},
                {"name": "Duration", "value": f"{hours:.2f} hours"},
            ],
            color=0x38BDF8,  # Sky blue
        )
        self._enqueue(payload)

    def notify_step_completed(
        self,
        cell_id: int,
        cycle_idx: int,
        step_idx: int,
        step_name: str,
        step_type: str,
        next_step_desc: str,
        capacity_mah: float,
        energy_mwh: float,
        duration_s: float,
        end_voltage_v: float,
        peak_current_a: float,
        peak_temp_c: float,
        cutoff_reason: str = "",
        dcir_mohm: Optional[float] = None,
    ) -> None:
        """Dispatch detailed step transition notification with capacity, energy, and next step."""
        if not self.settings.enabled or not self.settings.notify_step_completed or not self.settings.url:
            return

        st_lower = str(step_type).lower()
        if "charge" in st_lower:
            color = 0x6366F1  # Indigo
            type_icon = "⚡"
            cap_sign = "+"
        elif "discharge" in st_lower:
            color = 0x06B6D4  # Cyan
            type_icon = "🔋"
            cap_sign = "-"
        else:
            color = 0x64748B  # Slate
            type_icon = "⏸"
            cap_sign = ""

        fields = [
            {"name": "Next Step", "value": next_step_desc or "Advancing..."},
            {"name": "Step Capacity", "value": f"{cap_sign}{abs(capacity_mah):.1f} mAh"},
            {"name": "Step Energy", "value": f"{abs(energy_mwh) / 1000.0:.3f} Wh"},
            {"name": "Duration", "value": _format_duration(duration_s)},
            {"name": "End Voltage", "value": f"{end_voltage_v:.3f} V"},
            {"name": "Peak Current", "value": f"{peak_current_a:+.3f} A"},
            {"name": "Peak Temp", "value": f"{peak_temp_c:.1f} °C"},
            {"name": "Cutoff Trigger", "value": cutoff_reason or "Target Met"},
        ]
        if dcir_mohm is not None and dcir_mohm > 0.0:
            fields.append({"name": "DCIR Pulse", "value": f"{dcir_mohm:.2f} mΩ"})

        payload = build_universal_payload(
            event=NotificationEvent.STEP_COMPLETED,
            title=f"{type_icon} Step {step_idx} Completed: Cell {cell_id}",
            description=f"Cycle {cycle_idx} • Completed **{step_name}** ({step_type.upper()}).",
            fields=fields,
            color=color,
        )
        self._enqueue(payload)

    def notify_cycle_completed(
        self,
        cell_id: int,
        cycle_idx: int,
        total_cycles: int,
        charge_cap_mah: float,
        discharge_cap_mah: float,
        coulombic_eff_pct: float,
        energy_eff_pct: float,
        duration_s: float,
        dcir_mohm: Optional[float] = None,
    ) -> None:
        """Dispatch cycle qualification summary card."""
        if not self.settings.enabled or not self.settings.notify_cycle_completed or not self.settings.url:
            return

        fields = [
            {"name": "Cycle Progress", "value": f"Cycle {cycle_idx} of {total_cycles}"},
            {"name": "Charge Capacity", "value": f"{charge_cap_mah:.1f} mAh"},
            {"name": "Discharge Capacity", "value": f"{discharge_cap_mah:.1f} mAh"},
            {"name": "Coulombic Eff. (CE)", "value": f"{coulombic_eff_pct:.2f}%"},
            {"name": "Energy Eff. (EE)", "value": f"{energy_eff_pct:.2f}%"},
            {"name": "Cycle Duration", "value": _format_duration(duration_s)},
        ]
        if dcir_mohm is not None and dcir_mohm > 0.0:
            fields.append({"name": "Cycle DCIR", "value": f"{dcir_mohm:.2f} mΩ"})

        payload = build_universal_payload(
            event=NotificationEvent.CYCLE_COMPLETED,
            title=f"🔁 Cycle {cycle_idx} Summary: Cell {cell_id}",
            description=f"Completed Cycle {cycle_idx} on **Cell {cell_id}** with CE = **{coulombic_eff_pct:.2f}%**.",
            fields=fields,
            color=0xF59E0B,  # Amber Gold
        )
        self._enqueue(payload)

    def notify_test_paused(
        self,
        cell_id: int,
        step_name: str,
        voltage_v: float,
        current_a: float,
    ) -> None:
        """Dispatch notification when test is paused."""
        if not self.settings.enabled or not self.settings.notify_test_paused_resumed or not self.settings.url:
            return
        payload = build_universal_payload(
            event=NotificationEvent.TEST_PAUSED,
            title=f"⏸ Test Paused: Cell {cell_id}",
            description=f"Cycling test on **Cell {cell_id}** was **paused** by `{self.settings.operator_tag or 'Operator'}`.",
            fields=[
                {"name": "Active Step", "value": step_name},
                {"name": "Voltage", "value": f"{voltage_v:.3f} V"},
                {"name": "Current", "value": f"{current_a:+.3f} A"},
                {"name": "Timestamp", "value": datetime.now().strftime("%H:%M:%S")},
            ],
            color=0xF97316,  # Orange
        )
        self._enqueue(payload)

    def notify_test_resumed(
        self,
        cell_id: int,
        step_name: str,
        voltage_v: float,
        current_a: float,
    ) -> None:
        """Dispatch notification when test is resumed."""
        if not self.settings.enabled or not self.settings.notify_test_paused_resumed or not self.settings.url:
            return
        payload = build_universal_payload(
            event=NotificationEvent.TEST_RESUMED,
            title=f"▶ Test Resumed: Cell {cell_id}",
            description=f"Cycling test on **Cell {cell_id}** was **resumed** by `{self.settings.operator_tag or 'Operator'}`.",
            fields=[
                {"name": "Active Step", "value": step_name},
                {"name": "Voltage", "value": f"{voltage_v:.3f} V"},
                {"name": "Current", "value": f"{current_a:+.3f} A"},
                {"name": "Timestamp", "value": datetime.now().strftime("%H:%M:%S")},
            ],
            color=0x10B981,  # Emerald
        )
        self._enqueue(payload)

    def notify_emergency_stop(
        self,
        cell_id: int,
        step_name: str,
        voltage_v: float,
        current_a: float,
    ) -> None:
        """Dispatch critical notification when emergency stop is pushed."""
        if not self.settings.enabled or not self.settings.notify_emergency_stop or not self.settings.url:
            return
        payload = build_universal_payload(
            event=NotificationEvent.EMERGENCY_STOP,
            title=f"🛑 EMERGENCY STOP: Cell {cell_id}",
            description=f"CRITICAL: Manual Emergency Stop dispatched by `{self.settings.operator_tag or 'Operator'}`! Relays isolated.",
            fields=[
                {"name": "Cell", "value": f"Cell {cell_id}"},
                {"name": "Last Active Step", "value": step_name},
                {"name": "Cell Voltage", "value": f"{voltage_v:.3f} V"},
                {"name": "Current", "value": f"{current_a:+.3f} A"},
                {"name": "Timestamp", "value": datetime.now().strftime("%H:%M:%S")},
            ],
            color=0xDC2626,  # Red
        )
        self._enqueue(payload)

    def _enqueue(self, payload: Dict[str, Any]) -> None:
        try:
            self._queue.put_nowait((self.settings.url, payload))
        except queue.Full:
            logger.warning("Webhook dispatch queue full; dropping notification.")

    def close(self) -> None:
        self._is_running = False
