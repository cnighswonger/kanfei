"""
Mock External APIs for Testing.

Provides mock implementations of external services used by the nowcast system:
- NWS API (forecasts, alerts, grid points)
- Open-Meteo API (HRRR/GFS model guidance)
- IEM RadMap API (radar imagery)

These mocks return historic data instead of live data, allowing us to test
nowcast behavior with known conditions.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pathlib import Path
import json
import base64


class MockNWSAPI:
    """
    Mock NWS API for testing.

    Returns historic forecast and alert data instead of live data.
    """

    def __init__(self, historic_alerts: Optional[List[Dict[str, Any]]] = None):
        """
        Initialize mock NWS API.

        Args:
            historic_alerts: List of historic NWS alerts to return
        """
        self.historic_alerts = historic_alerts or []

    def get_active_alerts(
        self,
        lat: float,
        lon: float,
        timestamp: datetime
    ) -> List[Dict[str, Any]]:
        """
        Return historic alerts active at the given timestamp.

        Args:
            lat: Latitude
            lon: Longitude
            timestamp: Time to check for alerts

        Returns:
            List of alert dictionaries matching NWS API format
        """
        active_alerts = []

        for alert in self.historic_alerts:
            # Check if alert was active at this time
            issue_time = alert.get('issue_time')
            expire_time = alert.get('expire_time')

            # Parse timestamps if they're strings
            if isinstance(issue_time, str):
                try:
                    from dateutil import parser
                    issue_time = parser.parse(issue_time)
                except:
                    continue

            if isinstance(expire_time, str):
                try:
                    from dateutil import parser
                    expire_time = parser.parse(expire_time)
                except:
                    continue

            # Skip if we don't have valid timestamps
            if not issue_time or not expire_time:
                continue

            # Ensure timezone awareness
            if issue_time.tzinfo is None:
                issue_time = issue_time.replace(tzinfo=timezone.utc)
            if expire_time.tzinfo is None:
                expire_time = expire_time.replace(tzinfo=timezone.utc)

            if issue_time <= timestamp <= expire_time:
                # Convert to NWS API format
                nws_alert = {
                    'id': alert.get('product_id', ''),
                    'properties': {
                        'event': self._phenomena_to_event_name(
                            alert.get('phenomena'),
                            alert.get('significance')
                        ),
                        'severity': self._significance_to_severity(
                            alert.get('significance')
                        ),
                        'urgency': 'Immediate',
                        'onset': issue_time.isoformat(),
                        'expires': expire_time.isoformat(),
                        'description': alert.get('description', ''),
                        'instruction': alert.get('instruction', ''),
                    }
                }
                active_alerts.append(nws_alert)

        return active_alerts

    def get_forecast(
        self,
        lat: float,
        lon: float,
        timestamp: datetime
    ) -> Dict[str, Any]:
        """
        Return a mock NWS forecast.

        Args:
            lat: Latitude
            lon: Longitude
            timestamp: Time of forecast

        Returns:
            Mock forecast dictionary
        """
        # Return a generic forecast
        # In real testing, this would be populated with historic forecast data
        return {
            'properties': {
                'periods': [
                    {
                        'name': 'This Hour',
                        'temperature': 72,
                        'temperatureUnit': 'F',
                        'windSpeed': '10 mph',
                        'windDirection': 'S',
                        'shortForecast': 'Partly Cloudy',
                        'detailedForecast': 'Mock forecast for testing'
                    }
                ]
            }
        }

    def resolve_grid_point(
        self,
        lat: float,
        lon: float
    ) -> Dict[str, Any]:
        """
        Return mock grid point information.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Mock grid point data including radar station
        """
        # Determine radar station based on location
        radar_station = self._nearest_radar_station(lat, lon)

        return {
            'properties': {
                'gridId': 'OKX',
                'gridX': 50,
                'gridY': 50,
                'radarStation': radar_station,
            }
        }

    def _phenomena_to_event_name(self, phenomena: str, significance: str) -> str:
        """Convert VTEC codes to event name."""
        mapping = {
            ('TO', 'W'): 'Tornado Warning',
            ('TO', 'A'): 'Tornado Watch',
            ('SV', 'W'): 'Severe Thunderstorm Warning',
            ('SV', 'A'): 'Severe Thunderstorm Watch',
            ('FF', 'W'): 'Flash Flood Warning',
            ('FF', 'A'): 'Flash Flood Watch',
        }
        return mapping.get((phenomena, significance), f'{phenomena} {significance}')

    def _significance_to_severity(self, significance: str) -> str:
        """Convert VTEC significance to severity level."""
        mapping = {
            'W': 'Extreme',  # Warning
            'A': 'Severe',   # Watch
            'Y': 'Moderate', # Advisory
            'S': 'Minor',    # Statement
        }
        return mapping.get(significance, 'Unknown')

    def _nearest_radar_station(self, lat: float, lon: float) -> str:
        """Determine nearest radar station (simplified)."""
        # Simple logic for testing - would use actual distances in production
        if 34 <= lat <= 37 and -99 <= lon <= -95:
            return 'KTLX'  # Oklahoma City
        elif 38 <= lat <= 40 and -98 <= lon <= -94:
            return 'KICT'  # Wichita
        else:
            return 'KOUN'  # Norman (default)


class MockOpenMeteoAPI:
    """
    Mock Open-Meteo API for model guidance.

    Returns historic HRRR/GFS data instead of live forecasts.
    """

    def __init__(self, historic_model_data: Optional[Dict[str, Any]] = None):
        """
        Initialize mock Open-Meteo API.

        Args:
            historic_model_data: Historic model data to return
        """
        self.historic_model_data = historic_model_data or {}

    def get_forecast(
        self,
        lat: float,
        lon: float,
        timestamp: datetime,
        hours: int = 2
    ) -> Dict[str, Any]:
        """
        Return mock model guidance.

        Args:
            lat: Latitude
            lon: Longitude
            timestamp: Forecast initialization time
            hours: Number of forecast hours

        Returns:
            Mock forecast data in Open-Meteo format
        """
        # If we have historic data, return it
        if self.historic_model_data:
            return self.historic_model_data

        # Otherwise return generic mock data
        from datetime import timedelta

        hourly_times = [
            (timestamp + timedelta(hours=h)).isoformat()
            for h in range(hours + 1)
        ]

        return {
            'latitude': lat,
            'longitude': lon,
            'hourly': {
                'time': hourly_times,
                'temperature_2m': [72.0] * len(hourly_times),
                'relative_humidity_2m': [65.0] * len(hourly_times),
                'precipitation': [0.0] * len(hourly_times),
                'wind_speed_10m': [10.0] * len(hourly_times),
                'wind_direction_10m': [180.0] * len(hourly_times),
                'pressure_msl': [1013.0] * len(hourly_times),
                'cloud_cover': [50.0] * len(hourly_times),
            }
        }


class MockIEMRadMapAPI:
    """
    Mock IEM RadMap API for radar imagery.

    Returns historic radar images or generates synthetic ones.
    """

    def __init__(self, historic_radar_images: Optional[Dict[str, bytes]] = None):
        """
        Initialize mock IEM RadMap API.

        Args:
            historic_radar_images: Dict mapping product_id to PNG bytes
        """
        self.historic_radar_images = historic_radar_images or {}

    def get_radar_image(
        self,
        lat: float,
        lon: float,
        product: str,
        width: int = 480,
        height: int = 480,
        radius_degrees: float = 1.5,
        timestamp: Optional[datetime] = None
    ) -> Optional[bytes]:
        """
        Return radar image (historic or synthetic).

        Args:
            lat: Center latitude
            lon: Center longitude
            product: Product type ('composite', 'velocity', etc.)
            width: Image width in pixels
            height: Image height in pixels
            radius_degrees: Bounding box radius
            timestamp: Time of image (for historic data)

        Returns:
            PNG image bytes, or None if not available
        """
        # Check for historic image
        key = f"{product}_{timestamp.isoformat() if timestamp else 'latest'}"
        if key in self.historic_radar_images:
            return self.historic_radar_images[key]

        # Generate a synthetic placeholder image for testing
        return self._generate_placeholder_image(width, height, product)

    def _generate_placeholder_image(
        self,
        width: int,
        height: int,
        product: str
    ) -> bytes:
        """
        Generate a placeholder radar image for testing.

        Args:
            width: Image width
            height: Image height
            product: Product name (for labeling)

        Returns:
            PNG image bytes
        """
        try:
            from PIL import Image, ImageDraw, ImageFont
            import io

            # Create blank image
            img = Image.new('RGB', (width, height), color='black')
            draw = ImageDraw.Draw(img)

            # Draw label
            text = f"Mock {product}\n{width}x{height}"
            draw.text((width // 2, height // 2), text, fill='white', anchor='mm')

            # Convert to PNG bytes
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            return buffer.getvalue()

        except ImportError:
            # If PIL not available, return minimal PNG
            # 1x1 transparent PNG
            return base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
            )


class MockAPIFactory:
    """
    Factory for creating mock APIs configured with historic data.

    Simplifies test setup by loading historic data and creating
    appropriate mock instances.
    """

    @staticmethod
    def create_from_event_data(
        event_dir: Path
    ) -> Dict[str, Any]:
        """
        Create mock APIs from event fixture data.

        Args:
            event_dir: Path to event fixture directory

        Returns:
            Dictionary with mock API instances:
                {'nws': MockNWSAPI, 'openmeteo': MockOpenMeteoAPI, 'radmap': MockIEMRadMapAPI}
        """
        mocks = {}

        # Load NWS alerts
        alerts_file = event_dir / 'alerts' / 'alerts.json'
        if alerts_file.exists():
            with open(alerts_file) as f:
                alerts = json.load(f)
                mocks['nws'] = MockNWSAPI(historic_alerts=alerts)
        else:
            mocks['nws'] = MockNWSAPI()

        # Load model data
        model_file = event_dir / 'model' / 'guidance.json'
        if model_file.exists():
            with open(model_file) as f:
                model_data = json.load(f)
                mocks['openmeteo'] = MockOpenMeteoAPI(historic_model_data=model_data)
        else:
            mocks['openmeteo'] = MockOpenMeteoAPI()

        # Load radar images
        radar_dir = event_dir / 'radar_images'
        radar_images = {}
        if radar_dir.exists():
            for img_file in radar_dir.glob('*.png'):
                with open(img_file, 'rb') as f:
                    radar_images[img_file.stem] = f.read()

        mocks['radmap'] = MockIEMRadMapAPI(historic_radar_images=radar_images)

        return mocks
