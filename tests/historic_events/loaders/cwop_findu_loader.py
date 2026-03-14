"""
CWOP Data Loader - findu.com Archive.

Retrieves historic CWOP station observations from the findu.com archive
which has data going back to March 2000.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests
import re


class CWOPFinduLoader:
    """
    Loads historic CWOP observations from findu.com archive.

    The findu.com archive has CWOP data back to March 2000 and provides
    a simple text-based API for retrieving station data.
    """

    BASE_URL = "http://www.findu.com/cgi-bin/wx.cgi"

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize the CWOP findu loader.

        Args:
            cache_dir: Directory to cache downloaded data
        """
        self.cache_dir = cache_dir or Path('.test_cache') / 'cwop_findu'
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_station_data(
        self,
        station_id: str,
        hours_back: int = 24
    ) -> List[Dict[str, Any]]:
        """
        Get recent data for a specific CWOP station.

        Args:
            station_id: CWOP station ID (e.g., "CW1035", "DW1234")
            hours_back: How many hours of history to retrieve (max ~240)

        Returns:
            List of observation dictionaries
        """
        params = {
            'call': station_id,
            'last': min(hours_back, 240)  # API limit
        }

        try:
            print(f"Fetching findu.com data for {station_id} ({hours_back}h back)")
            response = requests.get(self.BASE_URL, params=params, timeout=30)
            response.raise_for_status()

            # Parse the text response
            observations = self._parse_findu_text(response.text, station_id)
            return observations

        except Exception as e:
            print(f"Warning: Could not fetch {station_id}: {e}")
            return []

    def _parse_findu_text(
        self,
        text: str,
        station_id: str
    ) -> List[Dict[str, Any]]:
        """
        Parse findu.com text response into observations.

        The format is tab-delimited with fields like:
        Date/Time, Wind Dir, Wind Speed, Gust, Temp, Rain/hr, Rain/24h, etc.

        Args:
            text: Response text from findu.com
            station_id: Station ID

        Returns:
            List of observation dictionaries
        """
        observations = []
        lines = text.strip().split('\n')

        # Skip header lines and find data
        data_started = False
        for line in lines:
            line = line.strip()

            # Skip empty lines and headers
            if not line or 'Date/Time' in line:
                if 'Date/Time' in line:
                    data_started = True
                continue

            if not data_started:
                continue

            # Parse data line (tab-delimited)
            parts = line.split('\t')
            if len(parts) < 3:
                continue

            try:
                # Example format: "03/02/26 14:23:00  090  003  -  73  -  -  29.92  -"
                # Fields: Date/Time, Wind Dir, Wind Spd, Gust, Temp, Rain/hr, Rain/24h, Pressure, Humidity

                timestamp_str = parts[0].strip()

                # Parse timestamp (format: MM/DD/YY HH:MM:SS or similar)
                try:
                    # Try common formats
                    for fmt in ['%m/%d/%y %H:%M:%S', '%Y/%m/%d %H:%M:%S', '%m/%d/%Y %H:%M:%S']:
                        try:
                            ts = datetime.strptime(timestamp_str, fmt)
                            # Assume UTC
                            if ts.tzinfo is None:
                                ts = ts.replace(tzinfo=timezone.utc)
                            break
                        except ValueError:
                            continue
                    else:
                        # Couldn't parse, skip
                        continue
                except:
                    continue

                obs = {
                    'station_id': station_id,
                    'timestamp': ts,
                }

                # Parse weather fields (handle '-' for missing data)
                if len(parts) > 1 and parts[1].strip() not in ['-', '']:
                    obs['wind_dir'] = float(parts[1].strip())

                if len(parts) > 2 and parts[2].strip() not in ['-', '']:
                    obs['wind_speed'] = float(parts[2].strip())  # mph

                if len(parts) > 3 and parts[3].strip() not in ['-', '']:
                    obs['wind_gust'] = float(parts[3].strip())  # mph

                if len(parts) > 4 and parts[4].strip() not in ['-', '']:
                    obs['temperature'] = float(parts[4].strip())  # °F

                if len(parts) > 5 and parts[5].strip() not in ['-', '']:
                    obs['rain_1h'] = float(parts[5].strip())  # inches

                if len(parts) > 6 and parts[6].strip() not in ['-', '']:
                    obs['rain_24h'] = float(parts[6].strip())  # inches

                if len(parts) > 7 and parts[7].strip() not in ['-', '']:
                    obs['pressure'] = float(parts[7].strip())  # inHg

                if len(parts) > 8 and parts[8].strip() not in ['-', '']:
                    obs['humidity'] = float(parts[8].strip())  # %

                observations.append(obs)

            except Exception as e:
                # Skip malformed lines
                continue

        return observations

    def find_stations_near(
        self,
        lat: float,
        lon: float,
        radius_miles: float = 50,
        timestamp: Optional[datetime] = None
    ) -> List[str]:
        """
        Find CWOP stations near a location.

        Note: findu.com doesn't have a spatial search API, so this would
        require knowing station IDs in advance or using another source
        (like MADIS or MesoWest) to find nearby stations first.

        Args:
            lat: Latitude
            lon: Longitude
            radius_miles: Search radius
            timestamp: Time (not used for findu.com)

        Returns:
            List of station IDs (empty - needs external station list)
        """
        # findu.com doesn't provide spatial search
        # This would need to be implemented by:
        # 1. Using MesoWest or MADIS to find nearby CWOP stations
        # 2. Then using findu.com to fetch their data
        print("Warning: findu.com doesn't support spatial search")
        print("Use MesoWest or MADIS to find nearby stations, then fetch with findu")
        return []

    def get_observations_for_event(
        self,
        station_ids: List[str],
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """
        Get observations from multiple stations for an event timeframe.

        Args:
            station_ids: List of CWOP station IDs
            start_time: Event start time
            end_time: Event end time

        Returns:
            Combined list of observations from all stations
        """
        all_observations = []

        # Calculate how many hours back from now
        # (findu.com API is relative to current time, not absolute)
        now = datetime.now(timezone.utc)
        hours_since_event = (now - start_time).total_seconds() / 3600

        if hours_since_event > 240:
            print(f"Warning: Event is {hours_since_event:.0f} hours ago")
            print("findu.com API limited to ~240 hours, data may be incomplete")
            hours_back = 240
        else:
            hours_back = int(hours_since_event) + 24  # Add buffer

        for station_id in station_ids:
            obs = self.get_station_data(station_id, hours_back=hours_back)

            # Filter to time range
            filtered = [
                o for o in obs
                if start_time <= o['timestamp'] <= end_time
            ]

            all_observations.extend(filtered)
            print(f"  {station_id}: {len(filtered)} observations in time range")

        return sorted(all_observations, key=lambda x: x['timestamp'])


# Convenience function
def get_cwop_data_findu(
    station_ids: List[str],
    start_time: datetime,
    end_time: datetime
) -> List[Dict[str, Any]]:
    """
    Quick function to get CWOP data from findu.com for multiple stations.

    Args:
        station_ids: List of CWOP station IDs
        start_time: Start of time range
        end_time: End of time range

    Returns:
        List of observations
    """
    loader = CWOPFinduLoader()
    return loader.get_observations_for_event(station_ids, start_time, end_time)
