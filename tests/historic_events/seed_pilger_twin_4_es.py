#!/usr/bin/env python3
"""
Seed database with Pilger 2014 twin tornadoes data for real-time simulation.

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

# Pilger event details
PILGER_LAT = 42.0094
PILGER_LON = -97.0542
PILGER_ELEVATION = 1500  # Nebraska elevation (~1500 ft)

# Simulation timeline
# Event closest_approach is 21:00 UTC, simulation starts at T-2hr = 19:00 UTC
START_TIME = datetime(2014, 6, 16, 19, 0, tzinfo=timezone.utc)
END_TIME = datetime(2014, 6, 16, 23, 0, tzinfo=timezone.utc)  # Full event through post-tornado

# Tornado time (twin tornadoes)
TORNADO_TIME = datetime(2014, 6, 16, 21, 0, tzinfo=timezone.utc)


def main():
    print("="*80)
    print("Seeding Database for Pilger Twin Tornadoes Real-Time Simulation")
    print("="*80)
    print()

    print(f"Event: Pilger 2014 Twin EF4 Tornadoes")
    print(f"Data window: {START_TIME} to {END_TIME}")
    print(f"Tornado time: {TORNADO_TIME}")
    print()

    cache_dir = Path(__file__).parent.parent.parent / '.test_cache'
    db_path = cache_dir / 'pilger_test.db'

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
        lat=PILGER_LAT,
        lon=PILGER_LON,
        radius_miles=25
    )

    print(f"  Found {len(observations)} CWOP observations")

    # Fetch METAR/ASOS data to supplement CWOP
    print(f"\nFetching METAR/ASOS observations...")
    metar_loader = METARLoader(cache_dir=cache_dir)
    metar_obs = metar_loader.get_observations(
        start_time=lookback_start,
        end_time=END_TIME,
        lat=PILGER_LAT,
        lon=PILGER_LON,
        radius_miles=50  # Wider radius for airports
    )

    print(f"  Found {len(metar_obs)} METAR observations")

    # Combine CWOP + METAR
    observations.extend(metar_obs)
    print(f"\n✓ Total observations: {len(observations)} (CWOP + METAR)")

    if not observations:
        print("\n❌ ERROR: No observations found from any source!")
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
        print(f"    ... and {len(stations) - 5} more")

    # Select local station (just use the one we found)
    local_station_id = list(stations.keys())[0]
    local_observations = [obs for obs in observations if obs['station_id'] == local_station_id]

    print(f"\n  Using '{local_station_id}' as local station")
    print(f"    Observations: {len(local_observations)}")

    # Seed database
    print(f"\nSeeding database...")
    seeder = DatabaseSeeder(db_path)
    seeder.create_tables()
    seeder.seed_station_config(
        lat=PILGER_LAT,
        lon=PILGER_LON,
        elevation=PILGER_ELEVATION,
        config_overrides={
            'nowcast_api_key': os.environ.get('ANTHROPIC_API_KEY', ''),
            'station_name': 'Pilger Test Station',
        }
    )
    seeder.seed_sensor_readings(local_observations)

    print()
    print("✅ Database seeding complete!")
    print(f"   Database: {db_path}")
    print(f"   Observations: {len(observations)}")
    print(f"   Stations: {len(stations)}")
    print()
    print("Ready to run: python3 tests/historic_events/run_realtime_simulation.py --event \"Pilger Twin EF4 Tornadoes\" --speed 999")

    return 0


if __name__ == '__main__':
    sys.exit(main())
