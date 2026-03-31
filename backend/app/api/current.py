"""GET /api/current - Latest sensor reading with derived values."""

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.sensor_reading import SensorReadingModel
from ..models.station_config import StationConfigModel
from ..models.sensor_meta import convert, SENSOR_DIVISORS, SENSOR_UNITS
from ..services.daily_extremes import get_daily_extremes
from ..protocol.constants import STATION_NAMES, StationModel

router = APIRouter()

CARDINAL_DIRECTIONS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def _cardinal(degrees: int | None) -> str | None:
    if degrees is None:
        return None
    idx = round(degrees / 22.5) % 16
    return CARDINAL_DIRECTIONS[idx]


def _get_rain_yesterday(db: Session) -> dict:
    """Read rain_yesterday from station_config."""
    row = db.query(StationConfigModel).filter_by(key="rain_yesterday").first()
    value = float(row.value) if row else 0.0
    return {"value": round(value, 2), "unit": "in"}


def _val(column: str, raw: int | None) -> dict | None:
    """Convert a raw DB value to {"value": ..., "unit": ...} using sensor_meta."""
    if raw is None:
        return None
    return {"value": convert(column, raw), "unit": SENSOR_UNITS.get(column, "")}


def _clamp_humidity(val: dict | None) -> dict | None:
    """Clamp humidity display to 0-100%. Raw values may exceed 100% due to sensor tolerance."""
    if val is None or val["value"] is None:
        return val
    val["value"] = max(0, min(100, val["value"]))
    return val


def _get_daily_extremes(db: Session) -> dict | None:
    """Delegate to shared implementation."""
    return get_daily_extremes(db)


@router.get("/current")
def get_current(db: Session = Depends(get_db)):
    """Return the most recent sensor reading plus all derived values."""
    reading = (
        db.query(SensorReadingModel)
        .order_by(SensorReadingModel.timestamp.desc())
        .first()
    )

    if reading is None:
        return {"error": "No data available", "timestamp": datetime.now(timezone.utc).isoformat()}

    try:
        station_name = STATION_NAMES.get(StationModel(reading.station_type), "Unknown")
    except ValueError:
        station_name = "Unknown"

    return {
        "timestamp": reading.timestamp.isoformat() if reading.timestamp else None,
        "station_type": station_name,
        "temperature": {
            "inside": _val("inside_temp", reading.inside_temp),
            "outside": _val("outside_temp", reading.outside_temp),
        },
        "humidity": {
            "inside": _clamp_humidity(_val("inside_humidity", reading.inside_humidity)),
            "outside": _clamp_humidity(_val("outside_humidity", reading.outside_humidity)),
        },
        "wind": {
            "speed": _val("wind_speed", reading.wind_speed),
            "direction": _val("wind_direction", reading.wind_direction),
            "cardinal": _cardinal(reading.wind_direction),
        },
        "barometer": {
            "value": convert("barometer", reading.barometer),
            "unit": "inHg",
            "trend": reading.pressure_trend,
        },
        "rain": {
            "daily": _val("rain_total", reading.rain_total),
            "yearly": _val("rain_yearly", reading.rain_yearly),
            "rate": _val("rain_rate", reading.rain_rate),
            "yesterday": _get_rain_yesterday(db),
        },
        "derived": {
            "heat_index": _val("heat_index", reading.heat_index),
            "dew_point": _val("dew_point", reading.dew_point),
            "wind_chill": _val("wind_chill", reading.wind_chill),
            "feels_like": _val("feels_like", reading.feels_like),
            "theta_e": _val("theta_e", reading.theta_e),
        },
        "solar_radiation": _val("solar_radiation", reading.solar_radiation),
        "uv_index": _val("uv_index", reading.uv_index),
        "daily_extremes": _get_daily_extremes(db),
    }
