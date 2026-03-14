#!/usr/bin/env python3
"""
Seed database with Hattiesburg 2013 EF4 tornado data for real-time simulation.

February 10, 2013: Rare February EF4 through Hattiesburg, MS metro area.
21.65-mile path from Lamar County (Oak Grove) through Hattiesburg/USM to Perry County.
0 fatalities, 82 injuries, $200M+ damage. 170 mph peak winds.

Remarkable for ZERO fatalities despite EF4 through a city of ~150K.
First major event leveraging dual-pol radar (KDGX).

Station placed at Oak Grove (peak EF4 damage zone) for direct-hit simulation.
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

# Station location: Oak Grove, MS (peak EF4 damage zone)
# Near Oak Grove High School where 170 mph winds occurred
HATTIESBURG_LAT = 31.290
HATTIESBURG_LON = -89.410
HATTIESBURG_ELEVATION = 200  # feet ASL

# Simulation timeline
# Tornado touchdown 23:03 UTC in Lamar County
# Peak intensity over Oak Grove ~23:12-23:15 UTC
# Over Hattiesburg/USM ~23:15-23:20 UTC
# Dissipated near Runnelstown ~23:36 UTC
START_TIME = datetime(2013, 2, 10, 22, 0, tzinfo=timezone.utc)
END_TIME = datetime(2013, 2, 11, 0, 30, tzinfo=timezone.utc)

# Tornado closest approach to test station
TORNADO_TIME = datetime(2013, 2, 10, 23, 15, tzinfo=timezone.utc)


def main():
    print("="*80)
    print("Seeding Database for Hattiesburg 2013 EF4 Real-Time Simulation")
    print("="*80)
    print()

    print(f"Event: February 10, 2013 - Hattiesburg EF4 Tornado")
    print(f"  21.65-mile path from Oak Grove through Hattiesburg to Perry Co")
    print(f"  0 fatalities, 82 injuries, $200M+ damage, ~45 mph forward speed")
    print(f"  Station: Oak Grove (peak EF4 zone) - direct hit")
    print(f"  Radar: KDGX (Jackson/Brandon, MS)")
    print(f"Data window: {START_TIME} to {END_TIME}")
    print(f"Tornado time: {TORNADO_TIME}")
    print()

    cache_dir = Path(__file__).parent.parent.parent / '.test_cache'
    db_path = cache_dir / 'hattiesburg_test.db'

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
        lat=HATTIESBURG_LAT,
        lon=HATTIESBURG_LON,
        radius_miles=30
    )

    print(f"  Found {len(observations)} CWOP observations")

    # Fetch METAR/ASOS data to supplement CWOP
    print(f"\nFetching METAR/ASOS observations...")
    metar_loader = METARLoader(cache_dir=cache_dir)
    metar_obs = metar_loader.get_observations(
        start_time=lookback_start,
        end_time=END_TIME,
        lat=HATTIESBURG_LAT,
        lon=HATTIESBURG_LON,
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
        lat=HATTIESBURG_LAT,
        lon=HATTIESBURG_LON,
        elevation=HATTIESBURG_ELEVATION,
        config_overrides={
            'nowcast_api_key': os.environ.get('ANTHROPIC_API_KEY', ''),
            'station_name': 'Oak Grove MS Test Station',
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
    print('  python3 tests/historic_events/run_realtime_simulation.py --event hattiesburg_ef4_tornado')

    return 0


if __name__ == '__main__':
    sys.exit(main())
