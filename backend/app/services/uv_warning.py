"""UV Index warning level classification.

Per WHO / WMO Global Solar UV Index guidance:

    UV Index    Category    Colour band
    ---------   ---------   -----------
    0-2         Low         Green
    3-5         Moderate    Yellow
    6-7         High        Orange
    8-10        Very High   Red
    11+         Extreme     Purple

The UV Index itself is dimensionless; the boundaries are inclusive-low
(i.e. UVI 3.0 is Moderate, 2.999 is Low). Fractional UVI values are
common — Vantage reports UVI as tenths of a unit — so we treat the
lower end of each band as inclusive.
"""

from typing import Optional


def classify_uv(uv_index: Optional[float]) -> Optional[str]:
    """Return the WHO band name for a UV Index value, or ``None`` when the
    input is ``None`` or negative (sentinel / no-sensor).
    """
    if uv_index is None or uv_index < 0:
        return None
    if uv_index < 3:
        return "Low"
    if uv_index < 6:
        return "Moderate"
    if uv_index < 8:
        return "High"
    if uv_index < 11:
        return "Very High"
    return "Extreme"
