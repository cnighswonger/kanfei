"""
Database Seeder for Historic Event Testing.

Populates a test database with historic sensor readings, station configuration,
and other data needed to run nowcast cycles in a test environment.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import sys
import math

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'backend'))

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker, Session
    from app.models.sensor_reading import SensorReadingModel
    from app.models.station_config import StationConfigModel
    from app.models.nowcast import NowcastHistory
except ImportError as e:
    print(f"Warning: Could not import app models: {e}")
    SensorReadingModel = None
    StationConfigModel = None
    NowcastHistory = None


class DatabaseSeeder:
    """
    Seeds a test database with historic data for nowcast testing.

    Converts CWOP observations into sensor_readings format and configures
    the station to match the test scenario.
    """

    def __init__(self, db_path: Path):
        """
        Initialize the database seeder.

        Args:
            db_path: Path to SQLite database file
        """
        if SensorReadingModel is None:
            raise ImportError("Could not import database models")

        self.db_path = db_path
        self.engine = create_engine(f'sqlite:///{db_path}')
        self.SessionLocal = sessionmaker(bind=self.engine)

    def create_tables(self):
        """Create all database tables."""
        from app.models.sensor_reading import Base as SensorBase
        from app.models.station_config import Base as ConfigBase
        from app.models.nowcast import Base as NowcastBase

        SensorBase.metadata.create_all(self.engine)
        ConfigBase.metadata.create_all(self.engine)
        NowcastBase.metadata.create_all(self.engine)

    def seed_station_config(
        self,
        lat: float,
        lon: float,
        elevation: float,
        station_type: str = 'Vantage Pro 2',
        config_overrides: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Seed station configuration.

        Args:
            lat: Station latitude
            lon: Station longitude
            elevation: Station elevation (feet)
            station_type: Station type string
            config_overrides: Additional config key-value pairs
        """
        session: Session = self.SessionLocal()

        try:
            # Default configuration for testing
            config = {
                'latitude': lat,
                'longitude': lon,
                'elevation': elevation,
                'station_type': station_type,
                'timezone': 'UTC',

                # Nowcast configuration
                'nowcast_enabled': True,
                'nowcast_api_key': 'test-key',
                'nowcast_model': 'haiku',
                'nowcast_max_tokens': 4000,
                'nowcast_cycle_minutes': 15,
                'nowcast_horizon_hours': 2,
                'nowcast_radar_enabled': True,
                'nowcast_radius': 25,
                'nowcast_disclaimer_accepted': True,

                # Disable uploads during testing
                'wu_enabled': False,
                'cwop_enabled': False,
            }

            # Apply overrides
            if config_overrides:
                config.update(config_overrides)

            # Insert config values
            for key, value in config.items():
                config_entry = StationConfigModel(
                    key=key,
                    value=str(value)
                )
                session.merge(config_entry)

            session.commit()
            print(f"Seeded station config: {lat}, {lon}, {elevation}ft")

        finally:
            session.close()

    def seed_sensor_readings(
        self,
        observations: List[Dict[str, Any]]
    ) -> None:
        """
        Seed sensor readings from CWOP observations.

        Converts CWOP observation format to SensorReadingModel format.

        Args:
            observations: List of CWOP observation dictionaries
        """
        session: Session = self.SessionLocal()

        try:
            for obs in observations:
                reading = self._cwop_to_sensor_reading(obs)
                if reading:
                    session.add(reading)

            session.commit()
            print(f"Seeded {len(observations)} sensor readings")

        finally:
            session.close()

    def _is_valid_number(self, value) -> bool:
        """Check if value is not None and not NaN."""
        return value is not None and not (isinstance(value, float) and math.isnan(value))

    def _calculate_relative_humidity(self, temp_c: float, dewpoint_c: float) -> Optional[int]:
        """
        Calculate relative humidity from temperature and dewpoint.

        Uses the Magnus-Tetens approximation.

        Args:
            temp_c: Temperature in Celsius
            dewpoint_c: Dewpoint in Celsius

        Returns:
            Relative humidity as integer percentage (0-100), or None if invalid
        """
        try:
            # Magnus-Tetens formula
            # RH = 100 * (exp((17.625*Td)/(243.04+Td))/exp((17.625*T)/(243.04+T)))
            a = 17.625
            b = 243.04

            numerator = math.exp((a * dewpoint_c) / (b + dewpoint_c))
            denominator = math.exp((a * temp_c) / (b + temp_c))

            if denominator == 0:
                return None

            rh = 100.0 * (numerator / denominator)

            # Clamp to valid range
            rh = max(0.0, min(100.0, rh))

            return int(round(rh))

        except (ValueError, ZeroDivisionError, OverflowError):
            return None

    def _calculate_heat_index(self, temp_f: float, humidity_pct: int) -> Optional[float]:
        """
        Calculate heat index using the NWS formula.

        Only applicable when temperature >= 80°F.

        Args:
            temp_f: Temperature in Fahrenheit
            humidity_pct: Relative humidity percentage

        Returns:
            Heat index in Fahrenheit, or None if not applicable
        """
        # Heat index is only meaningful at high temperatures
        if temp_f < 80.0:
            return None

        try:
            T = temp_f
            RH = humidity_pct

            # Rothfusz regression (NWS formula)
            HI = (-42.379 + 2.04901523 * T + 10.14333127 * RH
                  - 0.22475541 * T * RH - 0.00683783 * T * T
                  - 0.05481717 * RH * RH + 0.00122874 * T * T * RH
                  + 0.00085282 * T * RH * RH - 0.00000199 * T * T * RH * RH)

            # Adjustments for low humidity or high humidity
            if RH < 13 and 80 <= T <= 112:
                adjustment = ((13 - RH) / 4) * math.sqrt((17 - abs(T - 95)) / 17)
                HI -= adjustment
            elif RH > 85 and 80 <= T <= 87:
                adjustment = ((RH - 85) / 10) * ((87 - T) / 5)
                HI += adjustment

            return HI

        except (ValueError, ZeroDivisionError, OverflowError):
            return None

    def _calculate_wind_chill(self, temp_f: float, wind_mph: float) -> Optional[float]:
        """
        Calculate wind chill using the NWS formula.

        Only applicable when temperature <= 50°F and wind >= 3 mph.

        Args:
            temp_f: Temperature in Fahrenheit
            wind_mph: Wind speed in mph

        Returns:
            Wind chill in Fahrenheit, or None if not applicable
        """
        # Wind chill is only meaningful at cold temperatures and moderate winds
        if temp_f > 50.0 or wind_mph < 3.0:
            return None

        try:
            T = temp_f
            V = wind_mph

            # NWS wind chill formula (2001)
            WC = 35.74 + 0.6215 * T - 35.75 * (V ** 0.16) + 0.4275 * T * (V ** 0.16)

            return WC

        except (ValueError, ZeroDivisionError, OverflowError):
            return None

    def _cwop_to_sensor_reading(
        self,
        obs: Dict[str, Any]
    ) -> Optional[SensorReadingModel]:
        """
        Convert CWOP observation to SensorReadingModel.

        Args:
            obs: CWOP observation dictionary

        Returns:
            SensorReadingModel instance, or None if conversion fails
        """
        try:
            # CWOP uses SI units, need to convert to imperial for Davis compatibility
            # Temperature: C → F
            temp_f = None
            temp_c = obs.get('temperature')
            if temp_c is not None:
                temp_f = temp_c * 9/5 + 32

            dewpoint_f = None
            dewpoint_c = obs.get('dewpoint')
            if dewpoint_c is not None:
                dewpoint_f = dewpoint_c * 9/5 + 32

            # Calculate relative humidity from temp and dewpoint if not provided
            humidity_pct = None
            if temp_c is not None and dewpoint_c is not None:
                humidity_pct = self._calculate_relative_humidity(temp_c, dewpoint_c)

            # Pressure: mb/hPa → inHg
            pressure_inhg = None
            if obs.get('pressure') is not None:
                pressure_inhg = obs['pressure'] * 0.02953

            # Wind speed: m/s → mph
            wind_mph = None
            if obs.get('wind_speed') is not None:
                wind_mph = obs['wind_speed'] * 2.23694

            # Precipitation: mm → inches
            precip_in = None
            if obs.get('precip') is not None:
                precip_in = obs['precip'] * 0.0393701

            # Ensure timestamp is timezone-aware
            # num2date returns cftime objects, convert to standard datetime
            ts_raw = obs['timestamp']
            # Check if it's a standard Python datetime (not cftime)
            if isinstance(ts_raw, datetime):
                # Standard datetime - ensure it has timezone
                ts = ts_raw if ts_raw.tzinfo else ts_raw.replace(tzinfo=timezone.utc)
            else:
                # cftime datetime - convert to standard datetime
                ts = datetime(
                    ts_raw.year, ts_raw.month, ts_raw.day,
                    ts_raw.hour, ts_raw.minute, ts_raw.second,
                    tzinfo=timezone.utc
                )

            # Calculate heat index and wind chill if possible
            heat_index_f = None
            if temp_f is not None and humidity_pct is not None:
                heat_index_f = self._calculate_heat_index(temp_f, humidity_pct)

            wind_chill_f = None
            if temp_f is not None and wind_mph is not None:
                wind_chill_f = self._calculate_wind_chill(temp_f, wind_mph)

            # Davis stores temps scaled by 10 (e.g., 72.5°F → 725)
            # Create sensor reading
            reading = SensorReadingModel(
                timestamp=ts,
                station_type=16,  # Generic station type
                outside_temp=int(temp_f * 10) if self._is_valid_number(temp_f) else None,
                inside_temp=None,  # Not available from CWOP
                outside_humidity=humidity_pct if self._is_valid_number(humidity_pct) else None,
                inside_humidity=None,
                barometer=int(pressure_inhg * 1000) if self._is_valid_number(pressure_inhg) else None,
                wind_speed=int(wind_mph) if self._is_valid_number(wind_mph) else None,
                wind_direction=int(obs.get('wind_dir')) if self._is_valid_number(obs.get('wind_dir')) else None,
                rain_rate=None,  # Not directly available
                rain_total=int(precip_in * 100) if self._is_valid_number(precip_in) else None,
                solar_radiation=None,
                uv_index=None,
                dew_point=int(dewpoint_f * 10) if self._is_valid_number(dewpoint_f) else None,
                heat_index=int(heat_index_f * 10) if self._is_valid_number(heat_index_f) else None,
                wind_chill=int(wind_chill_f * 10) if self._is_valid_number(wind_chill_f) else None,
            )

            return reading

        except Exception as e:
            print(f"Warning: Could not convert CWOP observation: {e}")
            return None

    def seed_mock_readings(
        self,
        start_time: datetime,
        end_time: datetime,
        interval_seconds: int = 60,
        base_conditions: Optional[Dict[str, float]] = None
    ) -> None:
        """
        Seed mock sensor readings with realistic variations.

        Useful when CWOP data is not available for a test scenario.

        Args:
            start_time: Start of time series
            end_time: End of time series
            interval_seconds: Interval between readings
            base_conditions: Base weather conditions to vary from
        """
        import random

        if base_conditions is None:
            base_conditions = {
                'outside_temp': 72.0,  # °F
                'outside_humidity': 65.0,  # %
                'barometer': 29.92,  # inHg
                'wind_speed': 5.0,  # mph
                'wind_direction': 180.0,  # degrees
            }

        session: Session = self.SessionLocal()

        try:
            current_time = start_time
            count = 0

            while current_time <= end_time:
                # Add realistic variations
                temp = base_conditions['outside_temp'] + random.gauss(0, 2)
                hum = max(0, min(100, base_conditions['outside_humidity'] + random.gauss(0, 5)))
                baro = base_conditions['barometer'] + random.gauss(0, 0.05)
                wspd = max(0, base_conditions['wind_speed'] + random.gauss(0, 2))
                wdir = (base_conditions['wind_direction'] + random.gauss(0, 15)) % 360

                reading = SensorReadingModel(
                    timestamp=current_time,
                    station_type=16,  # Generic station type
                    outside_temp=int(temp * 10),  # Davis scaling: 72.5°F → 725
                    outside_humidity=int(hum),
                    barometer=int(baro * 1000),  # Davis scaling: 29.92 inHg → 29920
                    wind_speed=int(wspd),
                    wind_direction=int(wdir),
                    rain_rate=0,
                    rain_total=0,
                )

                session.add(reading)
                count += 1

                current_time += timedelta(seconds=interval_seconds)

            session.commit()
            print(f"Seeded {count} mock sensor readings")

        finally:
            session.close()

    def clear_tables(self, table_names: Optional[List[str]] = None):
        """
        Clear specified tables or all test data.

        Args:
            table_names: List of table names to clear, or None for all
        """
        session: Session = self.SessionLocal()

        try:
            if table_names is None or 'sensor_readings' in table_names:
                session.query(SensorReadingModel).delete()

            if table_names is None or 'station_config' in table_names:
                session.query(StationConfigModel).delete()

            if table_names is None or 'nowcast_history' in table_names:
                session.query(NowcastHistory).delete()

            session.commit()
            print("Cleared test tables")

        finally:
            session.close()

    def get_reading_count(self) -> int:
        """
        Get count of sensor readings in database.

        Returns:
            Number of sensor readings
        """
        session: Session = self.SessionLocal()
        try:
            count = session.query(SensorReadingModel).count()
            return count
        finally:
            session.close()

    def get_time_range(self) -> Optional[tuple[datetime, datetime]]:
        """
        Get time range of seeded sensor readings.

        Returns:
            Tuple of (earliest, latest) datetime, or None if no readings
        """
        session: Session = self.SessionLocal()
        try:
            readings = session.query(SensorReadingModel).order_by(
                SensorReadingModel.timestamp
            ).all()

            if not readings:
                return None

            # Timestamps are already datetime objects
            earliest = readings[0].timestamp
            latest = readings[-1].timestamp

            return (earliest, latest)

        finally:
            session.close()


# Convenience function for common use case
def seed_test_database(
    db_path: Path,
    lat: float,
    lon: float,
    elevation: float,
    observations: List[Dict[str, Any]],
    config_overrides: Optional[Dict[str, Any]] = None
) -> DatabaseSeeder:
    """
    Seed a test database with station config and observations.

    Args:
        db_path: Path to database file
        lat: Station latitude
        lon: Station longitude
        elevation: Station elevation (feet)
        observations: CWOP observations to seed
        config_overrides: Additional config overrides

    Returns:
        DatabaseSeeder instance
    """
    seeder = DatabaseSeeder(db_path)
    seeder.create_tables()
    seeder.seed_station_config(lat, lon, elevation, config_overrides=config_overrides)
    seeder.seed_sensor_readings(observations)

    return seeder
