"""Tests for Telegram bot service."""

import sqlite3
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.telegram import (
    TelegramBot,
    format_current_conditions,
    _read_telegram_config,
    _cardinal,
    _get_current_conditions,
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


class TestCardinal:

    def test_north(self):
        assert _cardinal(0) == "N"

    def test_south(self):
        assert _cardinal(180) == "S"

    def test_east(self):
        assert _cardinal(90) == "E"

    def test_west(self):
        assert _cardinal(270) == "W"

    def test_none(self):
        assert _cardinal(None) == "---"

    def test_northeast(self):
        assert _cardinal(45) == "NE"


class TestReadTelegramConfig:

    def test_defaults_when_empty(self, fake_db):
        cfg = _read_telegram_config(fake_db)
        assert cfg["bot_telegram_enabled"] is False
        assert cfg["bot_telegram_token"] == ""
        assert cfg["bot_telegram_chat_id"] == ""
        assert cfg["bot_telegram_commands"] == "current,status"

    def test_reads_saved_values(self, fake_db):
        conn = sqlite3.connect(fake_db)
        conn.execute(
            "INSERT INTO station_config VALUES ('bot_telegram_enabled', 'true', '2026-01-01')"
        )
        conn.execute(
            "INSERT INTO station_config VALUES ('bot_telegram_token', 'abc:123', '2026-01-01')"
        )
        conn.execute(
            "INSERT INTO station_config VALUES ('bot_telegram_chat_id', '999', '2026-01-01')"
        )
        conn.commit()
        conn.close()

        cfg = _read_telegram_config(fake_db)
        assert cfg["bot_telegram_enabled"] is True
        assert cfg["bot_telegram_token"] == "abc:123"
        assert cfg["bot_telegram_chat_id"] == "999"

    def test_nonexistent_db(self):
        cfg = _read_telegram_config("/nonexistent/db.sqlite")
        assert cfg["bot_telegram_enabled"] is False


class TestGetCurrentConditions:

    def test_returns_none_when_empty(self, fake_db):
        assert _get_current_conditions(fake_db) is None

    def test_returns_latest_reading(self, fake_db_with_reading):
        reading = _get_current_conditions(fake_db_with_reading)
        assert reading is not None
        assert reading["outside_temp"] == 222
        assert reading["wind_speed"] == 45
        assert reading["barometer"] == 10132


class TestFormatCurrentConditions:

    def test_basic_formatting(self):
        reading = {
            "timestamp": "2026-03-27T14:30:00+00:00",
            "outside_temp": 222,      # 22.2°C = 72.0°F
            "outside_humidity": 62,
            "wind_speed": 45,          # 4.5 m/s = 10 mph
            "wind_direction": 180,
            "barometer": 10132,        # 1013.2 hPa = 29.92 inHg
            "rain_total": 0,
            "rain_rate": 0,
            "dew_point": 150,
            "feels_like": 230,
            "uv_index": 50,
            "pressure_trend": "Steady",
        }
        text = format_current_conditions(reading)

        assert "72.0\u00b0F" in text
        assert "62%" in text
        assert "10 mph" in text
        assert "S" in text
        assert "29.92 inHg" in text
        assert "Steady" in text
        assert "5.0" in text  # UV index

    def test_handles_none_values(self):
        reading = {
            "timestamp": "",
            "outside_temp": None,
            "outside_humidity": None,
            "wind_speed": None,
            "wind_direction": None,
            "barometer": None,
            "rain_total": None,
            "rain_rate": None,
            "dew_point": None,
            "feels_like": None,
            "uv_index": None,
            "pressure_trend": None,
        }
        text = format_current_conditions(reading)
        assert "---" in text

    def test_includes_header(self):
        reading = {
            "timestamp": "2026-03-27T14:30:00+00:00",
            "outside_temp": 222,
            "outside_humidity": 62,
            "wind_speed": 45,
            "wind_direction": 180,
            "barometer": 10132,
            "rain_total": 0,
            "rain_rate": 0,
            "dew_point": 150,
            "feels_like": 230,
            "uv_index": 50,
            "pressure_trend": "",
        }
        text = format_current_conditions(reading)
        assert "Current Conditions" in text


class TestChatIdWhitelist:

    def test_allows_whitelisted_chat(self):
        bot = TelegramBot(
            token="test", chat_ids={"123", "456"}, db_path="",
            enabled_commands={"current"}, dry_run=True,
        )
        assert bot._is_chat_allowed("123") is True
        assert bot._is_chat_allowed("456") is True

    def test_rejects_non_whitelisted_chat(self):
        bot = TelegramBot(
            token="test", chat_ids={"123"}, db_path="",
            enabled_commands={"current"}, dry_run=True,
        )
        assert bot._is_chat_allowed("999") is False

    def test_empty_whitelist_allows_all(self):
        bot = TelegramBot(
            token="test", chat_ids=set(), db_path="",
            enabled_commands={"current"}, dry_run=True,
        )
        assert bot._is_chat_allowed("anything") is True


class TestRateLimiting:

    def test_first_command_not_limited(self):
        bot = TelegramBot(
            token="test", chat_ids=set(), db_path="",
            enabled_commands={"current"}, dry_run=True,
        )
        assert bot._is_rate_limited("123") is False

    def test_rapid_second_command_limited(self):
        bot = TelegramBot(
            token="test", chat_ids=set(), db_path="",
            enabled_commands={"current"}, dry_run=True,
        )
        bot._is_rate_limited("123")  # First call records time
        assert bot._is_rate_limited("123") is True

    def test_different_chats_independent(self):
        bot = TelegramBot(
            token="test", chat_ids=set(), db_path="",
            enabled_commands={"current"}, dry_run=True,
        )
        bot._is_rate_limited("123")
        assert bot._is_rate_limited("456") is False


class TestHandleCurrentCommand:

    @pytest.mark.asyncio
    async def test_sends_conditions(self, fake_db_with_reading):
        bot = TelegramBot(
            token="test", chat_ids=set(), db_path=fake_db_with_reading,
            enabled_commands={"current"}, dry_run=True,
        )
        bot._send_message = AsyncMock()

        update = MagicMock()
        update.effective_chat.id = 123
        context = MagicMock()

        await bot._handle_current(update, context)

        bot._send_message.assert_called_once()
        call_args = bot._send_message.call_args
        assert call_args[0][0] == "123"
        assert "72.0\u00b0F" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_no_data_message(self, fake_db):
        bot = TelegramBot(
            token="test", chat_ids=set(), db_path=fake_db,
            enabled_commands={"current"}, dry_run=True,
        )
        bot._send_message = AsyncMock()

        update = MagicMock()
        update.effective_chat.id = 123
        context = MagicMock()

        await bot._handle_current(update, context)

        bot._send_message.assert_called_once_with("123", "No weather data available.")

    @pytest.mark.asyncio
    async def test_unauthorized_chat_ignored(self, fake_db_with_reading):
        bot = TelegramBot(
            token="test", chat_ids={"999"}, db_path=fake_db_with_reading,
            enabled_commands={"current"}, dry_run=True,
        )
        bot._send_message = AsyncMock()

        update = MagicMock()
        update.effective_chat.id = 123
        context = MagicMock()

        await bot._handle_current(update, context)

        bot._send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_limited_ignored(self, fake_db_with_reading):
        bot = TelegramBot(
            token="test", chat_ids=set(), db_path=fake_db_with_reading,
            enabled_commands={"current"}, dry_run=True,
        )
        bot._send_message = AsyncMock()

        update = MagicMock()
        update.effective_chat.id = 123
        context = MagicMock()

        await bot._handle_current(update, context)
        bot._send_message.reset_mock()

        # Second call should be rate-limited
        await bot._handle_current(update, context)
        bot._send_message.assert_not_called()


class TestHandleStatusCommand:

    @pytest.mark.asyncio
    async def test_sends_status(self, fake_db_with_reading):
        bot = TelegramBot(
            token="test", chat_ids=set(), db_path=fake_db_with_reading,
            enabled_commands={"status"}, dry_run=True,
        )
        bot._send_message = AsyncMock()

        update = MagicMock()
        update.effective_chat.id = 123
        context = MagicMock()

        await bot._handle_status(update, context)

        bot._send_message.assert_called_once()
        text = bot._send_message.call_args[0][1]
        assert "Station Status" in text
        assert "online" in text

    @pytest.mark.asyncio
    async def test_offline_when_no_data(self, fake_db):
        bot = TelegramBot(
            token="test", chat_ids=set(), db_path=fake_db,
            enabled_commands={"status"}, dry_run=True,
        )
        bot._send_message = AsyncMock()

        update = MagicMock()
        update.effective_chat.id = 123
        context = MagicMock()

        await bot._handle_status(update, context)

        bot._send_message.assert_called_once()
        text = bot._send_message.call_args[0][1]
        assert "offline" in text
