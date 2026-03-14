#!/usr/bin/env python3
"""
Seed database with Sanford-Raleigh 2011 EF3 tornado data for real-time simulation.

April 16, 2011: Long-track EF3 tornado from Moore County through Sanford (Lee County)
to downtown Raleigh (Wake County). 63-mile path, 5 fatalities, $172M damage.
First East Coast test event for geographic diversity.

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

# Sanford, NC - along tornado path where EF3 damage was worst
SANFORD_LAT = 35.48
SANFORD_LON = -79.18
SANFORD_ELEVATION = 350  # feet ASL (Piedmont NC)

# Simulation timeline
# Tornado touchdown ~18:53 UTC in Moore County, closest approach to Sanford ~19:15 UTC
START_TIME = datetime(2011, 4, 16, 17, 0, tzinfo=timezone.utc)
END_TIME = datetime(2011, 4, 16, 21, 30, tzinfo=timezone.utc)

# Tornado closest approach to Sanford
TORNADO_TIME = datetime(2011, 4, 16, 19, 15, tzinfo=timezone.utc)


def main():
    print("="*80)
    print("Seeding Database for Sanford-Raleigh 2011 EF3 Real-Time Simulation")
    print("="*80)
    print()

    print(f"Event: April 16, 2011 - Sanford-Raleigh EF3 Tornado")
    print(f"  63-mile long-track from Moore Co through Sanford to Raleigh")
    print(f"  5 fatalities, $172M damage")
    print(f"  Radar: KRAX (Raleigh)")
    print(f"Data window: {START_TIME} to {END_TIME}")
    print(f"Tornado time: {TORNADO_TIME}")
    print()

    cache_dir = Path(__file__).parent.parent.parent / '.test_cache'
    db_path = cache_dir / 'sanford_raleigh_test.db'

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
        lat=SANFORD_LAT,
        lon=SANFORD_LON,
        radius_miles=30  # Slightly wider for NC Piedmont coverage
    )

    print(f"  Found {len(observations)} CWOP observations")

    # Fetch METAR/ASOS data to supplement CWOP
    print(f"\nFetching METAR/ASOS observations...")
    metar_loader = METARLoader(cache_dir=cache_dir)
    metar_obs = metar_loader.get_observations(
        start_time=lookback_start,
        end_time=END_TIME,
        lat=SANFORD_LAT,
        lon=SANFORD_LON,
        radius_miles=50  # Wider radius for airports (RDU, FAY, etc.)
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
        lat=SANFORD_LAT,
        lon=SANFORD_LON,
        elevation=SANFORD_ELEVATION,
        config_overrides={
            'nowcast_api_key': os.environ.get('ANTHROPIC_API_KEY', ''),
            'station_name': 'Sanford-Raleigh Test Station',
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
    print('  python3 tests/historic_events/run_realtime_simulation.py --event "Sanford-Raleigh EF3 Tornado" --speed 999')

    return 0


if __name__ == '__main__':
    sys.exit(main())
