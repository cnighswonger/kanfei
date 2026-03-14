# Real-Time Event Simulation

## Overview

This script simulates the Kanfei nowcast feature running during a historic severe weather event in **real-time**. It accurately reproduces production behavior including cycle timing, model escalation, and mid-cycle regeneration.

## What It Does

1. **Starts 2 hours before event** - Shows normal baseline conditions
2. **15-minute cycle timing** - Default nowcast interval
3. **Detects NWS alerts** - Automatic escalation when severe weather approaches
4. **5-minute rapid cycles** - During Extreme/Severe NWS alerts
5. **Model escalation** - Haiku → Sonnet during severe weather
6. **Mid-cycle regeneration** - Immediate update when NEW alerts arrive
7. **Live output** - Timestamped user-facing content as it would appear in the app
8. **Detailed logging** - Complete debug logs for post-event analysis

## Execution Instructions

### 1. Navigate to test directory
```bash
cd /home/manager/git_repos/kanfei_test/kanfei/tests/historic_events
```

### 2. Seed the database (if not already done)
```bash
python3 seed_hattiesburg.py    # or seed_moore_minimal.py, seed_dunn_kg4agd.py, etc.
```

### 3. Run simulation
```bash
# Real-time (cycles every 15min / 5min during alerts)
python3 run_realtime_simulation.py --event "Hattiesburg EF4 Tornado"

# Accelerated (999x = minimal wait between cycles)
python3 run_realtime_simulation.py --event "Hattiesburg EF4 Tornado" --speed 999
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--event` | Event display name (required) — e.g., `"Hattiesburg EF4 Tornado"` |
| `--speed` | Time acceleration factor (default: 1) |
| `--force-grok` | Skip Claude API entirely, use Grok fallback |
| `--start-time` | Override start time (ISO 8601 UTC) |
| `--end-time` | Override end time (ISO 8601 UTC) |

### 4. Watch from another terminal (Optional)
Open a second terminal and tail the simulation log:
```bash
# Find the latest simulation directory
ls -lt .test_cache/simulations/realtime_sim_*/ | head -5

# Tail the log
tail -f .test_cache/simulations/realtime_sim_hattiesburg_ef4_tornado_<timestamp>/simulation.log
```

## What You'll See

### Early Cycles (T-2hr to T-80min)
- **Normal conditions**
- No severe weather detected
- 15-minute cycle intervals
- Haiku model
- Baseline atmospheric analysis

### Alert Detection (around T-60min to T-30min)
- **ESCALATION TRIGGERED**
- First NWS Tornado Warning detected
- Switch to 5-minute cycles
- Model escalation: Haiku → Sonnet
- Increased temporal resolution

### Peak Event (T-30min to T-now)
- **TORNADO EMERGENCY**
- Multiple NWS alerts
- Rapid 5-minute cycles
- Detailed spatial tracking showing mesocyclone movement
- Station-by-station pressure/temperature analysis
- ETAs and recommended actions
- "Temporal tracking: pressure minimum moved from AR249 to this location"

### Post-Event (T-now to T+10min)
- Continued monitoring
- Assessment of threat persistence
- Return to normal cycles if alerts expire

## Output Files

All output saved to: `.test_cache/simulations/realtime_sim_<event_slug>_<timestamp>/`

### 1. `simulation.log` - Complete Debug Log
Contains:
- Data collection details (CWOP + METAR queries, alert checks)
- Mesocyclone tracking with persistent IDs
- Hail cell detection (MESH/VIL)
- QLCS line tracking (when applicable)
- Decision logic (escalation triggers, model selection, API fallback)
- CWOP/METAR station trends and spatial synthesis data
- Timing information and error traces

### 2. `user_output.log` - User-Facing Content
Contains:
- All content displayed to stdout
- Timestamped nowcast summaries
- Threat levels and recommended actions
- Exactly what app users would see

### 3. Radar Images (per cycle)
- `radar_reflectivity.png` - Base reflectivity
- `radar_velocity.png` - Radial velocity
- `radar_mesocyclone_composite.png` - Composite with detection overlays

## Available Events

Events are defined in `events.json`. Current catalog:

| Event | Date | Radar | Intensity | Seeder |
|-------|------|-------|-----------|--------|
| Moore EF5 Tornado | 2013-05-20 | KTLX | EF5 | `seed_moore_minimal.py` |
| El Reno EF3 Tornado | 2013-05-31 | KTLX | EF3 | `seed_el_reno.py` |
| Pilger Twin EF4 Tornadoes | 2014-06-16 | KOAX | EF4 | `seed_pilger_twin_4_es.py` |
| Joplin EF5 Tornado | 2011-05-22 | KSGF | EF5 | — |
| Sanford-Raleigh EF3 Tornado | 2011-04-16 | KRAX | EF3 | `seed_sanford_raleigh.py` |
| Dunn/KG4AGD EF3 Tornado | 2011-04-16 | KRAX | EF3 | `seed_dunn_kg4agd.py` |
| Hattiesburg EF4 Tornado | 2013-02-10 | KDGX | EF4 | `seed_hattiesburg.py` |
| Tuscaloosa EF4 Tornado | 2011-04-27 | KBMX | EF4 | — |

## Expected Behavior

Based on validation testing across multiple events:

### Typical Threat Progression:
- **Early cycles**: WATCH — baseline conditions, 15-min intervals, Haiku model
- **Alert detection**: WARNING — NWS alerts trigger 5-min cycles + Sonnet escalation
- **Approach phase**: EMERGENCY — mesocyclone approaching, TAKE SHELTER guidance
- **Post-event**: De-escalation as storm recedes

### Key Features to Observe:
- Persistent mesocyclone tracking (MESO-1, MESO-2, etc.) with multi-cycle speed averaging
- Network-wide spatial synthesis (temperature/pressure gradients by quadrant)
- Hail cell detection with MESH size estimates
- QLCS line tracking when applicable (Dunn event)
- RCAS (Range-Corrected Azimuthal Shear) for distant radar compensation
- API fallback chain: Claude → Grok → OpenAI (with error-specific cooldowns)

## Post-Simulation Analysis

After the simulation completes, review:

1. **Cycle timing accuracy**: Did escalation happen at the right times?
2. **Model selection**: Haiku baseline → Sonnet during alerts?
3. **Content quality**: Are recommended actions appropriate and supplemental to NWS?
4. **Temporal tracking**: Can you follow the mesocyclone movement through the station network?
5. **Data quality**: Were there any gaps or issues in CWOP/alert data?

## Data Sources Per Cycle

Each cycle collects data from multiple sources:

1. **NEXRAD Level II** — Reflectivity and velocity from AWS S3 (nearest radar per event)
2. **CWOP observations** — Citizen Weather Observer stations from NOAA MADIS (netCDF)
3. **METAR/ASOS** — Airport weather stations from IEM archive (integrated alongside CWOP)
4. **NWS alerts** — Active warnings/watches from IEM shapefile archive
5. **Local sensor_readings** — Seeded from nearest CWOP/METAR station to simulate local hardware

CWOP data uses a class-level extract cache to avoid re-parsing netCDF files across the 7+ temporal history calls per cycle.

## API Fallback Chain

The analyst call attempts APIs in order with error-specific cooldowns:

1. **Claude** (primary) — Sonnet during alerts, Haiku baseline
2. **Grok** (xAI fallback) — Used when Claude unavailable
3. **OpenAI** (last resort)

Cooldown logic:
- **401 Auth/billing error** → Skip Claude for 10 cycles
- **429 Rate limit** → Skip Claude for 3 cycles
- Use `--force-grok` to bypass Claude entirely

## Troubleshooting

### Simulation runs too fast/slow
- Use `--speed` parameter to adjust timing
- Real-time: `--speed 1` (default)
- Accelerated: `--speed 999` (minimal wait, ~2-3 min per cycle)

### No output appearing
- Check that you're in the correct directory
- Verify database exists: `.test_cache/<event>_test.db` (run seeder first)
- Check Python path and virtual environment

### Claude API errors
- 401 errors auto-cooldown for 10 cycles (Grok fallback handles it)
- Use `--force-grok` if Claude API key is known to be invalid
- Check `station_config` table in test DB for API keys

## Spatiotemporal CWOP Awareness

The simulation maintains cycle-to-cycle history of all CWOP and METAR stations, computing pre-computed rates that the analyst interprets (following the "meteorological team" philosophy — data pipeline does arithmetic, analyst synthesizes meaning).

### Per-Station Tracking
- **Pressure rate** (inHg/hr) — computed from consecutive readings
- **Temperature rate** (°F/hr) — detects RFD cooling signatures
- **Wind shift** (degrees) — identifies rotation passages
- **15-min deltas** — short-term acceleration/deceleration

### Three Trend Blocks
Knowledge entries include surface network trends organized into:
1. **Local network** — Stations within the configured radius of the local station
2. **Meso-proximity** — Stations near detected mesocyclone centers
3. **Approach corridor** — Stations between local station and mesocyclone (with dynamic corridor expansion when meso >40 mi away)

### Network-Wide Spatial Synthesis
The analyst prompt instructs grouping stations by quadrant relative to storm motion and describing the full temperature/pressure gradient across the network — not cherry-picking individual stations.

## QLCS Line Tracking

When the adaptive regime classifier identifies a **QLCS (Quasi-Linear Convective System)** environment, the simulation activates a two-layer threat model that supplements per-meso tracking:

### Layer 1: Convective Line Detection
- Thresholds radar reflectivity at **40+ dBZ** to identify convective cores
- Converts polar radar coordinates to geographic (lat/lon)
- Finds the **leading edge** — the 10km-deep band of high reflectivity closest to the station
- Uses **PCA (Principal Component Analysis)** on leading-edge points to determine line orientation
- Tracks the line centroid across cycles to compute motion vector and **ETA**

### Layer 2: Threat Corridor
- Defines a **±15km corridor** perpendicular to the line's approach vector (station → closest line point)
- Aggregates all rotation detections within this corridor over a **30-minute rolling window**
- Computes metrics: rotation count, max shear, nearest detection, active rotation flag
- Filters using cross-track distance (bearing difference method)

### Knowledge Injection
When in QLCS regime, the analyst receives line/corridor data **before** individual meso data:
```
QLCS LINE TRACKING (supplemental to individual mesocyclone tracking):
  LINE POSITION: Leading edge 25.3 km (15.7 mi) WSW of station
  LINE ORIENTATION: SW-NE (axis 035°), length ~80 km
  LINE MOTION: 78 km/hr (49 mph) toward ESE (bearing 110°)
  ETA AT STATION: ~19 minutes

  THREAT CORRIDOR (±15 km centered on approach vector):
    Rotation detections (last 30 min): 5
    Max shear in corridor: 56.5 s⁻¹ (TVS-strength)
    Most recent: 12.1 km from station, 2 min ago
    ⚠️ ACTIVE ROTATION IN APPROACHING SEGMENT — TREAT AS IMMINENT THREAT
```

### Diagnostic Log Markers
- `📏 QLCS LINE:` — line detection results (distance, axis, length, motion)
- `🎯 CORRIDOR:` — threat corridor metrics (rotation count, shear, nearest)
- `🌪️ REGIME CHANGE:` — storm regime transitions

### Coexistence with Per-Meso Tracking
- Per-meso tracking (MESO-1, MESO-2, etc.) continues running in parallel
- In supercell regime, only per-meso tracking is active (line tracking disabled)
- In QLCS regime, both systems run — line tracking provides the persistent threat picture while per-meso tracking provides rotation detail

## Hail Detection

The simulation detects hail-producing storm cells using multi-sweep reflectivity column analysis. This works with **single-pol NEXRAD data** (pre-2012 radars without dual-polarization).

### Algorithm
1. **Gate collection**: All reflectivity gates ≥45 dBZ across all elevation sweeps, with height computed via 4/3 earth beam propagation model
2. **DBSCAN clustering**: Groups gates into storm cells on horizontal coordinates (eps=5.0km)
3. **Per-cell analysis**:
   - **VIL** (Vertically Integrated Liquid): Trapezoidal integration of reflectivity column
   - **SHI/MESH**: Severe Hail Index using layers above the freezing level; `MESH (mm) = 2.54 × SHI^0.5`
   - **Column heights**: 45+ dBZ top and echo top (>15 dBZ)
   - **VIL density**: VIL / echo top height
4. **Hail probability**: Multi-factor maximum of MESH, VIL density, and max reflectivity indicators
5. **Size categories**: pea, penny/quarter, golf ball, ping pong ball, tennis ball, baseball+

### Knowledge Injection
```
HAIL SIGNATURES (automated radar reflectivity analysis):
  HAIL CELL: 12.3 km (7.6 mi) WSW | APPROACHING (was 18.5 km)
    Size: MESH=42mm (very large, ping pong ball)
    Probability: 85%
    Max reflectivity: 65.2 dBZ
    VIL: 48.3 kg/m²
    45+ dBZ column top: 32,800 ft | Echo top: 42,600 ft
    Assessment: HIGH DANGER — large hail likely, seek shelter immediately
```

### Diagnostic Log Markers
- `🧊 HAIL:` — hail detection results (cell count, top cell MESH/VIL/distance)

### Freezing Level
Each event has a `freezing_level_m` parameter (meters AGL) used for MESH computation:
- April NC events: 3500m
- May OK events: 4200m
- June NE events: 4500m

## Notes

- **This is a simulation using historic data** — times are relative to the event, not current time
- **Station data is authentic** — Real CWOP + METAR observations from the actual event
- **NWS alerts are authentic** — Real tornado warnings from IEM archive
- **AI analysis is live** — Each cycle generates a fresh nowcast using current production code (Claude, Grok, or OpenAI)
- **Cycle logic matches production** — Same escalation triggers, timing, and model selection
- **RCAS correction** — Range-Corrected Azimuthal Shear accounts for beam broadening at distant radars
