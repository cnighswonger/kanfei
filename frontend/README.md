# Kanfei Frontend

React + TypeScript + Vite frontend for the Kanfei weather station platform.

## Stack

- React 19
- TypeScript (strict)
- Vite
- React Router
- Highcharts

## Structure

- `src/pages/` - top-level routes (`Dashboard`, `History`, `Forecast`, `Astronomy`, `Settings`, `About`, optional `Nowcast` and `Spray`)
- `src/components/` - layout, charts, gauges, setup wizard, shared UI
- `src/dashboard/` - configurable dashboard grid/tile system
- `src/context/` - app-level state (weather data, theme, feature flags, alerts)
- `src/api/` - typed API client and payload types
- `src/themes/` - theme definitions

## Local Development

From repo root, preferred workflow:

```bash
python station.py dev
```

Frontend-only workflow:

```bash
cd frontend
npm install
npm run dev
```

Default dev URL is `http://localhost:3000` with proxy rules for:

- `/api` -> `http://localhost:8000`
- `/ws` -> WebSocket proxy to `ws://localhost:8000`

## Build

```bash
cd frontend
npm run build
```

Build output is written to `frontend/dist` and served by FastAPI in production mode.

## Notes

- Feature visibility for `Nowcast` and `Spray` is config-driven (`nowcast_enabled`, `spray_enabled`).
- First-run setup is gated by `/api/setup/status`; incomplete setup shows the Setup Wizard.
