"""Pseudo-METAR string generator.

Formats current weather conditions into a METAR-like string suitable
for display, logging, or amateur radio transmission.  This is NOT a
real aviation METAR -- it uses a simplified subset of the format for
personal weather station data.

All inputs are in SI units (tenths °C, tenths hPa, tenths m/s).
Conversion to METAR units (°C, knots, inHg) happens internally.

Format produced:
    METAR {ID} {DDHHMMz} {wind} {vis} {sky} {temp}/{dewpt} {altimeter}

Example:
    METAR KWXS 151753Z 27010KT 10SM CLR 22/15 A2992
"""

from datetime import datetime, timezone
from typing import Optional


def _format_wind(
    wind_dir_deg: Optional[int],
    wind_speed_knots: int,
) -> str:
    """Format wind direction and speed in METAR notation.

    Args:
        wind_dir_deg: Wind direction in degrees (0-359), or None if calm.
        wind_speed_knots: Wind speed in knots.

    Returns:
        METAR wind string, e.g., "27010KT", "VRB03KT", or "00000KT".
    """
    if wind_speed_knots == 0 or wind_dir_deg is None:
        if wind_speed_knots == 0:
            return "00000KT"
        # Speed > 0 but no direction: variable
        return f"VRB{wind_speed_knots:02d}KT"

    return f"{wind_dir_deg:03d}{wind_speed_knots:02d}KT"


def _si_temp_to_whole_c(temp_tenths_c: int) -> int:
    """Convert tenths of °C to whole degrees °C for METAR.

    Args:
        temp_tenths_c: Temperature in tenths of degrees Celsius.

    Returns:
        Temperature in whole degrees Celsius.
    """
    return round(temp_tenths_c / 10.0)


def _format_temp_c(temp_c: int) -> str:
    """Format a Celsius temperature for METAR.

    Negative temperatures are prefixed with 'M' (minus) per METAR convention.

    Args:
        temp_c: Temperature in whole degrees Celsius.

    Returns:
        METAR temperature string, e.g., "22", "M05".
    """
    if temp_c < 0:
        return f"M{abs(temp_c):02d}"
    return f"{temp_c:02d}"


def _ms_tenths_to_knots(speed_tenths_ms: int) -> int:
    """Convert wind speed from tenths of m/s to knots.

    Args:
        speed_tenths_ms: Wind speed in tenths of m/s.

    Returns:
        Wind speed in knots (rounded to nearest integer).
    """
    return round(speed_tenths_ms / 10.0 * 1.94384)


def _format_altimeter(pressure_tenths_hpa: int) -> str:
    """Format barometric pressure as METAR altimeter setting.

    METAR uses 'A' followed by pressure in hundredths of inHg (4 digits).

    Args:
        pressure_tenths_hpa: Sea-level pressure in tenths of hPa
            (e.g., 10132 = 1013.2 hPa).

    Returns:
        METAR altimeter string, e.g., "A2992".
    """
    # Convert tenths hPa to hundredths inHg
    inhg = pressure_tenths_hpa / 10.0 / 33.8639
    hundredths = round(inhg * 100)
    return f"A{hundredths:04d}"


def format_metar(
    station_id: str,
    wind_dir_deg: Optional[int],
    wind_speed_tenths_ms: int,
    temp_tenths_c: int,
    dew_point_tenths_c: int,
    pressure_tenths_hpa: int,
    obs_time: Optional[datetime] = None,
) -> str:
    """Format current conditions as a pseudo-METAR string.

    All inputs in SI units.

    Args:
        station_id: 4-character station identifier (e.g., "KWXS").
        wind_dir_deg: Wind direction in degrees (0-359), or None if calm.
        wind_speed_tenths_ms: Wind speed in tenths of m/s.
        temp_tenths_c: Temperature in tenths of °C.
        dew_point_tenths_c: Dew point in tenths of °C.
        pressure_tenths_hpa: Sea-level pressure in tenths of hPa.
        obs_time: Observation time (defaults to current UTC time).

    Returns:
        Pseudo-METAR string.
    """
    if obs_time is None:
        obs_time = datetime.now(timezone.utc)

    # Ensure station ID is uppercase and 4 characters
    sid = station_id.upper()[:4].ljust(4, "X")

    # Date/time group: DDHHMMz
    time_str = obs_time.strftime("%d%H%MZ")

    # Wind
    wind_knots = _ms_tenths_to_knots(wind_speed_tenths_ms)
    wind_str = _format_wind(wind_dir_deg, wind_knots)

    # Visibility: always 10SM (we don't measure visibility)
    vis_str = "10SM"

    # Sky condition: always CLR (we don't measure cloud cover)
    sky_str = "CLR"

    # Temperature / dew point in whole Celsius
    temp_c = _si_temp_to_whole_c(temp_tenths_c)
    dewpt_c = _si_temp_to_whole_c(dew_point_tenths_c)
    temp_str = f"{_format_temp_c(temp_c)}/{_format_temp_c(dewpt_c)}"

    # Altimeter
    alt_str = _format_altimeter(pressure_tenths_hpa)

    return f"METAR {sid} {time_str} {wind_str} {vis_str} {sky_str} {temp_str} {alt_str}"
