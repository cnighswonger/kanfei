"""
METAR/ASOS data loader using Iowa Environmental Mesonet (IEM) archive.

Provides airport weather station data as supplement/backup to CWOP observations.
IEM archives ASOS/AWOS/METAR from all US airports back to ~2000.

Station database is fetched dynamically from IEM's GeoJSON API and cached
locally for 30 days.  Returns empty results if IEM is unreachable.
"""

import gzip
import json
import math
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Optional

# IEM GeoJSON endpoint for ASOS station metadata by state network
_IEM_NETWORK_URL = "https://mesonet.agron.iastate.edu/geojson/network/{state}_ASOS.geojson"

# Cache the station database for 30 days (stations rarely change)
_STATION_CACHE_TTL_SECONDS = 30 * 86400

# Rough state centroid lookup for picking which networks to query.
# We only need to search states whose stations could plausibly be within
# ~100 miles of the target, so 200-mile radius from centroid is plenty.
_STATE_CENTROIDS = {
    "AL": (32.8, -86.8), "AR": (34.8, -92.2), "AZ": (34.3, -111.7),
    "CA": (37.2, -119.5), "CO": (39.0, -105.5), "CT": (41.6, -72.7),
    "DC": (38.9, -77.0), "DE": (39.0, -75.5), "FL": (28.6, -82.4),
    "GA": (32.7, -83.4), "IA": (42.0, -93.5), "ID": (44.4, -114.6),
    "IL": (40.0, -89.2), "IN": (39.8, -86.2), "KS": (38.5, -98.3),
    "KY": (37.8, -85.7), "LA": (31.1, -92.0), "MA": (42.3, -71.8),
    "MD": (39.0, -76.7), "ME": (45.3, -69.2), "MI": (44.2, -84.5),
    "MN": (46.3, -94.3), "MO": (38.5, -92.2), "MS": (32.7, -89.7),
    "MT": (47.0, -109.6), "NC": (35.5, -79.8), "ND": (47.4, -100.5),
    "NE": (41.5, -99.8), "NH": (43.7, -71.6), "NJ": (40.1, -74.7),
    "NM": (34.4, -106.1), "NV": (39.3, -116.6), "NY": (42.9, -75.5),
    "OH": (40.4, -82.8), "OK": (35.5, -97.5), "OR": (44.0, -120.5),
    "PA": (40.9, -77.8), "RI": (41.7, -71.5), "SC": (34.0, -81.0),
    "SD": (44.4, -100.2), "TN": (35.8, -86.3), "TX": (31.5, -99.4),
    "UT": (39.3, -111.7), "VA": (37.5, -78.8), "VT": (44.1, -72.6),
    "WA": (47.4, -120.5), "WI": (44.6, -89.7), "WV": (38.6, -80.6),
    "WY": (43.0, -107.5),
}


class METARLoader:
    """
    Load METAR/ASOS observations from Iowa Environmental Mesonet archive.

    IEM provides historical ASOS/AWOS/METAR data from airports and automated
    weather stations across the US. Data is free and doesn't require authentication.

    Station metadata is fetched dynamically from IEM's GeoJSON API and cached
    locally.  The loader determines which state networks to query based on
    proximity to the requested lat/lon, so it works for any US location
    without needing a hand-curated station list.
    """

    def __init__(self, cache_dir: Path = None):
        self.cache_dir = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

        # IEM ASOS data service
        self.base_url = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"

        # Lazily populated — keyed by state code
        self._station_cache: Dict[str, List[Dict]] = {}

    # ------------------------------------------------------------------
    # Station database — dynamic IEM lookup with local file cache
    # ------------------------------------------------------------------

    def _nearby_state_codes(self, lat: float, lon: float, margin_miles: float = 200) -> List[str]:
        """Return state codes whose centroid is within margin_miles of (lat, lon)."""
        codes = []
        for code, (clat, clon) in _STATE_CENTROIDS.items():
            if self._haversine_distance(lat, lon, clat, clon) <= margin_miles:
                codes.append(code)
        return sorted(codes)

    def _station_cache_path(self, state: str) -> Optional[Path]:
        if not self.cache_dir:
            return None
        return self.cache_dir / f"metar_stations_{state}.json"

    def _load_stations_for_state(self, state: str) -> List[Dict]:
        """Fetch ASOS station metadata for one state from IEM, with file cache."""
        if state in self._station_cache:
            return self._station_cache[state]

        # Try local file cache
        cache_path = self._station_cache_path(state)
        if cache_path and cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < _STATION_CACHE_TTL_SECONDS:
                with open(cache_path, 'r') as f:
                    stations = json.load(f)
                self._station_cache[state] = stations
                return stations

        # Fetch from IEM
        stations = self._fetch_iem_stations(state)

        # Persist to file cache
        if cache_path and stations:
            try:
                with open(cache_path, 'w') as f:
                    json.dump(stations, f)
            except OSError:
                pass

        self._station_cache[state] = stations
        return stations

    def _fetch_iem_stations(self, state: str) -> List[Dict]:
        """Hit IEM GeoJSON endpoint for a state's ASOS network."""
        url = _IEM_NETWORK_URL.format(state=state)
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"  IEM station fetch failed for {state}_ASOS: {exc}")
            return []

        stations = []
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            coords = feature.get("geometry", {}).get("coordinates", [])
            if len(coords) < 2:
                continue
            sid = props.get("sid", "")
            # IEM uses 3-letter FAA codes; prepend K for ICAO
            icao = f"K{sid}" if len(sid) == 3 else sid
            stations.append({
                "id": icao,
                "iem_id": sid,  # keep original for data queries
                "lat": coords[1],
                "lon": coords[0],
                "state": state,
                "name": props.get("sname", ""),
            })

        return stations

    def get_nearby_stations(self, lat: float, lon: float, radius_miles: float = 50) -> List[Dict]:
        """
        Find METAR stations within radius of location.

        Dynamically queries IEM for station metadata in nearby states,
        caches the results locally, and filters by distance.
        """
        # Determine which state networks to query
        state_codes = self._nearby_state_codes(lat, lon)
        if not state_codes:
            state_codes = self._nearby_state_codes(lat, lon, margin_miles=400)

        # Collect stations from all nearby states
        all_stations: List[Dict] = []
        for code in state_codes:
            all_stations.extend(self._load_stations_for_state(code))

        # Filter by distance
        nearby = []
        for station in all_stations:
            dist = self._haversine_distance(lat, lon, station['lat'], station['lon'])
            if dist <= radius_miles:
                nearby.append({
                    'station_id': station['id'],
                    'iem_id': station.get('iem_id', station['id']),
                    'latitude': station['lat'],
                    'longitude': station['lon'],
                    'distance_miles': dist,
                    'name': station['name'],
                    'state': station['state'],
                })

        nearby.sort(key=lambda x: x['distance_miles'])
        return nearby

    def get_observations(
        self,
        start_time: datetime,
        end_time: datetime,
        lat: float,
        lon: float,
        radius_miles: float = 50
    ) -> List[Dict]:
        """
        Get METAR observations for all stations near location.

        Args:
            start_time: Start time (UTC)
            end_time: End time (UTC)
            lat: Latitude
            lon: Longitude
            radius_miles: Search radius

        Returns:
            List of observation dicts in CWOP-compatible format
        """
        # Find nearby stations
        stations = self.get_nearby_stations(lat, lon, radius_miles)

        if not stations:
            print(f"  No METAR stations found within {radius_miles} miles")
            return []

        print(f"  Found {len(stations)} METAR stations within {radius_miles} miles")

        # Fetch data for each station
        all_obs = []

        for station in stations:
            # IEM data endpoint uses 3-letter FAA IDs, not ICAO
            query_id = station.get('iem_id', station['station_id'])
            try:
                obs = self._fetch_station_data(
                    query_id,
                    start_time,
                    end_time,
                    station['latitude'],
                    station['longitude'],
                    display_id=station['station_id'],
                )
                all_obs.extend(obs)
                print(f"    {station['station_id']}: {len(obs)} observations")
            except Exception as e:
                print(f"    {station['station_id']}: Failed - {e}")
                continue

        return all_obs

    def _fetch_station_data(
        self,
        station_id: str,
        start_time: datetime,
        end_time: datetime,
        lat: float,
        lon: float,
        display_id: str = None,
    ) -> List[Dict]:
        """Fetch ASOS data for a single station from IEM."""
        display_id = display_id or station_id

        # Build IEM request
        params = {
            'station': station_id,
            'data': 'all',
            'year1': start_time.year,
            'month1': start_time.month,
            'day1': start_time.day,
            'hour1': start_time.hour,
            'year2': end_time.year,
            'month2': end_time.month,
            'day2': end_time.day,
            'hour2': end_time.hour,
            'tz': 'Etc/UTC',
            'format': 'onlycomma',
            'latlon': 'yes',
            'elev': 'yes',
            'missing': 'null',
            'trace': '0.0001'
        }

        # Check cache
        cache_key = f"metar_{display_id}_{start_time.strftime('%Y%m%d%H')}_{end_time.strftime('%Y%m%d%H')}"
        if self.cache_dir:
            cache_file = self.cache_dir / f"{cache_key}.json.gz"
            if cache_file.exists():
                with gzip.open(cache_file, 'rt') as f:
                    cached = json.load(f)
                    # Restore datetime objects from ISO strings
                    for o in cached:
                        if isinstance(o.get('timestamp'), str):
                            o['timestamp'] = datetime.fromisoformat(o['timestamp'])
                    return cached

        # Fetch from IEM
        response = requests.get(self.base_url, params=params, timeout=30)
        response.raise_for_status()

        # Parse CSV response
        lines = response.text.strip().split('\n')
        if len(lines) < 2:
            return []

        # Parse header
        header = lines[0].split(',')

        # Parse observations
        observations = []
        for line in lines[1:]:
            if not line.strip():
                continue

            values = line.split(',')
            if len(values) != len(header):
                continue

            obs_dict = dict(zip(header, values))

            # Convert to CWOP-compatible format
            try:
                obs = self._convert_to_cwop_format(obs_dict, display_id, lat, lon)
                if obs:
                    observations.append(obs)
            except Exception:
                continue

        # Cache result (serialize datetimes to ISO strings for JSON)
        if self.cache_dir and observations:
            cache_obs = []
            for o in observations:
                co = dict(o)
                if isinstance(co.get('timestamp'), datetime):
                    co['timestamp'] = co['timestamp'].isoformat()
                cache_obs.append(co)
            with gzip.open(cache_file, 'wt') as f:
                json.dump(cache_obs, f)

        return observations

    def _convert_to_cwop_format(self, obs: Dict, station_id: str, lat: float, lon: float) -> Optional[Dict]:
        """Convert IEM ASOS format to CWOP-compatible format."""

        # Parse timestamp
        try:
            timestamp = datetime.strptime(obs['valid'], '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
        except (ValueError, KeyError):
            return None

        # Convert values (handle 'null' strings)
        def parse_float(val):
            if val in ('null', '', 'M', 'None'):
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        temp_f = parse_float(obs.get('tmpf'))
        dewpoint_f = parse_float(obs.get('dwpf'))
        pressure_mb = parse_float(obs.get('mslp'))  # Mean sea level pressure in mb
        wind_speed_mph = parse_float(obs.get('sknt'))  # Speed in knots
        wind_dir_deg = parse_float(obs.get('drct'))

        # Convert knots to mph
        if wind_speed_mph is not None:
            wind_speed_mph = wind_speed_mph * 1.15078

        # Convert to CWOP-compatible units: temperature (C), pressure (hPa),
        # wind_speed (m/s), dewpoint (C)
        # Note: IEM mslp is already in mb (= hPa), no conversion needed
        temp_c = (temp_f - 32) * 5 / 9 if temp_f is not None else None
        dewpoint_c = (dewpoint_f - 32) * 5 / 9 if dewpoint_f is not None else None
        pressure_hpa = pressure_mb
        wind_speed_ms = wind_speed_mph / 2.23694 if wind_speed_mph is not None else None

        return {
            'station_id': station_id,
            'timestamp': timestamp,
            'latitude': lat,
            'longitude': lon,
            'temperature': temp_c,
            'dewpoint': dewpoint_c,
            'pressure': pressure_hpa,
            'wind_speed': wind_speed_ms,
            'wind_dir': wind_dir_deg,
            'source': 'METAR',
            'station_type': 'asos',
        }

    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate great-circle distance in miles."""
        R = 3958.8  # Earth radius in miles

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = (math.sin(dlat/2)**2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2)
        c = 2 * math.asin(math.sqrt(a))

        return R * c
