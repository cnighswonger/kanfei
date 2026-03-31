"""LOOP packet parser for Davis WeatherLink protocol.

Parses raw LOOP packet bytes into SensorReading dataclass based on
station type. Handles little-endian byte order, signed/unsigned types,
and invalid data markers.

Reference: techref.txt lines 510-591, commands.c lines 122-141
"""

import struct
import logging
from typing import Optional

from .constants import (
    StationModel,
    BASIC_STATIONS,
    LOOP_DATA_SIZE,
    SOH,
    INVALID_TEMP_4NIB,
    INVALID_TEMP_NOT_CONNECTED,
    INVALID_TEMP_3NIB,
    INVALID_HUMIDITY,
    INVALID_WIND_DIR_4NIB,
    INVALID_SOLAR_RAD,
    INVALID_UV,
)
from .crc import crc_validate
from .station_types import SensorReading
from ..utils.units import (
    f_tenths_to_c_tenths,
    inhg_thousandths_to_hpa_tenths,
    mph_to_ms_tenths,
    in_hundredths_to_mm_tenths,
)

logger = logging.getLogger(__name__)


def _to_si(reading: SensorReading) -> SensorReading:
    """Convert a Davis-native SensorReading to SI units at the parse boundary.

    Davis reports: tenths °F, thousandths inHg, mph, hundredths inches.
    SI storage: tenths °C, tenths hPa, tenths m/s, tenths mm.
    """
    def _temp(v: Optional[int]) -> Optional[int]:
        return f_tenths_to_c_tenths(v) if v is not None else None

    def _press(v: Optional[int]) -> Optional[int]:
        return inhg_thousandths_to_hpa_tenths(v) if v is not None else None

    def _wind(v: Optional[int]) -> Optional[int]:
        return mph_to_ms_tenths(v) if v is not None else None

    def _rain(v: Optional[int]) -> Optional[int]:
        return in_hundredths_to_mm_tenths(v) if v is not None else None

    return SensorReading(
        inside_temp=_temp(reading.inside_temp),
        outside_temp=_temp(reading.outside_temp),
        soil_temp=_temp(reading.soil_temp),
        wind_speed=_wind(reading.wind_speed),
        wind_direction=reading.wind_direction,
        barometer=_press(reading.barometer),
        inside_humidity=reading.inside_humidity,
        outside_humidity=reading.outside_humidity,
        rain_total=_rain(reading.rain_total),
        rain_rate=_rain(reading.rain_rate),
        rain_yearly=_rain(reading.rain_yearly),
        solar_radiation=reading.solar_radiation,
        uv_index=reading.uv_index,
        # Pass through fields that don't need conversion
        wind_run_total=reading.wind_run_total,
        et_total=reading.et_total,
        degree_days_total=reading.degree_days_total,
        solar_energy_total=reading.solar_energy_total,
        leaf_wetness=reading.leaf_wetness,
        uv_dose=reading.uv_dose,
    )


def _unpack_u8(data: bytes, offset: int) -> int:
    """Unpack unsigned 8-bit value."""
    return data[offset]


def _unpack_i16(data: bytes, offset: int) -> int:
    """Unpack signed 16-bit little-endian value."""
    return struct.unpack_from("<h", data, offset)[0]


def _unpack_u16(data: bytes, offset: int) -> int:
    """Unpack unsigned 16-bit little-endian value."""
    return struct.unpack_from("<H", data, offset)[0]


def _unpack_u24(data: bytes, offset: int) -> int:
    """Unpack unsigned 24-bit little-endian value."""
    return data[offset] | (data[offset + 1] << 8) | (data[offset + 2] << 16)


def _valid_temp_4nib(value: int) -> Optional[int]:
    """Return temperature value if valid, None otherwise."""
    if value == INVALID_TEMP_4NIB or value == INVALID_TEMP_NOT_CONNECTED:
        return None
    # Also treat 0x7FFE and similar extreme values as suspect
    if value > 2500 or value < -900:  # > 250F or < -90F
        return None
    return value


def _valid_temp_3nib(value: int) -> Optional[int]:
    """Return 3-nibble temperature value if valid, None otherwise."""
    if value == INVALID_TEMP_3NIB or value == (INVALID_TEMP_3NIB + 1):
        return None
    return value


def _valid_humidity(value: int) -> Optional[int]:
    """Return humidity if valid, None if sentinel.

    Davis sensors can report slightly over 100% due to sensor tolerance.
    Clamp to 100 rather than rejecting — the reading is still meaningful.
    """
    if value == INVALID_HUMIDITY:
        return None
    return min(value, 100)


def _valid_wind_dir(value: int) -> Optional[int]:
    """Return wind direction if valid (0-359), None otherwise."""
    if value == INVALID_WIND_DIR_4NIB or value > 359:
        return None
    return value


def _valid_solar(value: int) -> Optional[int]:
    """Return solar radiation if valid, None otherwise."""
    if value == INVALID_SOLAR_RAD or value >= INVALID_SOLAR_RAD:
        return None
    return value


def _valid_uv(value: int) -> Optional[int]:
    """Return UV index if valid, None otherwise."""
    if value == INVALID_UV:
        return None
    return value


def parse_loop_packet(raw: bytes, model: StationModel) -> Optional[SensorReading]:
    """Parse a complete LOOP packet (SOH + data + CRC).

    Args:
        raw: Complete packet bytes including SOH header and 2-byte CRC.
        model: Station model type for format selection.

    Returns:
        SensorReading with parsed values, or None if validation fails.
    """
    expected_data_size = LOOP_DATA_SIZE[model]
    expected_total = 1 + expected_data_size + 2  # SOH + data + CRC

    if len(raw) < expected_total:
        logger.warning(
            "LOOP packet too short: %d bytes, expected %d",
            len(raw), expected_total,
        )
        return None

    # Verify SOH header
    if raw[0] != SOH:
        logger.warning("LOOP packet missing SOH header: 0x%02X", raw[0])
        return None

    # Validate CRC over data bytes + CRC (exclude SOH)
    data_and_crc = raw[1:expected_total]
    if not crc_validate(data_and_crc):
        logger.warning("LOOP packet CRC validation failed")
        return None

    # Extract data portion (between SOH and CRC)
    data = raw[1:1 + expected_data_size]

    if model in BASIC_STATIONS:
        return _to_si(_parse_basic(data))
    elif model == StationModel.GROWEATHER:
        return _to_si(_parse_groweather(data))
    elif model == StationModel.ENERGY:
        return _to_si(_parse_energy(data))
    elif model == StationModel.HEALTH:
        return _to_si(_parse_health(data))
    else:
        logger.error("Unknown station model: %s", model)
        return None


def _parse_basic(data: bytes) -> SensorReading:
    """Parse Monitor/Wizard/Perception LOOP packet (15 data bytes).

    Offsets from commands.c lines 122-141 and techref.txt:
    0-1: inside temp (signed i16, tenths F)
    2-3: outside temp (signed i16, tenths F)
    4:   wind speed (u8, mph)
    5-6: wind direction (u16, degrees)
    7-8: barometer (u16, thousandths inHg)
    9:   inside humidity (u8, percent)
    10:  outside humidity (u8, percent)
    11-12: total rain (u16, clicks)
    13-14: unused
    """
    return SensorReading(
        inside_temp=_valid_temp_4nib(_unpack_i16(data, 0)),
        outside_temp=_valid_temp_4nib(_unpack_i16(data, 2)),
        wind_speed=_unpack_u8(data, 4),
        wind_direction=_valid_wind_dir(_unpack_u16(data, 5)),
        barometer=_unpack_u16(data, 7),
        inside_humidity=_valid_humidity(_unpack_u8(data, 9)),
        outside_humidity=_valid_humidity(_unpack_u8(data, 10)),
        rain_total=_unpack_u16(data, 11),
    )


def _parse_groweather(data: bytes) -> SensorReading:
    """Parse GroWeather LOOP packet (33 data bytes)."""
    return SensorReading(
        soil_temp=_valid_temp_4nib(_unpack_i16(data, 3)),
        outside_temp=_valid_temp_4nib(_unpack_i16(data, 5)),
        wind_speed=_unpack_u8(data, 7),
        wind_direction=_valid_wind_dir(_unpack_u16(data, 8)),
        barometer=_unpack_u16(data, 10),
        rain_rate=_unpack_u8(data, 12),
        outside_humidity=_valid_humidity(_unpack_u8(data, 13)),
        rain_total=_unpack_u16(data, 14),
        solar_radiation=_valid_solar(_unpack_u16(data, 16)),
        wind_run_total=_unpack_u24(data, 18),
        et_total=_unpack_u16(data, 21),
        degree_days_total=_unpack_u24(data, 23),
        solar_energy_total=_unpack_u24(data, 26),
        leaf_wetness=_unpack_u8(data, 32),
    )


def _parse_energy(data: bytes) -> SensorReading:
    """Parse Energy LOOP packet (27 data bytes)."""
    return SensorReading(
        inside_temp=_valid_temp_4nib(_unpack_i16(data, 3)),
        outside_temp=_valid_temp_4nib(_unpack_i16(data, 5)),
        wind_speed=_unpack_u8(data, 7),
        wind_direction=_valid_wind_dir(_unpack_u16(data, 8)),
        barometer=_unpack_u16(data, 10),
        rain_rate=_unpack_u8(data, 12),
        outside_humidity=_valid_humidity(_unpack_u8(data, 13)),
        rain_total=_unpack_u16(data, 14),
        solar_radiation=_valid_solar(_unpack_u16(data, 16)),
    )


def _parse_health(data: bytes) -> SensorReading:
    """Parse Health LOOP packet (25 data bytes)."""
    return SensorReading(
        inside_temp=_valid_temp_4nib(_unpack_i16(data, 3)),
        outside_temp=_valid_temp_4nib(_unpack_i16(data, 5)),
        wind_speed=_unpack_u8(data, 7),
        wind_direction=_valid_wind_dir(_unpack_u16(data, 8)),
        barometer=_unpack_u16(data, 10),
        rain_rate=_unpack_u8(data, 12),
        rain_total=_unpack_u16(data, 13),
        solar_radiation=_valid_solar(_unpack_u16(data, 15)),
        inside_humidity=_valid_humidity(_unpack_u8(data, 17)),
        outside_humidity=_valid_humidity(_unpack_u8(data, 18)),
        uv_index=_valid_uv(_unpack_u8(data, 19)),
        uv_dose=_unpack_u16(data, 20),
    )
