# Kanfei

A self-hosted weather station dashboard and data logger with pluggable hardware drivers. Logs sensor data to SQLite and presents it through a modern, theme-able browser dashboard with real-time updates and agricultural spray advisory. Supports personal weather stations from Davis Instruments, Ecowitt/Fine Offset, WeatherFlow, Ambient Weather, and more.

## Features

- **Real-time dashboard** with SVG gauges for temperature, barometric pressure, wind speed/direction, humidity, rain, and solar/UV on a drag-resize 12-column grid
- **Historical charts** (Highcharts) with selectable sensor, date range, and resolution (raw, 5m, hourly, daily)
- **Spray Advisor** with rule-based go/no-go engine, outcome feedback, and per-product threshold tuning from application history
- **AI-powered nowcast** (optional add-on) — hyper-local weather intelligence via the [kanfei-nowcast](https://github.com/cnighswonger/kanfei-nowcast) package
- **Forecasting**: Zambretti barometric algorithm (local) blended with NWS API data (optional)
- **Astronomy**: sunrise/sunset arc, twilight times (civil/nautical/astronomical), moon phase with illumination
- **NWS alerts**: active alert monitoring for your station location
- **Data uploads**: Weather Underground PWS and CWOP/APRS-IS for NWS citizen weather data
- **Backup and restore**: scheduled automatic backups with rotation, CLI commands, REST API, and Settings UI with download/restore
- **Database admin**: stats, JSON export, sensor data compaction, and tiered purge
- **Calculated parameters**: heat index, dew point, wind chill, feels-like composite, equivalent potential temperature (theta-e)
- **Weather backgrounds**: condition-driven gradients with custom image uploads per scene
- **Three themes**: Dark, Light, and Classic Instrumental (brass/cream analog aesthetic)
- **WebSocket push** for live sensor updates
- **METAR output** generation (optional)
- **Cross-platform**: runs on Windows 10+, macOS, and Linux

## Documentation

Full documentation is available on the [Kanfei Wiki](https://github.com/cnighswonger/kanfei/wiki), including:

- [Getting Started](https://github.com/cnighswonger/kanfei/wiki/Getting-Started) — first-run setup and configuration
- [Installation and Deployment](https://github.com/cnighswonger/kanfei/wiki/Installation-and-Deployment) — systemd, .deb packages, reverse proxy
- [Configuration Reference](https://github.com/cnighswonger/kanfei/wiki/Configuration-Reference) — all settings and environment variables
- [Spray Advisor](https://github.com/cnighswonger/kanfei/wiki/Spray-Advisor) — agricultural spray advisory configuration
- [API Reference](https://github.com/cnighswonger/kanfei/wiki/API-Reference) — REST and WebSocket endpoints
- [Troubleshooting](https://github.com/cnighswonger/kanfei/wiki/Troubleshooting) — common issues and solutions
- [Serial and Hardware Troubleshooting](https://github.com/cnighswonger/kanfei/wiki/Serial-and-Hardware-Troubleshooting) — station connection issues

## Quick Start

Prerequisites: **Python 3.10+** and **Node.js 18+**

```bash
git clone https://github.com/cnighswonger/kanfei.git
cd kanfei

python station.py setup
python station.py run
```

Open **http://localhost:8000** in your browser.

If no station hardware is connected, the server starts in degraded mode — the UI loads and is fully navigable, but sensor readings will show placeholder values.

## Configuration

The setup wizard walks you through hardware detection, location, and unit preferences on first run. It creates a `.env` file from `.env.example`. You can also edit it directly:

```bash
# Serial port (Davis serial stations)
# Linux:   /dev/ttyUSB0  or  /dev/ttyS0
# macOS:   /dev/tty.usbserial-XXXX
# Windows: COM3  (check Device Manager -> Ports)
KANFEI_SERIAL_PORT=/dev/ttyUSB0
KANFEI_BAUD_RATE=2400

# Location (required for astronomy, NWS forecasts, and nearby stations)
KANFEI_LATITUDE=40.7128
KANFEI_LONGITUDE=-74.0060
KANFEI_ELEVATION_FT=33

# NWS forecast integration
KANFEI_NWS_ENABLED=true

# UI theme (dark, light, classic)
KANFEI_THEME=dark
```

All settings are also editable from the Settings page in the browser, including upload services, alerts, and spray advisor.

## Commands

| Command | Description |
|---------|-------------|
| `python station.py setup` | Create venv, install all dependencies, build frontend |
| `python station.py run` | Start production server on port 8000 |
| `python station.py dev` | Start backend (8000) + frontend HMR dev server (3000) |
| `python station.py test` | Run the backend test suite |
| `python station.py backup` | Create a backup of DB and backgrounds (.tar.gz) |
| `python station.py restore` | Restore from a backup archive |
| `python station.py status` | Check what's installed and ready |
| `python station.py clean` | Remove venv, node_modules, and build artifacts |

On Linux/macOS, `make` targets are also available (`make setup`, `make dev`, etc.).

## Architecture

```
Browser  <──WebSocket──>  FastAPI web app  <──IPC──>  Logger daemon  <──driver──>  Weather Station
           <──REST API──>  (serves UI +      (TCP)    (serial owner,
                            reads DB)                  poller, DB writer)
```

The logger daemon owns the hardware connection (serial, TCP, HTTP, or UDP depending on station type) and writes sensor data to SQLite. The web application reads the database and communicates with the logger via TCP IPC for hardware commands (reconnect, time sync, config writes). All drivers implement a common `StationDriver` interface, so the dashboard, charts, and all other features work identically regardless of hardware.

### Backend (Python / FastAPI)

```
backend/
├── app/
│   ├── protocol/        # Station drivers
│   │   ├── base.py      # StationDriver ABC + SensorSnapshot
│   │   ├── link_driver.py        # Davis legacy serial (stable)
│   │   ├── vantage/              # Davis Vantage Pro/Pro2/Vue
│   │   ├── weatherlink_ip/       # Davis WeatherLink IP (TCP)
│   │   ├── weatherlink_live/     # Davis WeatherLink Live (HTTP/UDP)
│   │   ├── ecowitt/              # Ecowitt / Fine Offset (TCP LAN API)
│   │   ├── ambient/              # Ambient Weather (HTTP push)
│   │   └── tempest/              # WeatherFlow Tempest (UDP)
│   ├── models/          # SQLAlchemy ORM (sensor readings, archive, config, spray)
│   ├── services/        # Poller, calculations, forecasts, astronomy, spray engine, CWOP, WU upload
│   ├── api/             # REST endpoints under /api
│   ├── ws/              # WebSocket handler at /ws/live
│   ├── ipc/             # IPC server (logger) and client (web app)
│   ├── output/          # METAR and APRS packet generators
│   ├── config.py        # Pydantic Settings (env vars + .env)
│   └── main.py          # Web app factory, lifespan, static file serving
└── logger_main.py       # Standalone logger daemon (serial, poller, IPC server)
```

### Frontend (React / TypeScript / Vite)

```
frontend/src/
├── components/
│   ├── gauges/          # TemperatureGauge, BarometerDial, WindCompass,
│   │                    # HumidityGauge, RainGauge, SolarUVGauge
│   ├── charts/          # TrendChart (sparkline), HistoricalChart (area)
│   ├── layout/          # AppShell, Header, Sidebar, Footer
│   └── setup/           # Setup wizard components
├── dashboard/           # DashboardGrid, DashboardTile (12-column drag-resize)
├── pages/               # Dashboard, History, Forecast, Astronomy,
│                        # SprayAdvisor, Settings, About
├── context/             # WeatherDataContext, ThemeContext, WeatherBackgroundContext
├── themes/              # dark, light, classic (CSS custom properties)
├── hooks/               # useWebSocket, useCurrentConditions, useIsMobile
├── api/                 # HTTP client, WebSocket manager, TypeScript types
└── utils/               # Unit conversions, formatting, timezone, constants
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/current` | Latest sensor reading + all derived values |
| GET | `/api/history` | Time-series data with aggregation (5m/hourly/daily) |
| GET | `/api/export` | CSV export with date range and resolution |
| GET | `/api/forecast` | Zambretti + NWS blended forecast |
| GET | `/api/astronomy` | Sun/moon times, twilight, moon phase |
| GET | `/api/station` | Station type, connection status, diagnostics |
| GET/PUT | `/api/config` | Read/update configuration |
| GET | `/api/spray/products` | Spray product definitions |
| GET | `/api/spray/schedules` | Spray schedules with evaluations |
| GET | `/api/spray/conditions` | Current spray conditions summary |
| GET | `/api/db-admin/stats` | Database row counts and file size |
| GET | `/api/db-admin/export/backup` | Full SQLite database backup |
| POST | `/api/db-admin/compact` | Compact sensor readings to 5-minute averages |
| POST | `/api/backup` | Create backup archive (DB + backgrounds) |
| GET | `/api/backup/list` | List existing backups |
| GET | `/api/backup/download/{name}` | Download a backup archive |
| POST | `/api/backup/restore` | Restore from uploaded archive |
| WS | `/ws/live` | Real-time sensor updates |

Additional API endpoints for AI nowcast, usage tracking, and NWS alerts are available when the optional [kanfei-nowcast](https://github.com/cnighswonger/kanfei-nowcast) package is installed.

## Supported Hardware

All drivers implement a common `StationDriver` interface. Drivers marked "in testing" are implemented and awaiting hardware validation — see linked issues for test plans. If you own the hardware and want to help test, comments on the issues are welcome.

### Davis Instruments

| Family | Models | Connection | Status |
|--------|--------|------------|--------|
| **Legacy serial** | Weather Monitor II, Wizard III, Wizard II, Perception II, GroWeather, Energy, Health | RS-232 serial (2400 baud) | Stable |
| **Vantage Pro/Pro2** | VP1, VP2 (6150, 6152, 6153, 6160, 6162, 6163) | RS-232 serial or USB (19200 baud) | [In testing (#1)](https://github.com/cnighswonger/kanfei/issues/1) |
| **Vantage Vue** | Vue (6250, 6351) | RS-232 serial or USB (19200 baud) | [In testing (#1)](https://github.com/cnighswonger/kanfei/issues/1) |
| **WeatherLink IP** | 6555 | Ethernet TCP (port 22222) | [In testing (#6)](https://github.com/cnighswonger/kanfei/issues/6) |
| **WeatherLink Live** | 6100 | WiFi — HTTP + UDP | [In testing (#5)](https://github.com/cnighswonger/kanfei/issues/5) |

### Ecowitt / Fine Offset

| Family | Models | Connection | Status |
|--------|--------|------------|--------|
| **WiFi gateways** | GW1000, GW1100, GW1200, GW2000 | TCP LAN API (port 45000) | [In testing (#2)](https://github.com/cnighswonger/kanfei/issues/2) |
| **WiFi consoles** | HP2551, HP2553, HP3500 | TCP LAN API (port 45000) | [In testing (#2)](https://github.com/cnighswonger/kanfei/issues/2) |
| **Branded variants** | WH2900, Sainlogic, Froggit, Bresser, Logia, Misol, Raddy | TCP LAN API (port 45000) | [In testing (#2)](https://github.com/cnighswonger/kanfei/issues/2) |

### Ambient Weather

| Family | Models | Connection | Status |
|--------|--------|------------|--------|
| **WiFi stations** | WS-2902, WS-5000 (Fine Offset OEM) | HTTP push | [In testing (#4)](https://github.com/cnighswonger/kanfei/issues/4) |

### WeatherFlow

| Family | Models | Connection | Status |
|--------|--------|------------|--------|
| **Tempest** | Tempest (ST-00001) | Local UDP broadcast | [In testing (#3)](https://github.com/cnighswonger/kanfei/issues/3) |

## Hardware Setup

The setup wizard auto-detects your station hardware on first run. For serial stations, connect the datalogger via a USB-to-serial adapter (or native RS-232 port). For WiFi/network stations (Ecowitt, WeatherLink Live, Tempest), provide the station's IP address or let the wizard discover it on the local network.

## Deployment

### Ubuntu / Debian (.deb package)

If you're installing from a release `.deb` artifact:

```bash
sudo dpkg -i <release-package>.deb
```

Then verify installed units on your host and enable/start them:

```bash
systemctl list-unit-files | rg kanfei
```

### Manual systemd (Linux)

A sample unit file is included at `kanfei.service`:

```bash
python station.py setup
sudo cp kanfei.service /etc/systemd/system/kanfei.service
sudo systemctl daemon-reload
sudo systemctl enable --now kanfei
```

Edit `Environment=` values in the unit file for your hardware/location before enabling it.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.10+, FastAPI, uvicorn |
| Hardware | pyserial, httpx (async HTTP/TCP/UDP drivers) |
| Database | SQLAlchemy + SQLite (WAL mode) |
| Astronomy | astral |
| NWS client | httpx (async) |
| Frontend | React 19, TypeScript (strict), Vite |
| Charts | Highcharts |
| Real-time | FastAPI WebSocket |

## About the Name

**Kanfei** (Hebrew: כַּנְפֵי, *kanfei ruach* — "wings of the wind") from Psalm 104:2-3 (KJV):

> *"Who coverest thyself with light as with a garment: who stretchest out the heavens like a curtain: Who layeth the beams of his chambers in the waters: who maketh the clouds his chariot: who walketh upon the wings of the wind."*

## Reference

The `reference/` directory contains the original Davis Instruments SDK materials (circa 1996-1999) documenting the PC-to-WeatherLink serial protocol: technical reference, command set, CRC tables, memory maps, and sample C/VB source code.

## License

Copyright (C) 2026 Chris Nighswonger

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, version 3. See [LICENSE](LICENSE) for the full text.
