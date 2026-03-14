#!/usr/bin/env python3
"""
Seed database with Harnett County 2026 QLCS cold front data for real-time simulation.

March 12, 2026: Sharp cold front with embedded QLCS pushed through central NC.
Severe straight-line winds with visible rotation (no tornado). 20+ degree F
temperature crash across the CWOP network in 30-45 minutes.

Station AD4CG in Harnett County, NC. Ground-truth validated by co-developer
located 7 miles from the station.

Seeds CWOP data for full simulation timeline plus 2hr lookback for trend data.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'backend'))

from loaders.cwop_loader import CWOPLoader
from fixtures.database_seeder import DatabaseSeeder

# AD4CG station location in Harnett County, NC
# Decoded from APRS packet: AD4CG>APRS  @111641z3518.98N/07833.36W
AD4CG_LAT = 35.3163
AD4CG_LON = -78.556
AD4CG_ELEVATION = 230  # feet ASL

# Simulation timeline
# QLCS front passage ~16:00-16:10 UTC (12:00-12:10 PM EDT)
# MESO-3 detected 8.1 km from station at 16:03 UTC
START_TIME = datetime(2026, 3, 12, 15, 0, tzinfo=timezone.utc)
END_TIME = datetime(2026, 3, 12, 17, 30, tzinfo=timezone.utc)

# Closest approach: embedded rotation passed directly over area
CLOSEST_APPROACH = datetime(2026, 3, 12, 16, 3, tzinfo=timezone.utc)


def main():
    print("=" * 80)
    print("Seeding Database for Harnett County 2026 QLCS Real-Time Simulation")
    print("=" * 80)
    print()

    print("Event: March 12, 2026 - Harnett County QLCS / Cold Front")
    print("  Sharp cold front with severe straight-line winds")
    print("  Embedded rotation visible (no funnel dropped)")
    print("  20+ degree F temp crash across station network")
    print(f"  Station: AD4CG ({AD4CG_LAT}, {AD4CG_LON})")
    print(f"  Radar: KRAX (Raleigh, 39 km)")
    print(f"Data window: {START_TIME} to {END_TIME}")
    print(f"Frontal passage: ~{CLOSEST_APPROACH}")
    print()

    cache_dir = Path(__file__).parent.parent.parent / '.test_cache'
    db_path = cache_dir / 'harnett_qlcs_2026_test.db'

    # Remove old database
    if db_path.exists():
        db_path.unlink()
        print("  Removed old database")

    # Load CWOP data - include 2hr lookback for trend baseline
    print("\nFetching CWOP observations...")
    loader = CWOPLoader(cache_dir=cache_dir / 'cwop')

    lookback_start = START_TIME - timedelta(hours=2)
    observations = loader.get_observations(
        start_time=lookback_start,
        end_time=END_TIME,
        lat=AD4CG_LAT,
        lon=AD4CG_LON,
        radius_miles=30
    )

    print(f"  Found {len(observations)} CWOP observations")

    if not observations:
        print("\n  WARNING: No CWOP observations from MADIS archive.")
        print("  The MADIS archive may not yet have data for this date.")
        print("  Try again later or use pre-cached MADIS files.")
        return 1

    # Show station breakdown
    stations = {}
    for obs in observations:
        sid = obs['station_id']
        stations[sid] = stations.get(sid, 0) + 1

    print(f"  Unique stations: {len(stations)}")
    for sid in sorted(stations.keys())[:10]:
        print(f"    {sid}: {stations[sid]} obs")
    if len(stations) > 10:
        print(f"    ... and {len(stations) - 10} more")

    # Select local station - prefer AD4CG-like stations near our coords
    # Pick station with most observations closest to our location
    local_station_id = max(stations, key=stations.get)
    local_observations = [obs for obs in observations if obs['station_id'] == local_station_id]

    print(f"\n  Using '{local_station_id}' as local station")
    print(f"    Observations: {len(local_observations)}")

    # Seed database
    print("\nSeeding database...")
    seeder = DatabaseSeeder(db_path)
    seeder.create_tables()
    seeder.seed_station_config(
        lat=AD4CG_LAT,
        lon=AD4CG_LON,
        elevation=AD4CG_ELEVATION,
        config_overrides={
            'nowcast_api_key': os.environ.get('ANTHROPIC_API_KEY', ''),
            'station_name': 'AD4CG Harnett County NC Test Station',
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
    print('  python3 tests/historic_events/run_realtime_simulation.py '
          '--event "Harnett County QLCS 2026" --speed 999')

    return 0


if __name__ == '__main__':
    sys.exit(main())
