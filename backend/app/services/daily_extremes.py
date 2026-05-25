"""Shared daily extremes query — used by both the REST API and the WebSocket poller."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.sensor_reading import SensorReadingModel
from ..models.sensor_meta import convert, SENSOR_UNITS


def _iso_z(ts: Optional[datetime]) -> Optional[str]:
    """Serialise a naive-UTC datetime (SQLite returns these) as ISO-8601 with Z.

    Frontend ``new Date(iso)`` requires an explicit timezone designator to
    parse as UTC; without it the value is interpreted as local time.
    """
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _val(column: str, raw, at: Optional[datetime] = None) -> Optional[dict]:
    if raw is None:
        return None
    return {
        "value": convert(column, raw),
        "unit": SENSOR_UNITS.get(column, ""),
        "at": _iso_z(at),
    }


def _clamp_hum(val: Optional[dict]) -> Optional[dict]:
    """Clamp humidity display to 0-100%."""
    if val is None or val["value"] is None:
        return val
    val["value"] = max(0, min(100, val["value"]))
    return val


def _at(db: Session, midnight: datetime, column, raw) -> Optional[datetime]:
    """Earliest timestamp at which ``column`` equalled ``raw`` since midnight.

    Returns ``None`` when ``raw`` is ``None``.  For tied extrema the earliest
    occurrence wins so the displayed time is the first time the peak was
    reached today.
    """
    if raw is None:
        return None
    S = SensorReadingModel
    row = (
        db.query(func.min(S.timestamp))
        .filter(S.timestamp >= midnight, column == raw)
        .first()
    )
    return row[0] if row is not None else None


def get_daily_extremes(db: Session) -> Optional[dict]:
    """Query today's high/low extremes from sensor_readings.

    Used by both GET /api/current and the WebSocket broadcast poller.
    """
    now = datetime.now().astimezone()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

    S = SensorReadingModel
    row = (
        db.query(
            func.max(S.outside_temp), func.min(S.outside_temp),
            func.max(S.inside_temp), func.min(S.inside_temp),
            func.max(S.wind_speed),
            func.max(S.barometer), func.min(S.barometer),
            func.max(S.outside_humidity), func.min(S.outside_humidity),
            func.max(S.rain_rate),
            func.max(S.inside_humidity), func.min(S.inside_humidity),
        )
        .filter(S.timestamp >= midnight)
        .first()
    )

    if row is None or row[0] is None:
        return None

    return {
        "outside_temp_hi": _val("outside_temp", row[0], _at(db, midnight, S.outside_temp, row[0])),
        "outside_temp_lo": _val("outside_temp", row[1], _at(db, midnight, S.outside_temp, row[1])),
        "inside_temp_hi": _val("inside_temp", row[2], _at(db, midnight, S.inside_temp, row[2])),
        "inside_temp_lo": _val("inside_temp", row[3], _at(db, midnight, S.inside_temp, row[3])),
        "wind_speed_hi": _val("wind_speed", row[4], _at(db, midnight, S.wind_speed, row[4])),
        "barometer_hi": _val("barometer", row[5], _at(db, midnight, S.barometer, row[5])),
        "barometer_lo": _val("barometer", row[6], _at(db, midnight, S.barometer, row[6])),
        "humidity_hi": _clamp_hum(_val("outside_humidity", row[7], _at(db, midnight, S.outside_humidity, row[7]))),
        "humidity_lo": _clamp_hum(_val("outside_humidity", row[8], _at(db, midnight, S.outside_humidity, row[8]))),
        "rain_rate_hi": _val("rain_rate", row[9], _at(db, midnight, S.rain_rate, row[9])),
        "inside_humidity_hi": _clamp_hum(_val("inside_humidity", row[10], _at(db, midnight, S.inside_humidity, row[10]))),
        "inside_humidity_lo": _clamp_hum(_val("inside_humidity", row[11], _at(db, midnight, S.inside_humidity, row[11]))),
    }
