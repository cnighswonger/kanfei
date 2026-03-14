"""Weather calculation services.

Heat index, dew point, wind chill, atmospheric entropy (theta_e),
feels-like composite, and rain rate.

All temperatures in tenths of degrees Fahrenheit unless noted.
"""

import math
from typing import Optional

# THI table ported from reference/thitable.h
# Rows: 68F to 122F (55 rows), Columns: 0% to 100% humidity in 10% steps (11 cols)
# Values > 125 are for interpolation only
THI_TABLE = [
    [61, 63, 63, 64, 66, 66, 68, 68, 70, 70, 70],  # 68
    [63, 64, 65, 65, 67, 67, 69, 69, 71, 71, 72],  # 69
    [65, 65, 66, 66, 68, 68, 70, 70, 72, 72, 74],  # 70
    [66, 66, 67, 67, 69, 69, 71, 71, 73, 73, 75],  # 71
    [67, 67, 68, 69, 70, 71, 72, 72, 74, 74, 76],  # 72
    [68, 68, 69, 71, 71, 73, 73, 74, 75, 75, 77],  # 73
    [69, 69, 70, 72, 72, 74, 74, 76, 76, 76, 78],  # 74
    [70, 71, 71, 73, 73, 75, 75, 77, 77, 78, 79],  # 75
    [71, 72, 73, 74, 74, 76, 76, 78, 79, 80, 80],  # 76
    [72, 73, 75, 75, 75, 77, 77, 79, 81, 81, 82],  # 77
    [74, 74, 76, 76, 77, 78, 79, 80, 82, 83, 84],  # 78
    [75, 75, 77, 77, 79, 79, 81, 81, 83, 85, 87],  # 79
    [76, 76, 78, 78, 80, 80, 82, 83, 85, 87, 90],  # 80
    [77, 77, 79, 79, 81, 81, 83, 85, 87, 89, 93],  # 81
    [78, 78, 80, 80, 82, 83, 84, 87, 89, 92, 96],  # 82
    [79, 79, 81, 81, 83, 85, 85, 89, 91, 95, 99],  # 83
    [79, 80, 81, 82, 84, 86, 87, 91, 94, 98, 103],  # 84
    [80, 81, 81, 83, 85, 87, 89, 93, 97, 101, 108],  # 85
    [81, 82, 82, 84, 86, 88, 91, 95, 99, 104, 113],  # 86
    [82, 83, 83, 85, 87, 90, 93, 97, 102, 109, 120],  # 87
    [83, 84, 84, 86, 88, 92, 95, 99, 105, 114, 131],  # 88
    [84, 84, 85, 87, 90, 94, 97, 102, 109, 120, 144],  # 89
    [84, 85, 86, 89, 92, 95, 99, 105, 113, 128, 150],  # 90
    [84, 86, 87, 91, 93, 96, 101, 108, 118, 136, 150],  # 91
    [85, 87, 88, 92, 94, 98, 104, 112, 124, 144, 150],  # 92
    [86, 88, 89, 93, 96, 100, 107, 116, 130, 150, 150],  # 93
    [87, 89, 90, 94, 98, 102, 110, 120, 137, 150, 150],  # 94
    [88, 90, 91, 95, 99, 104, 113, 124, 144, 150, 150],  # 95
    [89, 91, 93, 97, 101, 107, 117, 128, 150, 150, 150],  # 96
    [90, 92, 95, 99, 103, 110, 121, 132, 150, 150, 150],  # 97
    [90, 93, 96, 100, 105, 113, 125, 150, 150, 150, 150],  # 98
    [90, 94, 97, 101, 107, 116, 129, 150, 150, 150, 150],  # 99
    [91, 95, 98, 103, 110, 119, 133, 150, 150, 150, 150],  # 100
    [92, 96, 99, 105, 112, 122, 137, 150, 150, 150, 150],  # 101
    [93, 97, 100, 106, 114, 125, 150, 150, 150, 150, 150],  # 102
    [94, 98, 102, 107, 117, 128, 150, 150, 150, 150, 150],  # 103
    [95, 99, 104, 109, 120, 132, 150, 150, 150, 150, 150],  # 104
    [95, 100, 105, 111, 123, 135, 150, 150, 150, 150, 150],  # 105
    [95, 101, 106, 113, 126, 150, 150, 150, 150, 150, 150],  # 106
    [96, 102, 107, 115, 130, 150, 150, 150, 150, 150, 150],  # 107
    [97, 103, 108, 117, 133, 150, 150, 150, 150, 150, 150],  # 108
    [98, 104, 110, 119, 137, 150, 150, 150, 150, 150, 150],  # 109
    [99, 105, 112, 122, 142, 150, 150, 150, 150, 150, 150],  # 110
    [100, 106, 113, 125, 150, 150, 150, 150, 150, 150, 150],  # 111
    [100, 107, 115, 128, 150, 150, 150, 150, 150, 150, 150],  # 112
    [100, 108, 117, 131, 150, 150, 150, 150, 150, 150, 150],  # 113
    [101, 109, 119, 134, 150, 150, 150, 150, 150, 150, 150],  # 114
    [102, 110, 121, 136, 150, 150, 150, 150, 150, 150, 150],  # 115
    [103, 111, 123, 140, 150, 150, 150, 150, 150, 150, 150],  # 116
    [104, 112, 125, 143, 150, 150, 150, 150, 150, 150, 150],  # 117
    [105, 113, 127, 150, 150, 150, 150, 150, 150, 150, 150],  # 118
    [106, 114, 129, 150, 150, 150, 150, 150, 150, 150, 150],  # 119
    [107, 116, 131, 150, 150, 150, 150, 150, 150, 150, 150],  # 120
    [108, 117, 133, 150, 150, 150, 150, 150, 150, 150, 150],  # 121
    [108, 118, 136, 150, 150, 150, 150, 150, 150, 150, 150],  # 122
]

THI_BASE_TEMP = 68  # First row temperature
THI_MAX_TEMP = 122  # Last row temperature

# Wind chill factor tables from techref.txt lines 1497-1536
CHILL_TABLE_ONE = [156, 151, 146, 141, 133, 123, 110, 87, 61, 14, 0]
CHILL_TABLE_TWO = [0, 16, 16, 16, 25, 33, 41, 74, 82, 152, 0]


def heat_index(temp_tenths_f: int, humidity: int) -> Optional[int]:
    """Calculate heat index using THI table with bilinear interpolation.

    Args:
        temp_tenths_f: Temperature in tenths of degrees F (e.g., 850 = 85.0F)
        humidity: Relative humidity 0-100%

    Returns:
        Heat index in tenths of degrees F, or None if out of range.
    """
    temp_f = temp_tenths_f / 10.0

    if temp_f < THI_BASE_TEMP:
        return None  # Below table range
    if temp_f > THI_MAX_TEMP:
        return None  # Above table range
    if humidity < 0 or humidity > 100:
        return None

    # Table indices
    row_idx = temp_f - THI_BASE_TEMP
    col_idx = humidity / 10.0

    row_lo = int(row_idx)
    row_hi = min(row_lo + 1, len(THI_TABLE) - 1)
    row_frac = row_idx - row_lo

    col_lo = int(col_idx)
    col_hi = min(col_lo + 1, 10)
    col_frac = col_idx - col_lo

    # Bilinear interpolation
    v00 = THI_TABLE[row_lo][col_lo]
    v01 = THI_TABLE[row_lo][col_hi]
    v10 = THI_TABLE[row_hi][col_lo]
    v11 = THI_TABLE[row_hi][col_hi]

    v0 = v00 + (v01 - v00) * col_frac
    v1 = v10 + (v11 - v10) * col_frac
    result = v0 + (v1 - v0) * row_frac

    # Values > 125 are interpolation artifacts, not real
    if result > 125:
        return None

    return round(result * 10)  # Convert to tenths F


def dew_point(temp_tenths_f: int, humidity: int) -> Optional[int]:
    """Calculate dew point using Magnus formula.

    Per techref.txt lines 1547-1572.

    Args:
        temp_tenths_f: Temperature in tenths of degrees F
        humidity: Relative humidity 0-100%

    Returns:
        Dew point in tenths of degrees F, or None if invalid.
    """
    if humidity <= 0 or humidity > 100:
        return None

    temp_c = (temp_tenths_f / 10.0 - 32.0) * 5.0 / 9.0
    rh_frac = humidity / 100.0

    # Magnus formula constants
    a = 17.502
    b = 240.97

    # Saturation vapor pressure ratio
    gamma = math.log(rh_frac) + (a * temp_c) / (b + temp_c)
    dp_c = (b * gamma) / (a - gamma)

    dp_f = dp_c * 9.0 / 5.0 + 32.0
    return round(dp_f * 10)  # Convert to tenths F


def wind_chill(temp_tenths_f: int, wind_speed_mph: int) -> Optional[int]:
    """Calculate wind chill using Davis chill factor tables.

    Per techref.txt lines 1514-1536 (ChillCalc function):
      index = 10 - speed / 5
      cf = chillTableOne[index] + (chillTableTwo[index] / 16.0) * (speed % 5)
      chill = cf * ((t - 91.4) / 256.0) + t

    Args:
        temp_tenths_f: Temperature in tenths of degrees F
        wind_speed_mph: Wind speed in mph

    Returns:
        Wind chill in tenths of degrees F, or None if not applicable.
    """
    temp_f = temp_tenths_f / 10.0

    if temp_f >= 91.4:
        return None  # Wind chill not applicable above 91.4F
    if wind_speed_mph <= 0:
        return temp_tenths_f  # No wind, no chill

    # Cap at 50 mph per Davis implementation
    speed = min(wind_speed_mph, 50)

    # Index is REVERSED: 10 - speed/5 (integer division)
    index = 10 - speed // 5

    # Chill factor with interpolation
    # chillTableTwo is divided by 16.0 and multiplied by (speed % 5)
    cf = CHILL_TABLE_ONE[index] + (CHILL_TABLE_TWO[index] / 16.0) * (speed % 5)

    # Wind chill formula
    chill_f = cf * ((temp_f - 91.4) / 256.0) + temp_f

    # Wind chill should not exceed actual temperature
    chill_f = min(chill_f, temp_f)

    return round(chill_f * 10)


def feels_like(
    temp_tenths_f: int,
    humidity: int,
    wind_speed_mph: int,
) -> int:
    """Calculate "feels like" composite temperature.

    - If temp > 80F and humidity > 40%: use heat index
    - If temp < 50F and wind > 3 mph: use wind chill
    - Otherwise: actual temperature
    """
    temp_f = temp_tenths_f / 10.0

    if temp_f > 80.0 and humidity > 40:
        hi = heat_index(temp_tenths_f, humidity)
        if hi is not None:
            return hi

    if temp_f < 50.0 and wind_speed_mph > 3:
        wc = wind_chill(temp_tenths_f, wind_speed_mph)
        if wc is not None:
            return wc

    return temp_tenths_f


def equivalent_potential_temperature(
    temp_tenths_f: int,
    humidity: int,
    pressure_thousandths_inhg: int,
) -> Optional[int]:
    """Calculate equivalent potential temperature (atmospheric entropy proxy).

    Uses Bolton (1980) formula:
    theta_e = T * (1000/P)^0.2854 * exp((3.376/T_LCL - 0.00254) * r * (1 + 0.81e-3 * r))

    Args:
        temp_tenths_f: Temperature in tenths F
        humidity: RH 0-100%
        pressure_thousandths_inhg: Barometric pressure in thousandths inHg

    Returns:
        Theta_e in tenths of Kelvin, or None if invalid.
    """
    if humidity <= 0 or pressure_thousandths_inhg <= 0:
        return None

    # Convert to SI
    temp_f = temp_tenths_f / 10.0
    temp_c = (temp_f - 32.0) * 5.0 / 9.0
    temp_k = temp_c + 273.15
    pressure_hpa = pressure_thousandths_inhg / 1000.0 * 33.8639  # inHg to hPa
    rh = humidity / 100.0

    # Saturation vapor pressure (Bolton 1980)
    es = 6.112 * math.exp((17.67 * temp_c) / (temp_c + 243.5))
    e = rh * es  # actual vapor pressure

    # Mixing ratio (g/kg)
    r = 621.97 * e / (pressure_hpa - e)

    # Lifted condensation level temperature (Bolton 1980)
    t_lcl = (1.0 / (1.0 / (temp_k - 55) - math.log(rh) / 2840.0)) + 55

    # Equivalent potential temperature
    theta_e = temp_k * (1000.0 / pressure_hpa) ** 0.2854
    theta_e *= math.exp((3.376 / t_lcl - 0.00254) * r * (1 + 0.81e-3 * r))

    return round(theta_e * 10)  # tenths of K


def rain_rate_inches_per_hour(
    rain_clicks_now: int,
    rain_clicks_prev: int,
    rain_cal: int,
    interval_seconds: float,
) -> Optional[float]:
    """Calculate rain rate in inches per hour from accumulation delta.

    Args:
        rain_clicks_now: Current total rain clicks
        rain_clicks_prev: Previous total rain clicks
        rain_cal: Clicks per inch (from station calibration)
        interval_seconds: Time between readings in seconds

    Returns:
        Rain rate in inches per hour, or None if invalid.
    """
    if rain_cal <= 0 or interval_seconds <= 0:
        return None

    delta_clicks = rain_clicks_now - rain_clicks_prev
    if delta_clicks < 0:
        return None  # Counter rollover, skip

    delta_inches = delta_clicks / rain_cal
    rate = delta_inches * 3600.0 / interval_seconds
    return round(rate, 2)
