"""Discord Bot — Remote Command & Control for Bytehound BMS Cycler (IMP-14).

Runs a Discord slash-command bot in a background asyncio thread alongside the Qt app.
Allows lab engineers to query live telemetry, control tests, and trigger reports
directly from any Discord channel — without being physically at the workstation.

Supported Slash Commands
-------------------------
/status        — Live cell voltage, current, temperature, SoC, and engine state
/pause         — Pause the active test step
/resume        — Resume a paused test step
/stop          — Emergency-stop the active test (safe de-energization)
/export        — Generate & upload the diagnostic run package URL
/report        — Generate the HTML certification report and post a link
/preflight     — Run hardware pre-flight sanity checks and post results
/help          — List all available commands
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

logger = logging.getLogger("SingleCellCycler.DiscordBot")

BOT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "discord_bot_settings.json"

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@dataclass
class DiscordBotSettings:
    token: str = ""
    enabled: bool = False
    operator_tag: str = "Shreyas P"
    # Which commands to allow
    allow_status: bool = True
    allow_pause: bool = True
    allow_resume: bool = True
    allow_stop: bool = True
    allow_export: bool = True
    allow_report: bool = True
    allow_preflight: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token": self.token,
            "enabled": self.enabled,
            "operator_tag": self.operator_tag,
            "allow_status": self.allow_status,
            "allow_pause": self.allow_pause,
            "allow_resume": self.allow_resume,
            "allow_stop": self.allow_stop,
            "allow_export": self.allow_export,
            "allow_report": self.allow_report,
            "allow_preflight": self.allow_preflight,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DiscordBotSettings:
        return cls(
            token=data.get("token", ""),
            enabled=data.get("enabled", False),
            operator_tag=data.get("operator_tag", "Shreyas P"),
            allow_status=data.get("allow_status", True),
            allow_pause=data.get("allow_pause", True),
            allow_resume=data.get("allow_resume", True),
            allow_stop=data.get("allow_stop", True),
            allow_export=data.get("allow_export", True),
            allow_report=data.get("allow_report", True),
            allow_preflight=data.get("allow_preflight", True),
        )

    def save(self, path: Path = BOT_CONFIG_PATH) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Could not save Discord bot config: {exc}")

    @classmethod
    def load(cls, path: Path = BOT_CONFIG_PATH) -> DiscordBotSettings:
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return cls.from_dict(data)
        except Exception as exc:
            logger.warning(f"Could not load Discord bot config: {exc}")
        return cls()


# ---------------------------------------------------------------------------
# Telemetry Snapshot (passed from MainWindow → Bot)
# ---------------------------------------------------------------------------

@dataclass
class TelemetrySnapshot:
    """Thread-safe snapshot of live engine/cell telemetry for bot queries."""
    voltage_v: float = 0.0
    current_a: float = 0.0
    temperature_c: float = 0.0
    soc_pct: float = 0.0
    engine_state: str = "IDLE"
    active_cell: int = 1
    active_recipe: str = "—"
    active_step_index: int = 0
    total_steps: int = 0
    elapsed_s: float = 0.0
    cycle_count: int = 0
    is_safety_tripped: bool = False
    trip_reason: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# Command Callbacks (set by MainWindow at startup)
# ---------------------------------------------------------------------------

@dataclass
class BotCommandCallbacks:
    """Callables that the bot invokes when a Discord command is received.
    
    Each callable is called from the bot asyncio thread and MUST be thread-safe.
    MainWindow sets these via lambda wrappers that use QMetaObject.invokeMethod
    or direct reads from thread-safe primitives.
    """
    get_telemetry: Callable[[], TelemetrySnapshot] = field(
        default_factory=lambda: (lambda: TelemetrySnapshot())
    )
    do_pause: Callable[[], bool] = field(default_factory=lambda: (lambda: False))
    do_resume: Callable[[], bool] = field(default_factory=lambda: (lambda: False))
    do_stop: Callable[[], bool] = field(default_factory=lambda: (lambda: False))
    do_export: Callable[[], Optional[Path]] = field(default_factory=lambda: (lambda: None))
    do_report: Callable[[], Optional[Path]] = field(default_factory=lambda: (lambda: None))
    do_preflight: Callable[[], str] = field(default_factory=lambda: (lambda: "Preflight not available."))


# ---------------------------------------------------------------------------
# Bot Runner
# ---------------------------------------------------------------------------

class DiscordBotRunner:
    """Runs a discord.py bot in a dedicated background daemon thread.
    
    The bot listens for slash commands and delegates to BotCommandCallbacks,
    which are wired by MainWindow to the live engine state.
    """

    def __init__(
        self,
        settings: Optional[DiscordBotSettings] = None,
        callbacks: Optional[BotCommandCallbacks] = None,
    ):
        self.settings = settings or DiscordBotSettings.load()
        self.callbacks = callbacks or BotCommandCallbacks()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client = None
        self._thread: Optional[threading.Thread] = None
        self._is_running = False
        self.status_message: str = "Not started"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Start the Discord bot in a background thread. Returns True if started."""
        if not self.settings.enabled or not self.settings.token:
            self.status_message = "Bot disabled or no token configured."
            logger.info("[DiscordBot] Not started: disabled or no token.")
            return False

        try:
            import discord  # noqa: F401 — check import works
        except ImportError:
            self.status_message = "discord.py not installed. Run: pip install discord.py"
            logger.error("[DiscordBot] discord.py not installed.")
            return False

        if self._is_running:
            self.status_message = "Already running."
            return True

        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="DiscordBotThread")
        self._thread.start()
        self.status_message = "Starting..."
        logger.info("[DiscordBot] Background thread started.")
        return True

    def stop(self) -> None:
        """Gracefully stop the bot."""
        self._is_running = False
        if self._loop and self._client:
            asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
        self.status_message = "Stopped."
        logger.info("[DiscordBot] Stopped.")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """Entry point for background thread — creates its own event loop."""
        try:
            import discord
            from discord import app_commands

            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            intents = discord.Intents.default()
            intents.message_content = False  # Not needed for slash commands
            client = discord.Client(intents=intents)
            tree = app_commands.CommandTree(client)
            self._client = client
            self._is_running = True

            loop = self._loop
            s = self.settings
            cb = self.callbacks

            # ------------------------------------------------------------------
            # Helper: run a synchronous callback safely off the asyncio thread
            # ------------------------------------------------------------------
            async def _run_sync(fn, *args):
                """Execute a synchronous callback in a thread-pool executor so it
                never blocks the Discord gateway heartbeat / event loop."""
                return await loop.run_in_executor(None, fn, *args)

            def _err_embed(title: str, detail: str) -> "discord.Embed":
                embed = discord.Embed(title=f"⚠️ {title}", description=detail, color=0xEF4444)
                embed.set_footer(text=f"Bytehound BMS | Operator: {s.operator_tag}")
                return embed

            # -------------------------------------------------------
            # Register slash commands
            # -------------------------------------------------------

            if s.allow_status:
                @tree.command(name="status", description="Get live cell telemetry from Bytehound")
                async def cmd_status(interaction: discord.Interaction):
                    await interaction.response.defer(thinking=True)
                    try:
                        snap = await _run_sync(cb.get_telemetry)
                        state_emoji = {
                            "RUNNING": "▶️", "PAUSED": "⏸️", "IDLE": "⏹️",
                            "SAFETY_TRIP": "🛑", "STEP_TRANSITION": "🔄"
                        }.get(snap.engine_state, "❓")
                        embed = discord.Embed(
                            title=f"📊 Cell {snap.active_cell} — Live Telemetry",
                            description=f"{state_emoji} **State:** {snap.engine_state}",
                            color=0x22C55E if snap.engine_state == "RUNNING" else 0x94A3B8,
                            timestamp=snap.timestamp,
                        )
                        embed.add_field(name="⚡ Voltage",     value=f"{snap.voltage_v:.4f} V",          inline=True)
                        embed.add_field(name="🔋 Current",     value=f"{snap.current_a:+.4f} A",          inline=True)
                        embed.add_field(name="🌡️ Temperature", value=f"{snap.temperature_c:.1f} °C",      inline=True)
                        embed.add_field(name="📈 SoC",         value=f"{snap.soc_pct:.1f} %",             inline=True)
                        embed.add_field(name="🔁 Cycles",      value=str(snap.cycle_count),               inline=True)
                        embed.add_field(name="⏱️ Elapsed",     value=f"{snap.elapsed_s/3600:.2f} h",      inline=True)
                        embed.add_field(name="📋 Recipe",      value=snap.active_recipe or "—",           inline=False)
                        if snap.active_recipe and snap.total_steps:
                            embed.add_field(name="📍 Step", value=f"{snap.active_step_index}/{snap.total_steps}", inline=True)
                        if snap.is_safety_tripped:
                            embed.add_field(name="🛑 Trip Reason", value=snap.trip_reason, inline=False)
                        embed.set_footer(text=f"Bytehound BMS Cycler | Operator: {s.operator_tag}")
                        await interaction.followup.send(embed=embed)
                    except Exception as exc:
                        logger.error(f"[DiscordBot] /status error: {exc}", exc_info=True)
                        await interaction.followup.send(embed=_err_embed("Status Error", str(exc)))

            if s.allow_pause:
                @tree.command(name="pause", description="Pause the active Bytehound test step")
                async def cmd_pause(interaction: discord.Interaction):
                    await interaction.response.defer(thinking=True)
                    try:
                        ok = await _run_sync(cb.do_pause)
                        if ok:
                            embed = discord.Embed(title="⏸️ Test Paused", description="The active test step has been paused.", color=0xF59E0B)
                        else:
                            embed = discord.Embed(title="ℹ️ Cannot Pause", description="No test is currently running or it is already paused.", color=0x94A3B8)
                        embed.set_footer(text=f"Bytehound BMS | Operator: {s.operator_tag}")
                        await interaction.followup.send(embed=embed)
                    except Exception as exc:
                        logger.error(f"[DiscordBot] /pause error: {exc}", exc_info=True)
                        await interaction.followup.send(embed=_err_embed("Pause Error", str(exc)))

            if s.allow_resume:
                @tree.command(name="resume", description="Resume a paused Bytehound test step")
                async def cmd_resume(interaction: discord.Interaction):
                    await interaction.response.defer(thinking=True)
                    try:
                        ok = await _run_sync(cb.do_resume)
                        if ok:
                            embed = discord.Embed(title="▶️ Test Resumed", description="The test has been resumed.", color=0x22C55E)
                        else:
                            embed = discord.Embed(title="ℹ️ Cannot Resume", description="Test is not paused or not running.", color=0x94A3B8)
                        embed.set_footer(text=f"Bytehound BMS | Operator: {s.operator_tag}")
                        await interaction.followup.send(embed=embed)
                    except Exception as exc:
                        logger.error(f"[DiscordBot] /resume error: {exc}", exc_info=True)
                        await interaction.followup.send(embed=_err_embed("Resume Error", str(exc)))

            if s.allow_stop:
                @tree.command(name="stop", description="Emergency stop — safely de-energize the Bytehound cycler")
                async def cmd_stop(interaction: discord.Interaction):
                    await interaction.response.defer(thinking=True)
                    try:
                        ok = await _run_sync(cb.do_stop)
                        if ok:
                            embed = discord.Embed(
                                title="🛑 EMERGENCY STOP ISSUED",
                                description="Safe de-energization command dispatched. All hardware outputs set to zero.",
                                color=0xEF4444,
                            )
                        else:
                            embed = discord.Embed(title="ℹ️ No Active Test", description="No test was running to stop.", color=0x94A3B8)
                        embed.set_footer(text=f"Bytehound BMS | Operator: {s.operator_tag}")
                        await interaction.followup.send(embed=embed)
                    except Exception as exc:
                        logger.error(f"[DiscordBot] /stop error: {exc}", exc_info=True)
                        await interaction.followup.send(embed=_err_embed("Stop Error", str(exc)))

            if s.allow_export:
                @tree.command(name="export", description="Generate and export a Bytehound diagnostic run package")
                async def cmd_export(interaction: discord.Interaction):
                    await interaction.response.defer(thinking=True)
                    try:
                        path = await _run_sync(cb.do_export)
                        if path:
                            embed = discord.Embed(
                                title="📦 Run Package Exported",
                                description=f"Diagnostic package saved at:\n`{path}`\n\nContains: raw CSV, recipe JSON, step/cycle summaries, SHA-256 manifest.",
                                color=0x38BDF8,
                            )
                            embed.add_field(name="Filename", value=path.name, inline=False)
                        else:
                            embed = discord.Embed(title="⚠️ Export Failed", description="Could not generate run package. Run a test first.", color=0xEF4444)
                        embed.set_footer(text=f"Bytehound BMS | Operator: {s.operator_tag}")
                        await interaction.followup.send(embed=embed)
                    except Exception as exc:
                        logger.error(f"[DiscordBot] /export error: {exc}", exc_info=True)
                        await interaction.followup.send(embed=_err_embed("Export Error", str(exc)))

            if s.allow_report:
                @tree.command(name="report", description="Generate a Bytehound HTML test certification report")
                async def cmd_report(interaction: discord.Interaction):
                    await interaction.response.defer(thinking=True)
                    try:
                        path = await _run_sync(cb.do_report)
                        if path:
                            embed = discord.Embed(
                                title="📄 Test Certificate Generated",
                                description=f"IEC 62660-1 / USABC qualification report saved at:\n`{path}`",
                                color=0xC084FC,
                            )
                            embed.add_field(name="Filename", value=path.name, inline=False)
                        else:
                            embed = discord.Embed(title="⚠️ Report Failed", description="Could not generate certification report. Run a test first.", color=0xEF4444)
                        embed.set_footer(text=f"Bytehound BMS | Operator: {s.operator_tag}")
                        await interaction.followup.send(embed=embed)
                    except Exception as exc:
                        logger.error(f"[DiscordBot] /report error: {exc}", exc_info=True)
                        await interaction.followup.send(embed=_err_embed("Report Error", str(exc)))

            if s.allow_preflight:
                @tree.command(name="preflight", description="Run Bytehound hardware pre-flight sanity checks")
                async def cmd_preflight(interaction: discord.Interaction):
                    await interaction.response.defer(thinking=True)
                    try:
                        result_text = await _run_sync(cb.do_preflight)
                        embed = discord.Embed(
                            title="🛫 Pre-Flight Sanity Check",
                            description=result_text,
                            color=0x22C55E if "PASS" in result_text.upper() else 0xEF4444,
                        )
                        embed.set_footer(text=f"Bytehound BMS | Operator: {s.operator_tag}")
                        await interaction.followup.send(embed=embed)
                    except Exception as exc:
                        logger.error(f"[DiscordBot] /preflight error: {exc}", exc_info=True)
                        await interaction.followup.send(embed=_err_embed("Preflight Error", str(exc)))

            @tree.command(name="help", description="List all Bytehound remote commands")
            async def cmd_help(interaction: discord.Interaction):
                try:
                    embed = discord.Embed(
                        title="🤖 Bytehound Discord Bot — Command Reference",
                        description=f"Remote command & control for **Bytehound Single-Cell BMS Cycler**.\nOperator: **{s.operator_tag}**",
                        color=0x38BDF8,
                    )
                    cmds = [
                        ("/status",    "📊 Live voltage, current, temperature, SoC"),
                        ("/pause",     "⏸️ Pause the active test step"),
                        ("/resume",    "▶️ Resume a paused test"),
                        ("/stop",      "🛑 Emergency stop — safe de-energization"),
                        ("/export",    "📦 Generate diagnostic run package (.zip)"),
                        ("/report",    "📄 Generate HTML certification report"),
                        ("/preflight", "🛫 Run hardware sanity checks"),
                        ("/help",      "❓ Show this command list"),
                    ]
                    for cmd_name, desc in cmds:
                        embed.add_field(name=cmd_name, value=desc, inline=False)
                    embed.set_footer(text="Bytehound Single-Cell BMS Cycler")
                    await interaction.response.send_message(embed=embed)
                except Exception as exc:
                    logger.error(f"[DiscordBot] /help error: {exc}", exc_info=True)

            # -------------------------------------------------------
            # on_ready: sync slash commands globally
            # -------------------------------------------------------
            @client.event
            async def on_ready():
                self.status_message = f"Online as {client.user}"
                logger.info(f"[DiscordBot] Logged in as {client.user}. Syncing slash commands...")
                await tree.sync()
                logger.info("[DiscordBot] Slash commands synced globally. Bot is ready.")

            # -------------------------------------------------------
            # Run the bot
            # -------------------------------------------------------
            self._loop.run_until_complete(client.start(self.settings.token))

        except Exception as exc:
            self.status_message = f"Error: {exc}"
            logger.error(f"[DiscordBot] Bot crashed: {exc}", exc_info=True)
        finally:
            self._is_running = False
            self.status_message = "Offline."


