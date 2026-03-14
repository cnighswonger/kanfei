"""Zambretti barometric forecasting algorithm.

Classic Zambretti forecaster adapted for Davis Weather Station data.
Uses current sea-level barometer, 3-hour pressure trend, wind direction,
and month to produce a short-range local forecast.

All pressure values are in thousandths of inHg (native Davis format).
"""

from dataclasses import dataclass
from typing import Optional

# Zambretti forecast text tables.
# Each table maps a Z-number (index) to a forecast string.
# Derived from the original Zambretti wheel and Negretti & Zambra tables.

RISING_FORECASTS = [
    "Settled fine",
    "Fine weather",
    "Becoming fine",
    "Fairly fine, improving",
    "Fairly fine, possible showers early",
    "Showery early, improving",
    "Changeable, mending",
    "Rather unsettled, clearing later",
    "Unsettled, probably improving",
    "Unsettled, short fine intervals",
    "Very unsettled, finer at times",
]

STEADY_FORECASTS = [
    "Settled fine",
    "Fine weather",
    "Fine, possibly showers",
    "Fairly fine, showers likely",
    "Showery, bright intervals",
    "Changeable, some rain",
    "Unsettled, rain at times",
    "Rain at frequent intervals",
    "Very unsettled, rain",
    "Stormy, much rain",
]

FALLING_FORECASTS = [
    "Settled fine",
    "Fine weather",
    "Fine, becoming less settled",
    "Fairly fine, showery later",
    "Showery, becoming more unsettled",
    "Unsettled, rain later",
    "Unsettled, rain at times",
    "Rain at frequent intervals",
    "Very unsettled, rain",
    "Stormy, much rain",
]

# Pressure range constants (thousandths of inHg)
# Standard sea-level range for Zambretti: 950-1050 hPa ~ 28.05-31.00 inHg
PRESSURE_LOW = 28050   # 28.050 inHg (950 hPa)
PRESSURE_HIGH = 31000  # 31.000 inHg (1050 hPa)

# Trend classification thresholds (thousandths of inHg over 3 hours)
RISING_THRESHOLD = 16    # +0.016 inHg/3hr ~ +0.5 hPa/3hr
FALLING_THRESHOLD = -16  # -0.016 inHg/3hr ~ -0.5 hPa/3hr


@dataclass
class ZambrettiResult:
    """Result of a Zambretti forecast calculation."""
    forecast_text: str
    confidence: float  # 0.0 to 1.0
    z_number: int
    trend: str  # "rising", "falling", "steady"


def _wind_direction_adjustment(wind_dir_deg: Optional[int]) -> float:
    """Return a pressure adjustment factor based on wind direction.

    Wind from the south generally indicates lower pressure systems;
    wind from the north suggests higher pressure. This shifts the
    effective pressure reading to better match the Zambretti tables.

    Args:
        wind_dir_deg: Wind direction in degrees (0-359), or None if calm/unknown.

    Returns:
        Adjustment in thousandths of inHg to add to pressure.
    """
    if wind_dir_deg is None:
        return 0.0

    # Normalize to 0-359
    direction = wind_dir_deg % 360

    # Wind direction sectors and their adjustments (thousandths inHg):
    # N (315-45): high pressure indicator, raise effective pressure
    # E (45-135): neutral to slight high
    # S (135-225): low pressure indicator, lower effective pressure
    # W (225-315): neutral to slight low
    if 315 <= direction or direction < 45:
        return 30.0   # N wind -> raise pressure reading
    elif 45 <= direction < 135:
        return 15.0   # E wind -> slight raise
    elif 135 <= direction < 225:
        return -30.0  # S wind -> lower pressure reading
    else:
        return -15.0  # W wind -> slight lower


def _seasonal_adjustment(month: int) -> float:
    """Return a pressure adjustment for northern hemisphere season.

    Winter months have naturally higher average pressure; summer months
    lower. This corrects for seasonal bias in the Zambretti tables.

    Args:
        month: Month number 1-12.

    Returns:
        Adjustment in thousandths of inHg.
    """
    # Northern hemisphere seasonal corrections (thousandths inHg)
    # Positive in winter (higher pressure norm), negative in summer
    seasonal_table = {
        1: 15,    # January
        2: 12,    # February
        3: 6,     # March
        4: 0,     # April
        5: -6,    # May
        6: -12,   # June
        7: -15,   # July
        8: -12,   # August
        9: -6,    # September
        10: 0,    # October
        11: 6,    # November
        12: 12,   # December
    }
    return float(seasonal_table.get(month, 0))


def _classify_trend(pressure_change_3h: int) -> str:
    """Classify the 3-hour pressure change into rising/steady/falling.

    Args:
        pressure_change_3h: 3-hour barometric change in thousandths inHg.

    Returns:
        One of "rising", "steady", "falling".
    """
    if pressure_change_3h > RISING_THRESHOLD:
        return "rising"
    elif pressure_change_3h < FALLING_THRESHOLD:
        return "falling"
    else:
        return "steady"


def _compute_z_number(
    pressure: int,
    trend: str,
    table_size: int,
) -> int:
    """Compute the Zambretti Z-number from adjusted pressure and trend.

    Maps the pressure linearly into the range of the selected forecast
    table.  Higher pressure maps to lower Z-numbers (better weather).

    Args:
        pressure: Adjusted sea-level pressure in thousandths inHg.
        trend: One of "rising", "steady", "falling".
        table_size: Number of entries in the selected forecast table.

    Returns:
        Z-number (clamped to valid table index range).
    """
    # Clamp pressure to working range
    clamped = max(PRESSURE_LOW, min(PRESSURE_HIGH, pressure))

    # Normalize 0.0 (low pressure) to 1.0 (high pressure)
    normalized = (clamped - PRESSURE_LOW) / (PRESSURE_HIGH - PRESSURE_LOW)

    # Invert: low pressure = high Z (bad weather), high pressure = low Z (fine)
    z_raw = (1.0 - normalized) * (table_size - 1)

    # Apply trend bias: rising shifts toward better weather (lower Z),
    # falling shifts toward worse weather (higher Z)
    if trend == "rising":
        z_raw -= 1.0
    elif trend == "falling":
        z_raw += 1.0

    z_number = round(z_raw)
    return max(0, min(table_size - 1, z_number))


def _compute_confidence(
    pressure: int,
    pressure_change_3h: int,
) -> float:
    """Estimate forecast confidence from 0.0 to 1.0.

    Confidence is higher when:
    - Pressure is within normal range (not extreme)
    - Pressure change is moderate (strong trends are clear signals)

    Confidence is lower when:
    - Pressure is at extremes (unusual conditions)
    - Pressure is nearly static (hard to predict direction)

    Args:
        pressure: Sea-level pressure in thousandths inHg.
        pressure_change_3h: 3-hour pressure change in thousandths inHg.

    Returns:
        Confidence value between 0.0 and 1.0.
    """
    # Base confidence
    confidence = 0.6

    # Boost for clear trend signal
    abs_change = abs(pressure_change_3h)
    if abs_change > 50:
        confidence += 0.2  # Strong, clear trend
    elif abs_change > 20:
        confidence += 0.1  # Moderate trend

    # Penalize extreme pressures (unusual conditions are harder to predict)
    mid_pressure = (PRESSURE_HIGH + PRESSURE_LOW) / 2
    pressure_range = (PRESSURE_HIGH - PRESSURE_LOW) / 2
    deviation = abs(pressure - mid_pressure) / pressure_range
    if deviation > 0.8:
        confidence -= 0.15  # Extreme pressure

    return max(0.0, min(1.0, round(confidence, 2)))


def zambretti_forecast(
    pressure_thousandths: int,
    pressure_change_3h: int,
    wind_dir_deg: Optional[int] = None,
    month: int = 6,
) -> ZambrettiResult:
    """Compute a Zambretti barometric forecast.

    Args:
        pressure_thousandths: Current sea-level barometric pressure in
            thousandths of inHg (e.g., 29921 = 29.921 inHg).
        pressure_change_3h: Change in pressure over the last 3 hours,
            in thousandths of inHg (positive = rising).
        wind_dir_deg: Current wind direction in degrees 0-359,
            or None if calm or unknown.
        month: Current month (1-12) for seasonal adjustment.

    Returns:
        ZambrettiResult with forecast text, confidence, Z-number, and trend.
    """
    # Classify the pressure trend
    trend = _classify_trend(pressure_change_3h)

    # Adjust pressure for wind direction and season
    adjusted_pressure = pressure_thousandths
    adjusted_pressure += _wind_direction_adjustment(wind_dir_deg)
    adjusted_pressure += _seasonal_adjustment(month)
    adjusted_pressure = int(round(adjusted_pressure))

    # Select the appropriate forecast table
    if trend == "rising":
        table = RISING_FORECASTS
    elif trend == "falling":
        table = FALLING_FORECASTS
    else:
        table = STEADY_FORECASTS

    # Compute the Z-number and look up the forecast
    z_number = _compute_z_number(adjusted_pressure, trend, len(table))
    forecast_text = table[z_number]

    # Estimate confidence
    confidence = _compute_confidence(pressure_thousandths, pressure_change_3h)

    return ZambrettiResult(
        forecast_text=forecast_text,
        confidence=confidence,
        z_number=z_number,
        trend=trend,
    )
