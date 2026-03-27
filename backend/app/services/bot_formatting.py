"""Shared message formatting for bot integrations.

Platform-agnostic plain-text formatters used by all bot adapters
(Telegram, Discord, Slack). Each function takes structured data and
returns a human-readable string.
"""

import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_CARDINAL_DIRECTIONS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def cardinal(degrees: int | None) -> str:
    """Convert wind direction degrees to cardinal abbreviation."""
    if degrees is None:
        return "---"
    idx = round(degrees / 22.5) % 16
    return _CARDINAL_DIRECTIONS[idx]


def get_current_conditions(db_path: str) -> dict | None:
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
    """Format a sensor reading dict into a human-readable message.

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
    card = cardinal(wind_dir)
    wind_deg = f"{wind_dir}\u00b0" if wind_dir is not None else "---"

    trend = reading.get("pressure_trend", "")
    trend_str = f" ({trend})" if trend else ""

    lines = [
        f"\U0001f321 *Current Conditions*  \u2014  {ts}",
        "",
        f"Temp: {_temp(reading.get('outside_temp'))}  (Feels: {_temp(reading.get('feels_like'))})",
        f"Humidity: {_humidity(reading.get('outside_humidity'))}",
        f"Dew Point: {_temp(reading.get('dew_point'))}",
        f"Wind: {card} {wind_deg} at {_wind(reading.get('wind_speed'))}",
        f"Barometer: {_baro(reading.get('barometer'))}{trend_str}",
        f"Rain Today: {_rain(reading.get('rain_total'))}  (Rate: {_rain(reading.get('rain_rate'))}/hr)",
        f"UV Index: {_uv(reading.get('uv_index'))}",
    ]

    return "\n".join(lines)


def format_alert_triggered(data: dict) -> str:
    """Format an alert_triggered event into a message."""
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
    """Format an alert_cleared event into a message."""
    label = data.get("label", "Unknown alert")
    return f"\u2705 *Alert cleared: {label}*"


def format_nowcast_update(data: dict) -> str | None:
    """Format a nowcast_update event into a message.

    Returns None if the nowcast data lacks a summary.
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


def format_status(reading: dict | None) -> str:
    """Format station status into a message."""
    if reading is None:
        return "Station offline \u2014 no data available."

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

    lines = [
        "\U0001f4e1 *Station Status*",
        "",
        "Status: online",
        f"Last reading: {age_str}",
    ]
    return "\n".join(lines)
