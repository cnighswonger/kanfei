"""
NWS Alert Archive Loader.

Retrieves historic NWS watches, warnings, and advisories from the Iowa Environmental
Mesonet (IEM) archive. Complete VTEC data available from November 12, 2005 onwards,
with storm-based warning polygons from 2002.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests
import io
import zipfile

try:
    import geopandas as gpd
    from shapely.geometry import Point, box
except ImportError:
    gpd = None
    Point = None
    box = None


class NWSAlertLoader:
    """
    Loads historic NWS alerts from IEM archive.

    Data source: https://mesonet.agron.iastate.edu/request/gis/watchwarn.phtml
    """

    BASE_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/gis/watchwarn.py"

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize the NWS alert loader.

        Args:
            cache_dir: Directory to cache downloaded shapefiles
        """
        if gpd is None:
            raise ImportError(
                "geopandas is required for NWS alert loading. "
                "Install with: pip install geopandas"
            )

        self.cache_dir = cache_dir or Path('.test_cache') / 'nws_alerts'
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def download_alerts(
        self,
        start_time: datetime,
        end_time: datetime,
        phenomena: Optional[List[str]] = None,
        significance: Optional[List[str]] = None,
        state: Optional[str] = None,
        wfo: Optional[str] = None
    ) -> Optional[gpd.GeoDataFrame]:
        """
        Download NWS alerts for a time period.

        Args:
            start_time: Start of time range (UTC)
            end_time: End of time range (UTC)
            phenomena: VTEC phenomena codes (e.g., ['TO', 'SV', 'FF'])
                      TO=Tornado, SV=Severe Thunderstorm, FF=Flash Flood
            significance: VTEC significance codes (e.g., ['W', 'A'])
                         W=Warning, A=Watch, Y=Advisory
            state: Two-letter state code (e.g., 'OK')
            wfo: Weather Forecast Office code (e.g., 'OUN')

        Returns:
            GeoDataFrame with alert polygons and metadata, or None if download fails
        """
        # Build query parameters
        params = {
            'year1': start_time.year,
            'month1': start_time.month,
            'day1': start_time.day,
            'hour1': start_time.hour,
            'minute1': start_time.minute,
            'year2': end_time.year,
            'month2': end_time.month,
            'day2': end_time.day,
            'hour2': end_time.hour,
            'minute2': end_time.minute,
            'format': 'shp',  # Shapefile format
        }

        # Add optional filters
        if phenomena:
            params['phenomena'] = ','.join(phenomena)
        if significance:
            params['significance'] = ','.join(significance)
        if state:
            params['states'] = state
        if wfo:
            params['wfos'] = wfo

        try:
            print(f"Downloading NWS alerts: {start_time} to {end_time}")
            response = requests.get(self.BASE_URL, params=params, timeout=120)
            response.raise_for_status()

            # Response is a zip file containing shapefile
            zip_content = io.BytesIO(response.content)

            # Extract to temp directory
            temp_dir = self.cache_dir / 'temp'
            temp_dir.mkdir(exist_ok=True)

            with zipfile.ZipFile(zip_content, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            # Find the .shp file
            shp_files = list(temp_dir.glob('*.shp'))
            if not shp_files:
                print("Warning: No shapefile found in download")
                return None

            # Read shapefile
            gdf = gpd.read_file(shp_files[0])

            # Clean up temp files
            import shutil
            shutil.rmtree(temp_dir)

            return gdf

        except Exception as e:
            print(f"Error downloading alerts: {e}")
            return None

    def get_alerts_for_point(
        self,
        lat: float,
        lon: float,
        start_time: datetime,
        end_time: datetime,
        phenomena: Optional[List[str]] = None,
        significance: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all alerts affecting a specific point.

        Args:
            lat: Latitude
            lon: Longitude
            start_time: Start of time range (UTC)
            end_time: End of time range (UTC)
            phenomena: Filter by VTEC phenomena codes
            significance: Filter by VTEC significance codes

        Returns:
            List of alert dictionaries with metadata
        """
        gdf = self.download_alerts(
            start_time, end_time,
            phenomena=phenomena,
            significance=significance
        )

        if gdf is None or len(gdf) == 0:
            return []

        # Create point geometry
        point = Point(lon, lat)

        # Filter to alerts containing the point
        alerts = []
        for idx, row in gdf.iterrows():
            if row.geometry.contains(point):
                alert = {
                    'phenomena': row.get('PHENOMENA', ''),
                    'significance': row.get('SIG', ''),
                    'event_id': row.get('VTEC_ETN', ''),
                    'wfo': row.get('WFO', ''),
                    'issue_time': row.get('ISSUED', None),
                    'expire_time': row.get('EXPIRED', None),
                    'product_id': row.get('PRODUCT_ID', ''),
                    'polygon_begin': row.get('POLYGON_BEGIN', None),
                    'polygon_end': row.get('POLYGON_END', None),
                }
                alerts.append(alert)

        return alerts

    def get_tornado_warnings(
        self,
        lat: float,
        lon: float,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """
        Convenience method to get tornado warnings for a point.

        Args:
            lat: Latitude
            lon: Longitude
            start_time: Start of time range (UTC)
            end_time: End of time range (UTC)

        Returns:
            List of tornado warning dictionaries
        """
        return self.get_alerts_for_point(
            lat, lon, start_time, end_time,
            phenomena=['TO'],
            significance=['W']
        )

    def get_severe_thunderstorm_warnings(
        self,
        lat: float,
        lon: float,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """
        Convenience method to get severe thunderstorm warnings for a point.

        Args:
            lat: Latitude
            lon: Longitude
            start_time: Start of time range (UTC)
            end_time: End of time range (UTC)

        Returns:
            List of severe thunderstorm warning dictionaries
        """
        return self.get_alerts_for_point(
            lat, lon, start_time, end_time,
            phenomena=['SV'],
            significance=['W']
        )

    def parse_vtec_string(self, vtec: str) -> Dict[str, str]:
        """
        Parse VTEC (Valid Time Event Code) string.

        Format: /k.aaa.cccc.pp.s.####.yymmddThhnnZ-yymmddThhnnZ/

        Args:
            vtec: VTEC string

        Returns:
            Dictionary with parsed components
        """
        # Remove slashes
        vtec = vtec.strip('/')

        parts = vtec.split('.')
        if len(parts) < 7:
            return {}

        return {
            'class': parts[0],      # k = class code
            'action': parts[1],     # aaa = action code
            'office': parts[2],     # cccc = office ID
            'phenomena': parts[3],  # pp = phenomena code
            'significance': parts[4],  # s = significance code
            'event_tracking_number': parts[5],  # #### = ETN
            'begin_time': parts[6].split('-')[0] if '-' in parts[6] else parts[6],
            'end_time': parts[6].split('-')[1] if '-' in parts[6] else ''
        }

    def get_alert_timeline(
        self,
        lat: float,
        lon: float,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """
        Get a timeline of all alerts for a location.

        Useful for reconstructing the alert sequence during an event.

        Args:
            lat: Latitude
            lon: Longitude
            start_time: Start of time range (UTC)
            end_time: End of time range (UTC)

        Returns:
            List of alerts sorted by issue time
        """
        alerts = self.get_alerts_for_point(lat, lon, start_time, end_time)

        # Sort by issue time
        alerts.sort(key=lambda x: x.get('issue_time', ''))

        return alerts
