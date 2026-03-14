#!/usr/bin/env python3
"""
Live NEXRAD radar monitor with AI analyst.

Fetches near-real-time Level II data from AWS S3, runs mesocyclone/hail
detection, tracks threats across cycles, and (optionally) sends the full
knowledge payload to Claude for a nowcast analysis — producing output
identical to the simulation framework.

Usage:
    # Radar-only (no API key needed):
    python tools/live_nexrad_monitor.py --site KRAX --lat 35.32 --lon -78.56

    # With analyst (needs ANTHROPIC_API_KEY):
    python tools/live_nexrad_monitor.py --site KRAX --lat 35.32 --lon -78.56 --analyst

    # Continuous monitoring every 5 minutes:
    python tools/live_nexrad_monitor.py --site KRAX --lat 35.32 --lon -78.56 --analyst --cycles 0 --interval 300

    # Named presets:
    python tools/live_nexrad_monitor.py --preset ad4cg --analyst
"""

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.nexrad_loader import NEXRADLoader
from backend.app.services.radar_processor import process_radar_volume
from backend.app.services.threat_tracker import ThreatTracker
from backend.app.services.knowledge_formatter import build_knowledge_entries
from backend.app.models.radar_threats import bearing_to_cardinal


# ── ANSI colors ──────────────────────────────────────────────────────────────

class C:
    """Terminal colors."""
    BOLD = "\033[1m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    DIM = "\033[2m"
    END = "\033[0m"


# ── Station presets ──────────────────────────────────────────────────────────

PRESETS = {
    "ad4cg": {
        "name": "AD4CG Harnett County NC",
        "site": "KRAX",
        "lat": 35.3163,
        "lon": -78.556,
        "freezing": 3500,
    },
    "kg4agd": {
        "name": "KG4AGD Dunn NC",
        "site": "KRAX",
        "lat": 35.353,
        "lon": -78.558,
        "freezing": 3500,
    },
}


# ── Logging ──────────────────────────────────────────────────────────────────

_log_file = None


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if _log_file:
        _log_file.write(line + "\n")
        _log_file.flush()


def log_debug(msg: str) -> None:
    if _log_file:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        _log_file.write(f"[{ts}] DEBUG: {msg}\n")
        _log_file.flush()


# ── Analyst integration ──────────────────────────────────────────────────────

async def run_analyst(
    knowledge_entries: list[str],
    api_key: str,
    model: str,
    conversation_history: list[dict],
) -> tuple:
    """Call the Claude analyst with knowledge entries and return parsed result."""
    from backend.app.services.nowcast_analyst import generate_nowcast, SYSTEM_PROMPT
    from backend.app.services.nowcast_collector import CollectedData

    # Build a minimal CollectedData with knowledge entries
    data = CollectedData()
    data.knowledge_entries = knowledge_entries

    result, updated_history = await generate_nowcast(
        data=data,
        model=model,
        api_key_from_db=api_key,
        horizon_hours=2,
        max_tokens=4000,
        conversation_history=conversation_history,
    )
    return result, updated_history


def print_analyst_output(result, cycle_num: int, scan_time: datetime) -> None:
    """Print analyst result in simulation-style format."""
    tz_offset = timedelta(hours=-4)  # EDT — TODO: make configurable
    local_time = scan_time + tz_offset
    tz_label = "EDT"

    print(f"\n{C.BOLD}{'='*80}{C.END}")
    print(f"{C.BOLD}  CYCLE {cycle_num}  |  {scan_time.strftime('%H:%M:%S')} UTC "
          f"({local_time.strftime('%I:%M %p')} {tz_label}){C.END}")
    print(f"{C.BOLD}{'='*80}{C.END}")

    if result.severe_weather:
        threat = result.severe_weather.get('threat_level', 'UNKNOWN')
        color = C.RED if threat == 'EMERGENCY' else C.YELLOW if threat in ('WARNING', 'WATCH') else C.GREEN
        print(f"\n  {color}{C.BOLD}THREAT LEVEL: {threat}{C.END}")

        if result.severe_weather.get('primary_threat'):
            print(f"  Primary threat: {result.severe_weather['primary_threat']}")

        if result.severe_weather.get('distance_miles') is not None:
            d = result.severe_weather['distance_miles']
            b = result.severe_weather.get('bearing', '')
            eta = result.severe_weather.get('estimated_arrival', '')
            print(f"  Distance: {d:.0f} miles {b}  |  ETA: {eta}")
    else:
        print(f"\n  {C.GREEN}No severe weather detected{C.END}")

    print(f"\n  {C.BOLD}SUMMARY{C.END}")
    if result.summary:
        for line in result.summary.split('\n'):
            print(f"  {line}")

    if result.severe_weather and result.severe_weather.get('local_evidence'):
        print(f"\n  {C.BOLD}LOCAL EVIDENCE{C.END}")
        for ev in result.severe_weather['local_evidence']:
            print(f"    {ev}")

    if result.severe_weather and result.severe_weather.get('recommended_action'):
        threat = result.severe_weather.get('threat_level', '')
        color = C.RED if threat == 'EMERGENCY' else C.YELLOW
        print(f"\n  {color}{C.BOLD}RECOMMENDED ACTION{C.END}")
        print(f"  {color}{result.severe_weather['recommended_action']}{C.END}")

    if result.radar_analysis:
        print(f"\n  {C.BOLD}RADAR ANALYSIS{C.END}")
        for line in result.radar_analysis.split('\n'):
            print(f"  {line}")

    if result.data_quality:
        print(f"\n  {C.DIM}Data quality: {result.data_quality}{C.END}")

    print(f"\n  {C.DIM}Tokens: {result.input_tokens:,} in / {result.output_tokens:,} out{C.END}")
    print(f"{C.BOLD}{'='*80}{C.END}\n")


# ── Main cycle ───────────────────────────────────────────────────────────────

async def run_cycle(
    loader: NEXRADLoader,
    tracker: ThreatTracker,
    site: str,
    lat: float,
    lon: float,
    freezing_level_m: float,
    cycle_num: int,
    api_key: Optional[str] = None,
    model: str = "claude-haiku-4-5-20251001",
    conversation_history: Optional[list] = None,
    previous_threat_level: Optional[str] = None,
    previous_cycle_time: Optional[datetime] = None,
) -> tuple:
    """
    Run a single detection + analysis cycle.

    Returns:
        (threat_level, scan_time, updated_conversation_history)
    """
    now = datetime.now(timezone.utc)

    print(f"\n{C.CYAN}{C.BOLD}--- CYCLE {cycle_num} --- "
          f"{now.strftime('%Y-%m-%d %H:%M:%S UTC')}{C.END}")

    # ── Fetch latest radar scan ──
    keys = loader.list_files(site, now - timedelta(minutes=15), now + timedelta(minutes=5))
    if not keys:
        log("No radar scans found in last 15 minutes")
        return None, now, conversation_history or []

    latest_key = keys[-1]
    scan_time = loader._parse_filename_timestamp(latest_key)
    age_min = (now - scan_time).total_seconds() / 60
    log(f"Scan: {latest_key.split('/')[-1]} ({age_min:.0f} min old)")

    fpath = loader.download_file(latest_key)
    radar = loader.read_radar(fpath)
    log(f"Radar: {radar.nsweeps} sweeps, {radar.nrays} rays")

    # ── Process detections ──
    result = process_radar_volume(
        radar=radar,
        station_lat=lat,
        station_lon=lon,
        radar_site=site,
        nexrad_loader=loader,
        freezing_level_m=freezing_level_m,
        current_regime=tracker.state.current_regime,
        log_func=log_debug,
    )

    # ── Update tracker ──
    tracker.update(result, scan_time)
    state = tracker.state

    # ── Detection summary ──
    log(f"Regime: {state.current_regime.value}")

    if state.tracked_mesocyclones:
        log(f"Tracked mesocyclones: {len(state.tracked_mesocyclones)}")
        for m in state.tracked_mesocyclones:
            dist = f"{m.distance_km:.1f} km" if m.distance_km is not None else "?"
            bear = bearing_to_cardinal(m.bearing_deg) if m.bearing_deg is not None else "?"
            log(f"  {m.id}: {dist} {bear}, shear={m.shear:.1f} s-1, "
                f"cycles={m.cycle_count}, status={m.status}")

    if state.hail_cells:
        log(f"Hail cells: {len(state.hail_cells)}")
        for h in state.hail_cells:
            bear = bearing_to_cardinal(h.bearing_deg) if h.bearing_deg is not None else "?"
            log(f"  MESH={h.mesh_mm:.0f}mm {h.distance_km:.1f}km {bear} "
                f"(VIL={h.vil_kg_m2:.1f})")

    # ── Build knowledge entries ──
    entries = build_knowledge_entries(
        tracker_state=state,
        previous_threat_level=previous_threat_level,
        previous_cycle_time=previous_cycle_time,
        sim_time=scan_time,
        log_func=log_debug,
    )

    if entries:
        log(f"Knowledge entries: {len(entries)}")
        for entry in entries:
            for line in entry.split("\n"):
                log_debug(f"  | {line}")
    else:
        log("No threats detected")

    # ── Analyst call (optional) ──
    threat_level = None
    updated_history = conversation_history or []

    if api_key and entries:
        log(f"{C.CYAN}Calling analyst ({model.split('-')[1].upper()})...{C.END}")
        try:
            analyst_result, updated_history = await run_analyst(
                knowledge_entries=entries,
                api_key=api_key,
                model=model,
                conversation_history=conversation_history or [],
            )
            if analyst_result:
                print_analyst_output(analyst_result, cycle_num, scan_time)
                if analyst_result.severe_weather:
                    threat_level = analyst_result.severe_weather.get('threat_level')

                # Log full response to debug
                log_debug(json.dumps({
                    'summary': analyst_result.summary,
                    'severe_weather': analyst_result.severe_weather,
                    'radar_analysis': analyst_result.radar_analysis,
                }, indent=2))
            else:
                log(f"{C.YELLOW}Analyst returned no result{C.END}")
        except Exception as e:
            log(f"{C.RED}Analyst error: {e}{C.END}")
            log_debug(traceback.format_exc())
    elif api_key and not entries:
        log(f"{C.DIM}No threats — skipping analyst{C.END}")
    elif not api_key and entries:
        # Print knowledge entries in lieu of analyst
        print(f"\n{C.BOLD}--- KNOWLEDGE ENTRIES ({len(entries)}) ---{C.END}")
        for entry in entries:
            for line in entry.split("\n"):
                print(f"  {line}")
        print(f"{C.BOLD}--- END ---{C.END}\n")

    return threat_level, scan_time, updated_history


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Live NEXRAD radar monitor with AI analyst",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Presets:
  {', '.join(f'{k} ({v["name"]})' for k, v in PRESETS.items())}

Examples:
  %(prog)s --site KRAX --lat 35.32 --lon -78.56
  %(prog)s --preset ad4cg --analyst
  %(prog)s --preset ad4cg --analyst --cycles 0 --interval 300
""")

    # Location
    loc = parser.add_mutually_exclusive_group(required=True)
    loc.add_argument("--preset", choices=PRESETS.keys(), help="Use a named station preset")
    loc.add_argument("--site", help="NEXRAD site ID (e.g., KRAX)")

    parser.add_argument("--lat", type=float, help="Station latitude")
    parser.add_argument("--lon", type=float, help="Station longitude")
    parser.add_argument("--freezing", type=float, default=3500,
                        help="Freezing level meters AGL (default: 3500)")

    # Analyst
    parser.add_argument("--analyst", action="store_true",
                        help="Enable Claude analyst (needs ANTHROPIC_API_KEY)")
    parser.add_argument("--model", default="claude-haiku-4-5-20251001",
                        help="Claude model ID (default: haiku)")

    # Timing
    parser.add_argument("--cycles", type=int, default=1,
                        help="Number of cycles (default: 1, 0=infinite)")
    parser.add_argument("--interval", type=int, default=300,
                        help="Seconds between cycles (default: 300)")

    # Output
    parser.add_argument("--log-dir", type=str, default=None,
                        help="Directory for log files (default: .test_cache/live_monitor/)")
    parser.add_argument("--cache-dir", type=str, default=".test_cache/nexrad",
                        help="Cache directory for radar downloads")

    args = parser.parse_args()

    # Resolve preset
    if args.preset:
        p = PRESETS[args.preset]
        site = p["site"]
        lat = p["lat"]
        lon = p["lon"]
        freezing = p["freezing"]
        station_name = p["name"]
    else:
        site = args.site
        if not args.lat or not args.lon:
            parser.error("--lat and --lon are required when not using --preset")
        lat = args.lat
        lon = args.lon
        freezing = args.freezing
        station_name = f"{site} ({lat:.4f}, {lon:.4f})"

    # Resolve API key
    api_key = None
    if args.analyst:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print(f"{C.RED}Error: --analyst requires ANTHROPIC_API_KEY environment variable{C.END}")
            sys.exit(1)

    # Set up logging
    global _log_file
    log_dir = Path(args.log_dir) if args.log_dir else PROJECT_ROOT / ".test_cache" / "live_monitor"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"live_{site.lower()}_{ts_str}.log"
    _log_file = open(log_path, "w")

    # Initialize
    loader = NEXRADLoader(cache_dir=Path(args.cache_dir))
    tracker = ThreatTracker(station_lat=lat, station_lon=lon, log_func=log_debug)

    print(f"\n{C.BOLD}{'='*80}{C.END}")
    print(f"{C.BOLD}  LIVE NEXRAD MONITOR: {station_name.upper()}{C.END}")
    print(f"{C.BOLD}{'='*80}{C.END}")
    print(f"  Radar: {site}  |  Freezing: {freezing}m  |  Interval: {args.interval}s")
    print(f"  Analyst: {'ON (' + args.model.split('-')[1].upper() + ')' if api_key else 'OFF'}")
    print(f"  Log: {log_path}")
    print(f"{C.BOLD}{'='*80}{C.END}")

    # Run cycles
    conversation_history = []
    previous_threat = None
    previous_time = None
    cycle = 1
    max_cycles = args.cycles if args.cycles > 0 else float("inf")

    async def loop():
        nonlocal cycle, conversation_history, previous_threat, previous_time

        while cycle <= max_cycles:
            try:
                threat, scan_time, conversation_history = await run_cycle(
                    loader=loader,
                    tracker=tracker,
                    site=site,
                    lat=lat,
                    lon=lon,
                    freezing_level_m=freezing,
                    cycle_num=cycle,
                    api_key=api_key,
                    model=args.model,
                    conversation_history=conversation_history,
                    previous_threat_level=previous_threat,
                    previous_cycle_time=previous_time,
                )
                previous_threat = threat
                previous_time = scan_time
            except KeyboardInterrupt:
                log("Interrupted by user")
                break
            except Exception as e:
                log(f"{C.RED}ERROR: {e}{C.END}")
                log_debug(traceback.format_exc())

            cycle += 1
            if cycle <= max_cycles:
                log(f"{C.DIM}Next cycle in {args.interval}s...{C.END}")
                try:
                    await asyncio.sleep(args.interval)
                except (KeyboardInterrupt, asyncio.CancelledError):
                    log("Interrupted by user")
                    break

    try:
        asyncio.run(loop())
    except KeyboardInterrupt:
        pass
    finally:
        if _log_file:
            _log_file.close()
        print(f"\n{C.DIM}Log saved: {log_path}{C.END}")


if __name__ == "__main__":
    main()
