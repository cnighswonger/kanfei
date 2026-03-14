# Project: Kanfei

Self-hosted weather station dashboard and data logger for Davis Instruments stations (Vantage Pro 2, Weather Monitor II, etc.). Serial communication via a custom protocol driver, with a FastAPI backend and React/TypeScript frontend. Includes an agricultural spray advisory and optional AI-powered nowcasting (via the kanfei-nowcast add-on package).

## Repository Structure

- `backend/` — Python FastAPI app + logger daemon
  - `app/api/` — REST API endpoints
  - `app/protocol/` — Davis serial protocol driver (link layer, memory map, constants)
  - `app/services/` — Background services (poller, archive sync, upload services)
  - `app/ipc/` — IPC server/client for logger daemon communication
  - `app/output/` — Output format generators (APRS, METAR)
  - `logger_main.py` — Standalone logger daemon (serial owner, poller, IPC server)
  - `app/main.py` — FastAPI web application entry point
- `frontend/` — React + TypeScript + Vite
  - `src/pages/` — Page components (Dashboard, History, Settings, etc.)
- `kanfei.service` — sample systemd unit for manual Linux deployment
- `reference/` — Davis technical reference docs

## Git Workflow

- **Development branch**: `dev/wx-app` (local) — tracks `origin/main`. Default for small changes, bugfixes, and single-commit work.
- **Feature branches**: `feature/*` — for multi-commit features (e.g., `feature/spray-advisor`). Branch from `dev/wx-app`, push to remote, open a PR against `main`, merge via PR, delete branch after merge.
- **Docs branches**: `docs/*` — for documentation-only work (README/wiki/docs updates). Branch from `dev/wx-app`, open PR against `main`.
- **Debian packaging branch**: `deb` — for Debian package builds; cherry-pick from dev/wx-app
- **Main branch**: `origin/main` — receives pushes from dev/wx-app; will become stable-only after post-beta release
- Small changes (single commit, bugfixes, tweaks): commit directly to `dev/wx-app` and push to `origin/main`
- Large features (multi-commit): create `feature/<name>` from `dev/wx-app`, work there, push to remote, open PR against `main`, merge via PR

## Build

- Frontend: `cd frontend && npm run build`
- Backend: Python 3.10+, dependencies in `backend/pyproject.toml`
- Debian package: `dpkg-buildpackage -us -uc -b` from repo root (packaging assets maintained on `deb` branch)
- **GitHub release filenames**: GitHub silently converts `~` to `.` in uploaded asset filenames. Debian uses `~` in pre-release versions (e.g., `0.1.0~alpha4`) but the download will be `0.1.0.alpha4`. Use the actual GitHub filename in install instructions, not the local `.deb` filename.

## Key Patterns

- Config stored in `station_config` SQLite table; defaults in `backend/app/api/config.py` `_DEFAULTS` dict
- Upload services (WU, CWOP) reload config from DB each cycle — Settings UI changes take effect immediately
- Logger daemon owns the serial port; web app communicates via IPC (TCP JSON messages)
- Hardware config (archive/sample periods) cached at connect time to avoid serial contention
- AI nowcast is optional — requires the `kanfei-nowcast` add-on package. App starts cleanly without it.
- NWS `/points` data (grid point, radar station, state code) cached centrally in `forecast_nws.py`
- First-enable disclaimer gate required before nowcast can be activated (stored in `nowcast_disclaimer_accepted` config)
