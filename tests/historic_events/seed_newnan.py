#!/usr/bin/env python3
"""
Seed database with Newnan GA 2021 EF4 tornado data for real-time simulation.

March 25-26, 2021: Violent nocturnal EF4 tornado across Heard/Coweta/Fayette counties.
39-mile path, 170 mph peak winds on SW side of Newnan. 1,700 homes damaged.
KFFC radar (Peachtree City) only ~20 km east — excellent radar proximity.

Station placed at Newnan city center (peak EF4 damage zone) for direct-hit simulation.
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

# Station location: Newnan, GA (peak EF4 damage zone)
NEWNAN_LAT = 33.3807
NEWNAN_LON = -84.7997
NEWNAN_ELEVATION = 970  # feet ASL

# Simulation timeline
# Tornado touched down 0337 UTC in Heard County
# Peak intensity over Newnan ~0406 UTC
# Lifted 0430 UTC near Tyrone/Peachtree City
START_TIME = datetime(2021, 3, 26, 2, 30, tzinfo=timezone.utc)
END_TIME = datetime(2021, 3, 26, 5, 30, tzinfo=timezone.utc)

# Tornado closest approach to test station
TORNADO_TIME = datetime(2021, 3, 26, 4, 6, tzinfo=timezone.utc)


def main():
    print("="*80)
    print("Seeding Database for Newnan 2021 EF4 Real-Time Simulation")
    print("="*80)
    print()

    print(f"Event: March 25-26, 2021 - Newnan EF4 Tornado")
    print(f"  39-mile path from Heard Co through Newnan to Fayette Co")
    print(f"  1 indirect fatality, 1700 homes damaged, 170 mph peak winds")
    print(f"  Station: Newnan city center (peak EF4 zone) - direct hit")
    print(f"  Radar: KFFC (Peachtree City, GA) — ~20 km away")
    print(f"Data window: {START_TIME} to {END_TIME}")
    print(f"Tornado time: {TORNADO_TIME}")
    print()

    cache_dir = Path(__file__).parent.parent.parent / '.test_cache'
    db_path = cache_dir / 'newnan_test.db'

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
        lat=NEWNAN_LAT,
        lon=NEWNAN_LON,
        radius_miles=30
    )

    print(f"  Found {len(observations)} CWOP observations")

    # Fetch METAR/ASOS data to supplement CWOP
    print(f"\nFetching METAR/ASOS observations...")
    metar_loader = METARLoader(cache_dir=cache_dir)
    metar_obs = metar_loader.get_observations(
        start_time=lookback_start,
        end_time=END_TIME,
        lat=NEWNAN_LAT,
        lon=NEWNAN_LON,
        radius_miles=50
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
        local_station_id = max(cwop_stations, key=cwop_stations.get)
    else:
        local_station_id = max(stations, key=stations.get)

    local_observations = [obs for obs in observations if obs['station_id'] == local_station_id]

    print(f"\n  Using '{local_station_id}' as local station")
    print(f"    Observations: {len(local_observations)}")

    # Seed database
    print(f"\nSeeding database...")
    seeder = DatabaseSeeder(db_path)
    seeder.create_tables()
    seeder.seed_station_config(
        lat=NEWNAN_LAT,
        lon=NEWNAN_LON,
        elevation=NEWNAN_ELEVATION,
        config_overrides={
            'nowcast_api_key': os.environ.get('ANTHROPIC_API_KEY', ''),
            'station_name': 'Newnan GA Test Station',
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
    print('  python3 tests/historic_events/run_realtime_simulation.py --event newnan_ef4_tornado')

    return 0


if __name__ == '__main__':
    sys.exit(main())
