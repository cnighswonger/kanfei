"""NWS Active Alerts client.

Fetches active watches, warnings, and advisories from the NWS API for a
given location.  Results are cached for 2 minutes — alerts are time-critical
during severe weather.

NWS API docs: https://www.weather.gov/documentation/services-web-api
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Reuse the same NWS identity and base URL as forecast_nws.py.
NWS_USER_AGENT = "(kanfei, github.com/cnighswonger/kanfei)"
NWS_BASE_URL = "https://api.weather.gov"
REQUEST_TIMEOUT = 15.0

# Short cache — alerts change rapidly during severe weather.
CACHE_TTL_SECONDS = 120  # 2 minutes

# Severity sort order (most severe first).
SEVERITY_ORDER = {
    "Extreme": 0,
    "Severe": 1,
    "Moderate": 2,
    "Minor": 3,
    "Unknown": 4,
}


@dataclass
class NWSAlert:
    """A single active NWS alert (watch, warning, or advisory)."""
    event: str          # "Tornado Warning", "Severe Thunderstorm Watch", etc.
    severity: str       # "Extreme", "Severe", "Moderate", "Minor", "Unknown"
    certainty: str      # "Observed", "Likely", "Possible", "Unlikely"
    urgency: str        # "Immediate", "Expected", "Future", "Past"
    headline: str
    description: str
    instruction: str    # Recommended action
    onset: str          # ISO datetime
    expires: str        # ISO datetime
    sender_name: str    # Issuing NWS office
    alert_id: str       # Unique ID for change detection
    message_type: str   # "Alert", "Update", "Cancel"
    response: str       # "Shelter", "Evacuate", "Monitor", etc.


@dataclass
class NWSActiveAlerts:
    """All currently active alerts for a location."""
    alerts: list[NWSAlert]
    fetched_at: float
    count: int


# --- Cache ---

@dataclass
class _CacheEntry:
    data: NWSActiveAlerts
    expires_at: float

_cache: dict[tuple[float, float], _CacheEntry] = {}


def _cache_key(lat: float, lon: float) -> tuple[float, float]:
    return (round(lat, 4), round(lon, 4))


def _get_cached(lat: float, lon: float) -> Optional[NWSActiveAlerts]:
    key = _cache_key(lat, lon)
    entry = _cache.get(key)
    if entry is not None and time.time() < entry.expires_at:
        return entry.data
    return None


def _set_cached(lat: float, lon: float, data: NWSActiveAlerts) -> None:
    key = _cache_key(lat, lon)
    _cache[key] = _CacheEntry(data=data, expires_at=time.time() + CACHE_TTL_SECONDS)


# --- Fetch ---

def _parse_alert(feature: dict) -> Optional[NWSAlert]:
    """Parse a single GeoJSON feature into an NWSAlert."""
    props = feature.get("properties", {})
    event = props.get("event")
    if not event:
        return None

    return NWSAlert(
        event=event,
        severity=props.get("severity", "Unknown"),
        certainty=props.get("certainty", "Unknown"),
        urgency=props.get("urgency", "Unknown"),
        headline=props.get("headline", ""),
        description=props.get("description", ""),
        instruction=props.get("instruction") or "",
        onset=props.get("onset", ""),
        expires=props.get("expires", ""),
        sender_name=props.get("senderName", ""),
        alert_id=props.get("id", ""),
        message_type=props.get("messageType", "Alert"),
        response=props.get("response", "None"),
    )


async def fetch_nws_active_alerts(
    lat: float,
    lon: float,
) -> Optional[NWSActiveAlerts]:
    """Fetch active NWS alerts for a location.

    Uses the ``point`` query parameter to filter alerts to the exact
    coordinates.  Returns None on network/API failure — never raises.
    """
    cached = _get_cached(lat, lon)
    if cached is not None:
        return cached

    lat = round(lat, 4)
    lon = round(lon, 4)
    url = f"{NWS_BASE_URL}/alerts/active"

    try:
        async with httpx.AsyncClient(
            headers={
                "User-Agent": NWS_USER_AGENT,
                "Accept": "application/geo+json",
            },
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url, params={"point": f"{lat},{lon}"})
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("NWS alerts fetch failed for (%s, %s): %s", lat, lon, exc)
        return None

    features = data.get("features", [])
    alerts: list[NWSAlert] = []
    for f in features:
        alert = _parse_alert(f)
        if alert:
            alerts.append(alert)

    # Sort by severity (most severe first), then by onset.
    alerts.sort(key=lambda a: (SEVERITY_ORDER.get(a.severity, 4), a.onset))

    result = NWSActiveAlerts(
        alerts=alerts,
        fetched_at=time.time(),
        count=len(alerts),
    )

    _set_cached(lat, lon, result)

    if alerts:
        logger.info(
            "NWS alerts for (%.4f, %.4f): %d active — %s",
            lat, lon, len(alerts),
            ", ".join(a.event for a in alerts),
        )
    else:
        logger.debug("NWS alerts for (%.4f, %.4f): none active", lat, lon)

    return result
