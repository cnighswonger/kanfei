"""WeatherFlow Tempest sensor data parsing.

Parses observation arrays from UDP JSON datagrams. Tempest reports
natively in SI (°C, m/s, hPa, mm) — values pass through to
SensorSnapshot without unit conversion.
"""

from typing import Any, Optional

from ..base import SensorSnapshot
from .constants import (
    ST_TIMESTAMP, ST_WIND_LULL, ST_WIND_AVG, ST_WIND_GUST, ST_WIND_DIR,
    ST_PRESSURE, ST_TEMP, ST_HUMIDITY, ST_ILLUMINANCE, ST_UV_INDEX,
    ST_SOLAR_RAD, ST_RAIN_ACCUM, ST_PRECIP_TYPE, ST_LIGHTNING_DIST,
    ST_LIGHTNING_COUNT, ST_BATTERY, ST_REPORT_INTERVAL, ST_FIELD_COUNT,
    AIR_PRESSURE, AIR_TEMP, AIR_HUMIDITY, AIR_LIGHTNING_COUNT,
    AIR_LIGHTNING_DIST, AIR_BATTERY, AIR_REPORT_INTERVAL, AIR_FIELD_COUNT,
    SKY_ILLUMINANCE, SKY_UV_INDEX, SKY_RAIN_ACCUM, SKY_WIND_LULL,
    SKY_WIND_AVG, SKY_WIND_GUST, SKY_WIND_DIR, SKY_BATTERY,
    SKY_REPORT_INTERVAL, SKY_SOLAR_RAD, SKY_PRECIP_TYPE, SKY_FIELD_COUNT,
    RW_WIND_SPEED, RW_WIND_DIR, RW_FIELD_COUNT,
)


def _safe(obs: list, idx: int) -> Any:
    """Safely extract a value from an observation array."""
    if idx < len(obs):
        return obs[idx]
    return None


# --------------- Observation parsers (SI passthrough) ---------------

def parse_obs_st(obs: list) -> dict[str, Any]:
    """Parse an obs_st observation array (Tempest all-in-one, 18 fields).

    All values remain in native SI: °C, m/s, hPa, mm.
    """
    if len(obs) < ST_FIELD_COUNT:
        return {}

    temp_c = _safe(obs, ST_TEMP)
    pressure_hpa = _safe(obs, ST_PRESSURE)
    rain_mm = _safe(obs, ST_RAIN_ACCUM)
    interval = _safe(obs, ST_REPORT_INTERVAL)

    return {
        "timestamp": _safe(obs, ST_TIMESTAMP),
        "outside_temp_c": temp_c,
        "outside_humidity": int(obs[ST_HUMIDITY]) if obs[ST_HUMIDITY] is not None else None,
        "station_pressure_hpa": pressure_hpa,
        "wind_speed_ms": obs[ST_WIND_AVG],
        "wind_gust_ms": obs[ST_WIND_GUST],
        "wind_lull_ms": obs[ST_WIND_LULL],
        "wind_dir": int(obs[ST_WIND_DIR]) if obs[ST_WIND_DIR] is not None else None,
        "solar_radiation": int(obs[ST_SOLAR_RAD]) if obs[ST_SOLAR_RAD] is not None else None,
        "uv_index": obs[ST_UV_INDEX],
        "illuminance_lux": obs[ST_ILLUMINANCE],
        "rain_accum_mm": rain_mm if rain_mm is not None else 0.0,
        "report_interval_min": interval if interval is not None else 1,
        "precip_type": _safe(obs, ST_PRECIP_TYPE),
        "lightning_distance_km": _safe(obs, ST_LIGHTNING_DIST),
        "lightning_count": _safe(obs, ST_LIGHTNING_COUNT),
        "battery_v": _safe(obs, ST_BATTERY),
    }


def parse_obs_air(obs: list) -> dict[str, Any]:
    """Parse an obs_air observation array (legacy Air sensor, 8 fields)."""
    if len(obs) < AIR_FIELD_COUNT:
        return {}

    temp_c = _safe(obs, AIR_TEMP)
    pressure_hpa = _safe(obs, AIR_PRESSURE)

    return {
        "timestamp": obs[0],
        "outside_temp_c": temp_c,
        "outside_humidity": int(obs[AIR_HUMIDITY]) if obs[AIR_HUMIDITY] is not None else None,
        "station_pressure_hpa": pressure_hpa,
        "lightning_count": _safe(obs, AIR_LIGHTNING_COUNT),
        "lightning_distance_km": _safe(obs, AIR_LIGHTNING_DIST),
        "battery_v": _safe(obs, AIR_BATTERY),
        "report_interval_min": _safe(obs, AIR_REPORT_INTERVAL) or 1,
    }


def parse_obs_sky(obs: list) -> dict[str, Any]:
    """Parse an obs_sky observation array (legacy Sky sensor, 14 fields)."""
    if len(obs) < SKY_FIELD_COUNT:
        return {}

    rain_mm = _safe(obs, SKY_RAIN_ACCUM)

    return {
        "timestamp": obs[0],
        "wind_speed_ms": obs[SKY_WIND_AVG],
        "wind_gust_ms": obs[SKY_WIND_GUST],
        "wind_lull_ms": obs[SKY_WIND_LULL],
        "wind_dir": int(obs[SKY_WIND_DIR]) if obs[SKY_WIND_DIR] is not None else None,
        "solar_radiation": int(obs[SKY_SOLAR_RAD]) if obs[SKY_SOLAR_RAD] is not None else None,
        "uv_index": _safe(obs, SKY_UV_INDEX),
        "illuminance_lux": _safe(obs, SKY_ILLUMINANCE),
        "rain_accum_mm": rain_mm if rain_mm is not None else 0.0,
        "report_interval_min": _safe(obs, SKY_REPORT_INTERVAL) or 1,
        "precip_type": _safe(obs, SKY_PRECIP_TYPE),
        "battery_v": _safe(obs, SKY_BATTERY),
    }


def parse_rapid_wind(ob: list) -> dict[str, Any]:
    """Parse a rapid_wind observation (3 fields, single array under 'ob')."""
    if len(ob) < RW_FIELD_COUNT:
        return {}
    return {
        "timestamp": ob[0],
        "wind_speed_ms": ob[RW_WIND_SPEED],
        "wind_dir": int(ob[RW_WIND_DIR]) if ob[RW_WIND_DIR] is not None else None,
    }


def _correct_pressure(station_hpa: float, elevation_m: float) -> float:
    """Apply barometric altitude correction to station pressure (hPa).

    Converts station pressure to approximate sea-level pressure using
    the hypsometric formula.
    """
    if elevation_m == 0:
        return station_hpa
    ratio = 1.0 - (elevation_m / 44330.0)
    if ratio <= 0:
        return station_hpa
    return station_hpa / (ratio ** 5.255)


def build_snapshot(
    obs_data: dict[str, Any],
    rapid_wind: Optional[dict[str, Any]],
    rain_daily_mm: float,
    rain_yearly_mm: float,
    rain_rate_mm_hr: float,
    elevation_m: float = 0.0,
) -> SensorSnapshot:
    """Assemble a SensorSnapshot (SI) from parsed observation + rapid_wind data.

    rapid_wind overlays wind_speed and wind_direction when available
    (fresher 3-second data vs 60-second obs data). wind_gust always
    comes from the observation.
    """
    # Wind: prefer rapid_wind overlay for speed/direction
    wind_speed = obs_data.get("wind_speed_ms")
    wind_dir = obs_data.get("wind_dir")
    if rapid_wind:
        rw_speed = rapid_wind.get("wind_speed_ms")
        rw_dir = rapid_wind.get("wind_dir")
        if rw_speed is not None:
            wind_speed = rw_speed
        if rw_dir is not None:
            wind_dir = rw_dir

    # Pressure: apply altitude correction (all in hPa)
    station_hpa = obs_data.get("station_pressure_hpa")
    barometer = None
    if station_hpa is not None:
        barometer = round(_correct_pressure(station_hpa, elevation_m), 1)

    extra: dict[str, Any] = {}
    for key in ("wind_lull_ms", "illuminance_lux", "lightning_distance_km",
                "lightning_count", "battery_v", "precip_type"):
        val = obs_data.get(key)
        if val is not None:
            extra[key] = val

    if station_hpa is not None:
        extra["station_pressure_hpa"] = round(station_hpa, 1)

    return SensorSnapshot(
        outside_temp=obs_data.get("outside_temp_c"),
        outside_humidity=obs_data.get("outside_humidity"),
        wind_speed=wind_speed,
        wind_direction=wind_dir,
        wind_gust=obs_data.get("wind_gust_ms"),
        barometer=barometer,
        rain_rate=round(rain_rate_mm_hr, 1) if rain_rate_mm_hr else 0.0,
        rain_daily=round(rain_daily_mm, 1),
        rain_yearly=round(rain_yearly_mm, 1),
        solar_radiation=obs_data.get("solar_radiation"),
        uv_index=obs_data.get("uv_index"),
        extra=extra,
    )
