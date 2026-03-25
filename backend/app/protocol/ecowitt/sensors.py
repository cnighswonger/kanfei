"""Ecowitt live-data sensor parsing.

Parses the marker-byte-encoded payload from CMD_LIVEDATA (0x27).
Ecowitt hardware reports in metric (tenths °C, tenths hPa, tenths m/s,
tenths mm) which maps directly to SI SensorSnapshot units.
"""

import logging
import struct
from typing import Any, Optional

from ..base import SensorSnapshot
from .constants import MARKER_SIZE

logger = logging.getLogger(__name__)


# ---- Metric scaling helpers (tenths → whole SI units) ----

def _tenths(raw: int) -> float:
    """Tenths-unit integer → float (e.g., 225 → 22.5)."""
    return raw / 10.0


# ---- Marker parsing ----

def _decode_signed_temp(data: bytes, offset: int = 0) -> int:
    """Decode 2-byte signed big-endian temperature (tenths °C)."""
    return struct.unpack_from(">h", data, offset)[0]


def _decode_u16(data: bytes, offset: int = 0) -> int:
    """Decode 2-byte unsigned big-endian value."""
    return struct.unpack_from(">H", data, offset)[0]


def _decode_u32(data: bytes, offset: int = 0) -> int:
    """Decode 4-byte unsigned big-endian value."""
    return struct.unpack_from(">I", data, offset)[0]


# Markers that represent signed temperatures (all are i16 /10, °C).
_SIGNED_TEMP_MARKERS: frozenset[int] = frozenset(
    [0x01, 0x02, 0x03, 0x04, 0x05]        # in/out temp, dew, windchill, heatidx
    + list(range(0x1A, 0x22))              # multi-channel temp ch1-8
    + list(range(0x2B, 0x4B, 2))           # soil temp ch1-16 (every other)
)

# WN34 markers (3 bytes: signed i16 temp + u8 battery).
_WN34_MARKERS: frozenset[int] = frozenset(range(0x63, 0x6B))


def parse_live_data(payload: bytes) -> dict[int, Any]:
    """Parse CMD_LIVEDATA response payload into raw values keyed by marker.

    Walks the marker-byte-encoded payload until exhausted.  Unknown markers
    cause parsing to stop (their size is indeterminate).

    Returns dict mapping marker byte (int) to its decoded raw value.
    """
    result: dict[int, Any] = {}
    pos = 0
    length = len(payload)

    while pos < length:
        marker = payload[pos]
        pos += 1

        size = MARKER_SIZE.get(marker)
        if size is None:
            logger.warning(
                "Unknown Ecowitt marker 0x%02X at offset %d — stopping parse",
                marker, pos - 1,
            )
            break

        if pos + size > length:
            logger.warning(
                "Truncated data for marker 0x%02X: need %d bytes, have %d",
                marker, size, length - pos,
            )
            break

        data = payload[pos:pos + size]
        pos += size

        # Decode based on marker type
        if marker in _SIGNED_TEMP_MARKERS:
            result[marker] = _decode_signed_temp(data)
        elif marker in _WN34_MARKERS:
            # 3 bytes: signed i16 temp + u8 battery
            result[marker] = _decode_signed_temp(data)  # temp only
        elif size == 1:
            result[marker] = data[0]
        elif size == 2:
            result[marker] = _decode_u16(data)
        elif size == 4:
            result[marker] = _decode_u32(data)
        elif marker == 0x18:
            # datetime: 6 bytes (YY MM DD HH MM SS) — store as tuple
            result[marker] = tuple(data)
        elif marker == 0x70:
            # WH45 compound: 16 bytes — parse inline
            result[marker] = _parse_wh45(data)
        elif marker == 0x6B:
            # WH46 compound: 24 bytes — parse inline
            result[marker] = _parse_wh46(data)
        elif marker == 0x4C:
            # Legacy battery: 16 bytes — skip
            result[marker] = data
        else:
            result[marker] = data

    return result


def _parse_wh45(data: bytes) -> dict[str, Any]:
    """Parse WH45 air quality compound sensor (16 bytes)."""
    return {
        "co2": _decode_u16(data, 0),
        "co2_24h": _decode_u16(data, 2),
        "pm25": _decode_u16(data, 4),
        "pm25_24h": _decode_u16(data, 6),
        "pm10": _decode_u16(data, 8),
        "pm10_24h": _decode_u16(data, 10),
        "temp": _decode_signed_temp(data, 12),
        "humidity": data[14],
    }


def _parse_wh46(data: bytes) -> dict[str, Any]:
    """Parse WH46 air quality compound sensor (24 bytes)."""
    return {
        "co2": _decode_u16(data, 0),
        "co2_24h": _decode_u16(data, 2),
        "pm25": _decode_u16(data, 4),
        "pm25_24h": _decode_u16(data, 6),
        "pm10": _decode_u16(data, 8),
        "pm10_24h": _decode_u16(data, 10),
        "pm1": _decode_u16(data, 12),
        "pm1_24h": _decode_u16(data, 14),
        "pm4": _decode_u16(data, 16),
        "pm4_24h": _decode_u16(data, 18),
        "temp": _decode_signed_temp(data, 20),
        "humidity": data[22],
    }


# ---- SensorSnapshot builder ----

def raw_to_snapshot(raw: dict[int, Any]) -> SensorSnapshot:
    """Convert parsed raw marker values to a SensorSnapshot in SI units.

    Ecowitt reports metric natively: tenths °C, tenths hPa, tenths m/s,
    tenths mm. We just divide by 10 to get SI floats.
    """
    extra: dict[str, Any] = {}

    # ---- Temperatures (tenths °C → °C) ----
    inside_temp: Optional[float] = None
    if 0x01 in raw:
        inside_temp = _tenths(raw[0x01])

    outside_temp: Optional[float] = None
    if 0x02 in raw:
        outside_temp = _tenths(raw[0x02])

    if 0x03 in raw:
        extra["dew_point_c"] = _tenths(raw[0x03])
    if 0x04 in raw:
        extra["wind_chill_c"] = _tenths(raw[0x04])
    if 0x05 in raw:
        extra["heat_index_c"] = _tenths(raw[0x05])

    # ---- Humidity ----
    inside_humidity: Optional[int] = raw.get(0x06)
    outside_humidity: Optional[int] = raw.get(0x07)

    # ---- Barometer (tenths hPa → hPa) ----
    barometer: Optional[float] = None
    if 0x09 in raw:
        barometer = _tenths(raw[0x09])
    if 0x08 in raw:
        extra["abs_pressure_hpa"] = _tenths(raw[0x08])

    # ---- Wind (tenths m/s → m/s) ----
    wind_speed: Optional[float] = None
    if 0x0B in raw:
        wind_speed = _tenths(raw[0x0B])

    wind_direction: Optional[int] = raw.get(0x0A)

    wind_gust: Optional[float] = None
    if 0x0C in raw:
        wind_gust = _tenths(raw[0x0C])

    if 0x19 in raw:
        extra["max_daily_wind_ms"] = _tenths(raw[0x19])

    # ---- Rain (tenths mm → mm) ----
    rain_rate: Optional[float] = None
    if 0x0E in raw:
        rain_rate = _tenths(raw[0x0E])

    rain_daily: Optional[float] = None
    if 0x10 in raw:
        rain_daily = _tenths(raw[0x10])

    rain_yearly: Optional[float] = None
    if 0x13 in raw:
        rain_yearly = _tenths(raw[0x13])

    if 0x0D in raw:
        extra["rain_event_mm"] = _tenths(raw[0x0D])
    if 0x11 in raw:
        extra["rain_week_mm"] = _tenths(raw[0x11])
    if 0x12 in raw:
        extra["rain_month_mm"] = _tenths(raw[0x12])
    if 0x14 in raw:
        extra["rain_total_mm"] = _tenths(raw[0x14])

    # ---- Solar / UV ----
    solar_radiation: Optional[int] = None
    if 0x16 in raw:
        solar_radiation = round(raw[0x16] / 10.0)

    uv_index: Optional[float] = None
    if 0x17 in raw:
        uv_index = float(raw[0x17])

    if 0x15 in raw:
        extra["light_lux"] = round(raw[0x15] / 10.0, 1)

    # ---- Soil (ch1 → standard fields, rest → extra) ----
    soil_temp: Optional[float] = None
    if 0x2B in raw:
        soil_temp = _tenths(raw[0x2B])

    soil_moisture: Optional[int] = raw.get(0x2C)

    # Additional soil channels (ch2-16: temp/moisture pairs)
    for i, tm in enumerate(range(0x2D, 0x4B, 2), start=2):
        if tm in raw:
            extra[f"soil_temp_ch{i}_c"] = _tenths(raw[tm])
        mm_marker = tm + 1  # moisture follows temp
        if mm_marker in raw:
            extra[f"soil_moisture_ch{i}"] = raw[mm_marker]

    # ---- Leaf wetness (ch1 → standard, rest → extra) ----
    leaf_wetness: Optional[int] = raw.get(0x72)

    for i, m in enumerate(range(0x73, 0x7A), start=2):
        if m in raw:
            extra[f"leaf_wetness_ch{i}"] = raw[m]

    # ---- Multi-channel temp/humidity ----
    for i, m in enumerate(range(0x1A, 0x22), start=1):
        if m in raw:
            extra[f"temp_ch{i}_c"] = _tenths(raw[m])

    for i, m in enumerate(range(0x22, 0x2A), start=1):
        if m in raw:
            extra[f"humidity_ch{i}"] = raw[m]

    # WN34 temp sensors (ch9-16)
    for i, m in enumerate(range(0x63, 0x6B), start=9):
        if m in raw:
            extra[f"temp_ch{i}_c"] = _tenths(raw[m])

    # ---- PM2.5 ----
    if 0x2A in raw:
        extra["pm25_ch1"] = round(raw[0x2A] / 10.0, 1)
    for i, m in enumerate([0x51, 0x52, 0x53], start=2):
        if m in raw:
            extra[f"pm25_ch{i}"] = round(raw[m] / 10.0, 1)
    for i, m in enumerate([0x4D, 0x4E, 0x4F, 0x50], start=1):
        if m in raw:
            extra[f"pm25_ch{i}_24h"] = round(raw[m] / 10.0, 1)

    # ---- Lightning ----
    if 0x60 in raw:
        extra["lightning_distance"] = raw[0x60]
    if 0x61 in raw:
        extra["lightning_det_time"] = raw[0x61]
    if 0x62 in raw:
        extra["lightning_count"] = raw[0x62]

    # ---- Leak detection ----
    for i, m in enumerate([0x58, 0x59, 0x5A, 0x5B], start=1):
        if m in raw:
            extra[f"leak_ch{i}"] = raw[m]

    # ---- WH45 / WH46 air quality ----
    for marker in (0x70, 0x6B):
        if marker in raw and isinstance(raw[marker], dict):
            aq = raw[marker]
            if "co2" in aq:
                extra["co2"] = aq["co2"]
            if "co2_24h" in aq:
                extra["co2_24h"] = aq["co2_24h"]
            if "pm10" in aq:
                extra["pm10"] = round(aq["pm10"] / 10.0, 1)
            if "pm10_24h" in aq:
                extra["pm10_24h"] = round(aq["pm10_24h"] / 10.0, 1)

    return SensorSnapshot(
        inside_temp=inside_temp,
        outside_temp=outside_temp,
        inside_humidity=inside_humidity,
        outside_humidity=outside_humidity,
        wind_speed=wind_speed,
        wind_direction=wind_direction,
        wind_gust=wind_gust,
        barometer=barometer,
        rain_rate=rain_rate,
        rain_daily=rain_daily,
        rain_yearly=rain_yearly,
        solar_radiation=solar_radiation,
        uv_index=uv_index,
        soil_temp=soil_temp,
        soil_moisture=soil_moisture,
        leaf_wetness=leaf_wetness,
        extra=extra,
    )
