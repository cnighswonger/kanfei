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


async def _fetch_via_nowcast(
    lat: float, lon: float, radius_mi: int, cfg: dict,
) -> list[dict]:
    """Try kanfei-nowcast nearby_stations for IEM + APRS + WU data."""
    try:
        from kanfei_nowcast.data_feeds.nearby_stations import fetch_nearby_stations
    except ImportError:
        return []

    wu_key = str(cfg.get("nowcast_wu_api_key", ""))
    iem_enabled = cfg.get("nowcast_nearby_iem_enabled", True)
    wu_enabled = cfg.get("nowcast_nearby_wu_enabled", False) and bool(wu_key)
    aprs_enabled = cfg.get("nowcast_nearby_aprs_enabled", False)
    max_iem = int(cfg.get("nowcast_nearby_max_iem", 50))
    max_wu = int(cfg.get("nowcast_nearby_max_wu", 10))
    max_aprs = int(cfg.get("nowcast_nearby_max_aprs", 50))

    try:
        result = await fetch_nearby_stations(
            lat, lon,
            radius_miles=radius_mi,
            max_iem=max_iem,
            max_wu=max_wu,
            wu_api_key=wu_key,
            iem_enabled=iem_enabled,
            wu_enabled=wu_enabled,
            aprs_enabled=aprs_enabled,
            max_aprs=max_aprs,
        )
    except Exception:
        logger.warning("kanfei-nowcast nearby_stations fetch failed", exc_info=True)
        return []

    stations = []
    for obs in result.stations:
        pressure_inhg = obs.pressure_inhg
        pressure_hpa = round(pressure_inhg * 33.8639, 1) if pressure_inhg else None

        stations.append({
            "id": obs.station_id,
            "name": obs.station_name,
            "lat": obs.latitude,
            "lon": obs.longitude,
            "distance_mi": obs.distance_miles,
            "source": obs.source,
            "temp_f": obs.temp_f,
            "wind_mph": round(obs.wind_speed_mph) if obs.wind_speed_mph is not None else None,
            "wind_dir": obs.wind_dir_deg,
            "wind_gust_mph": round(obs.wind_gust_mph) if obs.wind_gust_mph is not None else None,
            "pressure_hpa": pressure_hpa,
            "pressure_inhg": round(pressure_inhg, 2) if pressure_inhg else None,
            "precip_in": obs.precip_in,
            "updated": obs.timestamp,
        })

    logger.info("Map: %d stations via kanfei-nowcast (iem=%d, wu=%d, aprs=%d)",
                len(stations), result.iem_count, result.wu_count, result.aprs_count)
    return stations


async def _fetch_via_iem_direct(
    lat: float, lon: float, radius_mi: int,
) -> list[dict]:
    """Fallback: query IEM ASOS+COOP directly when kanfei-nowcast is not installed."""
    state = _state_from_latlon(lat, lon)
    states = [state] + _STATE_NEIGHBORS.get(state, [])
    networks = []
    for st in states:
        asos = _STATE_NETWORKS.get(st)
        if asos:
            networks.append(asos)
            networks.append(asos.replace("_ASOS", "_COOP"))

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

    stations.sort(key=lambda s: s["distance_mi"])
    logger.info("Map: %d stations via IEM direct (%d networks)", len(stations), len(networks))
    return stations


@router.get("/nearby-stations")
async def get_nearby_stations(
    radius_mi: int = Query(default=50, ge=10, le=150),
    db: Session = Depends(get_db),
):
    """Return nearby weather station observations.

    Uses kanfei-nowcast (IEM + APRS + WU) if installed, falls back to
    direct IEM ASOS+COOP queries otherwise.
    """
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

    # Try kanfei-nowcast first (has APRS/CWOP + WU + IEM)
    stations = await _fetch_via_nowcast(lat, lon, radius_mi, cfg)
    if not stations:
        # Fallback to direct IEM query + native APRS collector
        stations = await _fetch_via_iem_direct(lat, lon, radius_mi)

    # Merge native APRS map collector observations (if running)
    try:
        from ..services.aprs_map_collector import get_nearby, is_running
        if is_running():
            aprs_obs = get_nearby(lat, lon, radius_mi, max_stations=100)
            existing_ids = {s["id"] for s in stations}
            for obs in aprs_obs:
                if obs.callsign not in existing_ids:
                    pressure_hpa = round(obs.pressure_inhg * 33.8639, 1) if obs.pressure_inhg else None
                    stations.append({
                        "id": obs.callsign,
                        "name": obs.callsign,
                        "lat": obs.latitude,
                        "lon": obs.longitude,
                        "distance_mi": round(_haversine_mi(lat, lon, obs.latitude, obs.longitude), 1),
                        "source": "CWOP",
                        "temp_f": obs.temp_f,
                        "wind_mph": round(obs.wind_speed_mph) if obs.wind_speed_mph is not None else None,
                        "wind_dir": obs.wind_dir_deg,
                        "wind_gust_mph": round(obs.wind_gust_mph) if obs.wind_gust_mph is not None else None,
                        "pressure_hpa": pressure_hpa,
                        "pressure_inhg": obs.pressure_inhg,
                        "precip_in": obs.precip_in,
                        "updated": datetime.fromtimestamp(obs.timestamp, tz=timezone.utc).isoformat(),
                    })
            if aprs_obs:
                stations.sort(key=lambda s: s["distance_mi"])
                logger.info("Map: merged %d APRS/CWOP stations", len(aprs_obs))
    except Exception:
        pass  # Collector not available — no CWOP data

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

    logger.info("Map: %d stations within %d mi", len(stations), radius_mi)

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


# ---------------------------------------------------------------------------
# Isobar contour computation
# ---------------------------------------------------------------------------

def _idw_interpolate(
    points: list[tuple[float, float, float]],  # (lat, lon, pressure_hpa)
    lat: float, lon: float, power: float = 2.0,
) -> float:
    """Inverse distance weighting interpolation."""
    w_sum = 0.0
    v_sum = 0.0
    for plat, plon, pval in points:
        d = math.sqrt((plat - lat) ** 2 + (plon - lon) ** 2)
        if d < 0.001:
            return pval
        w = 1.0 / d ** power
        w_sum += w
        v_sum += w * pval
    return v_sum / w_sum


def _marching_squares(
    grid: list[list[float]], rows: int, cols: int,
    lat_min: float, lat_max: float, lon_min: float, lon_max: float,
    level: float,
) -> list[list[list[float]]]:
    """Extract contour line segments at a given pressure level."""
    segments: list[list[list[float]]] = []
    d_lat = (lat_max - lat_min) / (rows - 1)
    d_lon = (lon_max - lon_min) / (cols - 1)

    for r in range(rows - 1):
        for c in range(cols - 1):
            tl, tr = grid[r][c], grid[r][c + 1]
            bl, br = grid[r + 1][c], grid[r + 1][c + 1]
            lat_t = lat_min + r * d_lat
            lat_b = lat_min + (r + 1) * d_lat
            lon_l = lon_min + c * d_lon
            lon_r = lon_min + (c + 1) * d_lon

            code = ((1 if tl >= level else 0) << 3 |
                    (1 if tr >= level else 0) << 2 |
                    (1 if br >= level else 0) << 1 |
                    (1 if bl >= level else 0))

            if code == 0 or code == 15:
                continue

            def lerp(v1, v2, p1, p2):
                t = (level - v1) / (v2 - v1) if v2 != v1 else 0.5
                return p1 + t * (p2 - p1)

            top = [lat_t, lerp(tl, tr, lon_l, lon_r)]
            right = [lerp(tr, br, lat_t, lat_b), lon_r]
            bottom = [lat_b, lerp(bl, br, lon_l, lon_r)]
            left = [lerp(tl, bl, lat_t, lat_b), lon_l]

            cases = {
                1: [[left, bottom]], 2: [[bottom, right]], 3: [[left, right]],
                4: [[top, right]], 5: [[top, right], [left, bottom]],
                6: [[top, bottom]], 7: [[top, left]], 8: [[top, left]],
                9: [[top, bottom]], 10: [[top, left], [bottom, right]],
                11: [[top, right]], 12: [[left, right]],
                13: [[bottom, right]], 14: [[left, bottom]],
            }
            segs = cases.get(code)
            if segs:
                segments.extend(segs)

    return segments


_isobar_cache: dict[str, _StationCache] = {}
_ISOBAR_CACHE_TTL = 300  # 5 minutes


@router.get("/isobars")
async def get_isobars(db: Session = Depends(get_db)):
    """Compute isobar contour lines from nearby station pressure data.

    Returns GeoJSON-style line segments at standard pressure intervals.
    Server-side computation, cached for 5 minutes.
    """
    cfg = get_effective_config(db)
    lat = float(cfg.get("latitude", 0))
    lon = float(cfg.get("longitude", 0))

    if lat == 0 and lon == 0:
        return {"contours": [], "interval_hpa": 4}

    # Check cache
    cache_key = f"iso:{round(lat, 2)}:{round(lon, 2)}"
    cached = _isobar_cache.get(cache_key)
    if cached and time.time() < cached.expires_at:
        return cached.data

    # Get station data from the existing cached nearby-stations.
    # Try common radii (frontend default is 50) — use whichever cache hit exists.
    station_cache = None
    for r in (50, 75, 100):
        sc = _station_cache.get(_cache_key(lat, lon, r))
        if sc and time.time() < sc.expires_at:
            station_cache = sc
            break
    if not station_cache:
        return {"contours": [], "interval_hpa": 4}

    stations = station_cache.data.get("stations", [])

    # Collect pressure points
    pressure_points: list[tuple[float, float, float]] = []
    for s in stations:
        p = s.get("pressure_hpa")
        if p is not None and s.get("lat") is not None:
            pressure_points.append((s["lat"], s["lon"], p))

    # Add home station barometer if available
    try:
        from ..models.database import SessionLocal
        from ..models.sensor_reading import SensorReadingModel
        from ..models.sensor_meta import convert
        _db = SessionLocal()
        row = _db.query(SensorReadingModel.barometer).order_by(
            SensorReadingModel.timestamp.desc()
        ).first()
        _db.close()
        if row and row[0] is not None:
            baro_display = convert("barometer", row[0])  # inHg
            if baro_display:
                baro_hpa = baro_display * 33.8639
                pressure_points.append((lat, lon, baro_hpa))
    except Exception:
        pass

    if len(pressure_points) < 5:
        return {"contours": [], "interval_hpa": 4}

    # Build interpolation grid
    GRID = 30
    pad = 1.2
    lat_min, lat_max = lat - pad, lat + pad
    lon_min, lon_max = lon - pad * 1.3, lon + pad * 1.3

    grid: list[list[float]] = []
    for r in range(GRID):
        row: list[float] = []
        g_lat = lat_min + (r / (GRID - 1)) * (lat_max - lat_min)
        for c in range(GRID):
            g_lon = lon_min + (c / (GRID - 1)) * (lon_max - lon_min)
            row.append(_idw_interpolate(pressure_points, g_lat, g_lon))
        grid.append(row)

    # Extract contours at 4 hPa intervals
    all_p = [p for _, _, p in pressure_points]
    start_level = math.floor(min(all_p) / 4) * 4
    end_level = math.ceil(max(all_p) / 4) * 4

    contours = []
    for level in range(start_level, end_level + 1, 4):
        segments = _marching_squares(
            grid, GRID, GRID, lat_min, lat_max, lon_min, lon_max, float(level),
        )
        if segments:
            contours.append({
                "level": level,
                "label": str(level),
                "segments": segments,
            })

    result = {
        "contours": contours,
        "interval_hpa": 4,
        "station_count": len(pressure_points),
    }

    _isobar_cache[cache_key] = _StationCache(
        data=result,
        expires_at=time.time() + _ISOBAR_CACHE_TTL,
    )

    logger.info("Map: computed %d isobar contours from %d pressure points",
                len(contours), len(pressure_points))

    return result
