"""Public weather data schema and endpoint.

Defines the canonical JSON schema for public weather data output.
Used by push export, REST API, MQTT publish, and third-party integrations.

The schema is versioned — consumers check `api_version` to handle
format changes gracefully.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import settings
from ..models.database import get_db
from ..models.sensor_reading import SensorReadingModel
from ..models.sensor_meta import convert, SENSOR_UNITS
from ..models.station_config import StationConfigModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/public", tags=["public"])

API_VERSION = "1"


# ---------------------------------------------------------------------------
# Schema models
# ---------------------------------------------------------------------------

class StationInfo(BaseModel):
    """Station identification and location."""
    name: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    elevation_ft: Optional[float] = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "My Weather Station",
                "latitude": 35.33,
                "longitude": -97.49,
                "elevation_ft": 1200,
            }
        }


class CurrentConditions(BaseModel):
    """Current sensor readings in display units."""
    temp_f: Optional[float] = Field(None, description="Temperature (°F)")
    temp_c: Optional[float] = Field(None, description="Temperature (°C)")
    humidity: Optional[int] = Field(None, description="Relative humidity (%)")
    dewpoint_f: Optional[float] = Field(None, description="Dew point (°F)")
    dewpoint_c: Optional[float] = Field(None, description="Dew point (°C)")
    wind_mph: Optional[int] = Field(None, description="Wind speed (mph)")
    wind_kmh: Optional[float] = Field(None, description="Wind speed (km/h)")
    wind_dir: Optional[int] = Field(None, description="Wind direction (degrees)")
    wind_dir_str: Optional[str] = Field(None, description="Wind direction (cardinal)")
    wind_gust_mph: Optional[int] = Field(None, description="Wind gust (mph)")
    barometer_inhg: Optional[float] = Field(None, description="Barometric pressure (inHg)")
    barometer_hpa: Optional[float] = Field(None, description="Barometric pressure (hPa)")
    rain_rate_in: Optional[float] = Field(None, description="Rain rate (in/hr)")
    rain_rate_mm: Optional[float] = Field(None, description="Rain rate (mm/hr)")
    rain_day_in: Optional[float] = Field(None, description="Rain today (inches)")
    rain_day_mm: Optional[float] = Field(None, description="Rain today (mm)")
    solar_radiation: Optional[int] = Field(None, description="Solar radiation (W/m²)")
    uv_index: Optional[float] = Field(None, description="UV index")
    feels_like_f: Optional[float] = Field(None, description="Feels like (°F)")
    feels_like_c: Optional[float] = Field(None, description="Feels like (°C)")
    heat_index_f: Optional[float] = Field(None, description="Heat index (°F)")
    heat_index_c: Optional[float] = Field(None, description="Heat index (°C)")
    wind_chill_f: Optional[float] = Field(None, description="Wind chill (°F)")
    wind_chill_c: Optional[float] = Field(None, description="Wind chill (°C)")
    pressure_trend: Optional[str] = Field(None, description="Pressure trend (rising/falling/steady)")


class DailyExtremes(BaseModel):
    """Today's high and low values."""
    temp_high_f: Optional[float] = Field(None, description="High temperature (°F)")
    temp_low_f: Optional[float] = Field(None, description="Low temperature (°F)")
    temp_high_c: Optional[float] = Field(None, description="High temperature (°C)")
    temp_low_c: Optional[float] = Field(None, description="Low temperature (°C)")
    wind_high_mph: Optional[int] = Field(None, description="Peak wind (mph)")
    rain_total_in: Optional[float] = Field(None, description="Total rain (inches)")
    rain_total_mm: Optional[float] = Field(None, description="Total rain (mm)")


class PublicMeta(BaseModel):
    """Metadata about the reading."""
    timestamp: str = Field(description="ISO 8601 UTC timestamp")
    station_type: Optional[str] = Field(None, description="Hardware model")
    software: str = Field(default="Kanfei", description="Software name")
    software_version: str = Field(default="0.1.0", description="Software version")
    api_version: str = Field(default=API_VERSION, description="Schema version")


class PublicWeatherData(BaseModel):
    """Complete public weather data payload.

    This is the canonical schema used by all public data outputs:
    push export, REST API, MQTT, and embeddable widgets.
    """
    station: StationInfo
    current: CurrentConditions
    daily: DailyExtremes
    meta: PublicMeta


# ---------------------------------------------------------------------------
# Cardinal direction helper
# ---------------------------------------------------------------------------

_CARDINALS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]

def _cardinal(deg: Optional[int]) -> Optional[str]:
    if deg is None:
        return None
    return _CARDINALS[round(deg / 22.5) % 16]


# ---------------------------------------------------------------------------
# Build public data from DB
# ---------------------------------------------------------------------------

def build_public_data(db: Session) -> PublicWeatherData:
    """Build a PublicWeatherData payload from the current DB state."""
    from ..models.sensor_meta import convert
    from ..utils.units import si_temp_to_display_c, si_pressure_to_display_hpa, si_wind_to_display_kmh, si_rain_to_display_mm

    # Station info from config
    def _cfg(key: str, default: str = "") -> str:
        row = db.query(StationConfigModel).filter_by(key=key).first()
        return row.value if row else default

    station = StationInfo(
        name=_cfg("station_name", "Kanfei Weather Station"),
        latitude=float(_cfg("latitude", "0")) or None,
        longitude=float(_cfg("longitude", "0")) or None,
        elevation_ft=float(_cfg("elevation", "0")) or None,
    )

    # Latest reading
    reading = (
        db.query(SensorReadingModel)
        .order_by(SensorReadingModel.timestamp.desc())
        .first()
    )

    if reading is None:
        return PublicWeatherData(
            station=station,
            current=CurrentConditions(),
            daily=DailyExtremes(),
            meta=PublicMeta(timestamp=datetime.now(timezone.utc).isoformat()),
        )

    # Convert SI DB values to both imperial and metric display
    temp_f = convert("outside_temp", reading.outside_temp)
    temp_c = si_temp_to_display_c(reading.outside_temp) if reading.outside_temp is not None else None
    baro_inhg = convert("barometer", reading.barometer)
    baro_hpa = si_pressure_to_display_hpa(reading.barometer) if reading.barometer is not None else None
    wind_mph = convert("wind_speed", reading.wind_speed)
    wind_kmh = si_wind_to_display_kmh(reading.wind_speed) if reading.wind_speed is not None else None
    rain_day_in = convert("rain_total", reading.rain_total)
    rain_day_mm = si_rain_to_display_mm(reading.rain_total) if reading.rain_total is not None else None
    rain_rate_in = convert("rain_rate", reading.rain_rate)
    rain_rate_mm = si_rain_to_display_mm(reading.rain_rate) if reading.rain_rate is not None else None

    dp_f = convert("dew_point", reading.dew_point)
    dp_c = si_temp_to_display_c(reading.dew_point) if reading.dew_point is not None else None
    fl_f = convert("feels_like", reading.feels_like)
    fl_c = si_temp_to_display_c(reading.feels_like) if reading.feels_like is not None else None
    hi_f = convert("heat_index", reading.heat_index)
    hi_c = si_temp_to_display_c(reading.heat_index) if reading.heat_index is not None else None
    wc_f = convert("wind_chill", reading.wind_chill)
    wc_c = si_temp_to_display_c(reading.wind_chill) if reading.wind_chill is not None else None

    current = CurrentConditions(
        temp_f=temp_f,
        temp_c=temp_c,
        humidity=reading.outside_humidity,
        dewpoint_f=dp_f,
        dewpoint_c=dp_c,
        wind_mph=wind_mph,
        wind_kmh=wind_kmh,
        wind_dir=reading.wind_direction,
        wind_dir_str=_cardinal(reading.wind_direction),
        barometer_inhg=baro_inhg,
        barometer_hpa=baro_hpa,
        rain_rate_in=rain_rate_in,
        rain_rate_mm=rain_rate_mm,
        rain_day_in=rain_day_in,
        rain_day_mm=rain_day_mm,
        solar_radiation=reading.solar_radiation,
        uv_index=convert("uv_index", reading.uv_index),
        feels_like_f=fl_f,
        feels_like_c=fl_c,
        heat_index_f=hi_f,
        heat_index_c=hi_c,
        wind_chill_f=wc_f,
        wind_chill_c=wc_c,
        pressure_trend=reading.pressure_trend,
    )

    # Daily extremes
    from sqlalchemy import func
    now = datetime.now().astimezone()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    S = SensorReadingModel

    row = (
        db.query(
            func.max(S.outside_temp), func.min(S.outside_temp),
            func.max(S.wind_speed),
            func.max(S.rain_total),
        )
        .filter(S.timestamp >= midnight)
        .first()
    )

    daily = DailyExtremes()
    if row and row[0] is not None:
        daily.temp_high_f = convert("outside_temp", row[0])
        daily.temp_low_f = convert("outside_temp", row[1])
        daily.temp_high_c = si_temp_to_display_c(row[0])
        daily.temp_low_c = si_temp_to_display_c(row[1])
        daily.wind_high_mph = convert("wind_speed", row[2])
        daily.rain_total_in = convert("rain_total", row[3])
        daily.rain_total_mm = si_rain_to_display_mm(row[3]) if row[3] is not None else None

    from ..protocol.constants import STATION_NAMES, StationModel
    try:
        station_type = STATION_NAMES.get(StationModel(reading.station_type), None)
    except (ValueError, KeyError):
        station_type = None

    meta = PublicMeta(
        timestamp=reading.timestamp.isoformat() if reading.timestamp else datetime.now(timezone.utc).isoformat(),
        station_type=station_type,
    )

    return PublicWeatherData(
        station=station,
        current=current,
        daily=daily,
        meta=meta,
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/weather", response_model=PublicWeatherData)
def get_public_weather(db: Session = Depends(get_db)):
    """Public weather data in the canonical JSON schema.

    Provides both imperial and metric values for all measurements.
    No authentication required.
    """
    return build_public_data(db)
