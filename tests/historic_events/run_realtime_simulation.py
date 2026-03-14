"""
Real-Time Event Simulation

Simulates the nowcast feature running during a historic severe weather event,
using actual production cycle logic and timing.

Features:
- Starts T-2hr before event to show baseline conditions
- 15-minute cycles normally, 5-minute during Extreme/Severe alerts
- Model escalation: Haiku → Sonnet during severe weather
- Mid-cycle regeneration on NEW alerts
- Live timestamped output showing user-facing content
- Detailed logging for post-event analysis

Usage:
    python run_realtime_simulation.py --event "Moore EF5 Tornado" [--speed 60]

    --speed: Time acceleration (default: 1 = real-time, 60 = 1hr per minute)
"""

import asyncio
import sys
import os
from pathlib import Path

# Auto-activate venv if not already active
VENV_PYTHON = Path(__file__).parent.parent.parent / 'backend' / 'venv' / 'bin' / 'python3'
if VENV_PYTHON.exists() and sys.executable != str(VENV_PYTHON):
    # Re-exec with venv Python
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

sys.dont_write_bytecode = True  # Prevent .pyc caching during development
import json
import signal
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
import traceback
from enum import Enum
import numpy as np
import math

# =============================================================================
# DEVELOPMENT MODE CONFIGURATION
# =============================================================================
#
# DEVELOPMENT_MODE controls how many mesocyclones are passed to Claude for analysis.
#
# DEVELOPMENT_MODE = True (Current - Single-Threat Testing):
#   - Multi-peak detection finds ALL mesocyclones (e.g., Moore + Kansas storms)
#   - System passes ONLY the nearest strong mesocyclone to Claude
#   - Focus: Tune Claude's threat analysis (approach, ETA, escalation logic)
#   - Use: Initial validation, parameter tuning, prompt engineering
#
# DEVELOPMENT_MODE = False (Future - Multi-Threat Operations):
#   - Multi-peak detection finds ALL mesocyclones
#   - System passes ALL nearby mesocyclones to Claude (within 100 km)
#   - Focus: Tune Claude's triage capability (which threat to prioritize)
#   - Use: Realistic operations, complex severe weather events
#
# Rationale: During development, we need to tune Claude's analysis of a single
# threat before adding the complexity of multi-threat triage. Claude must learn
# to assess: Is this real? Is it approaching? What's the ETA? When to escalate?
# Only after single-threat analysis is reliable do we add multi-threat scenarios.
#
DEVELOPMENT_MODE = True  # Single-threat testing mode

# Configure logging to capture production code errors to a file
# This will catch the logger.error() calls from nowcast_analyst.py
log_file_handler = None  # Will be set in Simulator.__init__()

class SimulationLogHandler(logging.Handler):
    """Custom handler that writes to simulation log file."""
    def __init__(self, simulator):
        super().__init__()
        self.simulator = simulator

    def emit(self, record):
        try:
            msg = self.format(record)
            if self.simulator:
                self.simulator.log_debug(f"[{record.name}] {msg}")
        except Exception:
            self.handleError(record)

# Set up console logging (warnings/errors only)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.WARNING)
console_handler.setFormatter(logging.Formatter('[%(name)s] %(levelname)s: %(message)s'))

logging.basicConfig(
    level=logging.DEBUG,  # Capture everything
    format='%(levelname)s: %(message)s',
    handlers=[console_handler]
)

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'backend'))

# Import anthropic to patch it
import anthropic

# Monkey-patch the Messages class directly
_original_messages_create = None

async def _patched_messages_create(self, **kwargs):
    """Wrapper to capture and log detailed API errors."""
    try:
        print(f"\n{'='*80}")
        print(f"ANTHROPIC API CALL")
        print(f"  Model: {kwargs.get('model')}")
        print(f"  Max tokens: {kwargs.get('max_tokens')}")
        print(f"  Messages: {len(kwargs.get('messages', []))}")
        print(f"{'='*80}\n")

        result = await _original_messages_create(self, **kwargs)

        print(f"\n{'='*80}")
        print(f"ANTHROPIC API SUCCESS")
        print(f"  Stop reason: {result.stop_reason}")
        print(f"  Usage: {result.usage.input_tokens if result.usage else '?'} in, {result.usage.output_tokens if result.usage else '?'} out")
        print(f"{'='*80}\n")

        return result
    except Exception as e:
        # Check if this is an expected/handled error (overload, rate limit)
        is_expected = False
        error_str = str(e).lower()
        if "overload" in error_str or "529" in str(e):
            is_expected = True
            error_type = "API Overload (529)"
        elif "rate" in error_str and "limit" in error_str:
            is_expected = True
            error_type = "Rate Limit"

        print(f"\n{'='*80}")
        print(f"ANTHROPIC API ERROR")

        if is_expected:
            # Clean output for expected errors
            print(f"  Type: {error_type}")
            print(f"  Message: {error_str[:150]}")  # Truncate long messages
            print(f"  (This is a transient Anthropic infrastructure issue)")
        else:
            # Full debug output for unexpected errors
            print(f"  Exception type: {type(e).__name__}")
            print(f"  Exception message: {str(e)}")
            print(f"  Full exception: {repr(e)}")
            if hasattr(e, 'status_code'):
                print(f"  Status code: {e.status_code}")
            if hasattr(e, 'response'):
                print(f"  Response: {e.response}")
            print(f"  Traceback:")
            traceback.print_exc()

        print(f"{'='*80}\n")
        raise

# Apply monkey patch at the AsyncMessages class level
if hasattr(anthropic, 'resources'):
    from anthropic.resources.messages import AsyncMessages
    _original_messages_create = AsyncMessages.create
    AsyncMessages.create = _patched_messages_create

from app.services.nowcast_analyst import generate_nowcast, _build_user_message
from app.services.nowcast_collector import CollectedData, RadarImage

# Add test modules to path
sys.path.insert(0, str(Path(__file__).parent))
from HISTORIC_EVENTS_CATALOG import get_event_by_name
from loaders.nws_alert_loader import NWSAlertLoader
from loaders.nexrad_loader import NEXRADLoader
from loaders.cwop_loader import CWOPLoader

# Shared modules (extracted from this file for reuse in production)
from app.models.radar_threats import (
    CWOPReading, StationTrend, HailCell, QLCSLine, ThreatCorridor,
    StormRegime, RegimeParameters, REGIME_PARAMS, TrackedMesocyclone,
    ThreatTrackerState, SurfaceAnalyzerState, RadarProcessingResult,
    haversine_km, calculate_bearing, bearing_to_cardinal,
)
from app.services.radar_processor import process_radar_volume
from app.services.threat_tracker import ThreatTracker
from app.services.surface_analyzer import SurfaceAnalyzer
from app.services.knowledge_formatter import build_knowledge_entries
from app.services.multi_radar import find_nearby_radars, merge_radar_results
from app.services.radar_visualizer import (
    generate_detection_composite, generate_situation_composite, generate_surface_analysis,
)

# MRMS cross-validation (optional — requires cfgrib + eccodes)
try:
    from app.services.mrms_loader import MRMSLoader, HAS_MRMS_DEPS
    MRMS_AVAILABLE = HAS_MRMS_DEPS
except ImportError:
    MRMS_AVAILABLE = False

# API keys — set via environment variables (never hardcode)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
XAI_API_KEY = os.environ.get("XAI_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Import OpenAI client
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("Warning: OpenAI package not installed. Run: pip install openai")


def build_nearby_stations(
    local_station_id: str,
    local_lat: float,
    local_lon: float,
    timestamp: datetime,
    radius_miles: float = 50
) -> Any:
    """
    Build nearby_stations data from CWOP observations.

    Returns a NearbyStationsResult-like object with spatial pressure data.
    """
    from dataclasses import dataclass, field
    import math

    @dataclass
    class NearbyObservation:
        source: str
        station_id: str
        station_name: str
        latitude: float
        longitude: float
        distance_miles: float
        bearing_cardinal: str
        timestamp: str
        temp_f: Optional[float] = None
        dew_point_f: Optional[float] = None
        humidity_pct: Optional[int] = None
        wind_speed_mph: Optional[float] = None
        wind_dir_deg: Optional[int] = None
        wind_gust_mph: Optional[float] = None
        pressure_inhg: Optional[float] = None
        precip_in: Optional[float] = None
        sky_cover: Optional[str] = None
        raw_metar: Optional[str] = None

    @dataclass
    class NearbyStationsResult:
        stations: list = field(default_factory=list)
        aprs_count: int = 0
        fetched_at: float = 0.0

    # Load CWOP observations
    loader = CWOPLoader()
    obs = loader.get_observations(
        start_time=timestamp - timedelta(minutes=15),
        end_time=timestamp + timedelta(minutes=15),
        lat=local_lat,
        lon=local_lon,
        radius_miles=radius_miles
    )

    # Also load METAR/ASOS airport observations
    try:
        from loaders.metar_loader import METARLoader
        metar_loader = METARLoader(cache_dir=Path('.test_cache'))
        metar_obs = metar_loader.get_observations(
            start_time=timestamp - timedelta(minutes=30),
            end_time=timestamp + timedelta(minutes=30),
            lat=local_lat,
            lon=local_lon,
            radius_miles=radius_miles
        )
        obs.extend(metar_obs)
    except Exception:
        pass  # METAR is supplementary — don't fail if unavailable

    # Helper: Calculate bearing
    def bearing_cardinal(lat1, lon1, lat2, lon2):
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        angle = math.degrees(math.atan2(dlon, dlat))
        directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                     'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
        idx = int((angle + 11.25) / 22.5) % 16
        return directions[idx]

    # Helper: Calculate distance
    def haversine_miles(lat1, lon1, lat2, lon2):
        R = 3958.8
        rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat/2)**2 +
             math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon/2)**2)
        c = 2 * math.asin(math.sqrt(a))
        return R * c

    # Normalize timestamps to standard datetime for safe comparison
    for o in obs:
        ts = o['timestamp']
        if not isinstance(ts, datetime):
            # cftime → standard datetime
            o['timestamp'] = datetime(ts.year, ts.month, ts.day,
                                      ts.hour, ts.minute, ts.second,
                                      tzinfo=timezone.utc)
        elif ts.tzinfo is None:
            o['timestamp'] = ts.replace(tzinfo=timezone.utc)

    # Group by station and get most recent obs for each
    stations = {}
    for o in obs:
        sid = o['station_id']
        if sid == local_station_id:
            continue
        if sid not in stations or o['timestamp'] > stations[sid]['timestamp']:
            stations[sid] = o

    # Convert to NearbyObservation objects
    nearby = []
    for sid, o in stations.items():
        dist = haversine_miles(local_lat, local_lon, o['latitude'], o['longitude'])
        bearing = bearing_cardinal(local_lat, local_lon, o['latitude'], o['longitude'])

        # Convert units
        temp_f = o['temperature'] * 9/5 + 32 if o.get('temperature') else None
        dewpt_f = o['dewpoint'] * 9/5 + 32 if o.get('dewpoint') else None
        pressure_inhg = o['pressure'] * 0.02953 if o.get('pressure') else None
        wind_mph = o['wind_speed'] * 2.237 if o.get('wind_speed') else None

        nearby.append(NearbyObservation(
            source=o.get('source', 'CWOP'),
            station_id=sid,
            station_name=f"{sid} ({o.get('station_type', 'unknown')})",
            latitude=o['latitude'],
            longitude=o['longitude'],
            distance_miles=dist,
            bearing_cardinal=bearing,
            timestamp=o['timestamp'].isoformat(),
            temp_f=temp_f,
            dew_point_f=dewpt_f,
            pressure_inhg=pressure_inhg,
            wind_speed_mph=wind_mph,
            wind_dir_deg=int(o['wind_dir']) if o.get('wind_dir') else None,
        ))

    # Sort by distance, take closest 10
    nearby.sort(key=lambda x: x.distance_miles)
    nearby = nearby[:10]

    metar_count = sum(1 for n in nearby if n.source == 'METAR')
    cwop_count = len(nearby) - metar_count
    src_parts = [f"{cwop_count} CWOP"]
    if metar_count:
        src_parts.append(f"{metar_count} METAR")
    print(f"  Built nearby_stations: {' + '.join(src_parts)}")
    for n in nearby[:5]:
        pressure_str = f"{n.pressure_inhg:.2f} inHg" if n.pressure_inhg else "N/A"
        print(f"    {n.station_id}: {n.distance_miles:.1f} mi {n.bearing_cardinal}, {pressure_str}")

    return NearbyStationsResult(
        stations=nearby,
        aprs_count=len(nearby),
        fetched_at=timestamp.timestamp()
    )


def load_event_config(event_name: str) -> dict:
    """
    Load event configuration from JSON file.

    Returns event config dict with all parameters needed for simulation.
    """
    config_file = Path(__file__).parent / 'events.json'

    if not config_file.exists():
        raise FileNotFoundError(f"Event config file not found: {config_file}")

    with open(config_file, 'r') as f:
        events = json.load(f)

    # Try exact match first
    if event_name in events:
        return events[event_name]

    # Try case-insensitive match on display name
    event_name_lower = event_name.lower()
    for key, config in events.items():
        if config['name'].lower() == event_name_lower:
            return config

    # List available events
    available = [cfg['name'] for cfg in events.values()]
    raise ValueError(f"Event '{event_name}' not found. Available events:\n  " + "\n  ".join(available))


def validate_and_seed_database(event_config: dict, cache_dir: Path) -> Path:
    """
    Validate database exists and is seeded. Auto-seed if needed.

    Returns path to validated database file.
    """
    db_file = event_config['db_file']
    db_path = cache_dir / db_file
    seeder_script = event_config.get('seeder_script')

    # Check if DB exists
    if not db_path.exists():
        if seeder_script:
            print(f"\n❌ Database not found: {db_path}")
            print(f"   Auto-seeding with: {seeder_script}")
            print()

            # Run seeder script
            seeder_path = Path(__file__).parent / seeder_script
            if not seeder_path.exists():
                raise FileNotFoundError(
                    f"Database missing and seeder script not found:\n"
                    f"  DB: {db_path}\n"
                    f"  Seeder: {seeder_path}\n"
                    f"  Please create seeder script or seed manually."
                )

            # Execute seeder
            import subprocess
            result = subprocess.run(
                [sys.executable, str(seeder_path)],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                print(f"❌ Seeding failed:")
                print(result.stdout)
                print(result.stderr)
                raise RuntimeError(f"Database seeding failed for {db_file}")

            print(result.stdout)

            # Verify DB now exists
            if not db_path.exists():
                raise RuntimeError(f"Seeding completed but database not found: {db_path}")

            print(f"✅ Database seeded successfully: {db_path}\n")
        else:
            raise FileNotFoundError(
                f"Database not found: {db_path}\n"
                f"No seeder script configured. Please seed manually:\n"
                f"  Run appropriate seed_*.py script first"
            )

    # TODO: Could add DB validation here (check table schemas, row counts, etc.)

    return db_path


def prune_old_images(messages: list, keep_last_n: int = 3) -> list:
    """Strip base64 image data from older messages to control memory.

    Keeps images in the most recent `keep_last_n` user messages.
    For older messages, replaces image_url blocks with a text placeholder
    so the analyst retains context about what images were shown.

    Works with OpenAI-format messages (image_url blocks).
    """
    # Find indices of user messages (they contain images)
    user_indices = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    # Only prune if we have more than keep_last_n user messages
    if len(user_indices) <= keep_last_n:
        return messages

    indices_to_prune = user_indices[:-keep_last_n]
    pruned = []
    for i, msg in enumerate(messages):
        if i in indices_to_prune and isinstance(msg.get("content"), list):
            new_content = []
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "image_url":
                    # Replace image with text placeholder
                    new_content.append({
                        "type": "text",
                        "text": "[Radar image from earlier cycle — removed to save context]"
                    })
                else:
                    new_content.append(block)
            pruned.append({"role": msg["role"], "content": new_content})
        else:
            pruned.append(msg)
    return pruned


def compact_history(history: list, keep_images_in_last: int = 1, max_pairs: int = 6) -> list:
    """Compact conversation history for storage between cycles.

    Two-stage compaction:
    1. Drop oldest user+assistant exchange pairs beyond max_pairs
    2. Strip base64 images from all but the last keep_images_in_last user messages

    This bounds both memory and token usage so fallback providers (especially
    OpenAI with its lower token limits) can handle the accumulated history.
    """
    if not history:
        return history

    # Stage 1: Cap the number of exchanges
    user_indices = [i for i, m in enumerate(history) if m.get("role") == "user"]
    if len(user_indices) > max_pairs:
        cutoff_idx = user_indices[-max_pairs]
        history = history[cutoff_idx:]

    # Stage 2: Strip images from older messages
    return prune_old_images(history, keep_last_n=keep_images_in_last)


async def generate_nowcast_openai(
    data: CollectedData,
    model: str = "gpt-4o",
    api_key: str = None,
    horizon_hours: int = 2,
    max_tokens: int = 8000,
    radar_station: str = "",
    conversation_history: Optional[list] = None,
) -> tuple[Optional[Any], list]:
    """
    Generate nowcast using OpenAI GPT-4o (fallback provider).

    This is a simplified version that mimics the Claude nowcast output format.
    Used as fallback when Anthropic API is unavailable.

    Args:
        data: CollectedData with station, alerts, radar, etc.
        model: OpenAI model to use (default: gpt-4o)
        api_key: OpenAI API key
        horizon_hours: Forecast horizon
        max_tokens: Max response tokens
        radar_station: Radar site identifier
        conversation_history: Previous conversation messages for context continuity.

    Returns:
        Tuple of (NowcastResult or None, updated conversation history).
    """
    if conversation_history is None:
        conversation_history = []

    if not OPENAI_AVAILABLE or not api_key:
        return None, conversation_history

    # OpenAI has lower token limits — aggressively trim history before building request
    conversation_history = compact_history(conversation_history, keep_images_in_last=1, max_pairs=3)

    try:
        # Work around Debian package httpx compatibility issue
        import os
        os.environ['OPENAI_API_KEY'] = api_key
        client = OpenAI()

        # Build system prompt (same as Claude's production prompt from nowcast_analyst.py)
        # Note: Zoom radar tool section removed since GPT doesn't have tool access in fallback mode
        system_prompt = """\
You are a mesoscale weather analyst for a personal weather station. Your role
is to refine broad numerical weather model guidance using real-time local
observations to produce accurate, hyper-local nowcasts.

HARD CONSTRAINTS:
- Never fabricate observations or station data.
- Never predict beyond what the data supports.
- Always distinguish between: "model guidance says X", "observations show Y",
  and "I am adjusting to Z because of [specific evidence]".
- Cite which data points informed each conclusion.
- Default to model guidance when local data is insufficient or contradictory.
- Express confidence per forecast element: HIGH, MEDIUM, or LOW.
- If data is contradictory or insufficient, say so explicitly.

ANALYTICAL METHOD:
1. Summarize current conditions from station observations.
2. Compare observations against model expectations — flag any divergences.
3. Analyze trends: 3-hour pressure tendency, temperature trajectory,
   dewpoint depression changes, wind direction shifts.
4. If nearby station data is available, identify spatial propagation patterns.
5. Produce timing refinements for precipitation onset/cessation,
   temperature extremes, and wind changes.
6. Assess confidence for each forecast element based on data agreement.

RADAR ANALYSIS (when radar imagery is provided):
- The image is NEXRAD composite reflectivity centered on the station.
- Reflectivity color scale: green = light rain (~15-30 dBZ),
  yellow = moderate-heavy (~35-45 dBZ), orange/red = very heavy (~45-60 dBZ),
  purple/white = severe (60+ dBZ). Blues may indicate snow.
- Analyze: precipitation coverage near station, echo movement direction
  (compare with model wind fields), approaching or departing precipitation,
  convective vs stratiform character, line segments or mesoscale structures.
- Use radar to refine precipitation timing: if echoes are 50 miles away
  moving at 30 mph, onset is approximately 1.5-2 hours out.
- If no significant echoes near the station, note radar is clear and state
  confidence in the dry forecast.
- Do NOT describe image colors/pixels — translate what you see into weather
  terms (e.g., "A band of moderate rain approaching from the southwest").

VELOCITY RADAR (when Storm Relative Velocity imagery is provided):
- Green shades = motion TOWARD radar; red = AWAY. Brighter = faster.
- CRITICAL: Gate-to-gate shear (bright green adjacent to bright red) = rotation.
- Mesocyclone signature: rotation 2-6 nm diameter, velocity difference >30 kt.
- TVS (Tornado Vortex Signature): tight rotation <1 nm, velocity >50 kt.
- Report distance/bearing from station, storm motion, and estimated time to
  closest approach.
- Cross-reference with reflectivity: rotation embedded in strong echoes
  (>50 dBZ) indicates higher threat level.
- If no rotation signatures are detected, state "No rotation signatures
  detected on velocity imagery."

SEVERE WEATHER CORRELATION PROTOCOL:
When ANY of the following triggers are present, activate this protocol:
  - NWS warning or watch is active for this location
  - Velocity radar shows gate-to-gate shear or rotation signatures
  - Station barometric pressure dropping >0.06 inHg/hr
  - Nearby stations showing wind shifts or pressure drops propagating
    toward this station

STEP 1 — Assess the threat:
  a. Identify the primary threat type (tornado, severe thunderstorm,
     flash flood, damaging winds, large hail).
  b. Locate the threat on radar: distance and bearing from station.
  c. Estimate storm motion using model wind fields or echo movement.
  d. Calculate estimated time to closest approach.

STEP 2 — Correlate local observations:
  a. Station pressure trend: rapid drop (>0.06 inHg/hr) indicates
     approaching mesoscale low or gust front.
  b. Wind direction shifts: veering (clockwise) ahead of warm front;
     backing (counterclockwise) with approaching storm outflow.
  c. Temperature/dewpoint: sudden dewpoint surge = outflow boundary.
     Rapid cooling = precipitation or downdraft arrival.
  d. Nearby station propagation: if stations to the W/SW show pressure
     drops or wind shifts, calculate propagation speed and ETA to this
     station.

STEP 3 — Populate the severe_weather output object:
  - threat_level: "WATCH" (conditions possible) | "WARNING" (imminent
    or occurring) | "EMERGENCY" (confirmed life-threatening, e.g.
    confirmed tornado + radar rotation + NWS tornado warning)
  - Provide distance, bearing, ETA, specific local evidence, and
    clear recommended action.
  - ALWAYS cross-reference: a warning without local supporting evidence
    should note "NWS warning active but no local confirming signatures
    yet — continue monitoring."
  - A rotation signature WITHOUT an NWS warning should note the
    observation and recommend monitoring — do not create false alarms.

STEP 4 — Escalation indicators (note in severe_weather.local_evidence):
  - Pressure drop rate accelerating
  - Multiple nearby stations showing same trend (spatial coherence)
  - Radar echoes intensifying and/or rotation tightening
  - Wind gusts exceeding forecast values

When NONE of the triggers above are present, set severe_weather to null.

TEMPORAL MESOCYCLONE TRACKING (when nearby_stations_history is provided):
When temporal pressure evolution data is available, use it to refine
threat assessment beyond what a single snapshot can provide:

1. TRACK PRESSURE MINIMUM MOVEMENT:
   - Identify the lowest pressure reading at each time point.
   - Note which station reports the minimum and when.
   - Calculate how the pressure "hole" moves through the station network.
   - Example: "Pressure minimum moved from AR249 (20:00) to AU444 (20:15)
     to local station area (20:30) — ~9 miles in 30 min = 18 mph NE motion"

2. DETECT RFD (REAR FLANK DOWNDRAFT) SIGNATURES:
   - Temperature crashes of 5°F+ in <15 minutes indicate tornado outflow.
   - Look for stations reporting sudden cooling as the system passes.
   - Example: "AR249: 81°F → 70°F in 12 min = RFD signature"

3. IDENTIFY WIND SHIFT PROGRESSION:
   - Sudden wind direction changes indicate boundary passage.
   - Chaotic wind patterns suggest complex supercell outflow.
   - Example: "Wind veered from 60° to 318° as mesocyclone passed"

4. CALCULATE THREAT VECTOR:
   - Speed: distance traveled / time elapsed.
   - Direction: bearing from earlier position to later position.
   - ETA: distance to local station / speed.
   - Example: "Mesocyclone tracking NE at 18 mph, ETA to station: 15-20 min"

5. PROVIDE HYPER-LOCAL REFINEMENT:
   - NWS warnings cover large polygons (~10-20 miles across).
   - Temporal tracking provides "last-mile" refinement within those polygons.
   - Give specific ETA and approach direction relative to the local station.
   - Example: "While NWS polygon includes this area, temporal analysis
     suggests core circulation will pass 2-3 miles north in 18 minutes"

NWS ACTIVE ALERTS (when provided):
- Watches, warnings, and advisories active for the station location are
  included in the data.  Reference them explicitly:
  * WARNINGS (Extreme/Severe) indicate imminent or occurring hazard —
    ALWAYS include the threat in the "special" field with actionable guidance.
  * WATCHES (Moderate) indicate potential hazard — mention in summary and
    the relevant forecast element (precipitation, wind, etc.).
  * ADVISORIES (Minor) indicate moderate hazard — mention in the relevant
    forecast element.
- Cross-reference alert timing with your radar and model analysis.
- When a warning is active, correlate local station observations and nearby
  station data to provide hyper-local situational awareness (e.g., "Barometer
  dropping rapidly consistent with approaching storm cited in warning").

SPECIAL CONDITIONS:
- The "special" field is for conditions that ARE occurring or imminent.
  Set it to null when no special conditions exist. Do NOT discuss why a
  condition is absent — only report what IS happening.
- When NWS warnings are active, the "special" field MUST include the threat
  with specific local correlation evidence and actionable guidance.
- FROST: Only mention when forecast air temp is 36°F or below.
  Never mention frost when temps are above 40°F.
- FOG: Only mention when visibility reduction is expected or occurring.
- HEAT: Only mention when heat index exceeds 100°F.
- WIND CHILL: Only mention when air temp is below 40°F AND wind > 5 mph.

TIME REFERENCES:
- Express ALL times in the station's local timezone as specified in the
  request. Use 12-hour format with AM/PM (e.g., "2:30 PM", "around 10 PM").
- Use ONLY the station's local timezone. Never show dual timezones
  (e.g., do NOT write "7:13 AM CST / 8:13 AM EST").
- Never use UTC in user-facing text unless the request specifies UTC.

OUTPUT FORMAT — respond with ONLY a JSON object (no markdown, no commentary):
{
  "summary": "2-3 sentence natural language nowcast for general audience",
  "current_vs_model": "Where and how observations diverge from model guidance",
  "radar_analysis": null or "Brief description of what radar shows and timing implications",
  "elements": {
    "temperature": {"forecast": "...", "confidence": "HIGH|MEDIUM|LOW"},
    "precipitation": {"forecast": "...", "confidence": "...", "timing": "..."},
    "wind": {"forecast": "...", "confidence": "..."},
    "sky": {"forecast": "...", "confidence": "..."},
    "special": null or "active/imminent special condition (fog, frost, severe weather) — null if none"
  },
  "farming_impact": "Brief agriculture-relevant note (field conditions, frost risk, spray windows, etc.)",
  "data_quality": "Assessment of input data sufficiency and any gaps",
  "proposed_knowledge": null or {"category": "bias|timing|terrain|seasonal", "content": "Learned insight for future reference"},
  "severe_weather": null or {
    "threat_level": "WATCH|WARNING|EMERGENCY",
    "primary_threat": "Tornado / Severe Thunderstorm / Flash Flood / etc.",
    "summary": "Concise correlated situation assessment with local evidence",
    "distance_miles": null or number,
    "bearing": null or "SW",
    "estimated_arrival": null or "~45 minutes",
    "local_evidence": ["Pressure dropping 0.08 inHg/hr", "Wind shift at nearby station"],
    "recommended_action": "Specific protective action"
  },
  "spray_advisory": null or {
    "summary": "Overall spray conditions assessment for the next several hours",
    "recommendations": []
  }
}

SPRAY APPLICATION ADVISORY (when spray schedules are provided):
- If no spray schedules are provided, set spray_advisory to null.
- When spray outcome history is provided, use it to calibrate your recommendations.
"""

        # Build user message content (same as Claude using production function)
        context_text = _build_user_message(data, horizon_hours)

        user_parts = [{"type": "text", "text": context_text}]

        # Add radar images using OpenAI's image_url format
        if data.radar_images:
            from zoneinfo import ZoneInfo
            tz_label = data.station_timezone or "UTC"
            try:
                tz = ZoneInfo(tz_label)
            except Exception:
                from datetime import timezone
                tz = timezone.utc

            for img in data.radar_images:
                user_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img.png_base64}",
                        "detail": "high"
                    }
                })
                # Add image context (same format as Claude)
                bbox = img.bbox
                miles_ns = (bbox[3] - bbox[1]) * 69
                fetched_local = datetime.fromtimestamp(img.fetched_at, tz=tz)
                fetched_str = fetched_local.strftime("%I:%M %p %Z").lstrip("0")
                user_parts.append({
                    "type": "text",
                    "text": (
                        f"Above: {img.label} fetched at {fetched_str}, "
                        f"centered on station location. "
                        f"Covers {bbox[1]:.2f}N to {bbox[3]:.2f}N, "
                        f"{abs(bbox[0]):.2f}W to {abs(bbox[2]):.2f}W "
                        f"(~{miles_ns:.0f} miles N-S). Station is at center."
                    )
                })

        # Build messages: system + conversation history + new user message
        new_user_msg = {"role": "user", "content": user_parts}
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation_history)
        messages.append(new_user_msg)

        # Prune old images — stored history is already compacted, but this catches
        # the new user message if it has images and we're past the retention window
        messages = [messages[0]] + prune_old_images(messages[1:], keep_last_n=1)

        # Call OpenAI API
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7,
            response_format={"type": "json_object"}
        )

        # Parse response
        content = response.choices[0].message.content
        result_json = json.loads(content)

        # Update conversation history (without system message)
        updated_history = messages[1:]  # Strip system message
        updated_history.append({"role": "assistant", "content": content})

        # Convert to expected format (simple object with attributes)
        class NowcastResult:
            def __init__(self, data):
                self.summary = data.get('summary', '')
                self.severe_weather = data.get('severe_weather')
                self.radar_analysis = data.get('radar_analysis', '')
                self.data_quality = data.get('data_quality', '')

        return NowcastResult(result_json), updated_history

    except Exception as e:
        print(f"OpenAI nowcast error: {e}")
        import traceback
        traceback.print_exc()
        return None, conversation_history


def gather_station_data_at_time(
    db, sim_time: datetime, station_timezone: str = "", log_func=None
):
    """
    Simulation version of gather_station_data() that queries at a specific time.

    Based on production code in nowcast_collector.py but accepts sim_time
    instead of using datetime.now(). This allows replaying historic events.

    Args:
        db: SQLAlchemy database session
        sim_time: The simulated "current time" for data queries
        station_timezone: IANA timezone string for timestamp conversion
        log_func: Optional logging function for debug output

    Returns:
        StationSnapshot with latest reading and 3-hour trend at sim_time
    """
    from app.services.nowcast_collector import (
        StationSnapshot, ObservationReading, _reading_to_obs
    )
    from app.models.sensor_reading import SensorReadingModel
    from zoneinfo import ZoneInfo

    def log(msg):
        if log_func:
            log_func(msg)

    # Remove timezone from sim_time for SQLite comparison (SQLite stores naive datetimes)
    sim_time_naive = sim_time.replace(tzinfo=None) if sim_time.tzinfo else sim_time

    # DEBUG: Check database contents
    total_count = db.query(SensorReadingModel).count()
    log(f"DEBUG: Total sensor readings in DB: {total_count}")
    log(f"DEBUG: Querying for readings <= {sim_time_naive}")

    # Get latest reading before sim_time
    latest = (
        db.query(SensorReadingModel)
        .filter(SensorReadingModel.timestamp <= sim_time_naive)
        .order_by(SensorReadingModel.timestamp.desc())
        .first()
    )

    if latest is None:
        log(f"DEBUG: Query returned None! (has_data will be False)")
        return StationSnapshot(latest=ObservationReading(), trend_3h=[], has_data=False)
    else:
        log(f"DEBUG: Found latest reading at {latest.timestamp}")

    # Resolve timezone for timestamp conversion (UTC → local)
    tz: ZoneInfo | None = None
    if station_timezone:
        try:
            tz = ZoneInfo(station_timezone)
        except (KeyError, Exception):
            log(f"Invalid station_timezone {station_timezone}, timestamps stay UTC")

    # Get 3-hour trend before sim_time
    cutoff = sim_time - timedelta(hours=3)
    cutoff_naive = cutoff.replace(tzinfo=None) if cutoff.tzinfo else cutoff
    log(f"DEBUG: Querying trend readings: {cutoff_naive} to {sim_time_naive}")
    trend_rows = (
        db.query(SensorReadingModel)
        .filter(SensorReadingModel.timestamp >= cutoff_naive)
        .filter(SensorReadingModel.timestamp <= sim_time_naive)
        .order_by(SensorReadingModel.timestamp.asc())
        .all()
    )
    log(f"DEBUG: Found {len(trend_rows)} trend readings")

    # Subsample trend to ~12 points (one per ~15 min) to keep prompt compact
    step = max(1, len(trend_rows) // 12)
    trend_sampled = [_reading_to_obs(r, tz) for r in trend_rows[::step]]
    log(f"DEBUG: Sampled to {len(trend_sampled)} readings, returning StationSnapshot with has_data=True")

    return StationSnapshot(
        latest=_reading_to_obs(latest, tz),
        trend_3h=trend_sampled,
        has_data=True
    )


async def generate_nowcast_grok(
    data: CollectedData,
    model: str = "grok-4-1-fast-reasoning",  # Latest Grok with fast reasoning
    api_key: str = None,
    horizon_hours: int = 2,
    max_tokens: int = 8000,
    radar_station: str = "",
    conversation_history: Optional[list] = None,
) -> tuple[Optional[Any], list]:
    """
    Generate nowcast using xAI Grok (second fallback after Claude).

    Uses Grok-4.1 with fast reasoning for superior analysis.
    Grok uses OpenAI-compatible API, so we use the OpenAI SDK with custom base_url.

    Args:
        data: CollectedData with station, alerts, radar, etc.
        model: Grok model to use (default: grok-beta)
        api_key: xAI API key
        horizon_hours: Forecast horizon
        max_tokens: Max response tokens
        radar_station: Radar site identifier
        conversation_history: Previous conversation messages for context continuity.

    Returns:
        Tuple of (AnalystResult or None, updated conversation history).
    """
    if conversation_history is None:
        conversation_history = []

    if not OPENAI_AVAILABLE or not api_key:
        return None, conversation_history

    try:
        # Use OpenAI SDK with xAI endpoint
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1"
        )

        # Use the same system prompt as OpenAI fallback
        # (Reusing the _build_user_message from production code)
        context_text = _build_user_message(data, horizon_hours)

        # Build messages with radar images
        user_parts = [{"type": "text", "text": context_text}]

        # Add radar images if available
        if data.radar_images:
            for img in data.radar_images:
                user_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img.png_base64}"
                    }
                })

        # Simplified system prompt (same as OpenAI - no tool use for fallback)
        from app.services.nowcast_analyst import SYSTEM_PROMPT
        # Remove zoom tool section from system prompt for fallback
        system_text = SYSTEM_PROMPT.split("ZOOM RADAR TOOL")[0] if "ZOOM RADAR TOOL" in SYSTEM_PROMPT else SYSTEM_PROMPT

        # Build messages: system + conversation history + new user message
        new_user_msg = {"role": "user", "content": user_parts}
        messages = [{"role": "system", "content": system_text}]
        messages.extend(conversation_history)
        messages.append(new_user_msg)

        # Prune old images — stored history is already compacted, but this catches
        # the new user message if it has images and we're past the retention window
        messages = [messages[0]] + prune_old_images(messages[1:], keep_last_n=1)

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1
        )

        raw_response = response.choices[0].message.content

        # Update conversation history (without system message)
        updated_history = messages[1:]  # Strip system message
        updated_history.append({"role": "assistant", "content": raw_response})

        # Parse JSON response (same format as Claude)
        import json
        import re
        json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
        else:
            parsed = json.loads(raw_response)

        # Convert to AnalystResult (same as production code)
        from app.services.nowcast_analyst import AnalystResult
        return AnalystResult(
            summary=parsed.get("summary", ""),
            current_vs_model=parsed.get("current_vs_model", ""),
            elements=parsed.get("elements", {}),
            farming_impact=parsed.get("farming_impact"),
            data_quality=parsed.get("data_quality", "Unknown"),
            proposed_knowledge=parsed.get("proposed_knowledge"),
            radar_analysis=parsed.get("radar_analysis"),
            spray_advisory=parsed.get("spray_advisory"),
            severe_weather=parsed.get("severe_weather"),
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            raw_response=raw_response
        ), updated_history

    except Exception as e:
        # Re-raise so caller can log the error properly to the simulation debug log
        raise RuntimeError(f"Grok API error: {type(e).__name__}: {e}") from e


# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


# =============================================================================
# NOTE: Data models (QLCSLine, ThreatCorridor, HailCell, StormRegime,
# RegimeParameters, REGIME_PARAMS, TrackedMesocyclone, CWOPReading,
# StationTrend) and utility functions (haversine_km, calculate_bearing,
# bearing_to_cardinal) have been extracted to:
#   backend/app/models/radar_threats.py
# =============================================================================


@dataclass
class CycleState:
    """Tracks nowcast cycle orchestration state (mimics production).

    NOTE: Tracking state (mesocyclones, regime, QLCS, hail, surface history)
    has been moved to ThreatTracker and SurfaceAnalyzer modules. CycleState
    now only holds orchestration-level fields.
    """
    cycle_interval_min: int = 15  # 15min normal, 5min during alerts
    current_model: str = 'claude-haiku-4-5-20251001'  # Haiku baseline, escalate to Sonnet
    last_alert_ids: set = None
    in_alert_mode: bool = False
    cycle_count: int = 0
    conversation_history: list = None  # Maintains conversation context across cycles

    # Previous cycle context for hysteresis
    previous_threat_level: str = None  # Previous cycle's threat level (WATCH/WARNING/EMERGENCY/None)
    previous_cycle_time: datetime = None  # When the previous cycle occurred

    def __post_init__(self):
        if self.last_alert_ids is None:
            self.last_alert_ids = set()
        if self.conversation_history is None:
            self.conversation_history = []


class RealtimeSimulator:
    """Simulates the nowcast service running during a historic event"""

    def __init__(self, event, db_path: Path, output_dir: Path, speed_factor: int = 1, force_grok: bool = False,
                 start_time_override: datetime = None, end_time_override: datetime = None,
                 multi_radar_count: int = 1):
        self.event = event
        self.db_path = db_path
        self.output_dir = output_dir
        self.speed_factor = speed_factor
        self.force_grok = force_grok
        self.start_time_override = start_time_override
        self.end_time_override = end_time_override
        self.multi_radar_count = multi_radar_count
        self._claude_cooldown_until = 0  # Cycle number until which Claude is skipped
        self.state = CycleState()

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Open log files
        self.debug_log = open(output_dir / 'simulation.log', 'w')
        self.user_log = open(output_dir / 'user_output.log', 'w')

        # Alert loader
        self.alert_loader = NWSAlertLoader()

        # NEXRAD loader for radar imagery
        cache_dir = Path('.test_cache')
        self.nexrad_loader = NEXRADLoader(cache_dir=cache_dir)

        # Modular tracking and analysis engines
        self.threat_tracker = ThreatTracker(
            station_lat=event.latitude,
            station_lon=event.longitude,
            log_func=self.log_debug,
        )
        self.surface_analyzer = SurfaceAnalyzer(
            log_func=self.log_debug,
        )

        # MRMS cross-validation (only for post-2020 events)
        self.mrms_loader = None
        if MRMS_AVAILABLE:
            self.mrms_loader = MRMSLoader(
                cache_dir=Path('.test_cache') / 'mrms',
                log_func=self.log_debug,
            )
            self.log_debug("MRMS cross-validation enabled")

        # Note: We don't load station data from the test DB because it contains
        # readings from the peak event time, not from the simulation timeline.
        # We'll build station data dynamically from CWOP at each sim_time.
        self.db_path = db_path

        self.log_debug(f"=== SIMULATION INITIALIZED ===")
        self.log_debug(f"Event: {event.name}")
        self.log_debug(f"Closest approach: {event.closest_approach.isoformat()}")
        self.log_debug(f"Speed factor: {speed_factor}x")
        self.log_debug(f"Output directory: {output_dir}")
        self.log_debug("")

    def log_debug(self, msg: str):
        """Write to debug log"""
        timestamp = datetime.now(timezone.utc).isoformat()
        self.debug_log.write(f"[{timestamp}] {msg}\n")
        self.debug_log.flush()

    def log_user(self, msg: str):
        """Write to user output log"""
        self.user_log.write(f"{msg}\n")
        self.user_log.flush()

    def print_header(self, text: str, color=Colors.BLUE):
        """Print formatted header to stdout and user log"""
        line = "=" * 80
        output = f"\n{color}{line}\n{text.center(80)}\n{line}{Colors.END}\n"
        print(output)
        self.log_user(output)

    def print_user_content(self, label: str, content: str, color=Colors.END):
        """Print user-facing content"""
        output = f"{color}{label}:{Colors.END}\n{content}\n"
        print(output)
        self.log_user(output)

    # =========================================================================
    # NOTE: Tracking methods (_compute_average_displacement, classify_storm_regime,
    # _compute_motion_vector, _predict_position, track_mesocyclones, _check_association,
    # detect_qlcs_line, track_qlcs_line, compute_threat_corridor, _update_cwop_history,
    # _compute_surface_trends, _bearing_to_cardinal) have been extracted to:
    #   backend/app/services/threat_tracker.py
    #   backend/app/services/surface_analyzer.py
    #   backend/app/services/radar_processor.py
    # =========================================================================

    # (Tracking method implementations removed — see extracted modules above)
    # Thin convenience properties to access tracking state from the simulation:

    @property
    def tracked_mesocyclones(self):
        """Access tracked mesocyclones from ThreatTracker."""
        return self.threat_tracker.state.tracked_mesocyclones

    @property
    def dissipated_mesocyclones(self):
        """Access dissipated mesocyclones from ThreatTracker."""
        return self.threat_tracker.state.dissipated_mesocyclones

    @property
    def hail_cells(self):
        """Access hail cells from ThreatTracker."""
        return self.threat_tracker.state.hail_cells

    @property
    def previous_hail_cells(self):
        """Access previous hail cells from ThreatTracker."""
        return self.threat_tracker.state.previous_hail_cells

    @property
    def current_regime(self):
        """Access current storm regime from ThreatTracker."""
        return self.threat_tracker.state.current_regime

    @property
    def tracked_qlcs_line(self):
        """Access tracked QLCS line from ThreatTracker."""
        return self.threat_tracker.state.tracked_qlcs_line

    @property
    def threat_corridor(self):
        """Access threat corridor from ThreatTracker."""
        return self.threat_tracker.state.threat_corridor

    @property
    def moderate_rotation_detections(self):
        """Access moderate rotation detections from ThreatTracker."""
        return self.threat_tracker.state.moderate_rotation_detections

    @property
    def cwop_station_history(self):
        """Access CWOP station history from SurfaceAnalyzer."""
        return self.surface_analyzer.state.cwop_station_history

    # Dummy to stop further reading of removed methods
    _TRACKING_METHODS_REMOVED = True

    async def collect_data(self, sim_time: datetime) -> CollectedData:
        """Collect CWOP, NWS alerts, and station data for a specific simulation time"""
        self.log_debug(f"--- Data Collection for {sim_time.isoformat()} ---")

        # Initialize mesocyclone nearby stations (will be populated if detection occurs)
        mesocyclone_nearby_stations = None

        # Build nearby stations snapshot for this time
        nearby_stations = build_nearby_stations(
            local_station_id='TEST',
            local_lat=self.event.latitude,
            local_lon=self.event.longitude,
            timestamp=sim_time
        )
        self.log_debug(f"Collected {len(nearby_stations.stations)} nearby CWOP stations")

        # Update CWOP station history for cycle-to-cycle trending
        self.surface_analyzer.update_history(nearby_stations, sim_time, 'local')

        # Build temporal history (last 90 minutes, 15-min intervals)
        nearby_stations_history = []
        for offset_min in range(-90, 15, 15):
            hist_time = sim_time + timedelta(minutes=offset_min)
            hist_snapshot = build_nearby_stations(
                local_station_id='TEST',
                local_lat=self.event.latitude,
                local_lon=self.event.longitude,
                timestamp=hist_time
            )
            nearby_stations_history.append({
                'timestamp': hist_time.isoformat(),
                'stations': hist_snapshot.stations
            })
        self.log_debug(f"Built temporal history: {len(nearby_stations_history)} snapshots")

        # Load NWS alerts - get ALL alert types (watches, warnings, advisories)
        # Only get alerts that were ALREADY ISSUED at sim_time (Don't look into the future!)

        # Get tornado watches AND warnings
        tornado_alerts = self.alert_loader.get_alerts_for_point(
            lat=self.event.latitude,
            lon=self.event.longitude,
            start_time=sim_time - timedelta(hours=6),  # Look back further for watches (issued hours in advance)
            end_time=sim_time,  # Don't look into the future!
            phenomena=['TO'],  # Tornado
            significance=['W', 'A']  # Warnings AND Watches
        )

        # Get severe thunderstorm watches AND warnings
        svr_alerts = self.alert_loader.get_alerts_for_point(
            lat=self.event.latitude,
            lon=self.event.longitude,
            start_time=sim_time - timedelta(hours=6),
            end_time=sim_time,
            phenomena=['SV'],  # Severe Thunderstorm
            significance=['W', 'A']  # Warnings AND Watches
        )

        # Combine all alerts
        alerts_raw = tornado_alerts + svr_alerts

        # Convert to API format - only include alerts that have been issued by sim_time
        nws_alerts = []
        self.log_debug(f"DEBUG: Processing {len(alerts_raw)} raw alerts from loader")
        for alert in alerts_raw:
            # Check issue_time (not 'issue' - the loader returns 'issue_time')
            issue_time = alert.get('issue_time')
            if issue_time:
                # If issue_time is a datetime object, use it directly
                # If it's a string, parse it
                if isinstance(issue_time, str):
                    from datetime import datetime as dt
                    try:
                        # Try ISO format first
                        issue_time = dt.fromisoformat(issue_time.replace('Z', '+00:00'))
                    except ValueError:
                        # Fall back to compact format YYYYMMDDHHmm (from IEM archive)
                        try:
                            issue_time = dt.strptime(issue_time, '%Y%m%d%H%M').replace(tzinfo=timezone.utc)
                        except ValueError as e:
                            self.log_debug(f"Failed to parse issue_time '{issue_time}': {e}")
                            continue

                # Skip alerts issued after sim_time
                if issue_time > sim_time:
                    self.log_debug(f"  Skipping future alert: issued at {issue_time}, sim_time is {sim_time}")
                    continue
                else:
                    self.log_debug(f"  ✓ Alert passed time filter: issued {issue_time}, sim_time {sim_time}")

            # Get expire_time (not 'expire')
            expire_time = alert.get('expire_time')

            # Parse expire_time if it's a string
            if expire_time and isinstance(expire_time, str):
                from datetime import datetime as dt
                try:
                    expire_time = dt.fromisoformat(expire_time.replace('Z', '+00:00'))
                except ValueError:
                    try:
                        expire_time = dt.strptime(expire_time, '%Y%m%d%H%M').replace(tzinfo=timezone.utc)
                    except ValueError:
                        expire_time = None  # Fall back to None if parse fails

            onset = issue_time.isoformat() if issue_time else sim_time.isoformat()
            expires = expire_time.isoformat() if expire_time else (sim_time + timedelta(hours=2)).isoformat()

            nws_alerts.append({
                'id': alert.get('product_id', ''),
                'event': 'Tornado Warning',
                'severity': 'Extreme',
                'urgency': 'Immediate',
                'certainty': 'Observed',
                'onset': onset,
                'expires': expires,
                'headline': alert.get('text', '')[:100],
                'description': alert.get('text', ''),
                'instruction': 'TAKE COVER NOW',
                'alert_id': alert.get('product_id', f'sim_{sim_time.timestamp()}'),
            })
            self.log_debug(f"  ✓ Added alert issued at {issue_time}")

        self.log_debug(f"Loaded {len(nws_alerts)} NWS alerts (from {len(alerts_raw)} raw)")

        # Gather local station data at sim_time using production code
        # Opens a database session to query sensor_readings at this simulation time
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine(f'sqlite:///{self.db_path}')
        Session = sessionmaker(bind=engine)
        db = Session()

        try:
            station = gather_station_data_at_time(
                db=db,
                sim_time=sim_time,
                station_timezone='America/Chicago',  # Moore, OK timezone
                log_func=self.log_debug
            )
            self.log_debug(f"Gathered station data at {sim_time.isoformat()}: "
                          f"{len(station.trend_3h)} trend readings (has_data={station.has_data})")
        finally:
            db.close()

        # Fetch NEXRAD radar images for this time (also gets CWOP near mesocyclone if detected)
        radar_images, mesocyclone_nearby_stations = self._fetch_radar_images(sim_time, nws_alerts=nws_alerts)
        self.log_debug(f"DEBUG: _fetch_radar_images returned {len(radar_images)} images, mesocyclone_nearby_stations={mesocyclone_nearby_stations}")

        # Build time-appropriate knowledge entries using the extracted module
        # IMPORTANT: Only provide knowledge that would be available at sim_time
        # to avoid causality violations (knowing about future events)

        # Event-specific location knowledge
        event_knowledge = []
        if "Moore" in self.event.name:
            event_knowledge.append("Moore, Oklahoma is in central Oklahoma, part of Tornado Alley.")
            event_knowledge.append("May is peak tornado season in Oklahoma.")
            event_knowledge.append("Moore has experienced significant tornadoes in 1999, 2003, and 2013.")
        elif "El Reno" in self.event.name:
            event_knowledge.append("El Reno, Oklahoma is in Canadian County, part of Tornado Alley.")
            event_knowledge.append("May-June is peak tornado season in Oklahoma.")
        elif "Joplin" in self.event.name:
            event_knowledge.append("Joplin, Missouri is in southwest Missouri near the Kansas border.")
            event_knowledge.append("May is peak tornado season in Missouri.")
        elif self.event.event_type == "tornado":
            event_knowledge.append(f"{self.event.cwop_region} is part of a tornado-prone region.")
            event_knowledge.append("Spring months (April-June) are peak tornado season.")

        # MRMS cross-validation (post-2020 events only)
        mrms_snapshot = None
        if self.mrms_loader and sim_time.year >= 2020:
            try:
                mrms_snapshot = self.mrms_loader.fetch_snapshot(
                    target_time=sim_time,
                    station_lat=self.event.latitude,
                    station_lon=self.event.longitude,
                    tracked_mesocyclones=self.tracked_mesocyclones,
                    hail_cells=self.hail_cells,
                )
            except Exception as exc:
                self.log_debug(f"MRMS fetch failed (non-fatal): {exc}")

        knowledge_entries = build_knowledge_entries(
            tracker_state=self.threat_tracker.state,
            surface_analyzer=self.surface_analyzer,
            previous_threat_level=self.state.previous_threat_level,
            previous_cycle_time=self.state.previous_cycle_time,
            sim_time=sim_time,
            event_knowledge=event_knowledge,
            mrms_snapshot=mrms_snapshot,
            log_func=self.log_debug,
        )

        # Add mesocyclone detection context if present - NEW MULTI-MESO FORMAT
        if self.tracked_mesocyclones:
            # Sort by threat score (highest first)
            tracked_sorted = sorted(self.tracked_mesocyclones, key=lambda m: m.threat_score, reverse=True)

            detection_lines = [
                "⚠️ AUTOMATED MESOCYCLONE DETECTION ⚠️",
                f"Radar algorithm detected {len(tracked_sorted)} active mesocyclone(s):",
                ""
            ]

            for i, meso in enumerate(tracked_sorted):
                # Determine if primary threat
                priority = "(PRIMARY THREAT)" if i == 0 else "(secondary)"

                # Categorize shear strength
                if meso.shear >= 40:
                    shear_category = "TVS-strength"
                elif meso.shear >= 30:
                    shear_category = "Strong"
                elif meso.shear >= 20:
                    shear_category = "Moderate"
                else:
                    shear_category = "Weak"

                # Calculate cardinal direction
                bearing_cardinal = bearing_to_cardinal(meso.bearing_deg)
                distance_mi = meso.distance_km * 0.621371

                # Determine movement status
                if meso.prev_distance_km:
                    dist_change = meso.distance_km - meso.prev_distance_km
                    if dist_change < -2:
                        movement = f"APPROACHING (was {meso.prev_distance_km:.1f} km)"
                    elif dist_change > 2:
                        movement = f"RECEDING (was {meso.prev_distance_km:.1f} km)"
                    else:
                        movement = "STATIONARY"
                else:
                    movement = "NEW DETECTION"

                # Format status
                status_emoji = {
                    "new": "✨",
                    "tracking": "👁",
                    "intensifying": "⚠️",
                    "dissipating": "☁️"
                }.get(meso.status, "•")

                detection_lines.extend([
                    f"{meso.id} {priority}:",
                    f"  • Location: {meso.distance_km:.1f} km ({distance_mi:.1f} mi) {bearing_cardinal}",
                    f"  • Rotation: {meso.shear:.1f} s⁻¹ ({shear_category})",
                    f"  • Threat score: {meso.threat_score:.3f}",
                    f"  • Movement: {movement}",
                    f"  • Status: {status_emoji} {meso.status.upper()} (tracked {meso.cycle_count} cycle(s))",
                    ""
                ])

            # Add lifecycle events if any
            if self.dissipated_mesocyclones:
                detection_lines.append("LIFECYCLE EVENTS:")
                for meso in self.dissipated_mesocyclones[-3:]:  # Last 3
                    detection_lines.append(f"  • {meso.id} dissipated (last seen {meso.cycle_count} cycles ago)")
                detection_lines.append("")

            detection_lines.extend([
                "REQUIRED ANALYSIS:",
                "1. Track EACH mesocyclone independently - do not conflate multiple circulations",
                "2. Focus threat assessment on PRIMARY THREAT (highest threat score)",
                "3. Compare positions to previous cycle - which are approaching vs receding?",
                "4. Correlate radar with nearby station observations (pressure/wind/temp anomalies)",
                "5. Assess whether PRIMARY threat is increasing or decreasing",
                "6. Determine if threat is upstream (danger) or downstream (passed)",
                "7. Make threat level decision independent of NWS warnings - hyper-local assessment",
                "",
                "CRITICAL: If PRIMARY threat is >50 km away OR downstream with no upstream threats,",
                "de-escalate from WARNING/EMERGENCY regardless of NWS alert status. NWS polygons cover",
                "large areas (~10-20 miles); your job is last-mile precision for THIS specific location.",
                "",
                "MULTI-VORTEX GUIDANCE: Multiple mesocyclones may indicate:",
                "  • Complex supercell with satellite circulations",
                "  • Multiple storm cells in the area",
                "  • Cycling mesocyclone (old dissipating, new forming)",
                "Track the PRIMARY THREAT but be aware of upstream secondary threats that may intensify."
            ])

            detection_note = "\n".join(detection_lines)
            knowledge_entries.append(detection_note)

            primary = tracked_sorted[0] if tracked_sorted else None

            # Add surface observations near the mesocyclone for correlation
            self.log_debug(f"  DEBUG: Checking mesocyclone_nearby_stations...")
            self.log_debug(f"  DEBUG: mesocyclone_nearby_stations = {mesocyclone_nearby_stations}")
            if mesocyclone_nearby_stations:
                if hasattr(mesocyclone_nearby_stations, 'stations'):
                    self.log_debug(f"  DEBUG: Has .stations attribute with {len(mesocyclone_nearby_stations.stations)} stations")
                else:
                    self.log_debug(f"  DEBUG: NO .stations attribute! Type: {type(mesocyclone_nearby_stations)}")
            else:
                self.log_debug(f"  DEBUG: mesocyclone_nearby_stations is None/False!")

            if mesocyclone_nearby_stations and mesocyclone_nearby_stations.stations:
                self.log_debug(f"  DEBUG: INSIDE if block - ADDING mesocyclone CWOP to knowledge_entries!")
                meso_range = primary.raw_detection.get('range_km', 0) if primary and primary.raw_detection else 0
                meso_obs_lines = [
                    f"\n📍 SURFACE OBSERVATIONS NEAR MESOCYCLONE LOCATION ({meso_range:.1f} km from radar):",
                    f"The following stations are located near the detected mesocyclone to help you assess surface correlation:"
                ]
                for obs in mesocyclone_nearby_stations.stations[:5]:  # Limit to 5 closest stations
                    fields = [f"{obs.station_id} ({obs.distance_miles:.1f} mi from meso)"]
                    if obs.pressure_inhg is not None:
                        fields.append(f"Baro={obs.pressure_inhg:.2f}inHg")
                    if obs.temp_f is not None:
                        fields.append(f"Temp={obs.temp_f:.1f}F")
                    if obs.wind_speed_mph is not None and obs.wind_dir_deg is not None:
                        fields.append(f"Wind={obs.wind_speed_mph:.0f}mph@{obs.wind_dir_deg}deg")
                    meso_obs_lines.append(f"  • {', '.join(fields)}")

                meso_obs_lines.append(
                    f"\nUse these observations to validate the mesocyclone: Look for pressure drops, wind shifts, "
                    f"temperature changes, or RFD signatures near the rotation center. This helps distinguish "
                    f"real mesocyclones from false positives."
                )
                knowledge_entries.append("\n".join(meso_obs_lines))
                self.log_debug(f"  DEBUG: Added mesocyclone CWOP entry. Total knowledge_entries: {len(knowledge_entries)}")
            else:
                self.log_debug(f"  DEBUG: Did NOT add mesocyclone CWOP (condition failed)")

        self.log_debug(f"  DEBUG: Final knowledge_entries count: {len(knowledge_entries)}")

        # Build CollectedData
        collected_data = CollectedData(
            station=station,
            nws_alerts=nws_alerts,
            nearby_stations=nearby_stations,
            nearby_stations_history=nearby_stations_history,
            radar_station=self.event.radar_station,
            radar_images=radar_images,
            location={'latitude': self.event.latitude, 'longitude': self.event.longitude},
            station_timezone='America/Chicago',
            collected_at=sim_time.isoformat(),
            knowledge_entries=knowledge_entries,
        )

        return collected_data, nws_alerts


    def _fetch_radar_images(self, sim_time: datetime,
                            nws_alerts: Optional[List[Dict]] = None) -> tuple[List[RadarImage], Any]:
        """
        Fetch NEXRAD radar images, run detection/tracking, and generate composites.

        Delegates to extracted modules:
        - process_radar_volume() for detection
        - threat_tracker.update() for persistent tracking
        - radar_visualizer functions for composite plots
        """
        import base64
        import time

        radar_site = self.event.radar_station
        station_lat = self.event.latitude
        station_lon = self.event.longitude
        mesocyclone_nearby_stations = None

        try:
            # Step 1: Determine radars to process
            if self.multi_radar_count > 1:
                nearby = find_nearby_radars(
                    station_lat, station_lon,
                    max_range_km=200, max_count=self.multi_radar_count,
                )
                radar_sites = [code for code, _ in nearby]
                # Ensure the event's primary radar is included
                if radar_site not in radar_sites:
                    radar_sites = [radar_site] + radar_sites[:self.multi_radar_count - 1]
                self.log_debug(f"Multi-radar mode: {', '.join(radar_sites)}")
            else:
                radar_sites = [radar_site]
                self.log_debug(f"Fetching NEXRAD data from {radar_site}...")

            # Step 2: Load and process each radar volume
            per_radar_results = []
            primary_radar = None   # Py-ART object for visualization
            primary_key = None     # S3 key for image source URL

            for site in radar_sites:
                files = self.nexrad_loader.list_files(
                    site=site,
                    start_time=sim_time - timedelta(minutes=10),
                    end_time=sim_time + timedelta(minutes=10),
                )
                if not files:
                    self.log_debug(f"  {site}: no data available")
                    continue

                def time_diff(key):
                    ft = self.nexrad_loader._parse_filename_timestamp(key)
                    return abs((ft - sim_time).total_seconds()) if ft else float('inf')

                closest_key = min(files, key=time_diff)
                file_time = self.nexrad_loader._parse_filename_timestamp(closest_key)

                local_path = self.nexrad_loader.download_file(closest_key)
                radar = self.nexrad_loader.read_radar(local_path)
                self.log_debug(f"  {site}: loaded {closest_key.split('/')[-1]} ({file_time})")

                result = process_radar_volume(
                    radar=radar,
                    station_lat=station_lat,
                    station_lon=station_lon,
                    radar_site=site,
                    nexrad_loader=self.nexrad_loader,
                    freezing_level_m=getattr(self.event, 'freezing_level_m', 4000),
                    max_hail_range_km=80,
                    current_regime=self.threat_tracker.state.current_regime,
                    log_func=self.log_debug,
                )
                result.radar_timestamp = file_time
                per_radar_results.append(result)

                # Keep the primary radar's Py-ART object for visualization
                if site == radar_sites[0]:
                    primary_radar = radar
                    primary_key = closest_key

            if not per_radar_results:
                self.log_debug("  No NEXRAD data available from any radar")
                return [], None

            # Step 2b: Merge results if multi-radar
            if len(per_radar_results) > 1:
                radar_result = merge_radar_results(per_radar_results, log_func=self.log_debug)
            else:
                radar_result = per_radar_results[0]

            radar = primary_radar
            closest_key = primary_key
            file_time = radar_result.radar_timestamp

            # Step 3: Update persistent tracking (regime, meso tracking, QLCS, hail)
            self.threat_tracker.update(radar_result, sim_time, nws_alerts=nws_alerts)

            # Step 4: Fetch CWOP near primary mesocyclone for surface correlation
            primary_dict = self.threat_tracker.get_primary_detection_dict()
            if primary_dict:
                meso_lat = primary_dict['latitude']
                meso_lon = primary_dict['longitude']

                mesocyclone_nearby_stations = build_nearby_stations(
                    local_station_id='MESOCYCLONE',
                    local_lat=meso_lat,
                    local_lon=meso_lon,
                    timestamp=sim_time
                )
                self.log_debug(f"  Collected {len(mesocyclone_nearby_stations.stations)} CWOP stations near mesocyclone")
                self.surface_analyzer.update_history(mesocyclone_nearby_stations, sim_time, 'meso')

                # Dynamic corridor expansion for distant mesocyclones
                meso_dist_mi = primary_dict.get('distance_to_station_km', 0) * 0.621371
                if meso_dist_mi > 40:
                    mid_lat = (station_lat + meso_lat) / 2
                    mid_lon = (station_lon + meso_lon) / 2
                    corridor_radius = min(meso_dist_mi / 2 + 10, 80)
                    corridor_stations = build_nearby_stations(
                        local_station_id='CORRIDOR',
                        local_lat=mid_lat,
                        local_lon=mid_lon,
                        timestamp=sim_time,
                        radius_miles=corridor_radius
                    )
                    self.surface_analyzer.update_history(corridor_stations, sim_time, 'corridor')
                    self.log_debug(
                        f"  CORRIDOR: {len(corridor_stations.stations)} stations "
                        f"at midpoint ({mid_lat:.2f}, {mid_lon:.2f}), radius {corridor_radius:.0f} mi"
                    )

            # Step 5: Generate radar images for analyst
            radar_images = []
            detections = radar_result.all_detections

            if detections:
                strongest = max(detections, key=lambda d: d['max_shear'])
                elev_idx = strongest['elevation_index']

                # Detection composite (reflectivity + velocity side-by-side)
                composite_bytes = generate_detection_composite(
                    radar, strongest, radar_site, self.nexrad_loader,
                    log_func=self.log_debug,
                )

                if composite_bytes:
                    png_base64 = base64.b64encode(composite_bytes).decode('utf-8')
                    radar_lat = radar.latitude['data'][0]
                    radar_lon = radar.longitude['data'][0]
                    range_km = 60
                    lat_delta = range_km / 111.0
                    lon_delta = range_km / (111.0 * np.cos(np.radians(radar_lat)))
                    bbox = (
                        radar_lon - lon_delta, radar_lat - lat_delta,
                        radar_lon + lon_delta, radar_lat + lat_delta,
                    )
                    radar_images.append(RadarImage(
                        product_id='mesocyclone_composite',
                        label=f'MESOCYCLONE DETECTION: {strongest["max_shear"]:.1f} s\u207b\u00b9 @ {strongest["elevation_angle"]:.2f}\u00b0',
                        png_base64=png_base64,
                        width=1600, height=700, bbox=bbox,
                        fetched_at=time.time(),
                        source_url=f"s3://{self.nexrad_loader.BUCKET}/{closest_key}",
                    ))
                    self.log_debug(f"  Generated mesocyclone composite")
            else:
                elev_idx = 0

            # Standard single-elevation images
            for product in ['reflectivity', 'velocity']:
                img_data = self.nexrad_loader.generate_radar_image(
                    radar, product=product,
                    elevation_index=elev_idx, range_km=120, size_px=800,
                )
                if img_data:
                    png_base64 = base64.b64encode(img_data['png_bytes']).decode('utf-8')
                    radar_images.append(RadarImage(
                        product_id=product,
                        label=f'NEXRAD {product.title()}',
                        png_base64=png_base64,
                        width=img_data['width'], height=img_data['height'],
                        bbox=img_data['bbox'], fetched_at=time.time(),
                        source_url=f"s3://{self.nexrad_loader.BUCKET}/{closest_key}",
                    ))

            self.log_debug(f"  Generated {len(radar_images)} radar products")

            # Step 6: Generate diagnostic composite plots
            try:
                # Compute local surface trends for surface analysis
                local_trends, _ = self.surface_analyzer.compute_trends('local')

                generate_situation_composite(
                    radar=radar, sim_time=sim_time,
                    station_lat=station_lat, station_lon=station_lon,
                    event_name=self.event.name, radar_station=radar_site,
                    cycle_count=self.state.cycle_count,
                    tracked_mesocyclones=self.tracked_mesocyclones,
                    hail_cells=self.hail_cells,
                    tracked_qlcs_line=self.tracked_qlcs_line,
                    cwop_station_history=self.cwop_station_history,
                    output_path=self.output_dir / 'situation_composite.png',
                    log_func=self.log_debug,
                )
            except Exception as e:
                self.log_debug(f"  Warning: Situation composite failed: {e}")

            try:
                local_trends, _ = self.surface_analyzer.compute_trends('local')
                generate_surface_analysis(
                    sim_time=sim_time,
                    station_lat=station_lat, station_lon=station_lon,
                    event_name=self.event.name, cycle_count=self.state.cycle_count,
                    cwop_station_history=self.cwop_station_history,
                    station_trends=local_trends,
                    tracked_mesocyclones=self.tracked_mesocyclones,
                    output_path=self.output_dir / 'surface_analysis.png',
                    log_func=self.log_debug,
                )
            except Exception as e:
                self.log_debug(f"  Warning: Surface analysis failed: {e}")

            # Save radar images to disk for inspection
            for img in radar_images:
                img_path = self.output_dir / f'radar_{img.product_id}.png'
                try:
                    img_bytes = base64.b64decode(img.png_base64)
                    with open(img_path, 'wb') as f:
                        f.write(img_bytes)
                    self.log_debug(f"  Saved {img.product_id} to {img_path.name}")
                except Exception as e:
                    self.log_debug(f"  Failed to save {img.product_id}: {e}")

            # Free the massive Py-ART radar object (~260 MB per volume)
            del radar
            import gc
            gc.collect()

            return radar_images, mesocyclone_nearby_stations

        except Exception as e:
            self.log_debug(f"  Warning: NEXRAD fetch failed: {e}")
            return [], None

    # NOTE: Visualization methods (_generate_detection_composite,
    # _generate_situation_composite, _generate_surface_analysis) have been
    # extracted to backend/app/services/radar_visualizer.py and are called
    # as standalone functions from _fetch_radar_images above.

    def get_nws_threat_level(self, nws_alerts: List[Dict]) -> str:
        """Derive NWS threat level from active alerts"""
        if not nws_alerts:
            return "NONE"

        # Check for tornado warnings (highest priority)
        for alert in nws_alerts:
            event = alert.get('event', '').lower()
            certainty = alert.get('certainty', '').lower()

            # Tornado Warning with "Observed" certainty = EMERGENCY level
            if 'tornado warning' in event and 'observed' in certainty:
                return "EMERGENCY"

            # Tornado Warning (general) = WARNING level
            if 'tornado warning' in event:
                return "WARNING"

        # Check for watches
        for alert in nws_alerts:
            event = alert.get('event', '').lower()
            if 'tornado watch' in event or 'severe thunderstorm watch' in event:
                return "WATCH"

        # Other severe alerts = WATCH
        for alert in nws_alerts:
            severity = alert.get('severity', '').lower()
            if severity in ['extreme', 'severe']:
                return "WATCH"

        return "NONE"

    def check_alert_escalation(self, nws_alerts: List[Dict]) -> bool:
        """Check if we should escalate cycle timing and model"""
        extreme_severe_alerts = [
            a for a in nws_alerts
            if a.get('severity') in ['Extreme', 'Severe']
        ]

        if extreme_severe_alerts and not self.state.in_alert_mode:
            self.log_debug("⚠️  ESCALATION: Extreme/Severe alerts detected - switching to 5-min cycles + Sonnet")
            self.state.cycle_interval_min = 5
            self.state.current_model = 'claude-sonnet-4-5-20250929'
            self.state.in_alert_mode = True
            return True
        elif not extreme_severe_alerts and self.state.in_alert_mode:
            self.log_debug("ℹ️  DE-ESCALATION: No more Extreme/Severe alerts - returning to 15-min cycles + Haiku")
            self.state.cycle_interval_min = 15
            self.state.current_model = 'claude-haiku-4-5-20251001'
            self.state.in_alert_mode = False
            return True

        return False

    def check_new_alerts(self, nws_alerts: List[Dict]) -> bool:
        """Check if there are new alerts (triggers mid-cycle regeneration)"""
        current_alert_ids = {a.get('alert_id') for a in nws_alerts}
        new_alerts = current_alert_ids - self.state.last_alert_ids
        self.state.last_alert_ids = current_alert_ids

        if new_alerts:
            self.log_debug(f"🚨 NEW ALERTS detected: {new_alerts}")
            return True
        return False

    async def run_cycle(self, sim_time: datetime, cycle_num: int, is_mid_cycle: bool = False):
        """Execute a single nowcast cycle"""
        self.state.cycle_count += 1

        cycle_label = f"CYCLE #{cycle_num}"
        if is_mid_cycle:
            cycle_label += " (MID-CYCLE REGENERATION)"

        self.log_debug(f"\n{'='*80}")
        self.log_debug(f"{cycle_label}")
        self.log_debug(f"Simulation time: {sim_time.isoformat()}")
        self.log_debug(f"Model: {self.state.current_model}")
        self.log_debug(f"Interval: {self.state.cycle_interval_min} minutes")
        self.log_debug(f"Alert mode: {self.state.in_alert_mode}")
        self.log_debug(f"{'='*80}")

        # Display cycle header to user
        time_relative = sim_time - self.event.closest_approach
        minutes_to_event = int(time_relative.total_seconds() / 60)
        time_label = f"T{minutes_to_event:+d} min" if minutes_to_event != 0 else "T-NOW"

        self.print_header(
            f"{cycle_label} - {time_label} ({sim_time.strftime('%H:%M:%S UTC')})",
            color=Colors.RED if is_mid_cycle else Colors.BLUE
        )

        try:
            # Collect data
            print(f"{Colors.CYAN}📊 Collecting data...{Colors.END}")
            collected_data, nws_alerts = await self.collect_data(sim_time)

            # Check for escalation
            escalated = self.check_alert_escalation(nws_alerts)
            if escalated:
                escalation_msg = f"⚠️  Alert mode: {'ACTIVE' if self.state.in_alert_mode else 'INACTIVE'} | " \
                                f"Cycle: {self.state.cycle_interval_min} min | " \
                                f"Model: {self.state.current_model.split('-')[1].upper()}"
                print(f"{Colors.YELLOW}{escalation_msg}{Colors.END}")
                self.log_user(escalation_msg)

            # Check for new alerts (for next cycle's mid-cycle regeneration check)
            self.check_new_alerts(nws_alerts)

            # Call Claude (or skip if --force-grok)
            result = None
            is_overload = False

            # Check cooldown — skip Claude if recently failed with auth error
            skip_claude = self.force_grok
            if not skip_claude and self.state.cycle_count < self._claude_cooldown_until:
                skip_claude = True
                remaining = self._claude_cooldown_until - self.state.cycle_count
                self.log_debug(f"🔑 Claude on cooldown ({remaining} cycles left), skipping to fallback")

            if not skip_claude:
                print(f"{Colors.CYAN}🤖 Generating nowcast with {self.state.current_model.split('-')[1].upper()}...{Colors.END}")
                self.log_debug(f"Calling Claude API: {self.state.current_model}")

            try:
                if skip_claude:
                    if self.force_grok:
                        self.log_debug("⚠️  --force-grok enabled, skipping Claude")
                    result = None
                else:
                    self.log_debug(f"Calling generate_nowcast with max_tokens=8000, radar_station={self.event.radar_station}")
                    self.log_debug(f"Conversation history: {len(self.state.conversation_history)} messages")
                    result, updated_history = await generate_nowcast(
                        data=collected_data,
                        model=self.state.current_model,
                        api_key_from_db=ANTHROPIC_API_KEY,
                        horizon_hours=2,
                        max_tokens=8000,  # Increased for testing to allow full analysis with radar
                        radar_station=self.event.radar_station,
                        conversation_history=self.state.conversation_history,
                    )
                    # Update conversation history for next cycle
                    self.state.conversation_history = compact_history(updated_history)
                    self.log_debug(f"Updated conversation history: {len(self.state.conversation_history)} messages")
                    if result is None:
                        from app.services.nowcast_analyst import last_api_error
                        self.log_debug(f"generate_nowcast returned None: {last_api_error or 'unknown reason'}")
                    else:
                        self.log_debug(f"generate_nowcast succeeded, checking result attributes...")
                        if hasattr(result, 'parse_failed') and result.parse_failed:
                            self.log_debug(f"⚠️  Result has parse_failed=True!")
                            self.log_debug(f"   Raw response[:500]: {result.raw_response[:500]}")
                        if hasattr(result, 'truncated') and result.truncated:
                            self.log_debug(f"⚠️  Result was truncated at max_tokens")
            except Exception as e:
                self.log_debug(f"❌ Claude API exception: {type(e).__name__}: {str(e)}")
                self.log_debug(f"   Full traceback:\n{traceback.format_exc()}")
                result = None

                # Check if this is an overload error (529)
                is_overload = "overload" in str(e).lower() or "529" in str(e)

            # Check for API errors — apply error-specific cooldown
            is_auth_error = False
            if result is None and not self.force_grok:
                from app.services.nowcast_analyst import last_api_error as _auth_check
                err_str = str(_auth_check) if _auth_check else ""
                if "AuthenticationError" in err_str or "401" in err_str:
                    # Auth/billing — long cooldown (key invalid or budget exhausted)
                    is_auth_error = True
                    self._claude_cooldown_until = self.state.cycle_count + 10
                    self.log_debug(f"🔑 Auth/billing error — Claude cooldown until cycle {self._claude_cooldown_until}")
                    print(f"{Colors.YELLOW}🔑 Claude API auth/billing failed — cooldown 10 cycles{Colors.END}")
                elif "RateLimitError" in err_str or "429" in err_str:
                    # Rate limit — short cooldown (transient)
                    is_auth_error = True
                    self._claude_cooldown_until = self.state.cycle_count + 3
                    self.log_debug(f"⏱️ Rate limited — Claude cooldown until cycle {self._claude_cooldown_until}")
                    print(f"{Colors.YELLOW}⏱️ Claude rate limited — cooldown 3 cycles{Colors.END}")

            # Retry Claude with exponential backoff on failure (unless skipped or auth error)
            if result is None and not skip_claude and not is_auth_error:
                if is_overload:
                    # API overload - use longer backoff and clear messaging
                    retry_delay = 10
                    self.log_debug(f"⚠️  Claude API overloaded (529), waiting {retry_delay}s before retry...")
                    print(f"{Colors.YELLOW}⚠️  Anthropic API is overloaded (529 error).{Colors.END}")
                    print(f"{Colors.YELLOW}   This is an Anthropic infrastructure issue, not a code bug.{Colors.END}")
                    print(f"{Colors.YELLOW}   Waiting {retry_delay}s before retry...{Colors.END}")
                else:
                    # Other error - shorter retry
                    retry_delay = 3
                    self.log_debug(f"⚠️  Claude failed, retrying in {retry_delay}s...")
                    print(f"{Colors.YELLOW}⚠️  Claude API failed, retrying once...{Colors.END}")

                await asyncio.sleep(retry_delay)

                try:
                    result, updated_history = await generate_nowcast(
                        data=collected_data,
                        model=self.state.current_model,
                        api_key_from_db=ANTHROPIC_API_KEY,
                        horizon_hours=2,
                        max_tokens=8000,
                        radar_station=self.event.radar_station,
                        conversation_history=self.state.conversation_history,
                    )
                    # Update conversation history for next cycle
                    self.state.conversation_history = compact_history(updated_history)
                except Exception as e:
                    self.log_debug(f"❌ Claude API retry exception: {type(e).__name__}: {str(e)}")
                    self.log_debug(f"   Full traceback:\n{traceback.format_exc()}")
                    result = None

                    # Check if retry also hit overload
                    if "overload" in str(e).lower() or "529" in str(e):
                        self.log_debug("⚠️  Claude API still overloaded after retry")
                        print(f"{Colors.YELLOW}⚠️  Anthropic API still overloaded after {retry_delay}s wait.{Colors.END}")
                        print(f"{Colors.YELLOW}   Falling back to OpenAI GPT-4o...{Colors.END}")

            # Fallback chain: Claude → Grok → OpenAI
            self.log_debug(f"Fallback check: result={result}, XAI_API_KEY={'SET' if XAI_API_KEY else 'NOT SET'}, OPENAI_API_KEY={'SET' if OPENAI_API_KEY else 'NOT SET'}")

            # First fallback: Try Grok
            if result is None and OPENAI_AVAILABLE and XAI_API_KEY:
                from app.services.nowcast_analyst import last_api_error as _api_err
                self.log_debug(f"⚠️  Claude failed ({_api_err or 'unknown'}), falling back to Grok...")
                print(f"{Colors.YELLOW}🔄 Claude failed: {_api_err or 'unknown reason'}{Colors.END}")
                print(f"{Colors.YELLOW}   Falling back to xAI Grok (deep thinking)...{Colors.END}")

                try:
                    result, updated_history = await generate_nowcast_grok(
                        data=collected_data,
                        model="grok-4-1-fast-reasoning",
                        api_key=XAI_API_KEY,
                        horizon_hours=2,
                        max_tokens=8000,
                        radar_station=self.event.radar_station,
                        conversation_history=self.state.conversation_history,
                    )

                    if result is not None:
                        self.state.conversation_history = compact_history(updated_history)
                        self.log_debug(f"✓ Grok fallback succeeded (history: {len(self.state.conversation_history)} messages)")
                        print(f"{Colors.GREEN}✓ Using Grok nowcast{Colors.END}")
                    else:
                        self.log_debug("❌ Grok fallback returned None (openai SDK unavailable or no API key)")
                except Exception as e:
                    self.log_debug(f"❌ Grok fallback exception: {type(e).__name__}: {str(e)}")
                    self.log_debug(f"   Traceback: {traceback.format_exc()}")
                    result = None

            # Second fallback: Try OpenAI if Grok also failed
            if result is None and OPENAI_AVAILABLE and OPENAI_API_KEY:
                self.log_debug("⚠️  Grok also failed, falling back to OpenAI GPT-4o...")
                print(f"{Colors.YELLOW}🔄 Falling back to OpenAI GPT-4o (last resort)...{Colors.END}")

                try:
                    result, updated_history = await generate_nowcast_openai(
                        data=collected_data,
                        model="gpt-4o",
                        api_key=OPENAI_API_KEY,
                        horizon_hours=2,
                        max_tokens=8000,
                        radar_station=self.event.radar_station,
                        conversation_history=self.state.conversation_history,
                    )

                    if result is not None:
                        self.state.conversation_history = compact_history(updated_history)
                        self.log_debug(f"✓ OpenAI fallback succeeded (history: {len(self.state.conversation_history)} messages)")
                        print(f"{Colors.GREEN}✓ Using OpenAI GPT-4o nowcast{Colors.END}")
                    else:
                        self.log_debug("❌ OpenAI fallback returned None (check stderr for errors)")
                except Exception as e:
                    self.log_debug(f"❌ OpenAI fallback exception: {type(e).__name__}: {str(e)}")
                    self.log_debug(f"   Traceback: {traceback.format_exc()}")

            if result is None:
                self.log_debug("❌ ERROR: No result from Claude, Grok, or OpenAI")
                print(f"{Colors.RED}❌ Nowcast generation failed (all providers){Colors.END}")
                return

            self.log_debug(f"✓ Received nowcast response")
            self.log_debug(f"  Summary length: {len(result.summary)} chars")
            self.log_debug(f"  Severe weather: {result.severe_weather is not None}")

            # Display user-facing content
            print(f"\n{Colors.BOLD}{'─'*80}{Colors.END}")

            # Dual threat level display (NWS + Hyper-local)
            nws_level = self.get_nws_threat_level(nws_alerts)

            if result.severe_weather:
                hyper_local_level = result.severe_weather.get('threat_level', 'UNKNOWN')
                hyper_local_color = Colors.RED if hyper_local_level == 'EMERGENCY' else Colors.YELLOW

                # Determine NWS color
                nws_color = Colors.RED if nws_level == 'EMERGENCY' else (Colors.YELLOW if nws_level in ['WARNING', 'WATCH'] else Colors.GREEN)

                # Display both levels
                self.print_user_content(
                    "🚨 THREAT LEVEL",
                    f"{hyper_local_color}{Colors.BOLD}{hyper_local_level}{Colors.END}",
                    color=hyper_local_color
                )

                # Show NWS level for comparison
                if nws_level != 'NONE':
                    self.print_user_content(
                        "📡 NWS ALERT LEVEL",
                        f"{nws_color}{Colors.BOLD}{nws_level}{Colors.END} (regional polygon)",
                        color=nws_color
                    )

                    # Add explanatory note if levels differ significantly
                    if (hyper_local_level == 'WATCH' and nws_level in ['WARNING', 'EMERGENCY']) or \
                       (hyper_local_level == 'WARNING' and nws_level == 'EMERGENCY'):
                        print(f"{Colors.CYAN}   ℹ️  Hyper-local assessment differs from NWS regional alert. Monitor both.{Colors.END}")
            else:
                self.print_user_content("✅ CONDITIONS", "No severe weather detected", color=Colors.GREEN)

                # Still show NWS level if active (hyper-local sees no threat but NWS has warnings)
                if nws_level != 'NONE':
                    nws_color = Colors.RED if nws_level == 'EMERGENCY' else Colors.YELLOW
                    self.print_user_content(
                        "📡 NWS ALERT LEVEL",
                        f"{nws_color}{Colors.BOLD}{nws_level}{Colors.END} (regional - not affecting this specific location)",
                        color=nws_color
                    )

            # Summary
            self.print_user_content("📋 SUMMARY", result.summary)

            # Local evidence
            if result.severe_weather and result.severe_weather.get('local_evidence'):
                evidence_text = "\n".join(f"  • {e}" for e in result.severe_weather['local_evidence'])
                self.print_user_content("🔍 LOCAL EVIDENCE", evidence_text)

            # Recommended action
            if result.severe_weather and result.severe_weather.get('recommended_action'):
                hyper_local_level = result.severe_weather.get('threat_level', 'UNKNOWN')
                self.print_user_content(
                    "⚠️  RECOMMENDED ACTION",
                    result.severe_weather['recommended_action'],
                    color=Colors.RED if hyper_local_level == 'EMERGENCY' else Colors.YELLOW
                )

            # Radar analysis
            if result.radar_analysis:
                self.print_user_content("📡 RADAR ANALYSIS", result.radar_analysis)

            # Data quality
            if result.data_quality:
                self.print_user_content("📊 DATA QUALITY", result.data_quality, color=Colors.CYAN)

            print(f"{Colors.BOLD}{'─'*80}{Colors.END}\n")

            # Log full response to debug log
            self.log_debug("\n--- FULL NOWCAST RESPONSE ---")
            self.log_debug(json.dumps({
                'summary': result.summary,
                'severe_weather': result.severe_weather,
                'radar_analysis': result.radar_analysis,
                'data_quality': result.data_quality,
            }, indent=2))
            self.log_debug("--- END RESPONSE ---\n")

            # Store current threat level for next cycle's hysteresis check
            if result.severe_weather:
                current_threat_level = result.severe_weather.get('threat_level')
                self.state.previous_threat_level = current_threat_level
                self.state.previous_cycle_time = sim_time
                self.log_debug(f"📝 Stored threat level for next cycle: {current_threat_level}")
            else:
                self.state.previous_threat_level = None
                self.state.previous_cycle_time = sim_time

        except Exception as e:
            self.log_debug(f"❌ ERROR in cycle: {e}")
            self.log_debug(traceback.format_exc())
            print(f"{Colors.RED}❌ ERROR: {e}{Colors.END}")

    async def run_simulation(self):
        """Run the complete simulation"""
        self.print_header(
            f"REAL-TIME SIMULATION: {self.event.name.upper()}",
            color=Colors.BOLD
        )

        print(f"{Colors.CYAN}Event:{Colors.END} {self.event.name}")
        print(f"{Colors.CYAN}Intensity:{Colors.END} {self.event.intensity}")
        print(f"{Colors.CYAN}Closest approach:{Colors.END} {self.event.closest_approach.strftime('%Y-%m-%d %H:%M UTC')}")
        window_desc = "T-2hr to T+2hr"
        if self.start_time_override or self.end_time_override:
            s = (self.start_time_override or (self.event.closest_approach - timedelta(hours=2))).strftime('%H:%M')
            e = (self.end_time_override or (self.event.closest_approach + timedelta(hours=2))).strftime('%H:%M')
            window_desc = f"{s} to {e} UTC (custom)"
        print(f"{Colors.CYAN}Simulation window:{Colors.END} {window_desc}")
        print(f"{Colors.CYAN}Speed:{Colors.END} {self.speed_factor}x")
        print(f"{Colors.CYAN}Output directory:{Colors.END} {self.output_dir}")
        print()

        # Calculate cycle times (use overrides if provided)
        start_time = self.start_time_override or (self.event.closest_approach - timedelta(hours=2))
        end_time = self.end_time_override or (self.event.closest_approach + timedelta(hours=2))

        current_time = start_time
        cycle_num = 0

        print(f"{Colors.GREEN}🚀 Starting simulation...{Colors.END}\n")
        self.log_debug(f"Simulation start: {start_time.isoformat()}")
        self.log_debug(f"Simulation end: {end_time.isoformat()}")

        while current_time <= end_time:
            cycle_num += 1

            # Run cycle
            await self.run_cycle(current_time, cycle_num)

            # Calculate next cycle time
            next_cycle_time = current_time + timedelta(minutes=self.state.cycle_interval_min)

            # Sleep until next cycle (adjusted for speed factor)
            if next_cycle_time <= end_time:
                sleep_seconds = self.state.cycle_interval_min * 60 / self.speed_factor

                print(f"{Colors.CYAN}⏳ Next cycle in {self.state.cycle_interval_min} minutes "
                      f"(sleeping {sleep_seconds:.1f}s at {self.speed_factor}x speed)...{Colors.END}\n")
                self.log_debug(f"Sleeping {sleep_seconds:.1f}s until next cycle")

                await asyncio.sleep(sleep_seconds)

            current_time = next_cycle_time

        # Simulation complete
        self.print_header("SIMULATION COMPLETE", color=Colors.GREEN)
        print(f"{Colors.GREEN}Total cycles executed: {cycle_num}{Colors.END}")
        print(f"{Colors.GREEN}Output saved to: {self.output_dir}{Colors.END}")

        self.log_debug("\n=== SIMULATION COMPLETE ===")
        self.log_debug(f"Total cycles: {cycle_num}")

        # Close log files
        self.debug_log.close()
        self.user_log.close()


async def main():
    import argparse

    parser = argparse.ArgumentParser(description='Real-time event simulation')
    parser.add_argument('--event', type=str, required=True, help='Event name (e.g., "Moore EF5 Tornado")')
    parser.add_argument('--speed', type=int, default=1, help='Time acceleration factor (default: 1 = real-time)')
    parser.add_argument('--force-grok', action='store_true', help='Skip Claude and go directly to Grok (for testing)')
    parser.add_argument('--start-time', type=str, default=None, help='Override start time (ISO 8601 UTC, e.g., 2011-04-16T18:45:00Z)')
    parser.add_argument('--end-time', type=str, default=None, help='Override end time (ISO 8601 UTC, e.g., 2011-04-16T21:00:00Z)')
    parser.add_argument('--multi-radar', type=int, default=1, metavar='N',
                        help='Number of radars to process per cycle (default: 1 = single radar, 2-3 recommended)')

    args = parser.parse_args()

    # Load event configuration from JSON
    try:
        event_config = load_event_config(args.event)
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ {e}")
        return 1

    # Validate/seed database
    cache_dir = Path('.test_cache')
    cache_dir.mkdir(exist_ok=True)

    try:
        db_path = validate_and_seed_database(event_config, cache_dir)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"❌ {e}")
        return 1

    # Create HistoricEvent object from config (for compatibility with existing code)
    from datetime import datetime, timezone
    from HISTORIC_EVENTS_CATALOG import HistoricEvent

    event = HistoricEvent(
        name=event_config['name'],
        event_type=event_config['event_type'],
        date=datetime.fromisoformat(event_config['date'].replace('Z', '+00:00')),
        closest_approach=datetime.fromisoformat(event_config['closest_approach'].replace('Z', '+00:00')),
        latitude=event_config['latitude'],
        longitude=event_config['longitude'],
        intensity=event_config['intensity'],
        description=event_config['description'],
        radar_station=event_config.get('radar_station', 'KTLX'),
        freezing_level_m=event_config.get('freezing_level_m', 4000),
        cwop_region=event_config['cwop_region'],
        approach_duration_min=event_config['approach_duration_min'],
        departure_duration_min=event_config['departure_duration_min']
    )

    # Output directory
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    event_slug = event.name.lower().replace(' ', '_')
    sim_dir = Path('.test_cache') / 'simulations'
    sim_dir.mkdir(parents=True, exist_ok=True)
    output_dir = sim_dir / f'realtime_sim_{event_slug}_{timestamp}'

    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        print(f"\n\n{Colors.YELLOW}🛑 Simulation interrupted by user (Ctrl+C){Colors.END}")
        print(f"{Colors.CYAN}Output saved to: {output_dir}{Colors.END}")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run simulation
    try:
        # Parse time overrides
        start_override = None
        end_override = None
        if args.start_time:
            start_override = datetime.fromisoformat(args.start_time.replace('Z', '+00:00'))
        if args.end_time:
            end_override = datetime.fromisoformat(args.end_time.replace('Z', '+00:00'))

        simulator = RealtimeSimulator(event, db_path, output_dir, speed_factor=args.speed, force_grok=args.force_grok,
                                      start_time_override=start_override, end_time_override=end_override,
                                      multi_radar_count=args.multi_radar)
        await simulator.run_simulation()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}🛑 Simulation interrupted{Colors.END}")
        print(f"{Colors.CYAN}Output saved to: {output_dir}{Colors.END}")
        return 130
    except Exception as e:
        print(f"\n\n{Colors.RED}❌ Simulation failed: {e}{Colors.END}")
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
