# Feature Roadmap

## Done
- [x] **Daily High/Low Records** — Query DB for today's min/max temp, peak wind gust, low barometer, max rain rate, etc. Display on dashboard + topbar.
- [x] **Data Export** — CSV download of historical data for a date range via `GET /api/export`. Download button on History page.
- [x] **Alerts/Thresholds** — Configurable per-sensor alerts with cooldown, toast notifications via WebSocket, Settings page UI.
- [x] **Weather Network Upload (WU/CWOP)** — Upload services implemented and wired to poller broadcasts with DB-configured intervals.
- [x] **Dynamic METAR Station Discovery** — Replaced hardcoded airport list with IEM GeoJSON API lookup. Derives nearby state codes from lat/lon, fetches all ASOS stations per state, caches 30 days. AD4CG area went from 3 stations to 14 within 50 miles (including KHRJ at 10.9 mi).

## Planned
- [ ] **Additional Weather Network Uploads** — Extend beyond current WU/CWOP support (e.g., PWSweather).
- [ ] **Data Retention** — Background job to downsample old sensor_readings (5s for 7d, 5min for 30d, hourly beyond). Keeps DB performant long-term.
- [ ] **Per-Model Max Token Limits** — Different providers need different max_tokens (Haiku: 3500, Grok: 8000). See issue #30.
- [ ] **Grok Fallback Prompt Tuning** — Grok 4.1 Fast Reasoning produces significantly shorter/less detailed output than Claude Haiku with the same system prompt. In the sim (with conversation history and severe weather context) they perform on par, so the issue is likely prompt-related rather than model capability. Investigate: provider-specific prompt hints, explicit output length guidance, or a Grok-tuned system prompt addendum.
- [ ] **DB Admin Tab** — Settings tab for database maintenance: purge knowledge base, nowcast history, sensor readings; export/backup; DB stats.

## Radar Detection Enhancement (Priority Order)

Two features to improve detection coverage and situational awareness.
Updated 2026-03-12 after Level III investigation.

### ~~NEXRAD Level III Threat Products~~ — Dropped
Investigated 2026-03-12. The `unidata-nexrad-level3` S3 bucket has no data before
2020 (rules out Moore 2013, Pilger 2014). TVS and Hail Index products were
discontinued ~2024 — not available for current events. Py-ART can't read the
remaining algorithmic products (NMD/141, N0M/166, NST/58). NMD data is mostly
empty 150-byte null files. Our Level II shear/hail detection from raw gates is
already superior to these pre-computed products.

### Priority 1: Multi-Radar Velocity Coverage
**Branch**: `feature/multi-radar`
**Status**: In progress

Query the 2-3 nearest NEXRAD radars for Level II velocity data rather than using a
single radar per event. Stations at the edge of one radar's coverage (e.g.,
Hattiesburg at 123 km from KDGX — right at velocity max range) get degraded
mesocyclone detection due to beam height and broadening. Running shear detection
independently on each nearby radar and merging detections (same lat/lon from
multiple radars = high confidence) significantly improves coverage.

NEXRAD Level II is available on AWS S3 (`noaa-nexrad-level2`) back to 1991, so
this works for all historic events. Infrastructure exists (NEXRADLoader,
radar_processor) — generalize from single-radar to N-radar and add a merge step.

### Priority 2: MRMS Integration (Supplementary Products)
**Branch**: `feature/mrms-integration`
**Status**: Planned

Layer NOAA MRMS products (`noaa-mrms-pds` on AWS S3) as supplementary indicators
alongside raw NEXRAD Level II. MRMS provides seamless CONUS composites at
1km/2-min: MESH (hail), VIL, rotation tracks, azimuthal shear, echo tops.

Use for: (1) seamless reflectivity mosaic as situation composite background,
(2) MESH/VIL cross-validation of our custom hail detection, (3) rotation track
confidence indicators. Cannot replace Level II for fine-scale velocity analysis
(MRMS shear is 1km vs Level II 250m) and is unavailable before Oct 2014 (excludes
our 2011-2013 test events). Hybrid approach: Level II primary for mesocyclone
detection, MRMS supplementary for display and confidence.
