"""Telegram bot integration — long-polling bot for weather queries
and outbound notifications for nowcast and alert events.
"""

import asyncio
import logging
import sqlite3
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# How often the supervisor checks config for enable/disable changes (seconds).
_SUPERVISOR_POLL = 30

# Rate limit: minimum seconds between repeated identical commands per chat.
_RATE_LIMIT_SAME_CMD = 5
# Rate limit: minimum seconds between different commands per chat (debounce).
_RATE_LIMIT_DIFF_CMD = 1

# Telegram message length limit.
_MAX_MESSAGE_LENGTH = 4096

# Cardinal direction labels for wind.
_CARDINAL_DIRECTIONS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def _cardinal(degrees: int | None) -> str:
    """Convert wind direction degrees to cardinal abbreviation."""
    if degrees is None:
        return "---"
    idx = round(degrees / 22.5) % 16
    return _CARDINAL_DIRECTIONS[idx]


def _read_telegram_config(db_path: str) -> dict:
    """Read current Telegram bot config from station_config (best-effort)."""
    defaults = {
        "bot_telegram_enabled": False,
        "bot_telegram_token": "",
        "bot_telegram_chat_id": "",
        "bot_telegram_commands": "current,status,help",
        "bot_telegram_notifications": "nowcast,alerts",
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


def _update_telegram_status(db_path: str, error: str = "") -> None:
    """Write bot status to station_config (best-effort)."""
    try:
        conn = sqlite3.connect(db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO station_config (key, value, updated_at) "
            "VALUES (?, ?, ?)",
            ("bot_telegram_last_error", error, now),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _get_current_conditions(db_path: str) -> dict | None:
    """Query the latest sensor reading from the database.

    Returns a dict of raw SI values, or None if no data.
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT * FROM sensor_readings ORDER BY timestamp DESC LIMIT 1"
        )
        row = cur.fetchone()
        conn.close()
        if row is None:
            return None
        return dict(row)
    except Exception:
        logger.debug("Failed to query current conditions", exc_info=True)
        return None


def format_current_conditions(reading: dict) -> str:
    """Format a sensor reading dict into a human-readable Telegram message.

    Converts raw SI storage values (tenths) to display units inline.
    """
    from ..utils.units import (
        si_temp_to_display_f,
        si_pressure_to_display_inhg,
        si_wind_to_display_mph,
        si_rain_to_display_in,
    )

    def _temp(raw: int | None) -> str:
        if raw is None:
            return "---"
        return f"{si_temp_to_display_f(raw)}\u00b0F"

    def _wind(raw: int | None) -> str:
        if raw is None:
            return "---"
        return f"{si_wind_to_display_mph(raw)} mph"

    def _baro(raw: int | None) -> str:
        if raw is None:
            return "---"
        return f"{si_pressure_to_display_inhg(raw)} inHg"

    def _rain(raw: int | None) -> str:
        if raw is None:
            return "---"
        return f'{si_rain_to_display_in(raw)}"'

    def _humidity(raw: int | None) -> str:
        if raw is None:
            return "---"
        return f"{raw}%"

    def _uv(raw: int | None) -> str:
        if raw is None:
            return "---"
        return f"{round(raw / 10, 1)}"

    ts = reading.get("timestamp", "")
    if ts:
        try:
            dt = datetime.fromisoformat(ts)
            ts = dt.strftime("%I:%M %p").lstrip("0")
        except (ValueError, TypeError):
            pass

    wind_dir = reading.get("wind_direction")
    cardinal = _cardinal(wind_dir)
    wind_deg = f"{wind_dir}\u00b0" if wind_dir is not None else "---"

    trend = reading.get("pressure_trend", "")
    trend_str = f" ({trend})" if trend else ""

    lines = [
        f"\U0001f321 *Current Conditions*  \u2014  {ts}",
        "",
        f"Temp: {_temp(reading.get('outside_temp'))}  (Feels: {_temp(reading.get('feels_like'))})",
        f"Humidity: {_humidity(reading.get('outside_humidity'))}",
        f"Dew Point: {_temp(reading.get('dew_point'))}",
        f"Wind: {cardinal} {wind_deg} at {_wind(reading.get('wind_speed'))}",
        f"Barometer: {_baro(reading.get('barometer'))}{trend_str}",
        f"Rain Today: {_rain(reading.get('rain_total'))}  (Rate: {_rain(reading.get('rain_rate'))}/hr)",
        f"UV Index: {_uv(reading.get('uv_index'))}",
    ]

    return "\n".join(lines)


def format_alert_triggered(data: dict) -> str:
    """Format an alert_triggered event into a Telegram message."""
    label = data.get("label", "Unknown alert")
    sensor = data.get("sensor", "")
    value = data.get("value", "?")
    threshold = data.get("threshold", "?")
    oper = data.get("operator", "")
    return (
        f"\u26a0\ufe0f *Alert: {label}*\n\n"
        f"{sensor} is {value} ({oper} {threshold})"
    )


def format_alert_cleared(data: dict) -> str:
    """Format an alert_cleared event into a Telegram message."""
    label = data.get("label", "Unknown alert")
    return f"\u2705 *Alert cleared: {label}*"


def format_nowcast_update(data: dict) -> str | None:
    """Format a nowcast_update event into a Telegram message.

    Returns None if the nowcast data lacks a summary (e.g. duplicate or empty).
    """
    summary = data.get("summary", "")
    if not summary:
        return None

    severe = data.get("severe_weather")
    model = data.get("model_used", "")

    lines = [
        "\U0001f4a8 *Nowcast Update*",
        "",
        summary,
    ]

    if severe and isinstance(severe, dict):
        threat = severe.get("threat_level", "")
        if threat:
            lines.append(f"\nThreat level: {threat}")

    if model:
        lines.append(f"\n_{model}_")

    return "\n".join(lines)


def format_help() -> str:
    """Format the /help command response."""
    return (
        "\U0001f4cb *Kanfei Weather Bot*\n\n"
        "/current \u2014 Current weather conditions\n"
        "/status \u2014 Station connection status\n"
        "/help \u2014 Show this message"
    )


class TelegramBot:
    """Telegram bot using long polling (getUpdates).

    Handles inbound commands from whitelisted chats with rate limiting.
    All Telegram API calls go through _send_message() for easy mocking
    and dry-run support.
    """

    def __init__(self, token: str, chat_ids: set[str], db_path: str,
                 enabled_commands: set[str], enabled_notifications: set[str] | None = None,
                 dry_run: bool = False) -> None:
        self._token = token
        self._chat_ids = chat_ids
        self._db_path = db_path
        self._enabled_commands = enabled_commands
        self._enabled_notifications = enabled_notifications or {"nowcast", "alerts"}
        self._dry_run = dry_run
        self._last_command_time: dict[tuple[str, str], float] = {}
        self._app = None
        self._running = False

    async def start(self) -> None:
        """Start the bot polling loop."""
        if self._dry_run:
            logger.info("Telegram bot started in dry-run mode")
            self._running = True
            return

        try:
            from telegram import Update
            from telegram.ext import (
                ApplicationBuilder,
                CommandHandler,
                ContextTypes,
            )
        except ImportError:
            logger.error(
                "python-telegram-bot is not installed. "
                "Install it with: pip install 'python-telegram-bot>=22.0'"
            )
            return

        self._app = (
            ApplicationBuilder()
            .token(self._token)
            .build()
        )

        if "current" in self._enabled_commands:
            self._app.add_handler(CommandHandler("current", self._handle_current))
        if "status" in self._enabled_commands:
            self._app.add_handler(CommandHandler("status", self._handle_status))
        if "help" in self._enabled_commands:
            self._app.add_handler(CommandHandler("help", self._handle_help))
            self._app.add_handler(CommandHandler("start", self._handle_help))

        self._running = True
        logger.info(
            "Telegram bot starting (commands=%s, chats=%s)",
            ",".join(sorted(self._enabled_commands)),
            ",".join(sorted(self._chat_ids)) if self._chat_ids else "any",
        )

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

        # Keep alive until cancelled
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the bot gracefully."""
        self._running = False
        if self._app is not None:
            try:
                if self._app.updater and self._app.updater.running:
                    await self._app.updater.stop()
                if self._app.running:
                    await self._app.stop()
                await self._app.shutdown()
            except Exception:
                logger.debug("Error during bot shutdown", exc_info=True)
            self._app = None
        logger.info("Telegram bot stopped")

    def _is_chat_allowed(self, chat_id: str) -> bool:
        """Check if a chat ID is in the whitelist (empty = allow all)."""
        if not self._chat_ids:
            return True
        return chat_id in self._chat_ids

    def _is_rate_limited(self, chat_id: str, command: str = "") -> bool:
        """Check if a chat has exceeded the rate limit for a command.

        Same command repeated: 5s cooldown (prevents spam).
        Different command: 1s cooldown (debounce double-taps only).
        """
        now = time.monotonic()
        key = (chat_id, command)

        # Check same-command cooldown
        last_same = self._last_command_time.get(key, 0.0)
        if now - last_same < _RATE_LIMIT_SAME_CMD:
            return True

        # Check cross-command debounce (any recent command from this chat)
        for (cid, _), ts in self._last_command_time.items():
            if cid == chat_id and now - ts < _RATE_LIMIT_DIFF_CMD:
                return True

        self._last_command_time[key] = now
        return False

    async def _send_message(self, chat_id: str, text: str,
                            parse_mode: str = "Markdown") -> None:
        """Send a message to a chat. Override point for dry-run and testing."""
        if self._dry_run:
            logger.info("DRY-RUN message to %s:\n%s", chat_id, text)
            return
        if self._app is None:
            return
        try:
            await self._app.bot.send_message(
                chat_id=int(chat_id),
                text=text[:_MAX_MESSAGE_LENGTH],
                parse_mode=parse_mode,
            )
        except Exception:
            logger.warning("Failed to send Telegram message to %s", chat_id,
                           exc_info=True)

    async def _handle_current(self, update, context) -> None:
        """Handle the /current command."""
        chat_id = str(update.effective_chat.id)

        if not self._is_chat_allowed(chat_id):
            logger.debug("Ignoring /current from unauthorized chat %s", chat_id)
            return

        if self._is_rate_limited(chat_id, "current"):
            return

        reading = _get_current_conditions(self._db_path)
        if reading is None:
            await self._send_message(chat_id, "No weather data available.")
            return

        text = format_current_conditions(reading)
        await self._send_message(chat_id, text)

    async def _handle_status(self, update, context) -> None:
        """Handle the /status command."""
        chat_id = str(update.effective_chat.id)

        if not self._is_chat_allowed(chat_id):
            logger.debug("Ignoring /status from unauthorized chat %s", chat_id)
            return

        if self._is_rate_limited(chat_id, "status"):
            return

        reading = _get_current_conditions(self._db_path)
        if reading is None:
            await self._send_message(chat_id, "Station offline \u2014 no data available.")
            return

        ts = reading.get("timestamp", "")
        age_str = "unknown"
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - dt).total_seconds()
                if age < 60:
                    age_str = f"{int(age)}s ago"
                elif age < 3600:
                    age_str = f"{int(age / 60)}m ago"
                else:
                    age_str = f"{age / 3600:.1f}h ago"
            except (ValueError, TypeError):
                pass

        status = "online" if reading else "offline"
        lines = [
            "\U0001f4e1 *Station Status*",
            "",
            f"Status: {status}",
            f"Last reading: {age_str}",
        ]
        await self._send_message(chat_id, "\n".join(lines))

    async def _handle_help(self, update, context) -> None:
        """Handle the /help and /start commands."""
        chat_id = str(update.effective_chat.id)

        if not self._is_chat_allowed(chat_id):
            return

        if self._is_rate_limited(chat_id, "help"):
            return

        await self._send_message(chat_id, format_help())

    async def send_notification(self, text: str) -> None:
        """Send a notification to all configured chat IDs."""
        if not text or not self._chat_ids:
            return
        for chat_id in self._chat_ids:
            await self._send_message(chat_id, text)

    async def handle_event(self, message: dict) -> None:
        """Process an IPC or emitter event and send notifications if applicable."""
        event_type = message.get("type", "")
        data = message.get("data", {})

        if event_type == "alert_triggered" and "alerts" in self._enabled_notifications:
            # Only notify on newly triggered alerts (first occurrence).
            # The alert checker sends triggered on every reading while active,
            # but we only want the initial notification.
            alert_id = data.get("id", "")
            if not hasattr(self, "_notified_alerts"):
                self._notified_alerts: set[str] = set()
            if alert_id in self._notified_alerts:
                return
            self._notified_alerts.add(alert_id)
            text = format_alert_triggered(data)
            await self.send_notification(text)

        elif event_type == "alert_cleared" and "alerts" in self._enabled_notifications:
            alert_id = data.get("id", "")
            if hasattr(self, "_notified_alerts"):
                self._notified_alerts.discard(alert_id)
            text = format_alert_cleared(data)
            await self.send_notification(text)

        elif event_type == "nowcast_update" and "nowcast" in self._enabled_notifications:
            text = format_nowcast_update(data)
            if text:
                await self.send_notification(text)


async def _ipc_event_loop(bot: TelegramBot, ipc_port: int) -> None:
    """Subscribe to IPC events and route alert notifications to the bot.

    Reconnects automatically if the logger daemon is unavailable.
    """
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
            logger.debug("IPC event loop error", exc_info=True)
            await asyncio.sleep(5.0)


async def telegram_bot_supervisor(db_path: str, ipc_port: int = 0,
                                  nc_events=None) -> None:
    """Background supervisor that manages the Telegram bot lifecycle.

    Polls config every _SUPERVISOR_POLL seconds and starts, stops, or
    restarts the bot as needed. Follows the same pattern as the nowcast
    supervisor and backup scheduler.

    Args:
        db_path: Path to the SQLite database.
        ipc_port: Logger daemon IPC port for alert subscriptions.
        nc_events: KanfeiEventEmitter instance for nowcast event listener.
    """
    logger.info("Telegram bot supervisor started (poll every %ds)", _SUPERVISOR_POLL)

    active_bot: TelegramBot | None = None
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
            cfg = _read_telegram_config(db_path)
            enabled = cfg["bot_telegram_enabled"]
            token = cfg["bot_telegram_token"]
            chat_id_str = cfg["bot_telegram_chat_id"]
            commands_str = cfg["bot_telegram_commands"]
            notifications_str = cfg["bot_telegram_notifications"]

            if not enabled or not token:
                if active_bot is not None:
                    _stop_current()
                    logger.info("Telegram bot disabled via config")
                    _update_telegram_status(db_path)
                await asyncio.sleep(_SUPERVISOR_POLL)
                continue

            chat_ids = {c.strip() for c in chat_id_str.split(",") if c.strip()}
            enabled_commands = {c.strip() for c in commands_str.split(",") if c.strip()}
            enabled_notifications = {c.strip() for c in notifications_str.split(",") if c.strip()}

            # Restart if token changed
            if active_bot is not None and token != active_token:
                logger.info("Telegram bot token changed, restarting")
                _stop_current()

            # Start if not running
            if active_bot is None:
                bot = TelegramBot(
                    token=token,
                    chat_ids=chat_ids,
                    db_path=db_path,
                    enabled_commands=enabled_commands,
                    enabled_notifications=enabled_notifications,
                )
                active_task = asyncio.create_task(bot.start())
                active_bot = bot
                active_token = token
                _update_telegram_status(db_path)
                logger.info("Telegram bot started")

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
                active_bot._chat_ids = chat_ids
                active_bot._enabled_commands = enabled_commands
                active_bot._enabled_notifications = enabled_notifications

            # Check if the bot task died
            if active_task is not None and active_task.done():
                exc = active_task.exception() if not active_task.cancelled() else None
                if exc:
                    logger.error("Telegram bot crashed: %s — restarting", exc)
                    _update_telegram_status(db_path, error=str(exc))
                else:
                    logger.warning("Telegram bot exited unexpectedly — restarting")
                _stop_current()
                # Will restart on the next loop iteration

        except Exception:
            logger.exception("Telegram bot supervisor tick failed")

        await asyncio.sleep(_SUPERVISOR_POLL)
