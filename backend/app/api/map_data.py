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
# At 250mi radius, NC reaches into WV, KY, MD, and deep into GA/TN.
_STATE_NEIGHBORS: dict[str, list[str]] = {
    "NC": ["SC", "VA", "TN", "GA", "WV", "KY", "MD", "DC"],
    "SC": ["NC", "GA", "VA"],
    "VA": ["NC", "WV", "KY", "TN", "MD", "DC", "PA"],
    "TN": ["NC", "VA", "KY", "GA", "AL", "MS", "AR", "MO"],
    "GA": ["NC", "SC", "TN", "AL", "FL"],
    "WV": ["VA", "KY", "OH", "PA", "MD"],
    "KY": ["TN", "VA", "WV", "OH", "IN", "IL", "MO"],
    "MD": ["VA", "WV", "PA", "DC", "DE"],
    "AL": ["TN", "GA", "MS", "FL"],
    "FL": ["GA", "AL"],
    "MS": ["TN", "AL", "AR", "LA"],
    "PA": ["MD", "WV", "VA", "OH", "NY", "NJ", "DE"],
    "OH": ["KY", "WV", "PA", "IN", "MI"],
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


def _thin_stations(
    stations: list[dict], lat: float, lon: float, max_stations: int,
) -> list[dict]:
    """Spatially thin stations to an evenly-distributed subset.

    Divides the area into a grid and picks the best station per cell
    (most complete data, then nearest). Produces a Windy-style
    representative view at lower zoom levels.
    """
    if len(stations) <= max_stations:
        return stations

    grid_size = math.ceil(math.sqrt(max_stations))

    lats = [s["lat"] for s in stations if s.get("lat") is not None]
    lons = [s["lon"] for s in stations if s.get("lon") is not None]
    if not lats or not lons:
        return stations[:max_stations]

    lat_min, lat_max = min(lats), max(lats)
    lon_min, lon_max = min(lons), max(lons)
    # Avoid zero-range edge cases
    lat_range = max(lat_max - lat_min, 0.01)
    lon_range = max(lon_max - lon_min, 0.01)

    def _completeness(s: dict) -> int:
        """Count non-null data fields — prefer stations with more readings."""
        return sum(1 for k in ("temp_f", "wind_mph", "pressure_hpa", "precip_in")
                   if s.get(k) is not None)

    # Bin stations into grid cells
    cells: dict[tuple[int, int], list[dict]] = {}
    for s in stations:
        if s.get("lat") is None or s.get("lon") is None:
            continue
        r = min(int((s["lat"] - lat_min) / lat_range * grid_size), grid_size - 1)
        c = min(int((s["lon"] - lon_min) / lon_range * grid_size), grid_size - 1)
        cells.setdefault((r, c), []).append(s)

    # Pick best station per cell
    thinned: list[dict] = []
    for cell_stations in cells.values():
        best = max(cell_stations, key=lambda s: (
            _completeness(s),
            -(s.get("distance_mi") or 9999),
        ))
        thinned.append(best)

    thinned.sort(key=lambda s: s.get("distance_mi") or 9999)
    return thinned[:max_stations]


@router.get("/nearby-stations")
async def get_nearby_stations(
    radius_mi: int = Query(default=50, ge=10, le=500),
    max_stations: int = Query(default=100, ge=10, le=500),
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

    # Check cache — keyed by radius only (all stations cached, thinned at response time)
    key = _cache_key(lat, lon, radius_mi)
    cached = _station_cache.get(key)
    if cached and time.time() < cached.expires_at:
        all_stations = cached.data["stations"]
        thinned = _thin_stations(all_stations, lat, lon, max_stations)
        return {**cached.data, "stations": thinned, "total_stations": len(all_stations)}

    # Try kanfei-nowcast first (has APRS/CWOP + WU + IEM)
    stations = await _fetch_via_nowcast(lat, lon, radius_mi, cfg)
    if not stations:
        # Fallback to direct IEM query + native APRS collector
        stations = await _fetch_via_iem_direct(lat, lon, radius_mi)

    # Merge native APRS map collector observations (if running)
    try:
        from ..services.aprs_map_collector import get_nearby, is_running
        if is_running():
            aprs_obs = get_nearby(lat, lon, radius_mi, max_stations=500)
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

    # Cache ALL stations (isobars need the full set); thin at response time
    result = {
        "stations": stations,
        "home_lat": lat,
        "home_lon": lon,
        "radius_mi": radius_mi,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    _station_cache[key] = _StationCache(
        data=result,
        expires_at=time.time() + _STATION_CACHE_TTL,
    )

    logger.info("Map: %d stations within %d mi", len(stations), radius_mi)

    thinned = _thin_stations(stations, lat, lon, max_stations)

    return {**result, "stations": thinned, "total_stations": len(stations)}


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
_PGRID_CACHE_TTL = 300  # 5 minutes
_pgrid_cache: dict[str, _StationCache] = {}


def _get_best_station_cache(
    lat: float, lon: float,
) -> Optional[_StationCache]:
    """Return the station cache entry with the most stations, or None."""
    lat_lon_prefix = f"{round(lat, 2)}:{round(lon, 2)}:"
    best_cache = None
    best_count = 0
    for cache_key_k, sc in _station_cache.items():
        if cache_key_k.startswith(lat_lon_prefix) and time.time() < sc.expires_at:
            count = len(sc.data.get("stations", []))
            if count > best_count:
                best_cache = sc
                best_count = count
    return best_cache


async def _ensure_station_cache(
    db: Session, lat: float, lon: float,
) -> Optional[_StationCache]:
    """Return best station cache, fetching stations if cache is empty."""
    cached = _get_best_station_cache(lat, lon)
    if cached:
        return cached

    # Self-seed: fetch stations at a wide radius so the grid has coverage
    cfg = get_effective_config(db)
    radius = int(cfg.get("map_max_radius", 450))
    stations = await _fetch_via_nowcast(lat, lon, radius, cfg)
    if not stations:
        stations = await _fetch_via_iem_direct(lat, lon, radius)

    # Merge native APRS map collector observations (same as get_nearby_stations)
    try:
        from ..services.aprs_map_collector import get_nearby, is_running
        if is_running():
            aprs_obs = get_nearby(lat, lon, radius, max_stations=500)
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
                stations.sort(key=lambda s: s.get("distance_mi") or 9999)
                logger.info("Map: merged %d APRS/CWOP stations into pressure grid seed", len(aprs_obs))
    except Exception:
        pass

    if not stations:
        return None

    result = {
        "stations": stations,
        "home_lat": lat,
        "home_lon": lon,
        "radius_mi": radius,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    key = _cache_key(lat, lon, radius)
    _station_cache[key] = _StationCache(
        data=result,
        expires_at=time.time() + _STATION_CACHE_TTL,
    )
    logger.info("Map: self-seeded station cache with %d stations", len(stations))
    return _station_cache[key]


def _collect_pressure_points(
    stations: list[dict], db: Session, lat: float, lon: float,
) -> list[tuple[float, float, float]]:
    """Collect pressure points from station list + home barometer."""
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

    return pressure_points


def _filter_pressure_outliers(
    points: list[tuple[float, float, float]],
    max_sigma: float = 2.5,
) -> list[tuple[float, float, float]]:
    """Remove pressure readings that are statistical outliers.

    Stations at elevation sometimes report uncorrected station pressure
    (vs sea-level altimeter setting), producing values far outside the
    normal range.  Remove anything beyond max_sigma standard deviations.
    """
    if len(points) < 5:
        return points
    pressures = [p[2] for p in points]
    mean = sum(pressures) / len(pressures)
    variance = sum((p - mean) ** 2 for p in pressures) / len(pressures)
    std = variance ** 0.5
    if std < 0.1:
        return points  # all nearly identical — nothing to filter
    filtered = [p for p in points if abs(p[2] - mean) <= max_sigma * std]
    removed = len(points) - len(filtered)
    if removed:
        logger.info("Map: filtered %d pressure outliers (mean=%.1f, std=%.2f)",
                    removed, mean, std)
    return filtered


def _build_idw_grid(
    pressure_points: list[tuple[float, float, float]],
    grid_size: int,
    margin: float = 0.2,
    power: float = 2.0,
    smooth_sigma: float = 0.0,
) -> tuple[list[list[float]], float, float, float, float]:
    """Build IDW-interpolated pressure grid from station points.

    Args:
        power: IDW exponent (lower = smoother, default 2.0 for isobars).
        smooth_sigma: If > 0, apply Gaussian blur with this sigma (grid cells).

    Returns (grid, lat_min, lat_max, lon_min, lon_max).
    """
    all_lats = [p[0] for p in pressure_points]
    all_lons = [p[1] for p in pressure_points]
    lat_min = min(all_lats) - margin
    lat_max = max(all_lats) + margin
    lon_min = min(all_lons) - margin
    lon_max = max(all_lons) + margin

    grid: list[list[float]] = []
    for r in range(grid_size):
        row: list[float] = []
        g_lat = lat_min + (r / (grid_size - 1)) * (lat_max - lat_min)
        for c in range(grid_size):
            g_lon = lon_min + (c / (grid_size - 1)) * (lon_max - lon_min)
            row.append(_idw_interpolate(pressure_points, g_lat, g_lon, power=power))
        grid.append(row)

    if smooth_sigma > 0:
        try:
            import numpy as np
            from scipy.ndimage import gaussian_filter
            arr = gaussian_filter(np.array(grid, dtype=np.float64), sigma=smooth_sigma)
            grid = arr.tolist()
        except ImportError:
            pass  # scipy not available — skip smoothing

    return grid, lat_min, lat_max, lon_min, lon_max


def _build_smooth_grid(
    pressure_points: list[tuple[float, float, float]],
    grid_size: int,
    margin: float = 0.2,
    blur_sigma: float = 2.0,
) -> tuple[list[list[float]], float, float, float, float]:
    """Build smooth pressure grid using cubic Clough-Tocher interpolation.

    Uses scipy.interpolate.griddata with method='cubic' — a local C1
    interpolation based on Delaunay triangulation.  No global oscillations
    (unlike thin-plate spline RBF).  Areas outside the convex hull of
    data points are filled with nearest-neighbor values.

    A light Gaussian blur is applied for extra smoothness.
    Falls back to IDW if scipy is unavailable.
    """
    import numpy as np
    all_lats = [p[0] for p in pressure_points]
    all_lons = [p[1] for p in pressure_points]
    lat_min = min(all_lats) - margin
    lat_max = max(all_lats) + margin
    lon_min = min(all_lons) - margin
    lon_max = max(all_lons) + margin

    try:
        from scipy.interpolate import griddata
        from scipy.ndimage import gaussian_filter

        coords = np.array([[p[0], p[1]] for p in pressure_points])
        values = np.array([p[2] for p in pressure_points])

        # Build evaluation grid
        lat_vals = np.linspace(lat_min, lat_max, grid_size)
        lon_vals = np.linspace(lon_min, lon_max, grid_size)
        mesh_lat, mesh_lon = np.meshgrid(lat_vals, lon_vals, indexing="ij")
        grid_points = np.column_stack([mesh_lat.ravel(), mesh_lon.ravel()])

        # Cubic interpolation — smooth C1 surface within convex hull
        arr = griddata(coords, values, grid_points, method="cubic")

        # Fill NaN (outside convex hull) with nearest-neighbor
        nan_mask = np.isnan(arr)
        if nan_mask.any():
            nearest = griddata(coords, values, grid_points, method="nearest")
            arr[nan_mask] = nearest[nan_mask]

        arr = arr.reshape(grid_size, grid_size)

        if blur_sigma > 0:
            arr = gaussian_filter(arr, sigma=blur_sigma)

        grid = arr.tolist()

    except ImportError:
        logger.warning("scipy not available — falling back to IDW for pressure grid")
        grid = []
        for r in range(grid_size):
            row = []
            g_lat = lat_min + (r / (grid_size - 1)) * (lat_max - lat_min)
            for c in range(grid_size):
                g_lon = lon_min + (c / (grid_size - 1)) * (lon_max - lon_min)
                row.append(_idw_interpolate(pressure_points, g_lat, g_lon, power=1.5))
            grid.append(row)

    return grid, lat_min, lat_max, lon_min, lon_max


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

    best = _get_best_station_cache(lat, lon)
    if not best:
        return {"contours": [], "interval_hpa": 1}
    stations = best.data.get("stations", [])
    pressure_points = _collect_pressure_points(stations, db, lat, lon)
    if not pressure_points:
        return {"contours": [], "interval_hpa": 1}

    # Check isobar cache — keyed by station count so it invalidates on zoom change
    cache_key = f"iso:{round(lat, 2)}:{round(lon, 2)}:{len(pressure_points)}"
    cached = _isobar_cache.get(cache_key)
    if cached and time.time() < cached.expires_at:
        return cached.data

    if len(pressure_points) < 5:
        return {"contours": [], "interval_hpa": 4}

    GRID = min(80, max(40, len(pressure_points) * 2))
    grid, lat_min, lat_max, lon_min, lon_max = _build_idw_grid(
        pressure_points, GRID,
    )

    # Extract contours at configurable hPa intervals
    INTERVAL = int(cfg.get("map_isobar_interval", 1))
    all_p = [p for _, _, p in pressure_points]
    start_level = math.floor(min(all_p) / INTERVAL) * INTERVAL
    end_level = math.ceil(max(all_p) / INTERVAL) * INTERVAL

    pressure_unit = cfg.get("pressure_unit", "inHg")

    contours = []
    for level in range(start_level, end_level + 1, INTERVAL):
        segments = _marching_squares(
            grid, GRID, GRID, lat_min, lat_max, lon_min, lon_max, float(level),
        )
        if segments:
            if pressure_unit == "inHg":
                label = f"{level / 33.8639:.2f}"
            else:
                label = str(level)
            contours.append({
                "level": level,
                "label": label,
                "segments": segments,
            })

    result = {
        "contours": contours,
        "pressure_unit": pressure_unit,
        "interval_hpa": INTERVAL,
        "station_count": len(pressure_points),
    }

    _isobar_cache[cache_key] = _StationCache(
        data=result,
        expires_at=time.time() + _ISOBAR_CACHE_TTL,
    )

    logger.info("Map: computed %d isobar contours from %d pressure points",
                len(contours), len(pressure_points))

    return result


@router.get("/pressure-grid")
async def get_pressure_grid(db: Session = Depends(get_db)):
    """Return high-resolution IDW pressure grid for 3D visualization.

    Cached for 5 minutes.  Grid is 120x120 interpolated from the best
    available nearby-station cache.
    """
    cfg = get_effective_config(db)
    lat = float(cfg.get("latitude", 0))
    lon = float(cfg.get("longitude", 0))

    if lat == 0 and lon == 0:
        return {"grid": [], "rows": 0, "cols": 0, "station_count": 0}

    # Self-seed station cache if needed (pressure page may load before map)
    best = await _ensure_station_cache(db, lat, lon)
    if not best:
        return {"grid": [], "rows": 0, "cols": 0, "station_count": 0}
    stations = best.data.get("stations", [])
    pressure_points = _collect_pressure_points(stations, db, lat, lon)
    pressure_points = _filter_pressure_outliers(pressure_points)
    if len(pressure_points) < 5:
        return {"grid": [], "rows": 0, "cols": 0, "station_count": len(pressure_points)}

    cache_key = f"pgrid:{round(lat, 2)}:{round(lon, 2)}:{len(pressure_points)}"
    cached = _pgrid_cache.get(cache_key)
    if cached and time.time() < cached.expires_at:
        return cached.data

    GRID = 120
    grid, lat_min, lat_max, lon_min, lon_max = _build_smooth_grid(
        pressure_points, GRID, blur_sigma=5.0,
    )

    all_p = [p for _, _, p in pressure_points]

    # Build station summary for frontend markers (include extra fields for detail panel)
    station_markers = []
    for pt_lat, pt_lon, pt_p in pressure_points:
        is_home = abs(pt_lat - lat) < 0.001 and abs(pt_lon - lon) < 0.001
        marker: dict = {
            "lat": pt_lat, "lon": pt_lon,
            "pressure_hpa": round(pt_p, 1), "name": "",
            "is_home": is_home,
        }
        if stations:
            for s in stations:
                if (s.get("lat") is not None
                        and abs(s["lat"] - pt_lat) < 0.001
                        and abs(s["lon"] - pt_lon) < 0.001):
                    marker["name"] = s.get("name", s.get("id", ""))
                    marker["id"] = s.get("id", "")
                    marker["source"] = s.get("source", "")
                    marker["temp_f"] = s.get("temp_f")
                    marker["wind_mph"] = s.get("wind_mph")
                    marker["wind_dir"] = s.get("wind_dir")
                    marker["pressure_inhg"] = s.get("pressure_inhg")
                    marker["updated"] = s.get("updated")
                    break
        station_markers.append(marker)

    result = {
        "grid": [[round(v, 2) for v in row] for row in grid],
        "rows": GRID,
        "cols": GRID,
        "lat_min": round(lat_min, 4),
        "lat_max": round(lat_max, 4),
        "lon_min": round(lon_min, 4),
        "lon_max": round(lon_max, 4),
        "pressure_min": round(min(all_p), 1),
        "pressure_max": round(max(all_p), 1),
        "station_count": len(pressure_points),
        "stations": station_markers,
        "pressure_unit": cfg.get("pressure_unit", "inHg"),
        "temp_unit": cfg.get("temp_unit", "F"),
        "wind_unit": cfg.get("wind_unit", "mph"),
    }

    _pgrid_cache[cache_key] = _StationCache(
        data=result,
        expires_at=time.time() + _PGRID_CACHE_TTL,
    )

    logger.info("Map: computed %dx%d pressure grid from %d points",
                GRID, GRID, len(pressure_points))

    return result
