"""Map data API — nearby station observations and alert polygons."""

import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..config import settings
from ..models.database import get_db
from .config import get_effective_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/map", tags=["map"])

# Cache TTL for nearby station data (seconds).
_STATION_CACHE_TTL = 300  # 5 minutes

# IEM currents API — free, no key required.
# Queried per state ASOS network; no working radius parameter.
_IEM_API = "https://mesonet.agron.iastate.edu/api/1/currents.json"

# US state ASOS network codes — we query the home state + neighbors.
_STATE_NETWORKS = {
    "AL": "AL_ASOS", "AK": "AK_ASOS", "AZ": "AZ_ASOS", "AR": "AR_ASOS",
    "CA": "CA_ASOS", "CO": "CO_ASOS", "CT": "CT_ASOS", "DE": "DE_ASOS",
    "FL": "FL_ASOS", "GA": "GA_ASOS", "HI": "HI_ASOS", "ID": "ID_ASOS",
    "IL": "IL_ASOS", "IN": "IN_ASOS", "IA": "IA_ASOS", "KS": "KS_ASOS",
    "KY": "KY_ASOS", "LA": "LA_ASOS", "ME": "ME_ASOS", "MD": "MD_ASOS",
    "MA": "MA_ASOS", "MI": "MI_ASOS", "MN": "MN_ASOS", "MS": "MS_ASOS",
    "MO": "MO_ASOS", "MT": "MT_ASOS", "NE": "NE_ASOS", "NV": "NV_ASOS",
    "NH": "NH_ASOS", "NJ": "NJ_ASOS", "NM": "NM_ASOS", "NY": "NY_ASOS",
    "NC": "NC_ASOS", "ND": "ND_ASOS", "OH": "OH_ASOS", "OK": "OK_ASOS",
    "OR": "OR_ASOS", "PA": "PA_ASOS", "RI": "RI_ASOS", "SC": "SC_ASOS",
    "SD": "SD_ASOS", "TN": "TN_ASOS", "TX": "TX_ASOS", "UT": "UT_ASOS",
    "VT": "VT_ASOS", "VA": "VA_ASOS", "WA": "WA_ASOS", "WV": "WV_ASOS",
    "WI": "WI_ASOS", "WY": "WY_ASOS", "DC": "DC_ASOS",
}

# State adjacency — query neighbors to cover stations near borders.
_STATE_NEIGHBORS: dict[str, list[str]] = {
    "NC": ["SC", "VA", "TN", "GA"],
    "SC": ["NC", "GA"],
    "VA": ["NC", "WV", "KY", "TN", "MD", "DC"],
    "TN": ["NC", "VA", "KY", "GA", "AL", "MS", "AR", "MO"],
    "GA": ["NC", "SC", "TN", "AL", "FL"],
    # Add more as needed — for now cover the southeast
}


def _haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles."""
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * \
        math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _state_from_latlon(lat: float, lon: float) -> str:
    """Rough state lookup by lat/lon for the continental US."""
    # Simple bounding-box heuristic — good enough for network selection
    if 33.8 < lat < 36.6 and -84.3 < lon < -75.5: return "NC"
    if 32.0 < lat < 35.2 and -83.4 < lon < -78.5: return "SC"
    if 36.5 < lat < 39.5 and -83.7 < lon < -75.2: return "VA"
    if 34.9 < lat < 36.7 and -90.3 < lon < -81.6: return "TN"
    if 30.3 < lat < 35.0 and -85.6 < lon < -80.8: return "GA"
    if 24.5 < lat < 31.0 and -87.6 < lon < -80.0: return "FL"
    if 32.3 < lat < 35.0 and -88.5 < lon < -84.9: return "AL"
    # Default: use NC (can be expanded)
    return "NC"


@dataclass
class _StationCache:
    data: dict
    expires_at: float

_station_cache: dict[str, _StationCache] = {}


def _cache_key(lat: float, lon: float, radius: int) -> str:
    return f"{round(lat, 2)}:{round(lon, 2)}:{radius}"


@router.get("/nearby-stations")
async def get_nearby_stations(
    radius_mi: int = Query(default=50, ge=10, le=150),
    db: Session = Depends(get_db),
):
    """Return nearby weather station observations from IEM."""
    cfg = get_effective_config(db)
    lat = float(cfg.get("latitude", 0))
    lon = float(cfg.get("longitude", 0))

    if lat == 0 and lon == 0:
        return {"stations": [], "home_lat": 0, "home_lon": 0,
                "radius_mi": radius_mi, "fetched_at": ""}

    # Check cache
    key = _cache_key(lat, lon, radius_mi)
    cached = _station_cache.get(key)
    if cached and time.time() < cached.expires_at:
        return cached.data

    # Determine which state networks to query (ASOS + COOP for density)
    state = _state_from_latlon(lat, lon)
    states = [state] + _STATE_NEIGHBORS.get(state, [])
    networks = []
    for st in states:
        asos = _STATE_NETWORKS.get(st)
        if asos:
            networks.append(asos)
            # Also add COOP network for the same state
            networks.append(asos.replace("_ASOS", "_COOP"))

    # Fetch from IEM — query each network
    all_raw: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            for network in networks:
                try:
                    resp = await client.get(_IEM_API, params={"network": network})
                    resp.raise_for_status()
                    raw = resp.json()
                    all_raw.extend(raw.get("data", []))
                except Exception:
                    logger.debug("IEM fetch failed for network %s", network)
    except Exception:
        logger.warning("IEM nearby stations fetch failed", exc_info=True)

    # Filter by distance and convert
    stations = []
    for s in all_raw:
        slat = s.get("lat")
        slon = s.get("lon")
        if slat is None or slon is None:
            continue
        dist = _haversine_mi(lat, lon, slat, slon)
        if dist > radius_mi:
            continue

        sknt = s.get("sknt")
        wind_mph = round(sknt * 1.15078) if sknt is not None else None
        gust = s.get("gust")
        gust_mph = round(gust * 1.15078) if gust is not None else None
        alti = s.get("alti")
        pressure_inhg = round(alti, 2) if alti is not None else None
        pressure_hpa = round(alti * 33.8639, 1) if alti is not None else None

        stations.append({
            "id": s.get("station", ""),
            "name": s.get("name", s.get("station", "")),
            "lat": slat,
            "lon": slon,
            "distance_mi": round(dist, 1),
            "source": s.get("network", "ASOS"),
            "temp_f": s.get("tmpf"),
            "wind_mph": wind_mph,
            "wind_dir": s.get("drct"),
            "wind_gust_mph": gust_mph,
            "pressure_hpa": pressure_hpa,
            "pressure_inhg": pressure_inhg,
            "precip_in": s.get("phour"),
            "updated": s.get("local_valid"),
        })

    # Sort by distance
    stations.sort(key=lambda s: s["distance_mi"])

    result = {
        "stations": stations,
        "home_lat": lat,
        "home_lon": lon,
        "radius_mi": radius_mi,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    # Cache the result
    _station_cache[key] = _StationCache(
        data=result,
        expires_at=time.time() + _STATION_CACHE_TTL,
    )

    logger.info("Map: %d stations within %d mi (queried %d networks)",
                len(stations), radius_mi, len(networks))

    return result


@router.get("/alerts")
async def get_map_alerts(db: Session = Depends(get_db)):
    """Return NWS alerts with polygon geometry for map rendering."""
    from ..services.alerts_nws import fetch_nws_active_alerts
    from dataclasses import asdict

    cfg = get_effective_config(db)
    lat = float(cfg.get("latitude", 0))
    lon = float(cfg.get("longitude", 0))

    if lat == 0 and lon == 0:
        return {"alerts": [], "count": 0}

    result = await fetch_nws_active_alerts(lat, lon)
    if result is None:
        return {"alerts": [], "count": 0}

    alerts = [asdict(a) for a in result.alerts]
    return {"alerts": alerts, "count": len(alerts)}
