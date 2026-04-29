"""Centralized sensor metadata — single source of truth for DB-to-display
unit conversion, column mappings, data quality bounds, and spike thresholds.

All raw sensor values are stored as integers in SI units:
  - Temperature: tenths of °C
  - Pressure: tenths of hPa
  - Wind speed: tenths of m/s
  - Rain: tenths of mm
  - Humidity: percent (0-100)
  - Theta-e: tenths of K
"""

from .sensor_reading import SensorReadingModel
from ..utils.units import (
    si_temp_to_display_f,
    si_pressure_to_display_inhg,
    si_wind_to_display_mph,
    si_rain_to_display_in,
    si_theta_e_to_display,
)

# ---------------------------------------------------------------------------
# DB column references (for SQLAlchemy queries)
# ---------------------------------------------------------------------------

SENSOR_COLUMNS = {
    "inside_temp": SensorReadingModel.inside_temp,
    "outside_temp": SensorReadingModel.outside_temp,
    "inside_humidity": SensorReadingModel.inside_humidity,
    "outside_humidity": SensorReadingModel.outside_humidity,
    "wind_speed": SensorReadingModel.wind_speed,
    "wind_gust": SensorReadingModel.wind_gust,
    "wind_direction": SensorReadingModel.wind_direction,
    "barometer": SensorReadingModel.barometer,
    "rain_total": SensorReadingModel.rain_total,
    "rain_rate": SensorReadingModel.rain_rate,
    "rain_yearly": SensorReadingModel.rain_yearly,
    "heat_index": SensorReadingModel.heat_index,
    "dew_point": SensorReadingModel.dew_point,
    "wind_chill": SensorReadingModel.wind_chill,
    "feels_like": SensorReadingModel.feels_like,
    "theta_e": SensorReadingModel.theta_e,
    "solar_radiation": SensorReadingModel.solar_radiation,
    "uv_index": SensorReadingModel.uv_index,
}

# ---------------------------------------------------------------------------
# Display units
# ---------------------------------------------------------------------------

SENSOR_UNITS: dict[str, str] = {
    "inside_temp": "F",
    "outside_temp": "F",
    "inside_humidity": "%",
    "outside_humidity": "%",
    "wind_speed": "mph",
    "wind_gust": "mph",
    "wind_direction": "°",
    "barometer": "inHg",
    "rain_total": "in",
    "rain_rate": "in/hr",
    "rain_yearly": "in",
    "heat_index": "F",
    "dew_point": "F",
    "wind_chill": "F",
    "feels_like": "F",
    "theta_e": "K",
    "solar_radiation": "W/m²",
    "uv_index": "",
}

# ---------------------------------------------------------------------------
# SI storage -> display unit converters
#
# DB stores SI: tenths °C, tenths hPa, tenths m/s, tenths mm.
# These converters produce display values for the API.
# Sensors without a converter return raw / divisor (or raw unchanged).
# ---------------------------------------------------------------------------

_TEMP_FIELDS = {"inside_temp", "outside_temp", "heat_index", "dew_point", "wind_chill", "feels_like"}
_RAIN_FIELDS = {"rain_total", "rain_yearly"}

SENSOR_CONVERTERS: dict[str, object] = {
    **{f: si_temp_to_display_f for f in _TEMP_FIELDS},
    "theta_e": si_theta_e_to_display,
    "barometer": si_pressure_to_display_inhg,
    "wind_speed": si_wind_to_display_mph,
    "wind_gust": si_wind_to_display_mph,
    "rain_total": si_rain_to_display_in,
    "rain_yearly": si_rain_to_display_in,
    "rain_rate": si_rain_to_display_in,  # tenths mm/hr → in/hr
}

# Fallback divisors for sensors that are already in display-ready units
SENSOR_DIVISORS: dict[str, float] = {
    "uv_index": 10,           # raw tenths
}

# ---------------------------------------------------------------------------
# Physically reasonable bounds for raw DB values.
# Values outside these ranges indicate a disconnected or faulty sensor
# (e.g. Davis 32767/255/65535 sentinel values).
# ---------------------------------------------------------------------------

SENSOR_BOUNDS: dict[str, tuple[int, int]] = {
    "inside_temp": (-400, 656),        # -40 to 65.6 °C  (tenths °C)
    "outside_temp": (-400, 656),
    "heat_index": (-400, 850),         # -40 to 85 °C    (tenths °C)
    "dew_point": (-400, 656),
    "wind_chill": (-733, 656),         # -73.3 to 65.6 °C (tenths °C)
    "feels_like": (-733, 850),
    "theta_e": (2000, 4500),           # 200 to 450 K    (tenths K)
    "inside_humidity": (1, 104),       # sensor tolerance: ±4% above 90% RH
    "outside_humidity": (1, 104),
    "wind_speed": (0, 894),            # 0 to 89.4 m/s ≈ 200 mph (tenths m/s)
    "wind_gust": (0, 894),             # same range as wind_speed
    "wind_direction": (0, 360),
    "barometer": (8466, 11863),        # 846.6 to 1186.3 hPa (tenths hPa)
    "rain_total": (0, 253746),         # 0 to 25374.6 mm (tenths mm)
    "rain_rate": (0, 25400),           # 0 to 2540 mm/hr (tenths mm/hr)
    "rain_yearly": (0, 253746),
    "solar_radiation": (0, 1800),      # 0 to 1800 W/m²
    "uv_index": (0, 160),             # 0 to 16 (tenths)
}

# ---------------------------------------------------------------------------
# Spike detection thresholds.
# Maximum reasonable change between consecutive samples (~10 s apart).
# A reading that differs from BOTH its neighbors by more than this
# threshold is treated as a single-sample spike and nulled out.
# Sensors omitted here (wind, rain, solar) can legitimately spike.
# ---------------------------------------------------------------------------

SENSOR_SPIKE_THRESHOLDS: dict[str, int] = {
    "inside_temp": 28,       # 2.8 °C ≈ 5 °F (tenths °C)
    "outside_temp": 28,
    "heat_index": 28,
    "dew_point": 28,
    "wind_chill": 28,
    "feels_like": 28,
    "theta_e": 50,           # 5 K    (tenths K)
    "inside_humidity": 15,
    "outside_humidity": 15,
    "barometer": 34,         # 3.4 hPa ≈ 0.1 inHg (tenths hPa)
}

# ---------------------------------------------------------------------------
# Frontend display names -> DB column names
# ---------------------------------------------------------------------------

SENSOR_ALIASES: dict[str, str] = {
    "temperature_inside": "inside_temp",
    "temperature_outside": "outside_temp",
    "humidity_inside": "inside_humidity",
    "humidity_outside": "outside_humidity",
    "rain_daily": "rain_total",
}


def convert(column: str, raw_value: int | float | None) -> int | float | None:
    """Convert a raw SI DB value to display units.

    Uses SENSOR_CONVERTERS for SI-to-display conversion (temperature,
    pressure, wind, rain). Falls back to SENSOR_DIVISORS for simple
    scaling (UV index). Returns raw value unchanged for unit-neutral
    sensors (humidity, wind direction, solar radiation).

    >>> convert("outside_temp", 222)  # 22.2°C in tenths
    72.0
    >>> convert("barometer", 10132)   # 1013.2 hPa in tenths
    29.92
    >>> convert("wind_speed", 45)     # 4.5 m/s in tenths
    10
    >>> convert("outside_humidity", 50)
    50
    """
    if raw_value is None:
        return None
    converter = SENSOR_CONVERTERS.get(column)
    if converter is not None:
        return converter(raw_value)
    divisor = SENSOR_DIVISORS.get(column, 1)
    if divisor == 1:
        return raw_value
    return round(raw_value / divisor, 2)
