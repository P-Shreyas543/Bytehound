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
    SAFETY_TRIP = "SAFETY_TRIP"
    TEST_COMPLETED = "TEST_COMPLETED"
    PING = "PING"


@dataclass
class WebhookSettings:
    url: str = ""
    enabled: bool = False
    notify_test_started: bool = True
    notify_safety_trip: bool = True
    notify_test_completed: bool = True
    operator_tag: str = "Shreyas P"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "enabled": self.enabled,
            "notify_test_started": self.notify_test_started,
            "notify_safety_trip": self.notify_safety_trip,
            "notify_test_completed": self.notify_test_completed,
            "operator_tag": self.operator_tag,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WebhookSettings:
        return cls(
            url=data.get("url", ""),
            enabled=data.get("enabled", False),
            notify_test_started=data.get("notify_test_started", True),
            notify_safety_trip=data.get("notify_safety_trip", True),
            notify_test_completed=data.get("notify_test_completed", True),
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

    def _enqueue(self, payload: Dict[str, Any]) -> None:
        try:
            self._queue.put_nowait((self.settings.url, payload))
        except queue.Full:
            logger.warning("Webhook dispatch queue full; dropping notification.")

    def close(self) -> None:
        self._is_running = False
