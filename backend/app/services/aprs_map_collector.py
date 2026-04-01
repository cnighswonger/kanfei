"""Lightweight APRS-IS listener for the map view.

Connects to APRS-IS as a read-only client with a geographic range filter,
parses CWOP weather packets, and maintains an in-memory cache of recent
observations. The map endpoint reads from this cache — instant, no blocking.

Adapted from kanfei-nowcast's aprs_collector.py for standalone Kanfei use.
When kanfei-nowcast is installed and its collector is running, the map
endpoint can use that instead — this collector is the fallback for
standalone Kanfei installations.

References:
    http://www.aprs-is.net/connecting.aspx
    http://www.aprs-is.net/javAPRSFilter.aspx
"""

import asyncio
import logging
import math
import re
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# --- Constants ---

APRS_IS_SERVERS = [
    ("noam.aprs2.net", 14580),
    ("rotate.aprs2.net", 14580),
]
CONNECT_TIMEOUT = 15.0
READ_TIMEOUT = 120.0
MILES_TO_KM = 1.60934
OBS_MAX_AGE = 1800  # 30 minutes
BACKOFF_INITIAL = 5.0
BACKOFF_MAX = 300.0
PRUNE_INTERVAL = 60
TENTHS_HPA_TO_INHG = 1.0 / (33.8639 * 10.0)


# --- Dataclass ---

@dataclass
class APRSObservation:
    callsign: str
    latitude: float
    longitude: float
    timestamp: float
    temp_f: Optional[float] = None
    humidity_pct: Optional[int] = None
    wind_speed_mph: Optional[float] = None
    wind_dir_deg: Optional[int] = None
    wind_gust_mph: Optional[float] = None
    pressure_inhg: Optional[float] = None
    precip_in: Optional[float] = None


# --- Cache persistence ---

_CACHE_FILE = ".aprs_map_cache.json"


def _save_cache() -> None:
    """Persist observations to disk for fast restart."""
    import json
    try:
        data = []
        for obs in _observations.values():
            data.append({
                "callsign": obs.callsign, "latitude": obs.latitude,
                "longitude": obs.longitude, "timestamp": obs.timestamp,
                "temp_f": obs.temp_f, "humidity_pct": obs.humidity_pct,
                "wind_speed_mph": obs.wind_speed_mph, "wind_dir_deg": obs.wind_dir_deg,
                "wind_gust_mph": obs.wind_gust_mph, "pressure_inhg": obs.pressure_inhg,
                "precip_in": obs.precip_in,
            })
        with open(_CACHE_FILE, "w") as f:
            json.dump(data, f)
        logger.debug("APRS map cache saved: %d observations", len(data))
    except Exception:
        logger.debug("APRS map cache save failed", exc_info=True)


def _load_cache() -> int:
    """Load persisted observations from disk. Returns count loaded."""
    import json
    try:
        with open(_CACHE_FILE) as f:
            data = json.load(f)
        cutoff = time.time() - OBS_MAX_AGE
        loaded = 0
        for d in data:
            if d.get("timestamp", 0) < cutoff:
                continue
            obs = APRSObservation(**d)
            _observations[obs.callsign] = obs
            loaded += 1
        if loaded:
            logger.info("APRS map cache loaded: %d observations from disk", loaded)
        return loaded
    except FileNotFoundError:
        return 0
    except Exception:
        logger.debug("APRS map cache load failed", exc_info=True)
        return 0


# --- Module state ---

_observations: dict[str, APRSObservation] = {}
_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None


# --- APRS weather packet parser ---

_POS_RE = re.compile(
    r"(\d{2})(\d{2}\.\d{2})([NS])"
    r"(.)"
    r"(\d{3})(\d{2}\.\d{2})([EW])"
)

_WX_FIELD_RE = re.compile(
    r"_(\d{3})/(\d{3})"
    r"(?:g(\d{3}))?"
    r"(?:t(-?\d{2,3}))?"
    r"(?:r(\d{3}))?"
    r"(?:p(\d{3}))?"
    r"(?:P(\d{3}))?"
    r"(?:h(\d{2}))?"
    r"(?:b(\d{5}))?"
)


def _parse_position(payload: str) -> Optional[tuple[float, float, int]]:
    m = _POS_RE.search(payload)
    if not m:
        return None
    lat = int(m.group(1)) + float(m.group(2)) / 60.0
    if m.group(3) == "S":
        lat = -lat
    lon = int(m.group(5)) + float(m.group(6)) / 60.0
    if m.group(7) == "W":
        lon = -lon
    return lat, lon, m.end()


def parse_weather_packet(raw_line: str) -> Optional[APRSObservation]:
    """Parse a raw APRS-IS line into an APRSObservation."""
    if raw_line.startswith("#"):
        return None
    colon = raw_line.find(":")
    if colon < 0:
        return None

    header = raw_line[:colon]
    payload = raw_line[colon + 1:]

    gt = header.find(">")
    if gt < 0:
        return None
    callsign = header[:gt].split("-")[0].strip().upper()
    if not callsign or not payload:
        return None

    if payload[0] not in ("@", "!", "=", "/"):
        return None

    pos = _parse_position(payload)
    if pos is None:
        return None
    lat, lon, pos_end = pos

    wx_start = payload.find("_", pos_end)
    if wx_start < 0:
        return None

    m = _WX_FIELD_RE.match(payload[wx_start:])
    if not m:
        return None

    temp_raw = m.group(4)
    if temp_raw is None:
        return None

    wind_dir_raw, wind_spd_raw = m.group(1), m.group(2)
    gust_raw = m.group(3)
    rain_mid_raw = m.group(7)
    hum_raw = m.group(8)
    baro_raw = m.group(9)

    humidity = None
    if hum_raw:
        humidity = int(hum_raw)
        if humidity == 0:
            humidity = 100

    pressure_inhg = None
    if baro_raw:
        pressure_inhg = round(int(baro_raw) * TENTHS_HPA_TO_INHG, 2)

    precip_in = None
    if rain_mid_raw:
        precip_in = round(int(rain_mid_raw) / 100.0, 2)

    return APRSObservation(
        callsign=callsign,
        latitude=lat,
        longitude=lon,
        timestamp=time.time(),
        temp_f=float(temp_raw),
        humidity_pct=humidity,
        wind_speed_mph=float(wind_spd_raw) if wind_spd_raw != "..." else None,
        wind_dir_deg=int(wind_dir_raw) if wind_dir_raw != "..." else None,
        wind_gust_mph=float(gust_raw) if gust_raw else None,
        pressure_inhg=pressure_inhg,
        precip_in=precip_in,
    )


# --- Background listener ---

def _prune_stale() -> int:
    cutoff = time.time() - OBS_MAX_AGE
    stale = [k for k, v in _observations.items() if v.timestamp < cutoff]
    for k in stale:
        del _observations[k]
    return len(stale)


async def _listen_loop(
    lat: float, lon: float, radius_km: int,
    own_callsign: str, stop: asyncio.Event,
) -> None:
    backoff = BACKOFF_INITIAL
    packet_count = 0

    while not stop.is_set():
        for host, port in APRS_IS_SERVERS:
            if stop.is_set():
                return
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=CONNECT_TIMEOUT,
                )
            except (OSError, asyncio.TimeoutError) as exc:
                logger.warning("APRS-IS connect to %s:%d failed: %s", host, port, exc)
                continue

            try:
                banner = await asyncio.wait_for(reader.readline(), timeout=CONNECT_TIMEOUT)
                logger.debug("APRS-IS banner: %s", banner.decode(errors="replace").strip())

                # Read-only login with range filter only (no t/w type filter).
                login = (
                    f"user N0CALL pass -1 vers kanfei-map 1.0 "
                    f"filter r/{lat:.4f}/{lon:.4f}/{radius_km}\r\n"
                )
                writer.write(login.encode())
                await writer.drain()

                ack = await asyncio.wait_for(reader.readline(), timeout=CONNECT_TIMEOUT)
                logger.info("APRS-IS (map) connected to %s:%d — %s",
                            host, port, ack.decode(errors="replace").strip())

                backoff = BACKOFF_INITIAL

                while not stop.is_set():
                    try:
                        raw = await asyncio.wait_for(reader.readline(), timeout=READ_TIMEOUT)
                    except asyncio.TimeoutError:
                        logger.warning("APRS-IS (map) read timeout, reconnecting")
                        break

                    if not raw:
                        logger.warning("APRS-IS (map) connection closed by server")
                        break

                    line = raw.decode(errors="replace").strip()
                    if not line or line.startswith("#"):
                        continue

                    obs = parse_weather_packet(line)
                    if obs is None:
                        continue

                    if own_callsign and obs.callsign == own_callsign:
                        continue

                    _observations[obs.callsign] = obs
                    packet_count += 1

                    if packet_count % PRUNE_INTERVAL == 0:
                        removed = _prune_stale()
                        if removed:
                            logger.debug("APRS map cache pruned %d stale, %d active",
                                         removed, len(_observations))

            except Exception as exc:
                logger.warning("APRS-IS (map) error on %s:%d: %s", host, port, exc)
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

        if not stop.is_set():
            logger.info("APRS-IS (map) reconnecting in %.0fs", backoff)
            try:
                await asyncio.wait_for(stop.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, BACKOFF_MAX)


# --- Public API ---

async def start(lat: float, lon: float, radius_miles: int,
                own_callsign: str = "") -> None:
    """Start the background APRS-IS listener for the map view."""
    global _task, _stop_event

    await stop_collector()

    # Load cached observations from previous run
    _load_cache()

    radius_km = int(math.ceil(radius_miles * MILES_TO_KM))
    own_call = own_callsign.strip().upper()

    _stop_event = asyncio.Event()
    _task = asyncio.create_task(
        _listen_loop(lat, lon, radius_km, own_call, _stop_event),
        name="aprs-map-collector",
    )
    logger.info("APRS map collector started (%.4f, %.4f, %d mi / %d km, cached=%d)",
                lat, lon, radius_miles, radius_km, len(_observations))


async def stop_collector() -> None:
    """Stop the background listener and persist cache."""
    global _task, _stop_event

    # Save before clearing
    if _observations:
        _save_cache()

    if _stop_event is not None:
        _stop_event.set()
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):
            pass
        _task = None
    _stop_event = None
    _observations.clear()


def is_running() -> bool:
    return _task is not None and not _task.done()


def _haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * \
        math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def get_nearby(lat: float, lon: float, radius_miles: int,
               max_stations: int = 100) -> list[APRSObservation]:
    """Return current observations filtered by distance, nearest-first."""
    _prune_stale()
    results: list[tuple[float, APRSObservation]] = []
    for obs in _observations.values():
        dist = _haversine_mi(lat, lon, obs.latitude, obs.longitude)
        if 0.5 < dist <= radius_miles:
            results.append((dist, obs))
    results.sort(key=lambda x: x[0])
    return [obs for _, obs in results[:max_stations]]
