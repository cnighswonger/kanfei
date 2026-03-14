"""Astronomical calculations for the weather station dashboard.

Provides sunrise/sunset times, twilight periods, day length statistics,
moon phase information, and upcoming lunar events using the astral library.
"""

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from astral import LocationInfo, moon
from astral.sun import sun, twilight, SunDirection


# Synodic month length in days (new moon to new moon).
SYNODIC_MONTH = 29.53059

# Moon phase names mapped to phase angle ranges (0-27.99).
# astral.moon.phase() returns 0-27.99 where:
#   0       = New Moon
#   ~7      = First Quarter
#   ~14     = Full Moon
#   ~21     = Last Quarter
MOON_PHASE_NAMES = [
    (0.0, 1.0, "New Moon"),
    (1.0, 6.0, "Waxing Crescent"),
    (6.0, 8.0, "First Quarter"),
    (8.0, 13.0, "Waxing Gibbous"),
    (13.0, 15.0, "Full Moon"),
    (15.0, 20.0, "Waning Gibbous"),
    (20.0, 22.0, "Last Quarter"),
    (22.0, 28.0, "Waning Crescent"),
]


@dataclass
class TwilightTimes:
    """Civil, nautical, and astronomical twilight start/end times (UTC)."""
    civil_start: Optional[datetime] = None
    civil_end: Optional[datetime] = None
    nautical_start: Optional[datetime] = None
    nautical_end: Optional[datetime] = None
    astronomical_start: Optional[datetime] = None
    astronomical_end: Optional[datetime] = None


@dataclass
class MoonInfo:
    """Lunar phase and upcoming event information."""
    phase_name: str
    phase_angle: float  # 0-27.99 from astral
    illumination_pct: float  # 0-100
    next_full_moon: date
    next_new_moon: date


@dataclass
class AstronomyData:
    """Complete astronomical data for a given location and date."""
    date: date
    latitude: float
    longitude: float
    elevation_m: float

    # Solar events (UTC)
    sunrise: Optional[datetime] = None
    sunset: Optional[datetime] = None
    solar_noon: Optional[datetime] = None

    # Twilight
    twilight: TwilightTimes = field(default_factory=TwilightTimes)

    # Day length
    day_length_seconds: Optional[float] = None
    day_change_seconds: Optional[float] = None  # vs yesterday

    # Moon
    moon_info: Optional[MoonInfo] = None


def _moon_phase_name(phase_angle: float) -> str:
    """Map an astral phase angle (0-27.99) to a human-readable name.

    Args:
        phase_angle: Moon phase from astral.moon.phase(), range 0 to ~27.99.

    Returns:
        Phase name string.
    """
    for low, high, name in MOON_PHASE_NAMES:
        if low <= phase_angle < high:
            return name
    # Wrap-around: phase_angle >= 28 should not happen, but handle gracefully.
    return "Waning Crescent"


def _moon_illumination(phase_angle: float) -> float:
    """Estimate moon illumination percentage from phase angle.

    Uses a cosine model: illumination peaks at phase_angle ~14 (full moon)
    and is zero at phase_angle 0 (new moon).

    Args:
        phase_angle: Moon phase from astral.moon.phase(), range 0 to ~27.99.

    Returns:
        Illumination percentage 0-100.
    """
    # Normalize phase to 0-1 cycle (0 = new, 0.5 = full, 1.0 = new again)
    normalized = phase_angle / SYNODIC_MONTH
    # Cosine illumination model
    illumination = (1.0 - math.cos(2.0 * math.pi * normalized)) / 2.0
    return round(illumination * 100.0, 1)


def _find_next_phase(start_date: date, target_phase_low: float, target_phase_high: float) -> date:
    """Find the next date when the moon phase falls within a target range.

    Searches forward day by day up to one full synodic month.

    Args:
        start_date: Date to start searching from.
        target_phase_low: Lower bound of target phase angle (inclusive).
        target_phase_high: Upper bound of target phase angle (exclusive).

    Returns:
        The first date on or after start_date when phase is in range.
    """
    for day_offset in range(1, 35):
        check_date = start_date + timedelta(days=day_offset)
        phase = moon.phase(check_date)
        if target_phase_low <= phase < target_phase_high:
            return check_date
    # Fallback: estimate from current phase
    return start_date + timedelta(days=15)


def _compute_day_length(
    location: LocationInfo,
    target_date: date,
) -> Optional[float]:
    """Compute day length in seconds for a given date.

    Args:
        location: Astral LocationInfo object.
        target_date: Date to compute for.

    Returns:
        Day length in seconds, or None if sun never rises/sets.
    """
    try:
        s = sun(location.observer, date=target_date)
        sunrise = s["sunrise"]
        sunset = s["sunset"]
        return (sunset - sunrise).total_seconds()
    except ValueError:
        # Polar day/night: sun never rises or never sets
        return None


def compute_astronomy(
    latitude: float,
    longitude: float,
    elevation_m: float,
    target_date: Optional[date] = None,
) -> AstronomyData:
    """Compute full astronomical data for a location and date.

    Args:
        latitude: Latitude in decimal degrees (positive north).
        longitude: Longitude in decimal degrees (positive east).
        elevation_m: Elevation in meters above sea level.
        target_date: Date to compute for (defaults to today UTC).

    Returns:
        AstronomyData dataclass with all computed fields.
    """
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    location = LocationInfo(
        name="Station",
        region="",
        timezone="UTC",
        latitude=latitude,
        longitude=longitude,
    )

    result = AstronomyData(
        date=target_date,
        latitude=latitude,
        longitude=longitude,
        elevation_m=elevation_m,
    )

    # --- Solar events ---
    try:
        s = sun(location.observer, date=target_date)
        result.sunrise = s.get("sunrise")
        result.sunset = s.get("sunset")
        result.solar_noon = s.get("noon")
    except ValueError:
        # Polar conditions: sun does not rise/set on this date
        pass

    # --- Twilight periods ---
    tw = TwilightTimes()

    # Civil twilight (6 degrees below horizon)
    try:
        civil = twilight(location.observer, date=target_date, direction=SunDirection.RISING)
        tw.civil_start = civil[0]
        civil_set = twilight(location.observer, date=target_date, direction=SunDirection.SETTING)
        tw.civil_end = civil_set[1]
    except ValueError:
        pass

    # Nautical twilight (12 degrees)
    try:
        nautical = twilight(
            location.observer, date=target_date,
            direction=SunDirection.RISING, tzinfo=timezone.utc,
        )
        tw.nautical_start = nautical[0]
        nautical_set = twilight(
            location.observer, date=target_date,
            direction=SunDirection.SETTING, tzinfo=timezone.utc,
        )
        tw.nautical_end = nautical_set[1]
    except (ValueError, TypeError):
        pass

    # Astronomical twilight (18 degrees)
    try:
        astro = twilight(
            location.observer, date=target_date,
            direction=SunDirection.RISING, tzinfo=timezone.utc,
        )
        tw.astronomical_start = astro[0]
        astro_set = twilight(
            location.observer, date=target_date,
            direction=SunDirection.SETTING, tzinfo=timezone.utc,
        )
        tw.astronomical_end = astro_set[1]
    except (ValueError, TypeError):
        pass

    result.twilight = tw

    # --- Day length ---
    today_length = _compute_day_length(location, target_date)
    result.day_length_seconds = today_length

    yesterday = target_date - timedelta(days=1)
    yesterday_length = _compute_day_length(location, yesterday)

    if today_length is not None and yesterday_length is not None:
        result.day_change_seconds = round(today_length - yesterday_length, 1)

    # --- Moon ---
    phase_angle = moon.phase(target_date)
    phase_name = _moon_phase_name(phase_angle)
    illumination = _moon_illumination(phase_angle)

    # Find next full moon (phase ~13-15) and new moon (phase ~0-1)
    next_full = _find_next_phase(target_date, 13.0, 15.0)
    next_new = _find_next_phase(target_date, 0.0, 1.0)

    result.moon_info = MoonInfo(
        phase_name=phase_name,
        phase_angle=round(phase_angle, 2),
        illumination_pct=illumination,
        next_full_moon=next_full,
        next_new_moon=next_new,
    )

    return result
