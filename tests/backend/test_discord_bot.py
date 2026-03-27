"""Tests for Discord bot service."""

import sqlite3
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.discord_bot import (
    DiscordBot,
    _read_discord_config,
)
from app.services.bot_formatting import (
    format_current_conditions,
    format_alert_triggered,
    format_alert_cleared,
    format_nowcast_update,
    format_help,
    get_current_conditions,
)


@pytest.fixture
def fake_db(tmp_path):
    """Create a minimal SQLite DB with station_config and sensor_readings."""
    db_path = tmp_path / "kanfei.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE station_config "
        "(key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE sensor_readings ("
        "  id INTEGER PRIMARY KEY,"
        "  timestamp TEXT,"
        "  station_type INTEGER,"
        "  inside_temp INTEGER,"
        "  outside_temp INTEGER,"
        "  inside_humidity INTEGER,"
        "  outside_humidity INTEGER,"
        "  wind_speed INTEGER,"
        "  wind_direction INTEGER,"
        "  barometer INTEGER,"
        "  rain_total INTEGER,"
        "  rain_rate INTEGER,"
        "  rain_yearly INTEGER,"
        "  solar_radiation INTEGER,"
        "  uv_index INTEGER,"
        "  extra_json TEXT,"
        "  heat_index INTEGER,"
        "  dew_point INTEGER,"
        "  wind_chill INTEGER,"
        "  feels_like INTEGER,"
        "  theta_e INTEGER,"
        "  pressure_trend TEXT"
        ")"
    )
    conn.commit()
    conn.close()
    return str(db_path)


@pytest.fixture
def fake_db_with_reading(fake_db):
    """Fake DB with one sensor reading."""
    conn = sqlite3.connect(fake_db)
    conn.execute(
        "INSERT INTO sensor_readings "
        "(timestamp, station_type, outside_temp, outside_humidity, "
        " wind_speed, wind_direction, barometer, rain_total, rain_rate, "
        " dew_point, feels_like, uv_index, pressure_trend) "
        "VALUES (?, 17, 222, 62, 45, 180, 10132, 0, 0, 150, 230, 50, 'Steady')",
        (datetime.now(timezone.utc).isoformat(),),
    )
    conn.commit()
    conn.close()
    return fake_db


class TestReadDiscordConfig:

    def test_defaults_when_empty(self, fake_db):
        cfg = _read_discord_config(fake_db)
        assert cfg["bot_discord_enabled"] is False
        assert cfg["bot_discord_token"] == ""
        assert cfg["bot_discord_guild_id"] == ""
        assert cfg["bot_discord_channel_id"] == ""
        assert cfg["bot_discord_commands"] == "current,status,help"
        assert cfg["bot_discord_notifications"] == "nowcast,alerts"

    def test_reads_saved_values(self, fake_db):
        conn = sqlite3.connect(fake_db)
        conn.execute(
            "INSERT INTO station_config VALUES ('bot_discord_enabled', 'true', '2026-01-01')"
        )
        conn.execute(
            "INSERT INTO station_config VALUES ('bot_discord_token', 'abc.123.xyz', '2026-01-01')"
        )
        conn.execute(
            "INSERT INTO station_config VALUES ('bot_discord_guild_id', '999888777', '2026-01-01')"
        )
        conn.commit()
        conn.close()

        cfg = _read_discord_config(fake_db)
        assert cfg["bot_discord_enabled"] is True
        assert cfg["bot_discord_token"] == "abc.123.xyz"
        assert cfg["bot_discord_guild_id"] == "999888777"

    def test_nonexistent_db(self):
        cfg = _read_discord_config("/nonexistent/db.sqlite")
        assert cfg["bot_discord_enabled"] is False


class TestChannelWhitelist:

    def test_allows_whitelisted_channel(self):
        bot = DiscordBot(
            token="test", guild_id="", channel_ids={"123", "456"},
            db_path="", enabled_commands={"current"}, dry_run=True,
        )
        assert bot._is_channel_allowed("123") is True
        assert bot._is_channel_allowed("456") is True

    def test_rejects_non_whitelisted_channel(self):
        bot = DiscordBot(
            token="test", guild_id="", channel_ids={"123"},
            db_path="", enabled_commands={"current"}, dry_run=True,
        )
        assert bot._is_channel_allowed("999") is False

    def test_empty_whitelist_allows_all(self):
        bot = DiscordBot(
            token="test", guild_id="", channel_ids=set(),
            db_path="", enabled_commands={"current"}, dry_run=True,
        )
        assert bot._is_channel_allowed("anything") is True


class TestHandleCurrentCommand:

    @pytest.mark.asyncio
    async def test_sends_conditions(self, fake_db_with_reading):
        bot = DiscordBot(
            token="test", guild_id="", channel_ids=set(),
            db_path=fake_db_with_reading,
            enabled_commands={"current"}, dry_run=True,
        )
        bot._send_response = AsyncMock()

        interaction = MagicMock()
        interaction.channel_id = 123

        await bot._handle_current(interaction)

        bot._send_response.assert_called_once()
        text = bot._send_response.call_args[0][1]
        assert "72.0\u00b0F" in text

    @pytest.mark.asyncio
    async def test_no_data_message(self, fake_db):
        bot = DiscordBot(
            token="test", guild_id="", channel_ids=set(),
            db_path=fake_db,
            enabled_commands={"current"}, dry_run=True,
        )
        bot._send_response = AsyncMock()

        interaction = MagicMock()
        interaction.channel_id = 123

        await bot._handle_current(interaction)

        bot._send_response.assert_called_once()
        text = bot._send_response.call_args[0][1]
        assert "No weather data" in text

    @pytest.mark.asyncio
    async def test_unauthorized_channel_ignored(self, fake_db_with_reading):
        bot = DiscordBot(
            token="test", guild_id="", channel_ids={"999"},
            db_path=fake_db_with_reading,
            enabled_commands={"current"}, dry_run=True,
        )
        bot._send_response = AsyncMock()

        interaction = MagicMock()
        interaction.channel_id = 123

        await bot._handle_current(interaction)

        bot._send_response.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_limited(self, fake_db_with_reading):
        bot = DiscordBot(
            token="test", guild_id="", channel_ids=set(),
            db_path=fake_db_with_reading,
            enabled_commands={"current"}, dry_run=True,
        )
        bot._send_response = AsyncMock()

        interaction = MagicMock()
        interaction.channel_id = 123

        await bot._handle_current(interaction)
        bot._send_response.reset_mock()

        await bot._handle_current(interaction)
        bot._send_response.assert_called_once()
        assert "wait" in bot._send_response.call_args[0][1].lower()


class TestHandleStatusCommand:

    @pytest.mark.asyncio
    async def test_sends_status(self, fake_db_with_reading):
        bot = DiscordBot(
            token="test", guild_id="", channel_ids=set(),
            db_path=fake_db_with_reading,
            enabled_commands={"status"}, dry_run=True,
        )
        bot._send_response = AsyncMock()

        interaction = MagicMock()
        interaction.channel_id = 123

        await bot._handle_status(interaction)

        bot._send_response.assert_called_once()
        text = bot._send_response.call_args[0][1]
        assert "Station Status" in text
        assert "online" in text

    @pytest.mark.asyncio
    async def test_offline_when_no_data(self, fake_db):
        bot = DiscordBot(
            token="test", guild_id="", channel_ids=set(),
            db_path=fake_db,
            enabled_commands={"status"}, dry_run=True,
        )
        bot._send_response = AsyncMock()

        interaction = MagicMock()
        interaction.channel_id = 123

        await bot._handle_status(interaction)

        bot._send_response.assert_called_once()
        text = bot._send_response.call_args[0][1]
        assert "offline" in text


class TestHandleHelpCommand:

    @pytest.mark.asyncio
    async def test_sends_help(self):
        bot = DiscordBot(
            token="test", guild_id="", channel_ids=set(),
            db_path="", enabled_commands={"help"}, dry_run=True,
        )
        bot._send_response = AsyncMock()

        interaction = MagicMock()
        interaction.channel_id = 123

        await bot._handle_help(interaction)

        bot._send_response.assert_called_once()
        text = bot._send_response.call_args[0][1]
        assert "/current" in text
        assert "/help" in text


class TestHandleEvent:

    @pytest.mark.asyncio
    async def test_alert_triggered_sends_notification(self):
        bot = DiscordBot(
            token="test", guild_id="", channel_ids={"123"},
            db_path="", enabled_commands=set(),
            enabled_notifications={"alerts"}, dry_run=True,
        )
        bot.send_notification = AsyncMock()

        await bot.handle_event({
            "type": "alert_triggered",
            "data": {
                "id": "a1", "label": "Wind Alert",
                "sensor": "wind_speed", "value": 35,
                "threshold": 30, "operator": ">=",
            },
        })

        bot.send_notification.assert_called_once()
        assert "Wind Alert" in bot.send_notification.call_args[0][0]

    @pytest.mark.asyncio
    async def test_alert_triggered_dedup(self):
        bot = DiscordBot(
            token="test", guild_id="", channel_ids={"123"},
            db_path="", enabled_commands=set(),
            enabled_notifications={"alerts"}, dry_run=True,
        )
        bot.send_notification = AsyncMock()

        msg = {
            "type": "alert_triggered",
            "data": {"id": "a1", "label": "Wind Alert",
                     "sensor": "wind_speed", "value": 35,
                     "threshold": 30, "operator": ">="},
        }
        await bot.handle_event(msg)
        await bot.handle_event(msg)

        assert bot.send_notification.call_count == 1

    @pytest.mark.asyncio
    async def test_alert_cleared_sends_notification(self):
        bot = DiscordBot(
            token="test", guild_id="", channel_ids={"123"},
            db_path="", enabled_commands=set(),
            enabled_notifications={"alerts"}, dry_run=True,
        )
        bot.send_notification = AsyncMock()

        await bot.handle_event({
            "type": "alert_triggered",
            "data": {"id": "a1", "label": "Wind Alert",
                     "sensor": "wind_speed", "value": 35,
                     "threshold": 30, "operator": ">="},
        })
        bot.send_notification.reset_mock()

        await bot.handle_event({
            "type": "alert_cleared",
            "data": {"id": "a1", "label": "Wind Alert"},
        })

        bot.send_notification.assert_called_once()
        assert "cleared" in bot.send_notification.call_args[0][0]

    @pytest.mark.asyncio
    async def test_nowcast_update_sends_notification(self):
        bot = DiscordBot(
            token="test", guild_id="", channel_ids={"123"},
            db_path="", enabled_commands=set(),
            enabled_notifications={"nowcast"}, dry_run=True,
        )
        bot.send_notification = AsyncMock()

        await bot.handle_event({
            "type": "nowcast_update",
            "data": {"summary": "Rain expected within 30 minutes."},
        })

        bot.send_notification.assert_called_once()
        assert "Rain expected" in bot.send_notification.call_args[0][0]

    @pytest.mark.asyncio
    async def test_disabled_notifications_ignored(self):
        bot = DiscordBot(
            token="test", guild_id="", channel_ids={"123"},
            db_path="", enabled_commands=set(),
            enabled_notifications={"alerts"}, dry_run=True,
        )
        bot.send_notification = AsyncMock()

        await bot.handle_event({
            "type": "nowcast_update",
            "data": {"summary": "Rain expected."},
        })

        bot.send_notification.assert_not_called()


class TestSendNotification:

    @pytest.mark.asyncio
    async def test_sends_to_all_channels(self):
        bot = DiscordBot(
            token="test", guild_id="", channel_ids={"111", "222"},
            db_path="", enabled_commands=set(), dry_run=True,
        )
        bot._send_to_channel = AsyncMock()

        await bot.send_notification("Test message")

        assert bot._send_to_channel.call_count == 2
        sent_channels = {call[0][0] for call in bot._send_to_channel.call_args_list}
        assert sent_channels == {"111", "222"}

    @pytest.mark.asyncio
    async def test_empty_text_skipped(self):
        bot = DiscordBot(
            token="test", guild_id="", channel_ids={"123"},
            db_path="", enabled_commands=set(), dry_run=True,
        )
        bot._send_to_channel = AsyncMock()

        await bot.send_notification("")
        bot._send_to_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_channels_skipped(self):
        bot = DiscordBot(
            token="test", guild_id="", channel_ids=set(),
            db_path="", enabled_commands=set(), dry_run=True,
        )
        bot._send_to_channel = AsyncMock()

        await bot.send_notification("Test")
        bot._send_to_channel.assert_not_called()
