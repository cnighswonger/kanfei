"""
CWOP (Citizen Weather Observer Program) Data Loader.

Retrieves historic CWOP station observations from NOAA MADIS archive.
Data is available from July 1, 2001 to present in netCDF format.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests

try:
    from netCDF4 import Dataset
    import numpy as np
except ImportError:
    Dataset = None
    np = None


class CWOPLoader:
    """
    Loads historic CWOP observations from NOAA MADIS.

    Data is stored in hourly netCDF files at:
    https://madis-data.ncep.noaa.gov/madisPublic1/data/YYYYMMDD_hhmm.gz

    Each file contains observations from hh:00 to hh:59 UTC.
    """

    # For archive data (older than ~1 day), use the archive path
    BASE_URL = "https://madis-data.ncep.noaa.gov/madisPublic1/data/archive"
    # For real-time data, would use: "https://madis-data.ncep.noaa.gov/madisPublic1/data/point/mesonet/netcdf"

    # Class-level cache for extracted station data: (file_path, bbox) -> observations
    # Persists across instances to avoid re-parsing same netCDF files
    _extract_cache = {}

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize the CWOP loader.

        Args:
            cache_dir: Directory to cache downloaded netCDF files
        """
        if Dataset is None:
            raise ImportError(
                "netCDF4 is required for CWOP data loading. "
                "Install with: pip install netCDF4"
            )

        self.cache_dir = cache_dir or Path('.test_cache') / 'cwop'
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def download_file(
        self,
        timestamp: datetime,
        force: bool = False
    ) -> Optional[Path]:
        """
        Download a MADIS CWOP file for a specific hour.

        Args:
            timestamp: UTC datetime (will use hour only)
            force: Force re-download even if cached

        Returns:
            Path to downloaded netCDF file, or None if download fails
        """
        # Round to hour
        hour_time = timestamp.replace(minute=0, second=0, microsecond=0)

        # Filename format: YYYYMMDD_hhmm.gz
        filename = hour_time.strftime("%Y%m%d_%H%M.gz")
        local_path = self.cache_dir / filename

        if local_path.exists() and not force:
            return local_path

        # Construct URL
        # Archive structure: /YYYY/MM/DD/LDAD/mesonet/netCDF/YYYYMMDD_hhmm.gz
        url = f"{self.BASE_URL}/{hour_time.year}/{hour_time.month:02d}/{hour_time.day:02d}/LDAD/mesonet/netCDF/{filename}"

        try:
            print(f"Downloading CWOP data: {filename}")
            response = requests.get(url, timeout=60, stream=True)
            response.raise_for_status()

            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            return local_path

        except requests.RequestException as e:
            print(f"Warning: Could not download {filename}: {e}")
            return None

    def read_netcdf(self, file_path: Path) -> Optional[Dataset]:
        """
        Read a MADIS CWOP netCDF file.

        Note: MADIS files are gzipped netCDF. They must be decompressed first.

        Args:
            file_path: Path to .gz netCDF file

        Returns:
            netCDF4 Dataset object, or None if read fails
        """
        import gzip
        import os

        # Decompress to cache directory
        decompressed_path = file_path.parent / file_path.stem  # Remove .gz extension

        if not decompressed_path.exists():
            try:
                with gzip.open(file_path, 'rb') as gz:
                    with open(decompressed_path, 'wb') as out:
                        out.write(gz.read())
            except Exception as e:
                print(f"Error decompressing {file_path}: {e}")
                return None

        try:
            ds = Dataset(decompressed_path, 'r')
            return ds
        except Exception as e:
            print(f"Error reading {decompressed_path}: {e}")
            return None

    def extract_stations(
        self,
        dataset: Dataset,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
        cwop_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Extract station observations within a geographic bounding box.

        Args:
            dataset: netCDF4 Dataset object
            lat_min: Minimum latitude
            lat_max: Maximum latitude
            lon_min: Minimum longitude
            lon_max: Maximum longitude
            cwop_only: If True, only include APRSWXNET (CWOP) stations

        Returns:
            List of observation dictionaries (CWOP PWS + ham radio stations)
        """
        observations = []

        # MADIS netCDF structure (variable names may vary)
        try:
            station_ids = dataset.variables.get('stationId', None)
            if station_ids is None:
                station_ids = dataset.variables.get('providerId', None)

            # Get data provider to filter for CWOP
            data_providers = dataset.variables.get('dataProvider', None)

            latitudes = dataset.variables['latitude'][:]
            longitudes = dataset.variables['longitude'][:]
            elevations = dataset.variables.get('elevation', [None] * len(latitudes))[:]

            # Weather variables (not all may be present)
            temperatures = dataset.variables.get('temperature', None)
            dewpoints = dataset.variables.get('dewpoint', None)
            pressures = dataset.variables.get('stationPressure', None)
            wind_speeds = dataset.variables.get('windSpeed', None)
            wind_dirs = dataset.variables.get('windDir', None)
            precips = dataset.variables.get('precipAccum', None)

            # APRSWXNET (CWOP) raw messages - needed because MADIS doesn't parse pressure
            raw_messages = dataset.variables.get('rawMessage', None)

            # Time
            times = dataset.variables['observationTime'][:]
            time_units = dataset.variables['observationTime'].units

            # Convert time to datetime
            from netCDF4 import num2date
            datetimes = num2date(times, time_units)

            # Filter by bounding box and CWOP provider
            for i in range(len(latitudes)):
                # Filter for APRSWXNET (CWOP) stations only
                if cwop_only and data_providers is not None:
                    try:
                        provider = data_providers[i].tobytes().decode('utf-8')
                        if 'APRSWXNET' not in provider:
                            continue  # Skip non-CWOP stations
                    except:
                        continue

                lat = latitudes[i]
                lon = longitudes[i]

                if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
                    station_id = station_ids[i].tobytes().decode('utf-8').strip() if station_ids is not None else f"UNKNOWN_{i}"

                    # Determine station type from ID pattern
                    # PWS (Personal Weather Stations): Cxxxx, Dxxxx, Exxxx, Fxxxx, Gxxxx (1 letter + 4 digits)
                    # Ham Radio: APxxxx, ARxxxx, ASxxxx, ATxxxx, AUxxxx, AVxxxx (2 letters + 3 digits)
                    station_type = 'unknown'
                    if len(station_id) >= 5:
                        # Check for PWS pattern: C####, D####, E####, F####, or G####
                        if station_id[0] in 'CDEFG' and station_id[1:5].isdigit():
                            station_type = 'pws'  # Personal Weather Station
                        # Check for ham pattern: AP###, AR###, AS###, AT###, AU###, AV###
                        elif len(station_id) >= 5 and station_id[:2].upper() in ['AP', 'AR', 'AS', 'AT', 'AU', 'AV']:
                            station_type = 'ham'  # Ham radio operator

                    obs = {
                        'station_id': station_id,
                        'station_type': station_type,  # 'pws', 'ham', or 'unknown'
                        'latitude': float(lat),
                        'longitude': float(lon),
                        'elevation': float(elevations[i]) if elevations[i] is not None else None,
                        'timestamp': datetimes[i],
                    }

                    # Add weather variables if available
                    # MADIS stores temperature in Kelvin, convert to Celsius
                    if temperatures is not None and i < len(temperatures):
                        temp_k = temperatures[i]
                        obs['temperature'] = float(temp_k) - 273.15 if not np.ma.is_masked(temp_k) else None
                    if dewpoints is not None and i < len(dewpoints):
                        dew_k = dewpoints[i]
                        obs['dewpoint'] = float(dew_k) - 273.15 if not np.ma.is_masked(dew_k) else None

                    # Pressure: Try parsed field first, fallback to raw message for CWOP
                    if pressures is not None and i < len(pressures):
                        press_pa = pressures[i]
                        if not np.ma.is_masked(press_pa):
                            # Convert pascals to hPa (1 Pa = 0.01 hPa)
                            obs['pressure'] = float(press_pa) * 0.01
                        elif raw_messages is not None and i < len(raw_messages):
                            # MADIS doesn't parse APRSWXNET pressure - extract from raw CSV
                            try:
                                raw = raw_messages[i].tobytes().decode('utf-8', errors='ignore').strip()
                                fields = raw.split(',')
                                if len(fields) >= 10 and fields[9] not in ['-9999.00', '-9999', '']:
                                    obs['pressure'] = float(fields[9])  # Already in hPa
                            except:
                                obs['pressure'] = None

                    if wind_speeds is not None and i < len(wind_speeds):
                        wind_spd = wind_speeds[i]
                        obs['wind_speed'] = float(wind_spd) if not np.ma.is_masked(wind_spd) else None
                    if wind_dirs is not None and i < len(wind_dirs):
                        wind_d = wind_dirs[i]
                        obs['wind_dir'] = float(wind_d) if not np.ma.is_masked(wind_d) else None
                    if precips is not None and i < len(precips):
                        precip_mm = precips[i]
                        obs['precip'] = float(precip_mm) if not np.ma.is_masked(precip_mm) else None

                    observations.append(obs)

        except Exception as e:
            print(f"Error extracting stations: {e}")

        return observations

    def get_observations(
        self,
        start_time: datetime,
        end_time: datetime,
        lat: float,
        lon: float,
        radius_miles: float = 25
    ) -> List[Dict[str, Any]]:
        """
        Get CWOP observations within a radius of a point for a time range.

        Args:
            start_time: Start of time range (UTC)
            end_time: End of time range (UTC)
            lat: Center latitude
            lon: Center longitude
            radius_miles: Search radius in miles

        Returns:
            List of all observations from stations within radius
        """
        # Convert radius to approximate lat/lon box
        # 1 degree latitude ≈ 69 miles
        # 1 degree longitude ≈ 69 * cos(lat) miles
        import math
        lat_delta = radius_miles / 69.0
        lon_delta = radius_miles / (69.0 * math.cos(math.radians(lat)))

        lat_min = lat - lat_delta
        lat_max = lat + lat_delta
        lon_min = lon - lon_delta
        lon_max = lon + lon_delta

        all_observations = []

        # Download and process each hour in the range
        # Use in-memory cache to avoid re-parsing the same netCDF file for same bbox
        bbox_key = (round(lat_min, 2), round(lat_max, 2), round(lon_min, 2), round(lon_max, 2))
        current_time = start_time.replace(minute=0, second=0, microsecond=0)
        while current_time <= end_time:
            file_path = self.download_file(current_time)
            if file_path:
                cache_key = (str(file_path), bbox_key)
                if cache_key in self._extract_cache:
                    all_observations.extend(self._extract_cache[cache_key])
                else:
                    dataset = self.read_netcdf(file_path)
                    if dataset:
                        obs = self.extract_stations(
                            dataset,
                            lat_min, lat_max,
                            lon_min, lon_max
                        )
                        self._extract_cache[cache_key] = obs
                        all_observations.extend(obs)
                        dataset.close()

            current_time += timedelta(hours=1)

        # Sort by timestamp
        all_observations.sort(key=lambda x: x['timestamp'])

        return all_observations

    def find_stations_in_area(
        self,
        timestamp: datetime,
        lat: float,
        lon: float,
        radius_miles: float = 25
    ) -> List[str]:
        """
        Find all CWOP station IDs active in an area at a given time.

        Useful for identifying which stations have data for an event.

        Args:
            timestamp: UTC datetime to check
            lat: Center latitude
            lon: Center longitude
            radius_miles: Search radius in miles

        Returns:
            List of station IDs
        """
        obs = self.get_observations(
            timestamp,
            timestamp + timedelta(hours=1),
            lat, lon, radius_miles
        )

        station_ids = list(set([o['station_id'] for o in obs]))
        return sorted(station_ids)
