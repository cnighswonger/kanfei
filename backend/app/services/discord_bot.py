"""Discord bot integration — gateway WebSocket bot for weather queries
and outbound notifications for nowcast and alert events.
"""

import asyncio
import logging
import sqlite3
from datetime import datetime, timezone

from .bot_formatting import (
    format_current_conditions,
    format_alert_triggered,
    format_alert_cleared,
    format_nowcast_update,
    format_help,
    format_status,
    get_current_conditions,
)
from .bot_ratelimit import RateLimiter

logger = logging.getLogger(__name__)

# How often the supervisor checks config for enable/disable changes (seconds).
_SUPERVISOR_POLL = 30

# Discord message length limit.
_MAX_MESSAGE_LENGTH = 2000


def _read_discord_config(db_path: str) -> dict:
    """Read current Discord bot config from station_config (best-effort)."""
    defaults = {
        "bot_discord_enabled": False,
        "bot_discord_token": "",
        "bot_discord_guild_id": "",
        "bot_discord_channel_id": "",
        "bot_discord_commands": "current,status,help",
        "bot_discord_notifications": "nowcast,alerts",
    }
    try:
        conn = sqlite3.connect(db_path)
        for key in defaults:
            cur = conn.execute(
                "SELECT value FROM station_config WHERE key = ?", (key,)
            )
            row = cur.fetchone()
            if row is not None:
                val = row[0]
                if val.lower() in ("true", "false"):
                    defaults[key] = val.lower() == "true"
                else:
                    defaults[key] = val
        conn.close()
    except Exception:
        pass
    return defaults


def _update_discord_status(db_path: str, error: str = "") -> None:
    """Write bot status to station_config (best-effort)."""
    try:
        conn = sqlite3.connect(db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO station_config (key, value, updated_at) "
            "VALUES (?, ?, ?)",
            ("bot_discord_last_error", error, now),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


class DiscordBot:
    """Discord bot using gateway WebSocket connection.

    Uses discord.py slash commands for inbound queries and channel
    messages for outbound notifications.
    """

    def __init__(self, token: str, guild_id: str, channel_ids: set[str],
                 db_path: str, enabled_commands: set[str],
                 enabled_notifications: set[str] | None = None,
                 dry_run: bool = False) -> None:
        self._token = token
        self._guild_id = guild_id
        self._channel_ids = channel_ids
        self._db_path = db_path
        self._enabled_commands = enabled_commands
        self._enabled_notifications = enabled_notifications or {"nowcast", "alerts"}
        self._dry_run = dry_run
        self._rate_limiter = RateLimiter()
        self._notified_alerts: set[str] = set()
        self._client = None
        self._tree = None
        self._running = False

    async def start(self) -> None:
        """Start the bot gateway connection."""
        if self._dry_run:
            logger.info("Discord bot started in dry-run mode")
            self._running = True
            return

        try:
            import discord
            from discord import app_commands
        except ImportError:
            logger.error(
                "discord.py is not installed. "
                "Install it with: pip install 'discord.py>=2.0'"
            )
            return

        intents = discord.Intents.default()
        self._client = discord.Client(intents=intents)
        self._tree = app_commands.CommandTree(self._client)

        guild_obj = discord.Object(id=int(self._guild_id)) if self._guild_id else None

        if "current" in self._enabled_commands:
            @self._tree.command(
                name="current",
                description="Current weather conditions",
                guild=guild_obj,
            )
            async def cmd_current(interaction: discord.Interaction):
                await self._handle_current(interaction)

        if "status" in self._enabled_commands:
            @self._tree.command(
                name="status",
                description="Station connection status",
                guild=guild_obj,
            )
            async def cmd_status(interaction: discord.Interaction):
                await self._handle_status(interaction)

        if "help" in self._enabled_commands:
            @self._tree.command(
                name="help",
                description="List available commands",
                guild=guild_obj,
            )
            async def cmd_help(interaction: discord.Interaction):
                await self._handle_help(interaction)

        @self._client.event
        async def on_ready():
            if guild_obj:
                self._tree.copy_global_to(guild=guild_obj)
                await self._tree.sync(guild=guild_obj)
            else:
                await self._tree.sync()
            logger.info(
                "Discord bot ready (user=%s, guild=%s)",
                self._client.user, self._guild_id or "global",
            )

        self._running = True
        logger.info(
            "Discord bot starting (commands=%s, guild=%s)",
            ",".join(sorted(self._enabled_commands)),
            self._guild_id or "global",
        )

        try:
            await self._client.start(self._token)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the bot gracefully."""
        self._running = False
        if self._client is not None and not self._client.is_closed():
            try:
                await self._client.close()
            except Exception:
                logger.debug("Error during Discord bot shutdown", exc_info=True)
        self._client = None
        self._tree = None
        logger.info("Discord bot stopped")

    def _is_channel_allowed(self, channel_id: str) -> bool:
        """Check if a channel ID is in the whitelist (empty = allow all)."""
        if not self._channel_ids:
            return True
        return channel_id in self._channel_ids

    async def _send_response(self, interaction, text: str) -> None:
        """Send an interaction response."""
        if self._dry_run:
            logger.info("DRY-RUN response:\n%s", text)
            return
        try:
            await interaction.response.send_message(
                text[:_MAX_MESSAGE_LENGTH]
            )
        except Exception:
            logger.warning("Failed to send Discord response", exc_info=True)

    async def _send_to_channel(self, channel_id: str, text: str) -> None:
        """Send a message to a channel by ID."""
        if self._dry_run:
            logger.info("DRY-RUN message to channel %s:\n%s", channel_id, text)
            return
        if self._client is None:
            return
        try:
            channel = self._client.get_channel(int(channel_id))
            if channel is None:
                channel = await self._client.fetch_channel(int(channel_id))
            await channel.send(text[:_MAX_MESSAGE_LENGTH])
        except Exception:
            logger.warning("Failed to send Discord message to channel %s",
                           channel_id, exc_info=True)

    async def _handle_current(self, interaction) -> None:
        """Handle the /current slash command."""
        channel_id = str(interaction.channel_id)

        if not self._is_channel_allowed(channel_id):
            return

        if self._rate_limiter.is_limited(channel_id, "current"):
            await self._send_response(interaction, "Please wait a moment before using this command again.")
            return

        reading = get_current_conditions(self._db_path)
        if reading is None:
            await self._send_response(interaction, "No weather data available.")
            return

        text = format_current_conditions(reading)
        await self._send_response(interaction, text)

    async def _handle_status(self, interaction) -> None:
        """Handle the /status slash command."""
        channel_id = str(interaction.channel_id)

        if not self._is_channel_allowed(channel_id):
            return

        if self._rate_limiter.is_limited(channel_id, "status"):
            await self._send_response(interaction, "Please wait a moment before using this command again.")
            return

        reading = get_current_conditions(self._db_path)
        text = format_status(reading)
        await self._send_response(interaction, text)

    async def _handle_help(self, interaction) -> None:
        """Handle the /help slash command."""
        channel_id = str(interaction.channel_id)

        if not self._is_channel_allowed(channel_id):
            return

        if self._rate_limiter.is_limited(channel_id, "help"):
            return

        await self._send_response(interaction, format_help())

    async def send_notification(self, text: str) -> None:
        """Send a notification to all configured channels."""
        if not text or not self._channel_ids:
            return
        for channel_id in self._channel_ids:
            await self._send_to_channel(channel_id, text)

    async def handle_event(self, message: dict) -> None:
        """Process an IPC or emitter event and send notifications if applicable."""
        event_type = message.get("type", "")
        data = message.get("data", {})

        if event_type == "alert_triggered" and "alerts" in self._enabled_notifications:
            alert_id = data.get("id", "")
            if alert_id in self._notified_alerts:
                return
            self._notified_alerts.add(alert_id)
            text = format_alert_triggered(data)
            await self.send_notification(text)

        elif event_type == "alert_cleared" and "alerts" in self._enabled_notifications:
            alert_id = data.get("id", "")
            self._notified_alerts.discard(alert_id)
            text = format_alert_cleared(data)
            await self.send_notification(text)

        elif event_type == "nowcast_update" and "nowcast" in self._enabled_notifications:
            text = format_nowcast_update(data)
            if text:
                await self.send_notification(text)


async def _ipc_event_loop(bot: DiscordBot, ipc_port: int) -> None:
    """Subscribe to IPC events and route alert notifications to the bot."""
    from ..ipc.client import IPCClient

    while True:
        try:
            client = IPCClient(ipc_port)
            async for msg in client.subscribe():
                event_type = msg.get("type", "")
                if event_type in ("alert_triggered", "alert_cleared"):
                    await bot.handle_event(msg)
        except asyncio.CancelledError:
            break
        except (ConnectionRefusedError, OSError):
            await asyncio.sleep(5.0)
        except Exception:
            logger.debug("Discord IPC event loop error", exc_info=True)
            await asyncio.sleep(5.0)


async def discord_bot_supervisor(db_path: str, ipc_port: int = 0,
                                 nc_events=None) -> None:
    """Background supervisor that manages the Discord bot lifecycle.

    Polls config every _SUPERVISOR_POLL seconds and starts, stops, or
    restarts the bot as needed.

    Args:
        db_path: Path to the SQLite database.
        ipc_port: Logger daemon IPC port for alert subscriptions.
        nc_events: KanfeiEventEmitter instance for nowcast event listener.
    """
    logger.info("Discord bot supervisor started (poll every %ds)", _SUPERVISOR_POLL)

    active_bot: DiscordBot | None = None
    active_task: asyncio.Task | None = None
    active_ipc_task: asyncio.Task | None = None
    active_token: str = ""
    listener_registered = False

    def _nowcast_listener(msg: dict):
        """Async callback registered with KanfeiEventEmitter."""
        if active_bot is not None:
            return active_bot.handle_event(msg)

    def _stop_current() -> None:
        nonlocal active_bot, active_task, active_ipc_task, active_token
        nonlocal listener_registered
        if active_ipc_task is not None:
            active_ipc_task.cancel()
            active_ipc_task = None
        if active_task is not None:
            active_task.cancel()
            active_task = None
        if listener_registered and nc_events is not None:
            nc_events.remove_listener(_nowcast_listener)
            listener_registered = False
        active_bot = None
        active_token = ""

    while True:
        try:
            cfg = _read_discord_config(db_path)
            enabled = cfg["bot_discord_enabled"]
            token = cfg["bot_discord_token"]
            guild_id = cfg["bot_discord_guild_id"]
            channel_id_str = cfg["bot_discord_channel_id"]
            commands_str = cfg["bot_discord_commands"]
            notifications_str = cfg["bot_discord_notifications"]

            if not enabled or not token:
                if active_bot is not None:
                    _stop_current()
                    logger.info("Discord bot disabled via config")
                    _update_discord_status(db_path)
                await asyncio.sleep(_SUPERVISOR_POLL)
                continue

            channel_ids = {c.strip() for c in channel_id_str.split(",") if c.strip()}
            enabled_commands = {c.strip() for c in commands_str.split(",") if c.strip()}
            enabled_notifications = {c.strip() for c in notifications_str.split(",") if c.strip()}

            # Restart if token changed
            if active_bot is not None and token != active_token:
                logger.info("Discord bot token changed, restarting")
                _stop_current()

            # Start if not running
            if active_bot is None:
                bot = DiscordBot(
                    token=token,
                    guild_id=guild_id,
                    channel_ids=channel_ids,
                    db_path=db_path,
                    enabled_commands=enabled_commands,
                    enabled_notifications=enabled_notifications,
                )
                active_task = asyncio.create_task(bot.start())
                active_bot = bot
                active_token = token
                _update_discord_status(db_path)
                logger.info("Discord bot started")

                # Start IPC event loop for alert notifications
                if ipc_port:
                    active_ipc_task = asyncio.create_task(
                        _ipc_event_loop(bot, ipc_port)
                    )

                # Register nowcast event listener
                if nc_events is not None and not listener_registered:
                    nc_events.add_listener(_nowcast_listener)
                    listener_registered = True
            else:
                # Update mutable config without restart
                active_bot._channel_ids = channel_ids
                active_bot._enabled_commands = enabled_commands
                active_bot._enabled_notifications = enabled_notifications

            # Check if the bot task died
            if active_task is not None and active_task.done():
                exc = active_task.exception() if not active_task.cancelled() else None
                if exc:
                    logger.error("Discord bot crashed: %s — restarting", exc)
                    _update_discord_status(db_path, error=str(exc))
                else:
                    logger.warning("Discord bot exited unexpectedly — restarting")
                _stop_current()

        except Exception:
            logger.exception("Discord bot supervisor tick failed")

        await asyncio.sleep(_SUPERVISOR_POLL)
