"""Map data API — nearby station observations and alert polygons."""

import logging
import time
from dataclasses import dataclass
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
_IEM_API = "https://mesonet.agron.iastate.edu/api/1/currents.json"


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

    # Fetch from IEM
    stations = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(_IEM_API, params={
                "lat": lat,
                "lon": lon,
                "radius": radius_mi,
            })
            resp.raise_for_status()
            raw = resp.json()

        for s in raw.get("data", []):
            # Convert IEM fields to our format
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
                "lat": s.get("lat"),
                "lon": s.get("lon"),
                "distance_mi": s.get("distance_mi"),
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

    except Exception:
        logger.warning("IEM nearby stations fetch failed", exc_info=True)

    from datetime import datetime, timezone
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
