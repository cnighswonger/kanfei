#!/usr/bin/env python3
"""
Seed database with Tuscaloosa 2011 EF4 tornado data for real-time simulation.

April 27, 2011: Part of the historic 2011 Super Outbreak — deadliest US tornado
outbreak since 1925. The Tuscaloosa-Birmingham tornado was a massive 1.5-mile-wide
wedge that struck Tuscaloosa around 5:13 PM CDT (22:13 UTC), traveled 80.7 miles
through Birmingham metro. 64 fatalities, 1500+ injuries. Peak winds estimated 190 mph.

Path: Greene County → Tuscaloosa → Birmingham → St. Clair County
Forward speed ~50 mph. On the ground for ~80 minutes.

Station placed at Tuscaloosa (University of Alabama area) for direct-hit simulation.
Seeds CWOP data for full simulation timeline plus 3hr lookback for trend data.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'backend'))

from loaders.cwop_loader import CWOPLoader
from loaders.metar_loader import METARLoader
from fixtures.database_seeder import DatabaseSeeder

# Station location: Tuscaloosa, AL (University of Alabama area)
# Tornado passed directly through this area at EF4 intensity
TUSCALOOSA_LAT = 33.2098
TUSCALOOSA_LON = -87.5692
TUSCALOOSA_ELEVATION = 230  # feet ASL

# Simulation timeline
# Tornado touched down in Greene County ~21:53 UTC (4:53 PM CDT)
# Hit Tuscaloosa ~22:10-22:16 UTC (5:10-5:16 PM CDT)
# Hit Birmingham ~22:43-22:50 UTC
# Lifted in St. Clair County ~23:13 UTC
START_TIME = datetime(2011, 4, 27, 20, 10, tzinfo=timezone.utc)
END_TIME = datetime(2011, 4, 28, 0, 10, tzinfo=timezone.utc)

# Tornado closest approach to test station
TORNADO_TIME = datetime(2011, 4, 27, 22, 10, tzinfo=timezone.utc)


def main():
    print("="*80)
    print("Seeding Database for Tuscaloosa 2011 EF4 Real-Time Simulation")
    print("="*80)
    print()

    print(f"Event: April 27, 2011 - Tuscaloosa-Birmingham EF4 Tornado")
    print(f"  80.7-mile path from Greene County through Tuscaloosa to St. Clair Co")
    print(f"  64 fatalities, 1500+ injuries, 1.5 mi wide, 190 mph peak")
    print(f"  Station: Tuscaloosa (UA campus area) - direct hit")
    print(f"  Radar: KBMX (Birmingham, AL)")
    print(f"Data window: {START_TIME} to {END_TIME}")
    print(f"Tornado time: {TORNADO_TIME}")
    print()

    cache_dir = Path(__file__).parent.parent.parent / '.test_cache'
    db_path = cache_dir / 'tuscaloosa_test.db'

    # Remove old database
    if db_path.exists():
        db_path.unlink()
        print(f"  Removed old database")

    # Load CWOP data - include 3hr lookback for trend
    print(f"\nFetching CWOP observations...")
    loader = CWOPLoader(cache_dir=cache_dir)

    lookback_start = START_TIME - timedelta(hours=3)
    observations = loader.get_observations(
        start_time=lookback_start,
        end_time=END_TIME,
        lat=TUSCALOOSA_LAT,
        lon=TUSCALOOSA_LON,
        radius_miles=30
    )

    print(f"  Found {len(observations)} CWOP observations")

    # Fetch METAR/ASOS data to supplement CWOP
    print(f"\nFetching METAR/ASOS observations...")
    metar_loader = METARLoader(cache_dir=cache_dir)
    metar_obs = metar_loader.get_observations(
        start_time=lookback_start,
        end_time=END_TIME,
        lat=TUSCALOOSA_LAT,
        lon=TUSCALOOSA_LON,
        radius_miles=50  # Wider radius for airports
    )

    print(f"  Found {len(metar_obs)} METAR observations")

    # Combine CWOP + METAR
    observations.extend(metar_obs)
    print(f"\n  Total observations: {len(observations)} (CWOP + METAR)")

    if not observations:
        print("\n  ERROR: No observations found from any source!")
        return 1

    # Show station breakdown
    stations = {}
    for obs in observations:
        sid = obs['station_id']
        stations[sid] = stations.get(sid, 0) + 1

    print(f"  Unique stations: {len(stations)}")
    for sid in sorted(stations.keys())[:10]:
        source = next((obs.get('source', 'CWOP') for obs in observations if obs['station_id'] == sid), 'CWOP')
        print(f"    {sid}: {stations[sid]} obs ({source})")
    if len(stations) > 10:
        print(f"    ... and {len(stations) - 10} more")

    # Select local station (prefer CWOP over METAR for local readings)
    cwop_stations = {sid: count for sid, count in stations.items()
                     if not any(obs['station_id'] == sid and obs.get('source') == 'METAR'
                               for obs in observations)}
    if cwop_stations:
        # Pick CWOP station with most observations
        local_station_id = max(cwop_stations, key=cwop_stations.get)
    else:
        # Fall back to any station with most observations
        local_station_id = max(stations, key=stations.get)

    local_observations = [obs for obs in observations if obs['station_id'] == local_station_id]

    print(f"\n  Using '{local_station_id}' as local station")
    print(f"    Observations: {len(local_observations)}")

    # Seed database
    print(f"\nSeeding database...")
    seeder = DatabaseSeeder(db_path)
    seeder.create_tables()
    seeder.seed_station_config(
        lat=TUSCALOOSA_LAT,
        lon=TUSCALOOSA_LON,
        elevation=TUSCALOOSA_ELEVATION,
        config_overrides={
            'nowcast_api_key': os.environ.get('ANTHROPIC_API_KEY', ''),
            'station_name': 'Tuscaloosa AL Test Station',
        }
    )
    seeder.seed_sensor_readings(local_observations)

    print()
    print("  Database seeding complete!")
    print(f"   Database: {db_path}")
    print(f"   Observations: {len(observations)}")
    print(f"   Stations: {len(stations)}")
    print()
    print("Ready to run:")
    print('  python3 tests/historic_events/run_realtime_simulation.py --event tuscaloosa_ef4_tornado')

    return 0


if __name__ == '__main__':
    sys.exit(main())
