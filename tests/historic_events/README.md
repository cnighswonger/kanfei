# Historic NEXRAD Event Testing

This directory contains test infrastructure for validating the **Last-Mile Severe WX Nowcast** feature using historic NEXRAD Level II data, CWOP station observations, and NWS alert archives.

## Overview

The testing framework validates nowcast accuracy across multiple dimensions:

1. **Mesocyclone Detection** - Verify the severe weather correlation protocol detects rotation signatures
2. **Severe Weather Escalation** - Validate model switching, cycle timing, and data archiving
3. **AI Analysis Quality** - Assess Claude's nowcast output accuracy and confidence calibration
4. **End-to-End Events** - Run complete historic event scenarios from start to finish

## Architecture

### Data Sources

- **NEXRAD Level II** - AWS S3 `noaa-nexrad-level2` bucket (1991-present, free access)
- **CWOP Observations** - NOAA MADIS archive (2001-present, netCDF format)
- **NWS Alerts** - IEM archive (2005-present complete, shapefile/CSV format)
- **ASOS/METAR** - IEM archive (1900-present, airport weather stations integrated into runtime simulations)

### Directory Structure

```
tests/historic_events/
├── README.md                   # This file
├── conftest.py                 # pytest configuration
├── events.json                 # Event definitions (8 events)
├── run_realtime_simulation.py  # Real-time event simulation runner
├── seed_*.py                   # Database seeders (per-event)
├── loaders/                    # Data fetching & processing
│   ├── nexrad_loader.py        # AWS S3 NEXRAD Level II retrieval
│   ├── cwop_loader.py          # MADIS CWOP observation retrieval
│   ├── metar_loader.py         # IEM ASOS/METAR airport data
│   ├── nws_alert_loader.py     # IEM NWS alert archive retrieval
│   └── fixture_manager.py      # Smart caching & fixture management
├── fixtures/                   # Test utilities
│   └── database_seeder.py      # Populate test DB with historic data
├── mocks/                      # External API mocks
│   └── api_mocks.py            # Mock NWS, Open-Meteo, IEM RadMap
├── directives/                 # Analyst prompt directives
└── test_results/               # Archived simulation results
```

### Fixture Repository

Large test data (NEXRAD files, CWOP observations) are stored separately in the **nexrad-test-fixtures** repository (or S3 bucket). The `fixture_manager.py` downloads fixtures on-demand and caches them locally in `.test_cache/` (gitignored).

## Installation

Install testing dependencies:

```bash
cd backend
pip install -e ".[testing]"
```

## Usage

### Run All Tests

```bash
pytest tests/historic_events/
```

### Run Specific Stage

```bash
# Stage 2: Mesocyclone detection
pytest tests/historic_events/ -m mesocyclone

# Stage 3: Escalation logic
pytest tests/historic_events/ -m escalation

# Stage 4: AI quality
pytest tests/historic_events/ -m ai_quality

# Stage 5: End-to-end
pytest tests/historic_events/ -m end_to_end
```

### Run Without Slow Tests

```bash
pytest tests/historic_events/ -m "not slow"
```

### Custom Fixture Repository

```bash
export NEXRAD_FIXTURE_REPO="https://your-custom-source.com/fixtures"
pytest tests/historic_events/
```

### Real-Time Event Simulation

The `run_realtime_simulation.py` script runs full end-to-end simulations of historic tornado events, displaying the AI analyst's nowcast output in real-time as if the event were unfolding. See `REALTIME_SIMULATION_README.md` for full details.

#### Usage

```bash
# Run Hattiesburg EF4 tornado simulation
python3 tests/historic_events/run_realtime_simulation.py --event "Hattiesburg EF4 Tornado"

# Accelerate simulation (999x real-time)
python3 tests/historic_events/run_realtime_simulation.py --event "Hattiesburg EF4 Tornado" --speed 999

# Force Grok fallback (skip Claude API)
python3 tests/historic_events/run_realtime_simulation.py --event "Hattiesburg EF4 Tornado" --speed 999 --force-grok

# Override time window
python3 tests/historic_events/run_realtime_simulation.py --event "Hattiesburg EF4 Tornado" --start-time "2013-02-10T20:00:00Z" --end-time "2013-02-10T23:00:00Z"
```

#### Output Features

The simulation displays:
- **Dual Alert Levels**: Both NWS regional alert level and hyper-local Claude threat level
  - `🚨 THREAT LEVEL`: Claude's hyper-local assessment (WATCH/WARNING/EMERGENCY)
  - `📡 NWS ALERT LEVEL`: Regional NWS polygon-based alert level
  - Explanatory notes when levels differ significantly
- **Multi-Mesocyclone Tracking**: Persistent IDs (MESO-1, MESO-2, etc.) across cycles
- **Local Evidence**: Pressure drops, temperature changes, wind shifts
- **Radar Analysis**: Rotation signatures, reflectivity cores, movement vectors
- **Recommended Actions**: Shelter guidance based on threat level

#### Dual Alert Level Philosophy

Claude's hyper-local threat level is **independent** of NWS alert levels:
- **NWS alerts** cover broad polygons (county-sized areas, 10-50+ miles)
- **Claude's assessment** is hyper-local (specific to station location)
- **Claude may assign LOWER threat** than NWS if local conditions don't warrant escalation
  - Example: NWS Tornado Warning active, but mesocyclone is 50 miles away and receding
  - Claude: WATCH | NWS: WARNING (appropriate difference)
- **Users should monitor both**:
  - NWS provides regional context and official warnings
  - Claude provides hyper-local precision for immediate decision-making

#### Simulation Timeline

Simulations run from a configurable approach/departure window relative to closest approach (per-event defaults in `events.json`):
- **Approach phase**: Early detection, WATCH → WARNING escalation
- **Peak danger window**: EMERGENCY expected near closest approach
- **Departure phase**: Receding, de-escalation

#### Output Files

Results are cached in `.test_cache/simulations/realtime_sim_<event>_<timestamp>/`:
- `simulation.log`: Complete debug log (data collection, tracking, API calls, timing)
- `user_output.log`: User-facing nowcast display
- `radar_reflectivity.png`, `radar_velocity.png`, `radar_mesocyclone_composite.png`: Per-cycle radar images

## Development Stages

### ✅ Stage 1: Data Pipeline Infrastructure

Build utilities to retrieve, process, and inject historic data.

**Status**: Complete

### ⏳ Stage 2: Mesocyclone Detection Accuracy

Test classic supercells, TVS, false positives, missed detections.

**Metrics**: POD, FAR, threat level accuracy, ETA accuracy

### ⏳ Stage 3: Severe Weather Escalation Logic

Verify model escalation, mid-cycle regeneration, cycle timing, archiving.

**Metrics**: Escalation trigger accuracy, cycle timing compliance, persistence completeness

### ⏳ Stage 4: AI Analysis Quality

Assess divergence handling, radar analysis, confidence calibration, correlation quality.

**Metrics**: Nowcast skill score, confidence calibration curves, semantic similarity

### ⏳ Stage 5: End-to-End Historic Event Testing

Run Moore 2013, Derecho 2012, flash flood, clear air baseline.

**Metrics**: Event-level verification against NWS Storm Reports

## Event Selection Strategy

1. **Find dense CWOP coverage** around significant events (Oklahoma/Kansas has excellent coverage)
2. **"Move" test station** to a location with good CWOP density
3. **Use multiple nearby CWOP stations** as the "nearby_stations" data source
4. **Select one CWOP station as "local station"** and use its observations as sensor_readings

This creates authentic test scenarios with real observations correlated to real NEXRAD data.

## Contributing

When adding new test events:

1. Add event definition to `events.json` with all required fields
2. Create a seeder script (`seed_<event_name>.py`) to populate the test database
3. Document expected outcomes (POD, threat levels, timing)
4. Run a simulation and archive results in `test_results/`
5. Update this README with event details

## References

- [NOAA MADIS CWOP Data](https://madis.ncep.noaa.gov/madis_cwop.shtml)
- [IEM NWS Alert Archive](https://mesonet.agron.iastate.edu/request/gis/watchwarn.phtml)
- [AWS NEXRAD on S3](https://registry.opendata.aws/noaa-nexrad/)
- [Py-ART Documentation](https://arm-doe.github.io/pyart/)
