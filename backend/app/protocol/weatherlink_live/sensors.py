"""Parse WeatherLink Live JSON response into SensorSnapshot (SI).

The WLL /v1/current_conditions endpoint returns JSON with a conditions
array containing up to 4 data structure types.  Values are in imperial
(°F, mph, inHg) and converted to SI (°C, m/s, hPa, mm) for the
SensorSnapshot.
"""

import logging
from typing import Any, Optional

from ..base import SensorSnapshot
from .constants import (
    DATA_TYPE_ISS,
    DATA_TYPE_LEAF_SOIL,
    DATA_TYPE_BAROMETER,
    DATA_TYPE_INDOOR,
    RAIN_CLICK_INCHES,
    DEFAULT_RAIN_CLICK_INCHES,
)

logger = logging.getLogger(__name__)


# --------------- helpers ---------------

def _safe_float(data: dict, key: str) -> Optional[float]:
    """Extract a float value, returning None if missing or null."""
    val = data.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(data: dict, key: str) -> Optional[int]:
    """Extract an int value, returning None if missing or null."""
    val = data.get(key)
    if val is None:
        return None
    try:
        return int(round(float(val)))
    except (ValueError, TypeError):
        return None


def _clicks_to_mm(
    clicks: Optional[float],
    rain_size: Optional[int],
) -> Optional[float]:
    """Convert rain bucket clicks to mm using the rain_size code."""
    if clicks is None:
        return None
    size_inches = RAIN_CLICK_INCHES.get(rain_size or 1, DEFAULT_RAIN_CLICK_INCHES)
    return round(clicks * size_inches * 25.4, 2)


def _f_to_c(f: Optional[float]) -> Optional[float]:
    """°F → °C."""
    return round((f - 32) * 5 / 9, 1) if f is not None else None


def _mph_to_ms(mph: Optional[int]) -> Optional[float]:
    """mph → m/s."""
    return round(mph * 0.44704, 1) if mph is not None else None


def _inhg_to_hpa(inhg: Optional[float]) -> Optional[float]:
    """inHg → hPa."""
    return round(inhg * 33.8639, 1) if inhg is not None else None


# --------------- per-type parsers ---------------

def _parse_iss(
    cond: dict,
    fields: dict[str, Any],
    extra: dict[str, Any],
) -> None:
    """Parse ISS (data_structure_type 1) into snapshot fields (SI)."""
    fields["outside_temp"] = _f_to_c(_safe_float(cond, "temp"))
    fields["outside_humidity"] = _safe_int(cond, "hum")
    fields["wind_speed"] = _mph_to_ms(_safe_int(cond, "wind_speed_last"))
    fields["wind_direction"] = _safe_int(cond, "wind_dir_last")
    fields["wind_gust"] = _mph_to_ms(_safe_int(cond, "wind_speed_hi_last_10_min"))
    fields["solar_radiation"] = _safe_int(cond, "solar_rad")
    fields["uv_index"] = _safe_float(cond, "uv_index")

    # Rain: convert from clicks to mm
    rain_size = _safe_int(cond, "rain_size")
    fields["rain_rate"] = _clicks_to_mm(
        _safe_float(cond, "rain_rate_last"), rain_size,
    )
    fields["rain_daily"] = _clicks_to_mm(
        _safe_float(cond, "rainfall_daily"), rain_size,
    )
    fields["rain_yearly"] = _clicks_to_mm(
        _safe_float(cond, "rainfall_year"), rain_size,
    )

    # Derived values → extra
    for json_key, extra_key in (
        ("dew_point", "dew_point_f"),
        ("heat_index", "heat_index_f"),
        ("wind_chill", "wind_chill_f"),
    ):
        val = _safe_float(cond, json_key)
        if val is not None:
            extra[extra_key] = val

    gust_dir = _safe_int(cond, "wind_dir_at_hi_speed_last_10_min")
    if gust_dir is not None:
        extra["wind_gust_direction"] = gust_dir

    txid = _safe_int(cond, "txid")
    if txid is not None:
        extra["txid"] = txid

    batt = _safe_int(cond, "trans_battery_flag")
    if batt is not None:
        extra["iss_battery_low"] = bool(batt)


def _parse_leaf_soil(
    cond: dict,
    fields: dict[str, Any],
    extra: dict[str, Any],
) -> None:
    """Parse Leaf/Soil (data_structure_type 2) into snapshot fields (SI)."""
    fields["soil_temp"] = _f_to_c(_safe_float(cond, "temp_1"))
    fields["soil_moisture"] = _safe_int(cond, "moist_soil_1")
    fields["leaf_wetness"] = _safe_int(cond, "wet_leaf_1")

    # Additional channels → extra
    for ch in range(2, 5):
        sm = _safe_int(cond, f"moist_soil_{ch}")
        if sm is not None:
            extra[f"soil_moisture_ch{ch}"] = sm
        st = _safe_float(cond, f"temp_{ch}")
        if st is not None:
            extra[f"soil_temp_ch{ch}"] = st
    wl2 = _safe_int(cond, "wet_leaf_2")
    if wl2 is not None:
        extra["leaf_wetness_ch2"] = wl2


def _parse_barometer(
    cond: dict,
    fields: dict[str, Any],
    extra: dict[str, Any],
) -> None:
    """Parse Barometer (data_structure_type 3) into snapshot fields (SI)."""
    fields["barometer"] = _inhg_to_hpa(_safe_float(cond, "bar_sea_level"))

    bar_trend = _safe_float(cond, "bar_trend")
    if bar_trend is not None:
        extra["bar_trend_inhg"] = bar_trend
    bar_abs = _safe_float(cond, "bar_absolute")
    if bar_abs is not None:
        extra["bar_absolute_inhg"] = bar_abs


def _parse_indoor(
    cond: dict,
    fields: dict[str, Any],
    extra: dict[str, Any],
) -> None:
    """Parse Indoor (data_structure_type 4) into snapshot fields (SI)."""
    fields["inside_temp"] = _f_to_c(_safe_float(cond, "temp_in"))
    fields["inside_humidity"] = _safe_int(cond, "hum_in")


# Dispatch table
_CONDITION_PARSERS = {
    DATA_TYPE_ISS: _parse_iss,
    DATA_TYPE_LEAF_SOIL: _parse_leaf_soil,
    DATA_TYPE_BAROMETER: _parse_barometer,
    DATA_TYPE_INDOOR: _parse_indoor,
}


# --------------- public API ---------------

def parse_wll_response(response: dict) -> Optional[SensorSnapshot]:
    """Parse a WLL /v1/current_conditions JSON response.

    Returns a SensorSnapshot, or None if the response is invalid.
    """
    if response.get("error"):
        logger.warning("WLL API error: %s", response["error"])
        return None

    data = response.get("data")
    if not data or "conditions" not in data:
        logger.warning("WLL response missing data.conditions")
        return None

    fields: dict[str, Any] = {}
    extra: dict[str, Any] = {}

    for cond in data["conditions"]:
        ds_type = cond.get("data_structure_type")
        parser = _CONDITION_PARSERS.get(ds_type)
        if parser:
            parser(cond, fields, extra)
        else:
            logger.debug("Unknown WLL data_structure_type: %s", ds_type)

    if extra:
        fields["extra"] = extra

    return SensorSnapshot(**fields)


def extract_device_info(response: dict) -> dict[str, Any]:
    """Extract device identification from a WLL response.

    Returns a dict with 'did' (device ID) and 'ts' (timestamp).
    """
    info: dict[str, Any] = {}
    data = response.get("data", {})
    if "did" in data:
        info["did"] = data["did"]
    if "ts" in data:
        info["ts"] = data["ts"]
    return info
