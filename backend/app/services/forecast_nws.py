"""NWS (National Weather Service) API forecast client.

Fetches grid-based forecasts from the NWS API for a given latitude/longitude.
Results are cached for 2 hours to reduce API traffic and handle intermittent
connectivity gracefully.

NWS API docs: https://www.weather.gov/documentation/services-web-api
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# NWS requires a User-Agent header identifying the application.
NWS_USER_AGENT = "(kanfei, github.com/cnighswonger/kanfei)"

NWS_BASE_URL = "https://api.weather.gov"

# Cache duration in seconds (2 hours).
CACHE_TTL_SECONDS = 2 * 60 * 60

# HTTP timeout for NWS requests (seconds).
REQUEST_TIMEOUT = 15.0


@dataclass
class ForecastPeriod:
    """A single NWS forecast period (e.g., 'Tonight', 'Tuesday')."""
    name: str
    temperature: Optional[int]  # Degrees F
    wind: str  # e.g., "SW 10 to 15 mph"
    precipitation_pct: Optional[int]  # 0-100 or None
    text: str  # Detailed forecast text
    icon_url: Optional[str] = None  # NWS icon URL
    short_forecast: Optional[str] = None  # e.g., "Partly Sunny"
    is_daytime: Optional[bool] = None


@dataclass
class NWSForecast:
    """Full NWS grid forecast containing multiple periods."""
    periods: list[ForecastPeriod]
    office: str
    grid_x: int
    grid_y: int
    fetched_at: float  # Unix timestamp


@dataclass
class _CacheEntry:
    """Internal cache entry for a grid point forecast."""
    forecast: NWSForecast
    expires_at: float


# Module-level cache keyed by (lat, lon) rounded to 4 decimal places.
_cache: dict[tuple[float, float], _CacheEntry] = {}

# Radar station cache — effectively resolves once per location.
_radar_station_cache: dict[tuple[float, float], str] = {}

# State code cache — resolved from /points relativeLocation.
_state_cache: dict[tuple[float, float], str] = {}


def _cache_key(lat: float, lon: float) -> tuple[float, float]:
    """Produce a stable cache key from coordinates."""
    return (round(lat, 4), round(lon, 4))


def _get_cached(lat: float, lon: float) -> Optional[NWSForecast]:
    """Return cached forecast if still valid, else None."""
    key = _cache_key(lat, lon)
    entry = _cache.get(key)
    if entry is not None and time.time() < entry.expires_at:
        logger.debug("NWS cache hit for (%s, %s)", lat, lon)
        return entry.forecast
    return None


def _set_cached(lat: float, lon: float, forecast: NWSForecast) -> None:
    """Store a forecast in the cache."""
    key = _cache_key(lat, lon)
    _cache[key] = _CacheEntry(
        forecast=forecast,
        expires_at=time.time() + CACHE_TTL_SECONDS,
    )


async def _resolve_grid_point(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
) -> Optional[tuple[str, int, int]]:
    """Resolve latitude/longitude to an NWS grid point.

    Calls the /points/{lat},{lon} endpoint to discover the forecast
    office and grid coordinates.

    Args:
        client: httpx async client with headers pre-configured.
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.

    Returns:
        Tuple of (office_id, gridX, gridY) or None on failure.
    """
    url = f"{NWS_BASE_URL}/points/{lat},{lon}"
    try:
        resp = await client.get(url)
        resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("NWS points lookup failed for (%s, %s): %s", lat, lon, exc)
        return None

    data = resp.json()
    props = data.get("properties", {})
    office = props.get("gridId")
    grid_x = props.get("gridX")
    grid_y = props.get("gridY")

    if office is None or grid_x is None or grid_y is None:
        logger.warning("NWS points response missing grid data for (%s, %s)", lat, lon)
        return None

    # Cache ancillary data from the /points response.
    key = _cache_key(lat, lon)
    radar_station = props.get("radarStation", "")
    if radar_station:
        _radar_station_cache[key] = radar_station
        logger.debug("Radar station for (%s, %s): %s", lat, lon, radar_station)

    # Cache the state code (used by nearby_stations for IEM network lookup).
    try:
        state = props["relativeLocation"]["properties"]["state"]
        if state:
            _state_cache[key] = state
    except (KeyError, TypeError):
        pass

    return (office, int(grid_x), int(grid_y))


async def _fetch_grid_forecast(
    client: httpx.AsyncClient,
    office: str,
    grid_x: int,
    grid_y: int,
) -> Optional[list[ForecastPeriod]]:
    """Fetch the textual forecast for a given NWS grid point.

    Args:
        client: httpx async client with headers pre-configured.
        office: NWS office identifier (e.g., "OKX").
        grid_x: Grid X coordinate.
        grid_y: Grid Y coordinate.

    Returns:
        List of ForecastPeriod objects, or None on failure.
    """
    url = f"{NWS_BASE_URL}/gridpoints/{office}/{grid_x},{grid_y}/forecast"
    try:
        resp = await client.get(url)
        resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning(
            "NWS forecast fetch failed for %s/%s,%s: %s",
            office, grid_x, grid_y, exc,
        )
        return None

    data = resp.json()
    raw_periods = data.get("properties", {}).get("periods", [])

    periods: list[ForecastPeriod] = []
    for p in raw_periods:
        # Extract precipitation probability from detailedForecast or
        # the probabilityOfPrecipitation field if available.
        precip_pct: Optional[int] = None
        precip_data = p.get("probabilityOfPrecipitation")
        if isinstance(precip_data, dict):
            precip_pct = precip_data.get("value")
        if precip_pct is not None:
            precip_pct = int(precip_pct)

        wind_text = f"{p.get('windDirection', '')} {p.get('windSpeed', '')}".strip()

        periods.append(ForecastPeriod(
            name=p.get("name", "Unknown"),
            temperature=p.get("temperature"),
            wind=wind_text,
            precipitation_pct=precip_pct,
            text=p.get("detailedForecast", ""),
            icon_url=p.get("icon"),
            short_forecast=p.get("shortForecast"),
            is_daytime=p.get("isDaytime"),
        ))

    return periods


async def fetch_nws_forecast(
    lat: float,
    lon: float,
) -> Optional[NWSForecast]:
    """Fetch NWS forecast for a location, with caching and graceful degradation.

    This is the main entry point for NWS forecast retrieval. It:
    1. Checks the cache (2-hour TTL).
    2. Resolves the NWS grid point from lat/lon.
    3. Fetches the grid forecast.
    4. Caches and returns the result.

    If the NWS API is unreachable or returns errors, this returns None
    rather than raising an exception, allowing the caller to fall back
    to local-only forecasting.

    Args:
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.

    Returns:
        NWSForecast with periods, or None if unavailable.
    """
    # Check cache first
    cached = _get_cached(lat, lon)
    if cached is not None:
        return cached

    headers = {
        "User-Agent": NWS_USER_AGENT,
        "Accept": "application/geo+json",
    }

    # Round to 4 decimal places (NWS redirects to this precision anyway)
    lat = round(lat, 4)
    lon = round(lon, 4)

    async with httpx.AsyncClient(
        headers=headers,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    ) as client:
        # Step 1: Resolve grid point
        grid = await _resolve_grid_point(client, lat, lon)
        if grid is None:
            return None

        office, grid_x, grid_y = grid

        # Step 2: Fetch forecast periods
        periods = await _fetch_grid_forecast(client, office, grid_x, grid_y)
        if periods is None:
            return None

    forecast = NWSForecast(
        periods=periods,
        office=office,
        grid_x=grid_x,
        grid_y=grid_y,
        fetched_at=time.time(),
    )

    _set_cached(lat, lon, forecast)
    logger.info(
        "NWS forecast fetched for (%s, %s) via %s/%s,%s: %d periods",
        lat, lon, office, grid_x, grid_y, len(periods),
    )

    return forecast


async def _ensure_points_resolved(lat: float, lon: float) -> None:
    """Ensure the /points API has been called for this location.

    All ancillary caches (radar station, state code) are populated as a
    side effect of ``_resolve_grid_point``.  This is a no-op if the data
    is already cached.
    """
    key = _cache_key(lat, lon)
    if key in _radar_station_cache or key in _state_cache:
        return  # Already resolved

    headers = {
        "User-Agent": NWS_USER_AGENT,
        "Accept": "application/geo+json",
    }
    lat = round(lat, 4)
    lon = round(lon, 4)

    async with httpx.AsyncClient(
        headers=headers,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    ) as client:
        await _resolve_grid_point(client, lat, lon)


async def resolve_radar_station(lat: float, lon: float) -> Optional[str]:
    """Return the nearest NEXRAD radar station ID for a location.

    Checks the in-memory cache first.  If not cached, makes a single
    /points call to discover the station (same call used for grid point
    resolution, so the result gets cached for both purposes).

    Returns a 4-character station ID (e.g. "KRAX") or None.
    """
    key = _cache_key(lat, lon)
    cached = _radar_station_cache.get(key)
    if cached:
        return cached

    await _ensure_points_resolved(lat, lon)
    return _radar_station_cache.get(key)


async def resolve_state(lat: float, lon: float) -> Optional[str]:
    """Return the 2-letter US state code for a location.

    Uses the same NWS /points cache as radar station resolution —
    no extra API call when the forecast has already been fetched.
    """
    key = _cache_key(lat, lon)
    cached = _state_cache.get(key)
    if cached:
        return cached

    await _ensure_points_resolved(lat, lon)
    return _state_cache.get(key)
