"""SI unit conversion utilities.

All internal storage uses SI units:
  - Temperature: tenths of °C (integer)
  - Pressure: tenths of hPa (integer)
  - Wind speed: tenths of m/s (integer)
  - Rain: tenths of mm (integer)

These functions convert between SI storage and other unit systems
(Davis native, display units, output formats).
"""


# ---------------------------------------------------------------------------
# Temperature: tenths °C <-> tenths °F
# ---------------------------------------------------------------------------

def f_tenths_to_c_tenths(f_tenths: int) -> int:
    """Convert tenths of °F to tenths of °C.

    >>> f_tenths_to_c_tenths(720)  # 72.0°F
    222  # 22.2°C
    """
    return round((f_tenths - 320) * 5 / 9)


def c_tenths_to_f_tenths(c_tenths: int) -> int:
    """Convert tenths of °C to tenths of °F.

    >>> c_tenths_to_f_tenths(222)  # 22.2°C
    720  # 72.0°F
    """
    return round(c_tenths * 9 / 5 + 320)


# ---------------------------------------------------------------------------
# Pressure: thousandths inHg <-> tenths hPa
# ---------------------------------------------------------------------------

def inhg_thousandths_to_hpa_tenths(inhg: int) -> int:
    """Convert thousandths of inHg to tenths of hPa.

    >>> inhg_thousandths_to_hpa_tenths(29920)  # 29.920 inHg
    10132  # 1013.2 hPa
    """
    return round(inhg * 33.8639 / 100)


def hpa_tenths_to_inhg_thousandths(hpa: int) -> int:
    """Convert tenths of hPa to thousandths of inHg.

    >>> hpa_tenths_to_inhg_thousandths(10132)  # 1013.2 hPa
    29920  # 29.920 inHg
    """
    return round(hpa * 100 / 33.8639)


# ---------------------------------------------------------------------------
# Wind speed: mph <-> tenths m/s
# ---------------------------------------------------------------------------

def mph_to_ms_tenths(mph: int) -> int:
    """Convert mph (integer) to tenths of m/s.

    >>> mph_to_ms_tenths(10)  # 10 mph
    45  # 4.5 m/s
    """
    return round(mph * 4.4704)  # 1 mph = 0.44704 m/s, * 10 for tenths


def ms_tenths_to_mph(ms: int) -> int:
    """Convert tenths of m/s to mph (integer).

    >>> ms_tenths_to_mph(45)  # 4.5 m/s
    10  # 10 mph
    """
    return round(ms / 4.4704)


# ---------------------------------------------------------------------------
# Rain: hundredths inches <-> tenths mm
# ---------------------------------------------------------------------------

def in_hundredths_to_mm_tenths(inches: int) -> int:
    """Convert hundredths of inches to tenths of mm.

    >>> in_hundredths_to_mm_tenths(100)  # 1.00 inch
    254  # 25.4 mm
    """
    return round(inches * 2.54)  # 1/100 in * 25.4 mm/in * 10 tenths/mm = * 2.54


def mm_tenths_to_in_hundredths(mm: int) -> int:
    """Convert tenths of mm to hundredths of inches.

    >>> mm_tenths_to_in_hundredths(254)  # 25.4 mm
    100  # 1.00 inch
    """
    return round(mm / 2.54)


# ---------------------------------------------------------------------------
# Display conversion: SI storage -> display values
# Used by sensor_meta.convert() to produce API output.
# ---------------------------------------------------------------------------

def si_temp_to_display_f(raw: int) -> float:
    """Tenths °C -> display °F.

    >>> si_temp_to_display_f(222)  # 22.2°C
    72.0
    """
    return round(raw / 10 * 9 / 5 + 32, 1)


def si_temp_to_display_c(raw: int) -> float:
    """Tenths °C -> display °C.

    >>> si_temp_to_display_c(222)
    22.2
    """
    return round(raw / 10, 1)


def si_pressure_to_display_inhg(raw: int) -> float:
    """Tenths hPa -> display inHg.

    >>> si_pressure_to_display_inhg(10132)  # 1013.2 hPa
    29.92
    """
    return round(raw / 10 / 33.8639, 2)


def si_pressure_to_display_hpa(raw: int) -> float:
    """Tenths hPa -> display hPa.

    >>> si_pressure_to_display_hpa(10132)
    1013.2
    """
    return round(raw / 10, 1)


def si_wind_to_display_mph(raw: int) -> int:
    """Tenths m/s -> display mph (integer).

    >>> si_wind_to_display_mph(45)  # 4.5 m/s
    10
    """
    return round(raw / 10 * 2.23694)


def si_wind_to_display_ms(raw: int) -> float:
    """Tenths m/s -> display m/s."""
    return round(raw / 10, 1)


def si_wind_to_display_kmh(raw: int) -> float:
    """Tenths m/s -> display km/h."""
    return round(raw / 10 * 3.6, 1)


def si_rain_to_display_in(raw: int) -> float:
    """Tenths mm -> display inches.

    >>> si_rain_to_display_in(254)  # 25.4 mm
    1.0
    """
    return round(raw / 10 / 25.4, 2)


def si_rain_to_display_mm(raw: int) -> float:
    """Tenths mm -> display mm."""
    return round(raw / 10, 1)


def si_theta_e_to_display(raw: int) -> float:
    """Tenths K -> display K."""
    return round(raw / 10, 1)
