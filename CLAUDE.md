# Project: Kanfei

Self-hosted weather station dashboard and data logger with pluggable hardware drivers. Supports Davis Instruments, Ecowitt/Fine Offset, Ambient Weather, and WeatherFlow Tempest stations. FastAPI backend with React/TypeScript frontend. Includes an agricultural spray advisory and optional AI-powered nowcasting via the kanfei-nowcast add-on package.

## Repository Structure

- `backend/` — Python FastAPI app + logger daemon
  - `app/api/` — REST API endpoints
    - `router.py` — route aggregation (nowcast API loaded conditionally)
    - `nowcast.py` — full nowcast API (requires kanfei-nowcast package)
    - `nowcast_lite.py` — lightweight nowcast API (built-in, works with remote mode)
    - `spray.py` — spray advisor CRUD + evaluation
    - `config.py` — station config with `_DEFAULTS` dict
  - `app/protocol/` — Station drivers (Davis serial, Vantage, WeatherLink IP/Live, Ecowitt, Ambient, Tempest)
    - `base.py` — `StationDriver` ABC + `SensorSnapshot`
  - `app/services/` — Background services (poller, archive sync, upload services)
    - `spray_engine.py` — OSS rule-based spray evaluation engine (real code, not a shim)
    - `forecast_nws.py` — NWS forecast client (real code, not a shim)
    - `alerts_nws.py` — NWS active alerts client (real code, not a shim)
    - `nowcast/` — Nowcast integration layer
      - `remote_client.py` — built-in HTTP client for remote nowcast mode (no kanfei-nowcast needed)
      - `service_ref.py` — module-level reference to active nowcast service
      - `kanfei_adapters.py` — adapters bridging nowcast protocols to Kanfei ORM
      - `protocols.py` — abstract interfaces (ConfigProvider, StorageBackend, EventEmitter)
  - `app/ipc/` — IPC server/client for logger daemon communication
  - `app/output/` — Output format generators (APRS, METAR)
  - `app/main.py` — FastAPI web app entry point (conditional nowcast initialization)
  - `logger_main.py` — Standalone logger daemon (serial owner, poller, IPC server)
- `frontend/` — React + TypeScript + Vite
  - `src/pages/` — Page components (Dashboard, History, Settings, Nowcast, Spray, etc.)
  - `src/context/WeatherDataContext.tsx` — live data provider with station status backoff polling
  - `src/context/FeatureFlagsContext.tsx` — controls nowcast/spray feature visibility
- `kanfei.service` — sample systemd unit for manual Linux deployment
- `debian/` — Debian packaging (full packaging on `deb` branch)
- `reference/` — Davis technical reference docs

## Git Workflow

- **Main branch**: `origin/main` — primary development target
- **Feature branches**: `feature/*` — for multi-commit features. Branch from main, open PR, merge via PR, delete branch.
- **Fix branches**: `fix/*` — for bugfixes
- **Docs branches**: `docs/*` — documentation-only work
- **Debian packaging branch**: `deb` — Debian package build files (control, rules, changelog, services, postinst/prerm/postrm)
- Small changes can go directly to main; larger work should use branches + PRs

## Build

- Frontend: `cd frontend && npm run build`
- Backend: Python 3.10+, dependencies in `backend/pyproject.toml`
- Debian package: `dpkg-buildpackage -us -uc -b` from repo root (on `deb` branch)
- **GitHub release filenames**: GitHub converts `~` to `.` in uploaded asset filenames. Debian uses `~` in pre-release versions (e.g., `0.1.0~beta1`) but the download will be `0.1.0.beta1`.

## Key Patterns

- Config stored in `station_config` SQLite table; defaults in `backend/app/api/config.py` `_DEFAULTS` dict
- Upload services (WU, CWOP) reload config from DB each cycle — Settings UI changes take effect immediately
- Logger daemon owns the serial port; web app communicates via IPC (TCP JSON messages)
- Hardware config (archive/sample periods) cached at connect time to avoid serial contention
- Default DB name is `kanfei.db` (renamed from `davis_wx.db`)
- Empty `.env` values handled gracefully by `_empty_str_to_default` field validator in config.py

## Nowcast Integration

- AI nowcast is optional — requires the `kanfei-nowcast` add-on package for local mode
- **Remote mode works without kanfei-nowcast** — built-in `NowcastRemoteClient` pushes readings and polls results via HTTP
- `main.py` checks `nowcast_mode` config: remote uses built-in client, local requires package
- `router.py` loads full `nowcast.py` API if kanfei-nowcast is installed, falls back to `nowcast_lite.py`
- `nowcast_lite.py` provides GET /nowcast, POST /nowcast/generate, GET /nowcast/status, GET /nowcast/presets, GET /nowcast/radar (proxied), GET /nowcast/alerts
- `service_ref.py` holds the module-level reference to the active service — import the module, not the variable (avoids stale None reference)
- Remote client sends `X-API-Key` header for SaaS authentication
- Remote client syncs quality preset changes to the remote server via POST /api/config
- Quality presets (Economy/Standard/Premium) replace raw model selection in the Settings UI
- Nowcast page shows contextual messages based on service status and auth errors
- Station status polling uses exponential backoff (5s → 5min) for fast recovery when logger starts after web app

## Nowcast Shim Files

These files in `backend/app/services/` are thin re-export shims — they import from `kanfei_nowcast` and only load when the package is installed. They are NOT real code:
- `nowcast_service.py`, `nowcast_collector.py`, `nowcast_analyst.py`, `nowcast_verifier.py`
- `radar_processor.py`, `radar_visualizer.py`, `threat_tracker.py`, `surface_analyzer.py`
- `knowledge_formatter.py`, `nexrad_loader.py`, `mrms_loader.py`, `multi_radar.py`
- `nearby_stations.py`, `aprs_collector.py`

These files ARE real code (restored from kanfei-nowcast during extraction):
- `spray_engine.py` — full rule-based spray evaluation engine
- `forecast_nws.py` — NWS forecast API client
- `alerts_nws.py` — NWS active alerts API client

## Debian Packaging

Package name: `kanfei` (renamed from `davis-wx` in beta1)
- Services: `kanfei-logger.service`, `kanfei-web.service`
- Paths: `/opt/kanfei/`, `/etc/kanfei/`, `/var/lib/kanfei/`
- System user: `kanfei`
- Config: `/etc/kanfei/kanfei.conf` (EnvironmentFile for systemd)
- DB: `/var/lib/kanfei/kanfei.db`
- Backgrounds: `/var/lib/kanfei/backgrounds/`

## Coding Discipline

- **Do not expose kanfei-nowcast internals** in this public repo — no prompt section names, detection algorithms, or architecture details in issues or code comments. Describe only user-visible symptoms and outcomes.
- Prefer editing existing files over creating new ones
- Run `npx tsc --noEmit` before committing frontend changes
- Run `py_compile` on modified Python files before committing
- localStorage migration keys (`davis-wx-*` in `uiPrefs.ts`) are intentional for backwards compatibility — do not remove
