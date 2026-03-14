"""Centralized sensor metadata — single source of truth for DB-to-display
unit conversion, column mappings, data quality bounds, and spike thresholds.

All raw sensor values are stored as integers in the sensor_readings table.
Divisors convert raw DB values to display units (e.g. raw 725 / 10 = 72.5 °F).
"""

from .sensor_reading import SensorReadingModel

# ---------------------------------------------------------------------------
# DB column references (for SQLAlchemy queries)
# ---------------------------------------------------------------------------

SENSOR_COLUMNS = {
    "inside_temp": SensorReadingModel.inside_temp,
    "outside_temp": SensorReadingModel.outside_temp,
    "inside_humidity": SensorReadingModel.inside_humidity,
    "outside_humidity": SensorReadingModel.outside_humidity,
    "wind_speed": SensorReadingModel.wind_speed,
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
# Raw DB value -> display unit divisors (default 1 if absent)
# ---------------------------------------------------------------------------

SENSOR_DIVISORS: dict[str, float] = {
    "inside_temp": 10,        # raw tenths °F
    "outside_temp": 10,
    "heat_index": 10,
    "dew_point": 10,
    "wind_chill": 10,
    "feels_like": 10,
    "theta_e": 10,            # raw tenths K
    "uv_index": 10,           # raw tenths
    "barometer": 1000,        # raw thousandths inHg
    "rain_total": 100,        # raw clicks (1 click = 0.01 in)
    "rain_yearly": 100,
    "rain_rate": 10,          # raw tenths in/hr
}

# ---------------------------------------------------------------------------
# Physically reasonable bounds for raw DB values.
# Values outside these ranges indicate a disconnected or faulty sensor
# (e.g. Davis 32767/255/65535 sentinel values).
# ---------------------------------------------------------------------------

SENSOR_BOUNDS: dict[str, tuple[int, int]] = {
    "inside_temp": (-400, 1500),       # -40 to 150 °F  (raw × 10)
    "outside_temp": (-400, 1500),
    "heat_index": (-400, 1850),        # -40 to 185 °F  (raw × 10)
    "dew_point": (-400, 1500),
    "wind_chill": (-1000, 1500),       # -100 to 150 °F (raw × 10)
    "feels_like": (-1000, 1850),
    "theta_e": (2000, 4500),           # 200 to 450 K   (raw × 10)
    "inside_humidity": (1, 100),
    "outside_humidity": (1, 100),
    "wind_speed": (0, 200),            # 0 to 200 mph
    "wind_direction": (0, 360),
    "barometer": (25000, 35000),       # 25 to 35 inHg  (raw × 1000)
    "rain_total": (0, 99900),          # 0 to 999 in    (raw clicks)
    "rain_rate": (0, 10000),           # 0 to 1000 in/hr (raw × 10)
    "rain_yearly": (0, 99900),
    "solar_radiation": (0, 1800),      # 0 to 1800 W/m²
    "uv_index": (0, 160),             # 0 to 16        (raw × 10)
}

# ---------------------------------------------------------------------------
# Spike detection thresholds.
# Maximum reasonable change between consecutive samples (~10 s apart).
# A reading that differs from BOTH its neighbors by more than this
# threshold is treated as a single-sample spike and nulled out.
# Sensors omitted here (wind, rain, solar) can legitimately spike.
# ---------------------------------------------------------------------------

SENSOR_SPIKE_THRESHOLDS: dict[str, int] = {
    "inside_temp": 50,       # 5 °F   (raw × 10)
    "outside_temp": 50,
    "heat_index": 50,
    "dew_point": 50,
    "wind_chill": 50,
    "feels_like": 50,
    "theta_e": 50,           # 5 K    (raw × 10)
    "inside_humidity": 15,
    "outside_humidity": 15,
    "barometer": 100,        # 0.1 inHg (raw × 1000)
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
    """Convert a raw DB value to display units.

    Returns the raw value unchanged for sensors with no divisor (e.g. humidity,
    wind speed) so integer types are preserved in API responses.

    >>> convert("outside_temp", 725)
    72.5
    >>> convert("rain_total", 3)
    0.03
    >>> convert("barometer", 30040)
    30.04
    >>> convert("wind_speed", 15)
    15
    """
    if raw_value is None:
        return None
    divisor = SENSOR_DIVISORS.get(column, 1)
    if divisor == 1:
        return raw_value
    return round(raw_value / divisor, 2)
