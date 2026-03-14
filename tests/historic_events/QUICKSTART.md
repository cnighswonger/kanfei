
# Quick Start - Validate Pipeline with Moore 2013

This guide walks through validating the testing infrastructure with the **Moore, OK Tornado (May 20, 2013)** - one of the most well-documented severe weather events with excellent data coverage.

## Event Details

- **Date**: May 20, 2013
- **Time**: ~19:45 - 20:30 UTC (2:45 PM - 3:30 PM CDT)
- **Location**: Moore, Oklahoma (35.3396°N, 97.4867°W)
- **Event**: EF5 tornado, 17 miles long, 1.3 miles wide at peak
- **NEXRAD**: KTLX (Oklahoma City radar, ~13 miles from Moore)
- **Deaths**: 24, Injuries: 377, Damage: $2 billion

## Prerequisites

1. **Install testing dependencies**:
   ```bash
   cd backend
   pip install -e ".[testing]"
   ```

2. **Verify imports work**:
   ```bash
   cd tests/historic_events
   python -c "from loaders.nexrad_loader import NEXRADLoader; print('OK')"
   ```

## Step 1: Download NEXRAD Data

```python
from loaders.nexrad_loader import NEXRADLoader
from datetime import datetime, timezone
from pathlib import Path

# Initialize loader
loader = NEXRADLoader(cache_dir=Path('.test_cache/nexrad'))

# Moore tornado timeframe
start_time = datetime(2013, 5, 20, 19, 45, tzinfo=timezone.utc)
end_time = datetime(2013, 5, 20, 20, 30, tzinfo=timezone.utc)

# List available files
files = loader.list_files('KTLX', start_time, end_time)
print(f"Found {len(files)} NEXRAD files")

# Download first file (smallest - just for testing)
if files:
    file_path = loader.download_file(files[0])
    print(f"Downloaded: {file_path}")

    # Read and process
    radar = loader.read_radar(file_path)
    products = loader.extract_products(radar)

    print(f"Products: {list(products.keys())}")

    # Check for mesocyclone signatures
    detections = loader.detect_mesocyclone_candidates(radar)
    print(f"Mesocyclone candidates: {len(detections)}")
    for det in detections:
        print(f"  Elev {det['elevation_angle']:.1f}°: shear={det['max_shear']:.4f} s^-1")
```

## Step 2: Download NWS Alerts

```python
from loaders.nws_alert_loader import NWSAlertLoader
from datetime import datetime, timezone
from pathlib import Path

loader = NWSAlertLoader(cache_dir=Path('.test_cache/nws_alerts'))

lat, lon = 35.3396, -97.4867
start_time = datetime(2013, 5, 20, 19, 0, tzinfo=timezone.utc)
end_time = datetime(2013, 5, 20, 21, 0, tzinfo=timezone.utc)

# Get tornado warnings
warnings = loader.get_tornado_warnings(lat, lon, start_time, end_time)
print(f"Found {len(warnings)} tornado warning(s)")

for warning in warnings:
    print(f"  {warning['phenomena']} {warning['significance']}")
    print(f"  WFO: {warning['wfo']}, Event: {warning['event_id']}")
    print(f"  Issued: {warning.get('issue_time')}")
```

## Step 3: Download CWOP Observations

```python
from loaders.cwop_loader import CWOPLoader
from datetime import datetime, timezone
from pathlib import Path

loader = CWOPLoader(cache_dir=Path('.test_cache/cwop'))

lat, lon = 35.3396, -97.4867
start_time = datetime(2013, 5, 20, 19, 0, tzinfo=timezone.utc)
end_time = datetime(2013, 5, 20, 21, 0, tzinfo=timezone.utc)

# Get observations within 50 miles
observations = loader.get_observations(
    start_time, end_time,
    lat, lon,
    radius_miles=50
)

print(f"Found {len(observations)} observations")

# Show unique stations
stations = set(obs['station_id'] for obs in observations)
print(f"Stations: {len(stations)}")
print(f"Sample: {list(stations)[:5]}")

# Show sample observations
for obs in observations[:3]:
    print(f"\n{obs['station_id']} @ {obs['timestamp']}")
    if obs.get('temperature'):
        print(f"  Temp: {obs['temperature']:.1f}°C, Dewpoint: {obs.get('dewpoint', 'N/A'):.1f}°C")
    if obs.get('pressure'):
        print(f"  Pressure: {obs['pressure']:.1f} mb")
    if obs.get('wind_speed'):
        print(f"  Wind: {obs['wind_speed']:.1f} m/s @ {obs.get('wind_dir', 'N/A'):.0f}°")
```

## Step 4: Seed Test Database

```python
from fixtures.database_seeder import seed_test_database
from pathlib import Path

# Assuming you have 'observations' from Step 3
db_path = Path('.test_cache/moore_2013.db')

seeder = seed_test_database(
    db_path,
    lat=35.3396,
    lon=-97.4867,
    elevation=1200,  # Moore elevation in feet
    observations=observations[:100],  # Use subset for testing
    config_overrides={
        'nowcast_enabled': True,
        'nowcast_radar_enabled': True,
    }
)

print(f"Database: {db_path}")
print(f"Readings: {seeder.get_reading_count()}")

time_range = seeder.get_time_range()
if time_range:
    print(f"Range: {time_range[0]} to {time_range[1]}")
```

## Step 5: Run Integration Test

```bash
# Run the full pipeline demo
pytest tests/historic_events/test_integration.py::TestPipelineIntegration::test_full_pipeline_demo -v -s

# Or run all integration tests
pytest tests/historic_events/test_integration.py -v
```

## Expected Results

### NEXRAD Data
- Should find **~40-50 volume scans** in the 45-minute window
- Each file is **~10-30 MB** compressed
- Should detect **strong rotation signatures** (shear >0.01 s^-1) at multiple elevations
- Classic **hook echo** visible in reflectivity

### NWS Alerts
- **Tornado Warning** issued by WFO OUN (Norman, OK)
- Should show **PDS (Particularly Dangerous Situation)** flag
- Multiple warning updates as tornado tracked through area

### CWOP Observations
- Should find **20-50 stations** within 50 miles (Oklahoma has excellent coverage)
- Stations should show:
  - **Rapid pressure drop** before tornado passage
  - **Wind shift** during passage
  - **Temperature drop** in some locations (outflow)

### Database
- **100+ sensor readings** seeded (if using full CWOP data)
- Readings spaced **~5-15 minutes** apart (MADIS 5-min updates)
- Time range covering **at least 2 hours**

## Troubleshooting

### "boto3 not found"
```bash
pip install boto3 s3fs
```

### "netCDF4 not found"
```bash
pip install netCDF4
```

### "geopandas not found"
```bash
pip install geopandas shapely
```

### "Could not import app models"
Make sure you're running from the correct directory:
```bash
cd /home/manager/git_repos/kanfei_test/kanfei/tests/historic_events
python -c "import sys; sys.path.insert(0, '../../backend'); from app.models.sensor_reading import SensorReadingModel; print('OK')"
```

### NEXRAD download is slow
Level II files are large (10-30 MB each). First download will take time, but files are cached in `.test_cache/nexrad/` for subsequent runs.

### MADIS access fails
MADIS may have availability issues or require registration in the future. If CWOP data is unavailable, use the mock data fallback:
```python
seeder.seed_mock_readings(start_time, end_time, interval_seconds=300)
```

## Next Steps

Once the pipeline validates successfully:

1. **Create event fixture** - Package downloaded data into the nexrad-test-fixtures repo
2. **Build test case** - Write a formal test that uses this event data
3. **Add verification** - Compare nowcast output against known storm behavior
4. **Expand coverage** - Add more events (derecho, flash flood, clear air)

## Reference Links

- [Moore Tornado Summary (NWS Norman)](https://www.weather.gov/oun/events-20130520)
- [NEXRAD Archive Browser](https://www.ncdc.noaa.gov/nexradinv/)
- [Storm Events Database](https://www.ncdc.noaa.gov/stormevents/)
- [IEM Archive](https://mesonet.agron.iastate.edu/archive/)
