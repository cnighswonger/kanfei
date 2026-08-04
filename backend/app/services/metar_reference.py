"""Nearby METAR observations, for use as a barometer calibration reference.

A Vantage console reports barometric reduction method 1 (Altimeter Setting),
so a METAR's ``Axxxx`` group is a like-for-like comparison with what the
console displays — no temperature term, no station-pressure conversion.
That equivalence is the whole reason this module exists, and it is why the
reference source has to be METAR specifically rather than a nearby personal
weather station.

Data comes from aviationweather.gov.  Note that only the ``bbox`` query form
returns results; ``radialDistance`` and the ``@ICAO`` syntax both come back
empty.

API docs: https://aviationweather.gov/data/api/
"""

import logging
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

AVIATION_WEATHER_URL = "https://aviationweather.gov/api/data/metar"

REQUEST_TIMEOUT = 15.0

# Short by the standards of this codebase's other caches, because the value
# is used to calibrate against *current* pressure: the console back-solves
# its offset from whatever it reads right now, so a stale reference bakes in
# the drift since it was taken.  Five minutes keeps a click-happy user from
# hammering the API without ever showing a materially staler number than a
# fresh request would return (routine METARs are hourly).
CACHE_TTL_SECONDS = 5 * 60

DEFAULT_RADIUS_MILES = 60
DEFAULT_LIMIT = 5

# The altimeter setting, in hundredths of an inch of mercury: "A3001".
#
# Parsed from the raw report rather than read from the JSON `altim` field,
# which is hPa to one decimal and does not round-trip.  Measured on live
# data: KMEB A3001 -> 30010 thousandths, but altim 1016.3 -> 30011; KOAJ
# A3002 -> 30020 vs altim 1016.7 -> 30023.  Three thousandths of an inch is
# ~0.1 hPa — below the console's noise floor, but a gratuitous disagreement
# in a tool whose entire purpose is agreement, and it would make the
# conversion factor pinned in test_barometer_calibration.py a lie about the
# path the data actually takes.
_ALTIMETER_RE = re.compile(r"\bA(\d{4})\b")

_CARDINALS = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
)

EARTH_RADIUS_MILES = 3958.8


@dataclass
class MetarReference:
    """One nearby airport observation, usable as a calibration reference."""

    station_id: str
    station_name: str
    distance_miles: float
    bearing_cardinal: str
    observed_at: str                    # ISO 8601 UTC
    altimeter_thousandths_inhg: int     # what BAR= wants
    altimeter_inhg: float               # for display
    raw_metar: str
    report_type: str                    # "METAR" or "SPECI"


@dataclass
class _CacheEntry:
    references: list[MetarReference]
    expires_at: float


_cache: dict[tuple[float, float, int], _CacheEntry] = {}


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return EARTH_RADIUS_MILES * 2 * math.asin(math.sqrt(a))


def _bearing_cardinal(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    deg = (math.degrees(math.atan2(y, x)) + 360) % 360
    return _CARDINALS[round(deg / 22.5) % 16]


def parse_altimeter_thousandths(raw_metar: str) -> Optional[int]:
    """Thousandths of an inch of mercury from a raw METAR, or None.

    Returns None rather than a default when the report carries no altimeter
    group: an unpopulated reference is a station to drop, and a plausible
    wrong number is worse here than no number.
    """
    if not raw_metar:
        return None
    match = _ALTIMETER_RE.search(raw_metar)
    if match is None:
        return None
    return int(match.group(1)) * 10


def _to_reference(obs: dict[str, Any], lat: float, lon: float) -> Optional[MetarReference]:
    raw = obs.get("rawOb") or ""
    thousandths = parse_altimeter_thousandths(raw)
    if thousandths is None:
        return None

    try:
        obs_lat = float(obs["lat"])
        obs_lon = float(obs["lon"])
        obs_time = int(obs["obsTime"])
    except (KeyError, TypeError, ValueError):
        return None

    return MetarReference(
        station_id=str(obs.get("icaoId") or "").strip(),
        station_name=str(obs.get("name") or "").strip(),
        distance_miles=round(_haversine_miles(lat, lon, obs_lat, obs_lon), 1),
        bearing_cardinal=_bearing_cardinal(lat, lon, obs_lat, obs_lon),
        observed_at=datetime.fromtimestamp(obs_time, tz=timezone.utc).isoformat(),
        altimeter_thousandths_inhg=thousandths,
        altimeter_inhg=round(thousandths / 1000, 3),
        raw_metar=raw.strip(),
        report_type=str(obs.get("metarType") or "METAR").strip(),
    )


def _newest_per_station(
    observations: list[dict[str, Any]],
    lat: float,
    lon: float,
) -> list[MetarReference]:
    """Reduce many observations per airport to the newest usable one.

    The feed returns every report in the requested window — typically three
    to five per station — so without this the caller sees the same airport
    repeatedly at different ages.
    """
    best: dict[str, tuple[int, MetarReference]] = {}
    for obs in observations:
        ref = _to_reference(obs, lat, lon)
        if ref is None or not ref.station_id:
            continue
        obs_time = int(obs["obsTime"])
        current = best.get(ref.station_id)
        if current is None or obs_time > current[0]:
            best[ref.station_id] = (obs_time, ref)
    return [ref for _, ref in best.values()]


def _bounding_box(
    lat: float, lon: float, radius_miles: int
) -> tuple[float, float, float, float]:
    lat_span = radius_miles / 69.0
    # A degree of longitude shrinks with latitude; without the cosine the box
    # is too narrow east-west at this latitude and drops reachable airports.
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    lon_span = lat_span / cos_lat
    return (lat - lat_span, lon - lon_span, lat + lat_span, lon + lon_span)


async def fetch_metar_references(
    lat: float,
    lon: float,
    radius_miles: int = DEFAULT_RADIUS_MILES,
    limit: int = DEFAULT_LIMIT,
) -> list[MetarReference]:
    """Nearby METAR observations, nearest first.

    Returns an empty list on any fetch or parse failure — a calibration
    reference is optional context, and the panel that consumes this must
    render its "no reference available" state rather than break.
    """
    key = (round(lat, 3), round(lon, 3), radius_miles)
    entry = _cache.get(key)
    if entry is not None and time.time() < entry.expires_at:
        return entry.references[:limit]

    lat0, lon0, lat1, lon1 = _bounding_box(lat, lon, radius_miles)
    params = {
        "bbox": f"{lat0:.4f},{lon0:.4f},{lat1:.4f},{lon1:.4f}",
        "format": "json",
        "hours": 2,
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(AVIATION_WEATHER_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
        logger.warning("METAR reference fetch failed: %s", exc)
        return []

    if not isinstance(payload, list):
        logger.warning("METAR reference: unexpected payload type %s", type(payload))
        return []

    references = _newest_per_station(payload, lat, lon)
    references = [r for r in references if r.distance_miles <= radius_miles]
    references.sort(key=lambda r: r.distance_miles)

    _cache[key] = _CacheEntry(
        references=references,
        expires_at=time.time() + CACHE_TTL_SECONDS,
    )
    return references[:limit]
