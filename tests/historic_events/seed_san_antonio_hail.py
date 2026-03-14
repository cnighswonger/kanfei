#!/usr/bin/env python3
"""
Seed database with San Antonio 2021 giant hail event data for real-time simulation.

April 28-29, 2021: Record-setting hail event across south-central Texas.
6.4" hailstone at Hondo (TX state record). 2-4" hail across N Bexar County.
Supercell tracked by KEWX radar (New Braunfels, ~50 km NE of SA).

Station placed in north San Antonio for direct-hit simulation.
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

# Station location: North San Antonio (hail target zone)
SA_LAT = 29.4241
SA_LON = -98.4936
SA_ELEVATION = 790  # feet ASL

# Simulation timeline
# Supercell activity began ~2000 UTC Apr 28
# Record hail at Hondo ~0035 UTC Apr 29
# SA metro hail ~0100-0200 UTC Apr 29
START_TIME = datetime(2021, 4, 28, 22, 30, tzinfo=timezone.utc)
END_TIME = datetime(2021, 4, 29, 3, 30, tzinfo=timezone.utc)

# Peak hail at station location
PEAK_HAIL_TIME = datetime(2021, 4, 29, 1, 30, tzinfo=timezone.utc)


def main():
    print("="*80)
    print("Seeding Database for San Antonio 2021 Giant Hail Real-Time Simulation")
    print("="*80)
    print()

    print(f"Event: April 28-29, 2021 - Giant Hail San Antonio")
    print(f"  6.4\" TX state record hailstone at Hondo")
    print(f"  2-4\" hail across N Bexar County")
    print(f"  Station: North San Antonio (hail target zone)")
    print(f"  Radar: KEWX (New Braunfels, TX)")
    print(f"Data window: {START_TIME} to {END_TIME}")
    print(f"Peak hail time: {PEAK_HAIL_TIME}")
    print()

    cache_dir = Path(__file__).parent.parent.parent / '.test_cache'
    db_path = cache_dir / 'san_antonio_hail_test.db'

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
        lat=SA_LAT,
        lon=SA_LON,
        radius_miles=30
    )

    print(f"  Found {len(observations)} CWOP observations")

    # Fetch METAR/ASOS data to supplement CWOP
    print(f"\nFetching METAR/ASOS observations...")
    metar_loader = METARLoader(cache_dir=cache_dir)
    metar_obs = metar_loader.get_observations(
        start_time=lookback_start,
        end_time=END_TIME,
        lat=SA_LAT,
        lon=SA_LON,
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
        lat=SA_LAT,
        lon=SA_LON,
        elevation=SA_ELEVATION,
        config_overrides={
            'nowcast_api_key': os.environ.get('ANTHROPIC_API_KEY', ''),
            'station_name': 'North San Antonio TX Test Station',
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
    print('  python3 tests/historic_events/run_realtime_simulation.py --event giant_hail_san_antonio')

    return 0


if __name__ == '__main__':
    sys.exit(main())
