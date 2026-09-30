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
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("SingleCellCycler.WebhookNotifier")

def _resolve_settings_path() -> Path:
    """Per-machine webhook settings (they contain a secret URL, so they are never bundled or tracked).

    Installed app: %LOCALAPPDATA%\\Bytehound\\SingleCellCycler\\webhook_settings.json (the install
    folder under Program Files is read-only). Source tree: config/webhook_settings.json, which is
    git-ignored; config/webhook_settings.example.json is the tracked template.
    """
    import os
    import sys

    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Bytehound" / "SingleCellCycler" / "webhook_settings.json"
    return Path(__file__).resolve().parent.parent / "config" / "webhook_settings.json"


CONFIG_PATH = _resolve_settings_path()


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


# No URL is built into the source: a webhook URL contains a secret token. It lives only in
# config/webhook_settings.json (or is entered in the Webhook dialog).
DEFAULT_WEBHOOK_URL = ""
DEFAULT_OPERATOR_TAG = "Shreyas P"


@dataclass
class WebhookSettings:
    url: str = DEFAULT_WEBHOOK_URL
    enabled: bool = True
    notify_test_started: bool = True
    notify_step_completed: bool = True
    notify_cycle_completed: bool = True
    notify_safety_trip: bool = True
    notify_test_completed: bool = True
    notify_test_paused_resumed: bool = True
    notify_emergency_stop: bool = True
    operator_tag: str = DEFAULT_OPERATOR_TAG
    # Upload the run's CSV files (telemetry + step/cycle/dQ-dV summaries) when a test ends
    send_csv_on_test_end: bool = True
    # The protocol currently does not carry a BMS serial-number frame. This is
    # therefore user-configurable, with MainWindow supplying a USB/COM fallback.
    bms_serial_number: str = ""

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
            "bms_serial_number": self.bms_serial_number,
            "send_csv_on_test_end": self.send_csv_on_test_end,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WebhookSettings:
        raw_url = data.get("url", "")
        return cls(
            url=raw_url or DEFAULT_WEBHOOK_URL,
            enabled=data.get("enabled", True),
            notify_test_started=data.get("notify_test_started", True),
            notify_step_completed=data.get("notify_step_completed", True),
            notify_cycle_completed=data.get("notify_cycle_completed", True),
            notify_safety_trip=data.get("notify_safety_trip", True),
            notify_test_completed=data.get("notify_test_completed", True),
            notify_test_paused_resumed=data.get("notify_test_paused_resumed", True),
            notify_emergency_stop=data.get("notify_emergency_stop", True),
            operator_tag=data.get("operator_tag") or DEFAULT_OPERATOR_TAG,
            bms_serial_number=str(data.get("bms_serial_number") or "").strip(),
            send_csv_on_test_end=bool(data.get("send_csv_on_test_end", True)),
        )

    def save(self, path: Optional[Path] = None) -> None:
        path = Path(path) if path is not None else CONFIG_PATH   # resolved at call time
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Could not save webhook config: {exc}")

    @classmethod
    def load(cls, path: Optional[Path] = None) -> WebhookSettings:
        path = Path(path) if path is not None else CONFIG_PATH   # resolved at call time
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return cls.from_dict(data)
            else:
                default_settings = cls()
                default_settings.save(path)
                return default_settings
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


def _utc_timestamp() -> str:
    """Return an unambiguous UTC ISO-8601 timestamp for webhook consumers."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _local_timestamp() -> str:
    """Return a human-readable local timestamp including the timezone."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


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
        "timestamp": _utc_timestamp(),
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


# Discord rejects webhook uploads over 10 MB per message; stay safely under it
DISCORD_FILE_LIMIT_BYTES = 8 * 1024 * 1024


def _is_discord(url: str) -> bool:
    return "discord.com/api/webhooks" in url or "discordapp.com/api/webhooks" in url


def _block(lines: List[str]) -> str:
    """Monospace block for an embed field (Discord field values max 1024 chars)."""
    text = "\n".join(line for line in lines if line)
    return ("```\n" + text[:1000] + "\n```") if text else "—"


def package_run_files(
    csv_paths: List[Path], out_dir: Path, run_label: str, part_limit: int = DISCORD_FILE_LIMIT_BYTES
) -> List[Path]:
    """Zip a run's CSV files into one or more archives, each under part_limit bytes.

    Small files go into part 1 whole. A telemetry CSV too large for one archive is split by
    rows, repeating the header line, so every part opens on its own in Excel / pandas.
    """
    import zipfile

    out_dir.mkdir(parents=True, exist_ok=True)
    files = [Path(f) for f in csv_paths if f and Path(f).exists()]
    if not files:
        return []
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in run_label)[:80] or "run"
    parts: List[Path] = []
    part_no = 1
    current = out_dir / f"{safe}_part{part_no}.zip"
    zf = zipfile.ZipFile(current, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6)

    def _roll() -> None:
        nonlocal zf, current, part_no
        zf.close()
        parts.append(current)
        part_no += 1
        current = out_dir / f"{safe}_part{part_no}.zip"
        zf = zipfile.ZipFile(current, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6)

    # CSV compresses ~8-10x; budget raw bytes per archive conservatively at 5x the limit
    raw_budget = part_limit * 5
    for f in sorted(files, key=lambda x: x.stat().st_size):
        size = f.stat().st_size
        if size <= raw_budget // 2:
            zf.write(f, arcname=f.name)
            if current.stat().st_size > part_limit * 0.9:
                _roll()
            continue
        # large telemetry file: split by rows with the header repeated
        with f.open("r", encoding="utf-8", errors="replace") as src:
            header = src.readline()
            chunk_idx = 1
            buf: List[str] = [header]
            buf_bytes = len(header)
            for line in src:
                buf.append(line)
                buf_bytes += len(line)
                if buf_bytes >= raw_budget:
                    zf.writestr(f"{f.stem}_chunk{chunk_idx:03d}.csv", "".join(buf))
                    chunk_idx += 1
                    buf, buf_bytes = [header], len(header)
                    _roll()
            if len(buf) > 1:
                zf.writestr(f"{f.stem}_chunk{chunk_idx:03d}.csv", "".join(buf))
    zf.close()
    if zipfile.ZipFile(current).namelist():
        parts.append(current)
    else:
        current.unlink(missing_ok=True)
    return parts


class WebhookNotifier:
    """Non-blocking background thread notifier sending HTTP POST payloads to webhook endpoints."""

    def __init__(self, settings: Optional[WebhookSettings] = None):
        self.settings = settings or WebhookSettings.load()
        # Set by the main window: returns device identity + live readings for every message
        self.context_provider: Optional[Any] = None
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
                item = self._queue.get(timeout=0.5)
                if len(item) == 3:                       # ("files", url, (payload, [zip paths]))
                    _, url, (payload, zips) = item
                    self._post_files(url, payload, zips)
                else:
                    url, payload = item
                    self._post_with_retry(url, payload)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as exc:
                logger.error(f"Unexpected worker error: {exc}")

    def _post_with_retry(self, url: str, payload: Dict[str, Any], attempts: int = 3) -> None:
        """Retry transient webhook failures without blocking the application thread."""
        delay_s = 1.0
        for attempt in range(1, attempts + 1):
            success, message = self._post_http(url, payload)
            if success:
                return
            if attempt < attempts and self._is_running:
                logger.warning(f"Webhook attempt {attempt}/{attempts} failed; retrying in {delay_s:.1f}s: {message}")
                time.sleep(delay_s)
                delay_s *= 2.0
        logger.error(f"Webhook notification abandoned after {attempts} attempts: {message}")

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

    def _post_multipart(self, url: str, payload: Dict[str, Any], file_path: Path, timeout_s: float = 90.0) -> Tuple[bool, str]:
        """Discord webhook upload: multipart/form-data with payload_json + files[0]."""
        import uuid

        boundary = f"----BytehoundBoundary{uuid.uuid4().hex}"
        data = Path(file_path).read_bytes()
        body = b"".join([
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="payload_json"\r\n',
            b"Content-Type: application/json\r\n\r\n",
            json.dumps(payload).encode("utf-8"), b"\r\n",
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="files[0]"; filename="{Path(file_path).name}"\r\n'.encode(),
            b"Content-Type: application/zip\r\n\r\n",
            data, b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ])
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                if 200 <= resp.status < 300:
                    logger.info(f"Webhook file delivered: {Path(file_path).name} ({len(data) / 1024:.0f} KB)")
                    return True, f"HTTP {resp.status} OK"
                return False, f"HTTP {resp.status}"
        except urllib.error.HTTPError as exc:
            return False, f"HTTP Error {exc.code}: {exc.reason}"
        except Exception as exc:
            return False, f"Error: {exc}"

    def _post_files(self, url: str, payload: Dict[str, Any], zips: List[Path]) -> None:
        n = len(zips)
        for k, zp in enumerate(zips, start=1):
            part_payload = json.loads(json.dumps(payload))
            if n > 1:
                part_payload["content"] = f"{part_payload.get('content', '')} (part {k}/{n})"
            for attempt in range(1, 4):
                ok, msg = self._post_multipart(url, part_payload, zp)
                if ok:
                    break
                logger.warning(f"Webhook file upload {zp.name} attempt {attempt}/3 failed: {msg}")
                time.sleep(2.0 * attempt)
            else:
                logger.error(f"Webhook file upload abandoned: {zp.name}")

    def send_run_files(self, csv_paths: List[Path], end_status: str, work_dir: Path) -> None:
        """Queue the run's CSV files for upload when a test ends (Discord only).

        Other platforms' incoming webhooks cannot carry files; they get a message listing where
        the files are saved on the workstation instead.
        """
        if not (self.settings.enabled and self.settings.send_csv_on_test_end and self.settings.url):
            return
        files = [Path(f) for f in csv_paths if f and Path(f).exists()]
        if not files:
            return
        ctx = self._context()
        run_label = f"{ctx.get('run_id', 'run')}_Cell{ctx.get('cell', '')}_{self._bms_identity()}"
        listing = [f"{f.name}  ({f.stat().st_size / 1024:.0f} KB)" for f in files]
        payload = build_universal_payload(
            event=NotificationEvent.TEST_COMPLETED,
            title=f"📎 Test Data Files: Cell {ctx.get('cell', '?')}",
            description=f"Run data after **{end_status}**. CSV files are zipped; large telemetry is split into parts.",
            fields=[{"name": "Files", "value": _block(listing)}],
            color=0x64748B,
        )
        payload["embeds"][0]["fields"][0]["inline"] = False
        self._add_bms_identity(payload)
        self._decorate(payload)
        if not _is_discord(self.settings.url):
            payload["embeds"][0]["fields"].append(
                {"name": "Saved on workstation", "value": _block([str(files[0].parent)]), "inline": False}
            )
            self._queue_json(payload)
            return
        try:
            zips = package_run_files(files, Path(work_dir), run_label)
        except Exception as exc:
            logger.error(f"Could not package run files for webhook: {exc}")
            return
        try:
            self._queue.put_nowait(("files", self.settings.url, (payload, zips)))
        except queue.Full:
            logger.warning("Webhook dispatch queue full; dropping file upload.")

    def _context(self) -> Dict[str, Any]:
        if self.context_provider is None:
            return {}
        try:
            return dict(self.context_provider() or {})
        except Exception as exc:
            logger.debug(f"Webhook context provider failed: {exc}")
            return {}

    def _decorate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make every message identifiable at a glance and add device + live readings."""
        ctx = self._context()
        identity = self._bms_identity()
        cell = ctx.get("cell")
        host = ctx.get("host", "")
        embed = payload.get("embeds", [{}])[0]
        title = embed.get("title", "")
        tag = f"{identity} · Cell {cell}" if cell else identity
        embed["author"] = {"name": " · ".join(x for x in (tag, host, ctx.get("port", "")) if x)[:250]}
        payload["content"] = f"**[{tag}]** {title}" + (f" — {ctx['recipe']}" if ctx.get("recipe") else "")

        device = [
            f"BMS / Device : {identity}",
            f"Cell         : {cell}" if cell else "",
            f"Serial port  : {ctx.get('port', '')} {ctx.get('adapter', '')}".rstrip(),
            f"Workstation  : {host}" if host else "",
            f"Operator     : {self.settings.operator_tag}" if self.settings.operator_tag else "",
            f"Run ID       : {ctx.get('run_id', '')}" if ctx.get("run_id") else "",
            f"Recipe       : {ctx.get('recipe', '')}" if ctx.get("recipe") else "",
            f"Chemistry    : {ctx.get('chemistry', '')}" if ctx.get("chemistry") else "",
            f"App version  : {ctx.get('app_version', '')}" if ctx.get("app_version") else "",
            f"Local time   : {_local_timestamp()}",
        ]
        live = ctx.get("live_lines") or []
        fields = embed.setdefault("fields", [])
        fields.append({"name": "🔎 Device & Run", "value": _block(device), "inline": False})
        if live:
            fields.append({"name": "📊 Readings at this moment", "value": _block(live), "inline": False})
        del fields[25:]                                        # Discord: max 25 fields
        payload["text"] = f"[{tag}] {title} — " + " | ".join(x for x in device if x)
        return payload

    def notify_test_stopped(self, cell_id: int, step_name: str, reason: str = "Stopped by operator") -> None:
        """Operator pressed STOP: the run ended early (no message was sent for this before)."""
        if not self.settings.enabled or not self.settings.notify_test_completed or not self.settings.url:
            return
        payload = build_universal_payload(
            event=NotificationEvent.TEST_COMPLETED,
            title=f"⏹ Test Stopped: Cell {cell_id}",
            description=f"The test on **Cell {cell_id}** was stopped before completion. {reason}.",
            fields=[{"name": "Last Active Step", "value": step_name or "—"}],
            color=0x94A3B8,
        )
        self._enqueue(payload)

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
                {"name": "Time", "value": _local_timestamp()},
                {"name": "Workstation", "value": "Bytehound BMS Lab"},
            ],
            color=0x38BDF8,  # Sky blue
        )
        self._add_bms_identity(payload)
        self._decorate(payload)
        return self._post_http(self.settings.url, payload, timeout_s=8.0)

    def set_bms_serial_number(self, serial_number: str) -> None:
        """Set the identifier shown on subsequent alerts without forcing persistence."""
        self.settings.bms_serial_number = str(serial_number or "").strip()

    def _bms_identity(self) -> str:
        return self.settings.bms_serial_number.strip() or "Unknown / not configured"

    def _add_bms_identity(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Add the BMS identifier consistently to all platform payloads."""
        identity = self._bms_identity()
        embed = payload.get("embeds", [{}])[0]
        fields = embed.setdefault("fields", [])
        if not any(field.get("name") == "BMS Serial / Device ID" for field in fields):
            fields.insert(0, {"name": "BMS Serial / Device ID", "value": identity, "inline": True})
        payload["content"] = f"{payload.get('content', '')} [BMS: {identity}]"
        payload["text"] = f"{payload.get('text', '')} [BMS: {identity}]"
        return payload

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
        if st_lower == "charge":
            color = 0x6366F1  # Indigo
            type_icon = "⚡"
            cap_sign = "+"
        elif st_lower == "discharge":
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
                {"name": "Timestamp", "value": _local_timestamp()},
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
                {"name": "Timestamp", "value": _local_timestamp()},
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
                {"name": "Timestamp", "value": _local_timestamp()},
            ],
            color=0xDC2626,  # Red
        )
        self._enqueue(payload)

    def _enqueue(self, payload: Dict[str, Any]) -> None:
        self._add_bms_identity(payload)
        self._decorate(payload)
        self._queue_json(payload)

    def _queue_json(self, payload: Dict[str, Any]) -> None:
        try:
            self._queue.put_nowait((self.settings.url, payload))
        except queue.Full:
            logger.warning("Webhook dispatch queue full; dropping notification.")

    def close(self) -> None:
        self._is_running = False
