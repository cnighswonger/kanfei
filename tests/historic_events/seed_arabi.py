#!/usr/bin/env python3
"""
Seed database with Arabi LA 2022 EF3 tornado data for real-time simulation.

March 22, 2022: EF3 tornado, 11.5-mile path from Gretna across the Mississippi
through Lower 9th Ward and Arabi (St. Bernard Parish) to New Orleans East.
Peak 160 mph winds. Strongest tornado on record for New Orleans metro.
1 death, 8 injuries, ~200 structures damaged.

KLIX radar (Slidell, LA) ~25 km ENE of Arabi.

Station placed at Arabi (peak EF3 damage zone) for direct-hit simulation.
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

# Station location: Arabi, St. Bernard Parish (peak EF3 damage zone)
ARABI_LAT = 29.9544
ARABI_LON = -90.0053
ARABI_ELEVATION = 3  # feet ASL (essentially sea level)

# Simulation timeline
# Tornado touched down 0021 UTC Mar 23 at Harvey
# Peak intensity over Arabi ~0030 UTC
# Lifted 0038 UTC near New Orleans East
START_TIME = datetime(2022, 3, 22, 23, 0, tzinfo=timezone.utc)
END_TIME = datetime(2022, 3, 23, 1, 30, tzinfo=timezone.utc)

# Tornado closest approach to test station
TORNADO_TIME = datetime(2022, 3, 23, 0, 30, tzinfo=timezone.utc)


def main():
    print("="*80)
    print("Seeding Database for Arabi 2022 EF3 Real-Time Simulation")
    print("="*80)
    print()

    print(f"Event: March 22, 2022 - Arabi EF3 Tornado")
    print(f"  11.5-mile path from Gretna through Lower 9th Ward/Arabi to NOLA East")
    print(f"  1 fatality, 8 injuries, ~200 structures damaged, 160 mph peak winds")
    print(f"  Strongest tornado on record for New Orleans metro")
    print(f"  Station: Arabi (peak EF3 zone) - direct hit")
    print(f"  Radar: KLIX (Slidell, LA) — ~25 km ENE")
    print(f"Data window: {START_TIME} to {END_TIME}")
    print(f"Tornado time: {TORNADO_TIME}")
    print()

    cache_dir = Path(__file__).parent.parent.parent / '.test_cache'
    db_path = cache_dir / 'arabi_test.db'

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
        lat=ARABI_LAT,
        lon=ARABI_LON,
        radius_miles=30
    )

    print(f"  Found {len(observations)} CWOP observations")

    # Fetch METAR/ASOS data to supplement CWOP
    print(f"\nFetching METAR/ASOS observations...")
    metar_loader = METARLoader(cache_dir=cache_dir)
    metar_obs = metar_loader.get_observations(
        start_time=lookback_start,
        end_time=END_TIME,
        lat=ARABI_LAT,
        lon=ARABI_LON,
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
        lat=ARABI_LAT,
        lon=ARABI_LON,
        elevation=ARABI_ELEVATION,
        config_overrides={
            'nowcast_api_key': os.environ.get('ANTHROPIC_API_KEY', ''),
            'station_name': 'Arabi LA Test Station',
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
    print('  python3 tests/historic_events/run_realtime_simulation.py --event arabi_ef3_tornado')

    return 0


if __name__ == '__main__':
    sys.exit(main())
