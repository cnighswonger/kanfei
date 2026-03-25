"""Parse HTTP push parameters into a SensorSnapshot (SI).

Supports both Wunderground and Ecowitt push formats. Both formats use
imperial units (°F, mph, inHg, inches) — values are converted to SI
(°C, m/s, hPa, mm) for the SensorSnapshot.
"""

import logging
import re
from typing import Any

from ..base import SensorSnapshot
from .constants import (
    ECOWITT_FIELD_MAP,
    ECOWITT_INDICATORS,
    ECOWITT_MULTI_CHANNEL_PATTERNS,
    WU_FIELD_MAP,
    WU_INDICATORS,
)

logger = logging.getLogger(__name__)


def detect_format(params: dict[str, str]) -> str:
    """Detect whether parameters are Wunderground or Ecowitt format."""
    param_keys = set(params.keys())
    if param_keys & ECOWITT_INDICATORS:
        return "ecowitt"
    if param_keys & WU_INDICATORS:
        return "wunderground"
    # Ecowitt-specific field names as fallback
    if "baromrelin" in params or "rainratein" in params or "tempinf" in params:
        return "ecowitt"
    return "wunderground"


def _safe_convert(value: str, target_type: type) -> Any:
    """Safely convert a string value to the target type."""
    try:
        if target_type is int:
            return int(round(float(value)))
        return target_type(value)
    except (ValueError, TypeError):
        return None


def _parse_ecowitt_multi_channel(
    params: dict[str, str],
) -> dict[str, Any]:
    """Parse multi-channel Ecowitt parameters into extra dict entries.

    Handles patterns like soilmoisture2, tf_ch3, leafwetness_ch4, etc.
    Channel 1 for some sensors is already handled in the main field map.
    """
    extra: dict[str, Any] = {}

    for param_name, value in params.items():
        for prefix, (extra_prefix, target_type) in ECOWITT_MULTI_CHANNEL_PATTERNS.items():
            # Match "prefix" followed by digits (e.g., soilmoisture2, tf_ch3)
            match = re.match(rf"^{re.escape(prefix)}(\d+)$", param_name)
            if match:
                channel = match.group(1)
                # Skip channel 1 for sensors already in the primary field map
                if prefix == "soilmoisture" and channel == "1":
                    break
                converted = _safe_convert(value, target_type)
                if converted is not None:
                    extra[f"{extra_prefix}{channel}"] = converted
                break

    return extra


def _imperial_to_si(fields: dict[str, Any]) -> dict[str, Any]:
    """Convert parsed imperial fields to SI for SensorSnapshot.

    Temps: °F → °C, Pressure: inHg → hPa, Wind: mph → m/s, Rain: in → mm.
    """
    result = dict(fields)

    # Temperature fields (°F → °C)
    for key in ("outside_temp", "inside_temp", "soil_temp"):
        if key in result and result[key] is not None:
            result[key] = round((result[key] - 32) * 5 / 9, 1)

    # Pressure (inHg → hPa)
    if "barometer" in result and result["barometer"] is not None:
        result["barometer"] = round(result["barometer"] * 33.8639, 1)

    # Wind (mph → m/s)
    for key in ("wind_speed", "wind_gust"):
        if key in result and result[key] is not None:
            result[key] = round(result[key] * 0.44704, 1)

    # Rain (inches → mm)
    for key in ("rain_rate", "rain_daily", "rain_yearly"):
        if key in result and result[key] is not None:
            result[key] = round(result[key] * 25.4, 1)

    return result


def parse_params(params: dict[str, str]) -> SensorSnapshot:
    """Parse HTTP push parameters into a SensorSnapshot (SI).

    Auto-detects the format (Wunderground or Ecowitt) and applies the
    appropriate field mapping, then converts imperial to SI.
    """
    fmt = detect_format(params)
    field_map = ECOWITT_FIELD_MAP if fmt == "ecowitt" else WU_FIELD_MAP

    fields: dict[str, Any] = {}
    extra: dict[str, Any] = {}

    for param_name, value in params.items():
        if param_name in field_map:
            snapshot_field, is_extra, target_type = field_map[param_name]
            converted = _safe_convert(value, target_type)
            if converted is not None:
                if is_extra:
                    extra[snapshot_field] = converted
                else:
                    fields[snapshot_field] = converted

    # Parse multi-channel extras for Ecowitt format
    if fmt == "ecowitt":
        extra.update(_parse_ecowitt_multi_channel(params))

    # Convert imperial push values to SI
    fields = _imperial_to_si(fields)

    if extra:
        fields["extra"] = extra

    return SensorSnapshot(**fields)


def extract_station_info(params: dict[str, str]) -> dict[str, str]:
    """Extract station identification from push parameters.

    Returns a dict with optional keys: model, passkey, firmware.
    """
    info: dict[str, str] = {}

    # Ecowitt: stationtype is "MODEL_VVERSION" (e.g., "GW2000A_V2.1.8")
    station_type = params.get("stationtype", "")
    if station_type:
        info["raw_type"] = station_type
        if "_V" in station_type:
            model, version = station_type.split("_V", 1)
            info["model"] = model
            info["firmware"] = version
        else:
            info["model"] = station_type

    passkey = params.get("PASSKEY", "")
    if passkey:
        info["passkey"] = passkey

    # Wunderground: ID field
    station_id = params.get("ID", "")
    if station_id:
        info["station_id"] = station_id

    # Model field (some newer firmware)
    model = params.get("model", "")
    if model and "model" not in info:
        info["model"] = model

    return info
