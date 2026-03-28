"""Telegram bot integration — long-polling bot for weather queries
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

# Telegram message length limit.
_MAX_MESSAGE_LENGTH = 4096


def _read_telegram_config(db_path: str) -> dict:
    """Read current Telegram bot config from station_config (best-effort)."""
    defaults = {
        "bot_telegram_enabled": False,
        "bot_telegram_token": "",
        "bot_telegram_chat_id": "",
        "bot_telegram_commands": "current,status,help",
        "bot_telegram_notifications": "nowcast,alerts",
        "bot_telegram_conditions_enabled": False,
        "bot_telegram_conditions_interval": 30,
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
        self._rate_limiter = RateLimiter()
        self._notified_alerts: set[str] = set()
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

        if self._rate_limiter.is_limited(chat_id, "current"):
            return

        reading = get_current_conditions(self._db_path)
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

        if self._rate_limiter.is_limited(chat_id, "status"):
            return

        reading = get_current_conditions(self._db_path)
        text = format_status(reading)
        await self._send_message(chat_id, text)

    async def _handle_help(self, update, context) -> None:
        """Handle the /help and /start commands."""
        chat_id = str(update.effective_chat.id)

        if not self._is_chat_allowed(chat_id):
            return

        if self._rate_limiter.is_limited(chat_id, "help"):
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
    last_conditions_push: float = 0.0
    conditions_was_enabled = False

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

            # Scheduled conditions push
            conditions_enabled = cfg.get("bot_telegram_conditions_enabled", False)
            conditions_interval = int(cfg.get("bot_telegram_conditions_interval", 30)) * 60
            if conditions_enabled and not conditions_was_enabled:
                last_conditions_push = 0.0  # Reset timer on re-enable → immediate push
            conditions_was_enabled = conditions_enabled
            if active_bot is not None and conditions_enabled and conditions_interval > 0:
                import time
                now = time.monotonic()
                if now - last_conditions_push >= conditions_interval:
                    reading = get_current_conditions(db_path)
                    if reading:
                        text = format_current_conditions(reading)
                        try:
                            await active_bot.send_notification(text)
                            last_conditions_push = now
                            logger.debug("Telegram conditions push sent")
                        except Exception:
                            logger.debug("Telegram conditions push failed", exc_info=True)

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
