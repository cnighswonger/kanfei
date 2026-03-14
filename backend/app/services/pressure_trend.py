"""Barometric pressure trend analysis.

Determines rising/falling/steady from historical barometric readings.
"""

from dataclasses import dataclass
from typing import Optional

# Threshold for trend classification (thousandths of inHg)
# 0.020 inHg = 20 thousandths
TREND_THRESHOLD = 20

# Time window for trend analysis (seconds)
TREND_WINDOW_HOURS = 3
TREND_WINDOW_SECONDS = TREND_WINDOW_HOURS * 3600


@dataclass
class PressureTrend:
    """Result of pressure trend analysis."""
    trend: str  # "rising", "falling", "steady"
    change: int  # Change in thousandths inHg over the window
    rate_per_hour: float  # Change rate in thousandths inHg per hour


def analyze_pressure_trend(
    readings: list[tuple[float, int]],
) -> Optional[PressureTrend]:
    """Analyze barometric pressure trend from historical readings.

    Args:
        readings: List of (timestamp_unix, barometer_thousandths) tuples,
                  sorted by timestamp ascending.

    Returns:
        PressureTrend or None if insufficient data.
    """
    if len(readings) < 2:
        return None

    # Use oldest and newest readings in the window
    oldest_time, oldest_bar = readings[0]
    newest_time, newest_bar = readings[-1]

    elapsed_hours = (newest_time - oldest_time) / 3600.0
    if elapsed_hours <= 0:
        return None

    change = newest_bar - oldest_bar
    rate = change / elapsed_hours

    if change > TREND_THRESHOLD:
        trend = "rising"
    elif change < -TREND_THRESHOLD:
        trend = "falling"
    else:
        trend = "steady"

    return PressureTrend(trend=trend, change=change, rate_per_hour=round(rate, 1))
