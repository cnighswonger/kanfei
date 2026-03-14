# Kanfei Documentation Directive

You are documenting **Kanfei** — a self-hosted weather intelligence platform for
personal weather stations. The repo is at the current working directory. Read
CLAUDE.md first for project structure, then explore the codebase to write
accurate documentation. Do NOT guess — read the actual code.

## Project Identity

- **Name**: Kanfei (Hebrew: "wings of the wind", Psalm 104:2-3 KJV)
- **Repo**: github.com/cnighswonger/kanfei
- **License**: Check the repo (if present)
- **Status**: Beta (v0.1.0-alpha series)
- **Audience**: Self-hosters running personal weather stations on Linux

## Architecture Overview

Two-process architecture:

1. **Logger daemon** (`backend/logger_main.py`) — Owns the serial port, polls the
   Davis station at configurable intervals, writes sensor readings to SQLite, serves
   an IPC (TCP JSON) interface for the web app to request live data.

2. **Web app** (`backend/app/main.py`) — FastAPI serving REST API + static frontend.
   Communicates with the logger daemon via IPC. Runs background asyncio tasks for
   nowcast, uploads, alerts, etc.

**Frontend**: React 19 + TypeScript + Vite. Inline styles throughout (no CSS
framework). Pages: Dashboard (drag-and-drop tile grid), History (charts),
Forecast (NWS + Open-Meteo blend), Astronomy (sun/moon), Nowcast (AI weather
analysis), Spray (agricultural spray advisory), Settings, About.

**Database**: Single SQLite file via SQLAlchemy. Config stored in `station_config`
table (key-value). Sensor readings in `sensor_readings`. Nowcast history, knowledge
base, spray schedules, alert history all have their own tables.

## Key Systems to Document

### 1. Davis Protocol Driver (`backend/app/protocol/`)
- Custom serial protocol implementation for Davis Instruments stations
- Link layer with CRC validation, command/response framing
- LOOP packet parser (real-time weather data)
- Memory map for archive/EEPROM access
- Station type detection and capability discovery

### 2. Data Pipeline
- Poller service (`services/poller.py`) — periodic LOOP requests via IPC
- Archive sync (`services/archive_sync.py`) — downloads stored archive records
- WebSocket broadcast — real-time push to connected browsers
- Upload services — Weather Underground (`services/wunderground.py`),
  CWOP/APRS (`services/cwop.py`)

### 3. AI Nowcast System (`services/nowcast_*.py`)
This is the most complex subsystem. Four-layer architecture:
- **Collector** (`nowcast_collector.py`) — Gathers station data, Open-Meteo forecast,
  NWS forecast, NEXRAD radar imagery (composite reflectivity + storm-relative
  velocity with per-product bounding boxes), nearby station data from IEM ASOS,
  Weather Underground PWS, and CWOP/APRS-IS
- **Analyst** (`nowcast_analyst.py`) — Sends collected data + radar images to Claude
  API with a detailed meteorological system prompt. Supports tool use: the analyst
  can invoke a `zoom_radar` tool mid-analysis to fetch higher-resolution radar
  imagery of specific areas of interest (max 2 zooms per cycle)
- **Verifier** (`nowcast_verifier.py`) — After the forecast period expires,
  compares predictions against actuals and scores accuracy
- **Service** (`nowcast_service.py`) — Orchestrates the cycle. Auto-escalates from
  Haiku to Sonnet during active NWS alerts. Shortens interval from 15min to 5min
  in alert mode. New alerts trigger immediate regeneration.
- **Knowledge base** — Persistent learnings the analyst can propose (bias corrections,
  local effects, terrain notes). Auto-accepted after configurable hours.

### 4. Spray Advisory (`services/spray_engine.py`, `api/spray.py`)
- Rule engine using station actuals for wind/temp/humidity thresholds
- AI override via nowcast analyst (has access to HRRR/NWS/radar data)
- Outcome feedback system for learning from past spray decisions
- Schedule management with configurable spray windows

### 5. NWS Integration
- `services/forecast_nws.py` — NWS API client, grid point resolution, caching
- `services/alerts_nws.py` — Active alert monitoring with polling
- `services/alerts.py` — Alert evaluation, threshold checking, WebSocket push
- `services/forecast_blender.py` — Blends NWS + Open-Meteo forecasts

### 6. Frontend Architecture
- **State**: React Context providers for weather data (WebSocket), theme (dark/light
  with animated weather backgrounds), alerts, feature flags, dashboard layout
- **Dashboard**: Drag-and-drop tile grid system (`frontend/src/dashboard/`) with
  tile catalog, resize handles, layout persistence
- **Gauges**: Custom SVG gauges for temp, humidity, barometer, wind compass, rain,
  solar/UV
- **Responsive**: `useIsMobile` hook (768px breakpoint), auto-hide header on mobile
  scroll, responsive grid layouts
- **Setup wizard**: First-run setup flow for serial port, coordinates, station type

### 7. Configuration System
- `station_config` SQLite table (key-value pairs)
- Defaults in `backend/app/api/config.py` `_DEFAULTS` dict
- Settings page includes Station, Display, Services, Alerts, Nowcast, Spray,
  Usage, and Database surfaces
- Services reload config from DB each cycle — changes take effect immediately

### 8. Deployment
- Debian package with two systemd services (logger + web)
- This branch includes `davis-wx.service` for manual systemd deployment.
  Packaging assets may be maintained on the `deb` branch.
- Targets Debian/Ubuntu on ARM or x86 (Raspberry Pi common target)

## Documentation Targets

Prioritise synchronising these artifacts with the current codebase:

1. **README.md** (repo root) — Project overview, quick start, deployment notes,
   architecture summary, and supported features.

2. **frontend/README.md** — Frontend-specific development and architecture notes
   (replace template boilerplate).

3. **TODO.md** — Keep roadmap/checklists aligned with implemented features.

4. **GitHub Wiki** — Deep-dive operational and subsystem docs (architecture,
   API, configuration, troubleshooting, migration, backup/restore).

When producing API/config docs, read `backend/app/api/router.py` and the endpoint
modules directly; do not infer route behavior.

## Style Guidelines

- Write for a technical audience who runs Linux servers but may not know Python/React
- Use plain English, avoid jargon where possible
- Include actual command examples (apt install, systemctl, etc.)
- Reference specific files/modules when describing architecture
- Don't fabricate features — if you're unsure, read the code
- The app is in beta — note that where appropriate
