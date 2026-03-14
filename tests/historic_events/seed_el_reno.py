#!/usr/bin/env python3
"""
Seed database with El Reno 2013 data for real-time simulation.

Seeds CWOP data for full simulation timeline (21:00 UTC - 01:00 UTC)
plus 3hr lookback for trend data.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'backend'))

from loaders.cwop_loader import CWOPLoader
from fixtures.database_seeder import DatabaseSeeder

# El Reno event details
EL_RENO_LAT = 35.5331
EL_RENO_LON = -97.9506
EL_RENO_ELEVATION = 1400  # El Reno area elevation (~1400 ft)

# Simulation timeline
# Event closest_approach is 23:00 UTC, simulation starts at T-2hr = 21:00 UTC
START_TIME = datetime(2013, 5, 31, 21, 0, tzinfo=timezone.utc)
END_TIME = datetime(2013, 6, 1, 1, 0, tzinfo=timezone.utc)  # Full event through post-tornado

# Tornado time (widest on record, rapid expansion)
TORNADO_TIME = datetime(2013, 5, 31, 23, 0, tzinfo=timezone.utc)


def main():
    print("="*80)
    print("Seeding Database for El Reno Real-Time Simulation")
    print("="*80)
    print()

    print(f"Event: El Reno 2013 EF3 Tornado (widest on record)")
    print(f"Data window: {START_TIME} to {END_TIME}")
    print(f"Tornado time: {TORNADO_TIME}")
    print()

    cache_dir = Path(__file__).parent.parent.parent / '.test_cache'
    db_path = cache_dir / 'el_reno_test.db'

    # Remove old database
    if db_path.exists():
        db_path.unlink()
        print(f"✓ Removed old database")

    # Load CWOP data - include 3hr lookback for trend
    print(f"\nFetching CWOP observations...")
    loader = CWOPLoader(cache_dir=cache_dir)

    lookback_start = START_TIME - timedelta(hours=3)
    observations = loader.get_observations(
        start_time=lookback_start,
        end_time=END_TIME,
        lat=EL_RENO_LAT,
        lon=EL_RENO_LON,
        radius_miles=25
    )

    print(f"  Found {len(observations)} observations")

    if not observations:
        print("\n❌ ERROR: No observations found!")
        return 1

    # Show station breakdown
    stations = {}
    for obs in observations:
        sid = obs['station_id']
        stations[sid] = stations.get(sid, 0) + 1

    print(f"  Unique stations: {len(stations)}")
    for sid in sorted(stations.keys())[:5]:
        print(f"    {sid}: {stations[sid]} obs")
    if len(stations) > 5:
        print(f"    ... and {len(stations)-5} more")

    # Select CLOSEST station to El Reno for "local station"
    import math

    def haversine_miles(lat1, lon1, lat2, lon2):
        """Calculate great-circle distance in miles."""
        R = 3958.8  # Earth radius in miles
        rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat/2)**2 +
             math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon/2)**2)
        c = 2 * math.asin(math.sqrt(a))
        return R * c

    # Calculate distance and bearing for each station
    station_info = {}
    for obs in observations:
        sid = obs['station_id']
        if sid not in station_info and 'latitude' in obs and 'longitude' in obs:
            dist = haversine_miles(EL_RENO_LAT, EL_RENO_LON, obs['latitude'], obs['longitude'])
            # Calculate bearing (0°=N, 90°=E, 180°=S, 270°=W)
            dlon = obs['longitude'] - EL_RENO_LON
            dlat = obs['latitude'] - EL_RENO_LAT
            bearing = math.degrees(math.atan2(dlon, dlat))
            if bearing < 0:
                bearing += 360
            station_info[sid] = {
                'distance': dist,
                'bearing': bearing,
                'lat': obs['latitude'],
                'lon': obs['longitude']
            }

    if not station_info:
        print("\n  ❌ ERROR: No stations have lat/lon data!")
        return 1

    # El Reno tornado moved E-NE, so prefer station with good data coverage
    # Just pick closest station with most observations
    local_station_id = max(station_info.items(),
                          key=lambda x: (stations[x[0]], -x[1]['distance']))[0]

    local_distance = station_info[local_station_id]['distance']
    local_bearing = station_info[local_station_id]['bearing']
    local_obs_count = stations[local_station_id]

    print(f"\n  Selecting '{local_station_id}' as local station:")
    print(f"    Distance from El Reno: {local_distance:.2f} miles")
    print(f"    Bearing from El Reno: {local_bearing:.1f}°")
    print(f"    Observations: {local_obs_count}")

    # Show other nearby stations for context
    print(f"\n  Other nearby stations:")
    sorted_stations = sorted(station_info.items(), key=lambda x: x[1]['distance'])
    for sid, info in sorted_stations[:6]:  # Show 6 closest
        if sid != local_station_id:
            print(f"    {sid}: {info['distance']:.2f} mi @ {info['bearing']:.0f}° ({stations[sid]} obs)")

    # Filter to only the local station's observations
    local_observations = [obs for obs in observations if obs['station_id'] == local_station_id]

    print(f"\n  Filtered: {len(observations)} total → {len(local_observations)} from local station")

    # Seed database
    print(f"\nSeeding database...")
    seeder = DatabaseSeeder(db_path)
    seeder.create_tables()
    seeder.seed_station_config(
        lat=EL_RENO_LAT,
        lon=EL_RENO_LON,
        elevation=EL_RENO_ELEVATION,
        config_overrides={
            'nowcast_api_key': os.environ.get('ANTHROPIC_API_KEY', ''),
            'station_name': 'El Reno Test Station',
        }
    )
    seeder.seed_sensor_readings(local_observations)

    reading_count = seeder.get_reading_count()
    time_range = seeder.get_time_range()

    print(f"  ✓ Created tables")
    print(f"  ✓ Seeded config")
    print(f"  ✓ Seeded {reading_count} readings")

    if time_range:
        earliest, latest = time_range
        duration = (latest - earliest).total_seconds() / 3600
        print(f"  ✓ Time range: {earliest} to {latest} ({duration:.1f} hours)")

    print()
    print("="*80)
    print("Database ready!")
    print("="*80)
    print()
    print(f"Database path: {db_path}")
    print()
    print("Next step:")
    print("  cd tests/historic_events")
    print("  python3 run_realtime_simulation.py --event 'El Reno EF3 Tornado' --speed 999")
    print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
