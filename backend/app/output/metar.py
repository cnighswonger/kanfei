"""Pseudo-METAR string generator.

Formats current weather conditions into a METAR-like string suitable
for display, logging, or amateur radio transmission.  This is NOT a
real aviation METAR -- it uses a simplified subset of the format for
personal weather station data.

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


def _f_to_c(temp_tenths_f: int) -> int:
    """Convert temperature from tenths of degrees F to whole degrees C.

    Args:
        temp_tenths_f: Temperature in tenths of degrees Fahrenheit.

    Returns:
        Temperature in whole degrees Celsius.
    """
    temp_f = temp_tenths_f / 10.0
    temp_c = (temp_f - 32.0) * 5.0 / 9.0
    return round(temp_c)


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


def _mph_to_knots(speed_mph: int) -> int:
    """Convert wind speed from mph to knots.

    Args:
        speed_mph: Wind speed in miles per hour.

    Returns:
        Wind speed in knots (rounded to nearest integer).
    """
    return round(speed_mph * 0.868976)


def _format_altimeter(barometer_thousandths: int) -> str:
    """Format barometric pressure as METAR altimeter setting.

    METAR uses 'A' followed by pressure in hundredths of inHg (4 digits).

    Args:
        barometer_thousandths: Sea-level pressure in thousandths of inHg
            (e.g., 29921 = 29.921 inHg).

    Returns:
        METAR altimeter string, e.g., "A2992".
    """
    # Convert thousandths to hundredths (drop last digit, round)
    hundredths = round(barometer_thousandths / 10.0)
    return f"A{hundredths:04d}"


def format_metar(
    station_id: str,
    wind_dir_deg: Optional[int],
    wind_speed_mph: int,
    temp_tenths_f: int,
    dew_point_tenths_f: int,
    barometer_thousandths: int,
    obs_time: Optional[datetime] = None,
) -> str:
    """Format current conditions as a pseudo-METAR string.

    Args:
        station_id: 4-character station identifier (e.g., "KWXS").
        wind_dir_deg: Wind direction in degrees (0-359), or None if calm.
        wind_speed_mph: Wind speed in mph (will be converted to knots).
        temp_tenths_f: Temperature in tenths of degrees Fahrenheit.
        dew_point_tenths_f: Dew point in tenths of degrees Fahrenheit.
        barometer_thousandths: Sea-level barometric pressure in thousandths
            of inHg (e.g., 29921 = 29.921 inHg).
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
    wind_knots = _mph_to_knots(wind_speed_mph)
    wind_str = _format_wind(wind_dir_deg, wind_knots)

    # Visibility: always 10SM (we don't measure visibility)
    vis_str = "10SM"

    # Sky condition: always CLR (we don't measure cloud cover)
    sky_str = "CLR"

    # Temperature / dew point in Celsius
    temp_c = _f_to_c(temp_tenths_f)
    dewpt_c = _f_to_c(dew_point_tenths_f)
    temp_str = f"{_format_temp_c(temp_c)}/{_format_temp_c(dewpt_c)}"

    # Altimeter
    alt_str = _format_altimeter(barometer_thousandths)

    return f"METAR {sid} {time_str} {wind_str} {vis_str} {sky_str} {temp_str} {alt_str}"
