# Harnett County QLCS 2026 — Ground Truth

March 12, 2026: Sharp cold front with embedded QLCS through Harnett County, NC.

## Event Summary

- **Date/Time**: 2026-03-12, ~16:00-16:14 UTC (12:00-12:14 PM EDT)
- **Type**: QLCS / cold front with severe straight-line winds and embedded rotation
- **Station**: AD4CG (35.3163°N, 78.556°W, 230 ft ASL)
- **Radar**: KRAX (Raleigh, 39 km)
- **Validation**: Co-developer located 7 miles from AD4CG station

## Timeline

| Time (UTC) | Time (EDT) | Event |
|------------|------------|-------|
| 15:30 | 11:30 AM | Sim cycle 1 — MESO-1 detected 34 mi NNW, WARNING |
| 16:00 | 12:00 PM | Sim cycle 7 — WATCH, 3 min to closest approach |
| 16:03 | 12:03 PM | Closest approach — MESO-3 at 8.1 km SSE, 50.5 s⁻¹ shear |
| 16:05 | 12:05 PM | Sim cycle 8 — EMERGENCY, QLCS line 1.0 km W, ETA 1 min |
| 16:10 | 12:10 PM | Sim cycle 9 — EMERGENCY. Structure damage near KG4AGD (photo) |
| 16:14 | 12:14 PM | Microburst strikes ground (video sequence). Debris launched skyward |
| 16:15 | 12:15 PM | Sim cycle 10 — EMERGENCY holds through passage |
| 16:20 | 12:20 PM | Sim cycle 11 — de-escalation to WARNING, line moving away |
| 16:35 | 12:35 PM | Sim cycle 14 — second EMERGENCY spike (trailing rotation feature) |

## Observations

- Severe straight-line winds strong enough to overturn structures
- Visible rotation in the line as it passed (no funnel dropped)
- 20+ degree F temperature crash across the CWOP network in 30-45 minutes
- MESO-3 detected by pipeline at 8.1 km SSE with 50.5 s⁻¹ azimuthal shear at 16:03 UTC
- Lazy rotation also noted near KG4AGD station
- Microburst/downdraft impact observed at ~16:14 UTC with debris column visible on video

## Simulation Results

15-cycle simulation (15:30-16:40 UTC) with Grok analyst, 5-min alert-mode cycles:

| Cycle | Time | Threat Level |
|-------|------|-------------|
| 1-6 | 15:30-15:55 | WARNING |
| 7 | 16:00 | WATCH |
| 8-10 | 16:05-16:15 | **EMERGENCY** |
| 11-13 | 16:20-16:30 | WARNING |
| 14 | 16:35 | **EMERGENCY** |

QLCS regime correctly classified. EMERGENCY window (16:05-16:15 UTC) directly
overlaps observed ground-truth damage window (16:10-16:14 UTC). Two-minute
accuracy on a fast-moving QLCS event.

## Photos

### straightline_wind_damage_near_kg4agd.jpg
Mobile home/shed overturned by straight-line winds near the KG4AGD CWOP station
in Harnett County. Photographed at approximately 16:10 UTC (12:10 PM EDT) during
sim cycle 9 (EMERGENCY). Demonstrates the severity of wind damage from the QLCS
passage. Lazy rotation was also noted at this location.

### straightline_wind_sequence/ (3 frames from video, looking SSE)

Extracted from `wx_event_straightline_wind.mp4` at 12-second intervals. Camera
is looking SSE toward the approaching gust front. Microburst impact at ~16:14 UTC
(12:14 PM EDT), between sim cycles 9 and 10 (both EMERGENCY).

- **frame_0044s.jpg** — Gust front approaching behind the treeline. Hazy wall
  building to the SSE, trees still mostly upright, visibility moderate.
- **frame_0056s.jpg** — Downdraft impact. Massive debris column rising from the
  surface as the wind strikes the ground. Dirt and material launched vertically
  upward. Classic straight-line wind signature.
- **frame_0068s.jpg** — Full engulfment. Entire scene wrapped in blown dirt and
  debris. Metal building barely visible through the haze. Near-zero visibility.
