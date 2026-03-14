#!/usr/bin/env python3
"""
Seed database with Dunn/KG4AGD 2011 EF3 tornado data for real-time simulation.

April 16, 2011: Fayetteville-Smithfield EF3 tornado, 58.5-mile path from Hoke County
through Fayetteville (Cumberland Co), Dunn (Harnett Co), to Smithfield (Johnston Co).
3 fatalities, $141M damage. Part of NC's record 32-tornado outbreak.

Station KG4AGD (AV021) in Dunn took a direct hit at ~20:20 UTC (4:20 PM EDT).
This is a SEPARATE supercell from the Sanford-Raleigh EF3 that was tracked simultaneously.

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

# KG4AGD station location in Dunn, NC (Harnett County)
# Coordinates from findu.com: http://www.findu.com/cgi-bin/wxpage.cgi?call=kg4agd
DUNN_LAT = 35.3530
DUNN_LON = -78.5578
DUNN_ELEVATION = 229  # feet ASL

# Simulation timeline
# Tornado touchdown ~19:33 UTC in Hoke County, closest approach to Dunn ~20:20 UTC
# Dissipated near Smithfield ~20:45 UTC
START_TIME = datetime(2011, 4, 16, 18, 20, tzinfo=timezone.utc)
END_TIME = datetime(2011, 4, 16, 22, 20, tzinfo=timezone.utc)

# Tornado closest approach to KG4AGD station
TORNADO_TIME = datetime(2011, 4, 16, 20, 20, tzinfo=timezone.utc)


def main():
    print("="*80)
    print("Seeding Database for Dunn/KG4AGD 2011 EF3 Real-Time Simulation")
    print("="*80)
    print()

    print(f"Event: April 16, 2011 - Fayetteville-Smithfield EF3 Tornado")
    print(f"  58.5-mile long-track from Hoke Co through Dunn to Smithfield")
    print(f"  3 fatalities, $141M damage, ~49 mph forward speed")
    print(f"  Station: KG4AGD (AV021) - direct hit")
    print(f"  Radar: KRAX (Raleigh)")
    print(f"Data window: {START_TIME} to {END_TIME}")
    print(f"Tornado time: {TORNADO_TIME}")
    print()

    cache_dir = Path(__file__).parent.parent.parent / '.test_cache'
    db_path = cache_dir / 'dunn_kg4agd_test.db'

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
        lat=DUNN_LAT,
        lon=DUNN_LON,
        radius_miles=30
    )

    print(f"  Found {len(observations)} CWOP observations")

    # Fetch METAR/ASOS data to supplement CWOP
    print(f"\nFetching METAR/ASOS observations...")
    metar_loader = METARLoader(cache_dir=cache_dir)
    metar_obs = metar_loader.get_observations(
        start_time=lookback_start,
        end_time=END_TIME,
        lat=DUNN_LAT,
        lon=DUNN_LON,
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
        lat=DUNN_LAT,
        lon=DUNN_LON,
        elevation=DUNN_ELEVATION,
        config_overrides={
            'nowcast_api_key': os.environ.get('ANTHROPIC_API_KEY', ''),
            'station_name': 'KG4AGD Dunn NC Test Station',
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
    print('  python3 tests/historic_events/run_realtime_simulation.py --event "Dunn KG4AGD EF3 Tornado" --speed 999')

    return 0


if __name__ == '__main__':
    sys.exit(main())
