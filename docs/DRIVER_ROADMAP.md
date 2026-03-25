# Kanfei — Hardware Driver Roadmap

## Overview

Kanfei aims to support personal weather stations from multiple manufacturers through a pluggable driver architecture. Each manufacturer's equipment is documented using the standard template below, with implementation phases ordered by user impact.

---

## Part 1: Driver Abstraction Layer

Before adding new hardware drivers, the codebase needs a generic abstraction layer that decouples station-specific protocol details from the polling, storage, and API layers.

### StationDriver Interface

Every hardware driver implements this abstract base class:

```
StationDriver (ABC)
├── connect()                          Open serial/TCP/HTTP connection
├── disconnect()                       Clean shutdown
├── detect_hardware() -> HardwareInfo  Identify model, firmware, capabilities
├── poll() -> SensorSnapshot           Read current sensor values
├── read_archive(since) -> list[ArchiveRecord]  Retrieve stored history
├── get_config() -> dict               Read station configuration
├── set_config(key, value) -> bool     Write station configuration
├── sync_clock(dt: datetime)           Set station clock
└── properties
    ├── connected: bool
    ├── station_name: str              Human-readable model name
    └── capabilities: set[str]         What this driver supports
```

### SensorSnapshot

A canonical data class returned by every driver's `poll()` method. All values are in **SI units** — the driver is responsible for converting from its hardware-native format to SI. Everything downstream (poller, calculations, DB storage) assumes SI.

| Field | Unit | Notes |
|-------|------|-------|
| `inside_temp` | °C | `None` if sensor absent |
| `outside_temp` | °C | |
| `inside_humidity` | % | |
| `outside_humidity` | % | |
| `wind_speed` | m/s | |
| `wind_direction` | degrees (0–359) | |
| `wind_gust` | m/s | |
| `barometer` | hPa | Sea-level corrected |
| `rain_rate` | mm/hr | |
| `rain_daily` | mm | Since midnight |
| `rain_yearly` | mm | Since Jan 1 |
| `solar_radiation` | W/m² | `None` if no sensor |
| `uv_index` | index | `None` if no sensor |
| `soil_temp` | °C | `None` if no sensor |
| `soil_moisture` | cb | Centibars, `None` if absent |
| `leaf_wetness` | 0–15 | `None` if no sensor |
| `et_daily` | mm | Evapotranspiration |
| `extra` | dict | Vendor-specific fields |

Display-unit conversion (°C → °F, hPa → inHg, etc.) happens at the API/broadcast boundary, not in the driver.

### Integration Points

| Layer | Current State | Multi-Driver Change |
|-------|--------------|-------------------|
| **IPC protocol** | Generic JSON-over-TCP | No change needed |
| **API responses** | Generic shape (temp, humidity, wind, etc.) | No change needed |
| **Database** | `SensorReadingModel` stores SI (tenths °C, tenths hPa, tenths m/s, tenths mm) with `extra_json` TEXT for vendor-specific fields | No change needed — already unit-agnostic |
| **Poller** | Accepts any `StationDriver` via SI `SensorSnapshot`; stores ×10 to DB; calculations accept SI | No change needed — driver-agnostic |
| **Logger daemon** | Creates `LinkDriver` directly | Driver factory based on config (`station_driver_type`) |
| **Settings UI** | Davis-specific fields (calibration, rain clicks) | Driver reports its configurable parameters; UI renders dynamically |

### Capabilities System

Drivers declare what they support so the UI and services can adapt:

```python
capabilities = {
    "archive_sync",      # Can retrieve historical records
    "calibration_rw",    # Can read/write calibration offsets
    "clock_sync",        # Can set station clock
    "rain_reset",        # Can clear rain accumulators
    "hilows",            # Can retrieve hi/low records
    "loop2",             # Supports enhanced wind data (Davis Vantage)
    "real_time_wind",    # Sub-second wind updates (WL Live UDP)
}
```

---

## Part 2: Driver Roadmap Template

Use this template when adding support for a new manufacturer. Copy the structure and fill in for each vendor.

---

### {Manufacturer} Driver Roadmap

#### Manufacturer Overview

- Company name, headquarters, market position
- Product line summary
- Official protocol documentation references (URLs, PDF links)
- Open-source reference implementations (weewx driver, etc.)

#### Product Families

| Family | Models | Protocol | Connection | Production Status |
|--------|--------|----------|------------|-------------------|
| | | | | Active / Discontinued |

#### Protocol Inventory

For each distinct protocol this manufacturer uses:

**Protocol: {Name}**

| Attribute | Value |
|-----------|-------|
| Connection | Serial / USB / TCP / HTTP / BLE / WiFi |
| Baud / Port | e.g. 19200 8N1 / port 80 |
| Handshake | Wakeup sequence, authentication |
| Polling | Command and response format |
| Packet size | Bytes per reading |
| Archive | Retrieval method and record format |
| Calibration | Read/write method |
| Clock | Sync method |
| CRC / checksum | Algorithm |
| Quirks | Known issues, firmware-specific behavior |
| Reference impl | weewx driver, GitHub links |

#### Driver Phases

Ordered by user impact (market share of models):

**Phase N: {Protocol/Family Name}**
- Models supported: ...
- Prerequisites: abstraction layer, connection type support
- Effort: S / M / L
- Key notes: ...

#### Compatibility Matrix

| Feature | Model A | Model B | Model C |
|---------|---------|---------|---------|
| Live polling | | | |
| Archive sync | | | |
| Calibration R/W | | | |
| Clock sync | | | |
| Rain accumulators | | | |

---

## Part 3: Davis Instruments

### Manufacturer Overview

- **Company**: Davis Instruments, Hayward, CA (est. 1963)
- **Market position**: Leading US personal weather station manufacturer
- **Documentation**:
  - Legacy protocol: `reference/techref.txt` (Rev 3.3, 1998) — in this repo
  - Vantage protocol: "Vantage Pro, Pro2, and Vue Serial Communication Reference Manual" v2.6.1 (2013)
  - WeatherLink Live: [Local API docs](https://weatherlink.github.io/weatherlink-live-local-api/)
- **Reference implementations**: [weewx vantage driver](https://github.com/weewx/weewx), PyWeather

### Product Families

| Family | Models | Protocol | Connection | Status |
|--------|--------|----------|------------|--------|
| **Legacy** | Weather Monitor II, Wizard III, Wizard II, Perception II, GroWeather, Energy, Health | WeatherLink Serial (1998) | RS-232 serial | Discontinued |
| **Vantage Pro** | VP1 (6150, 6160) | Vantage Serial | RS-232 / USB | Discontinued |
| **Vantage Pro2** | VP2 (6152, 6153, 6162, 6163) | Vantage Serial | RS-232 / USB | **Active** |
| **Vantage Vue** | Vue (6250, 6351) | Vantage Serial | RS-232 / USB | **Active** |
| **WeatherLink IP** | 6555 | Vantage Serial over TCP | Ethernet (port 22222) | Discontinued |
| **WeatherLink Live** | 6100 | HTTP/JSON + UDP | WiFi / Ethernet | **Active** |
| **WeatherLink Console** | 6313 | HTTP/JSON | WiFi | **Active** |
| **AirLink** | 7210 | HTTP/JSON | WiFi | **Active** (air quality only) |

### Protocol Inventory

#### Protocol: WeatherLink Serial (Legacy)

| Attribute | Value |
|-----------|-------|
| Connection | RS-232 serial |
| Baud | 2400 8N1 (factory default) |
| Handshake | None — station responds immediately |
| Polling | `LOOP` command, variable-length response (15–33 bytes by model) |
| Archive | `SRD` direct SRAM read, circular buffer up to 32KB |
| Calibration | `WRD`/`WWR` memory-mapped (Bank 0/1, nibble-addressed) |
| Clock | Write to BCD memory addresses |
| CRC | CCITT CRC-1021 (Rev E only for command responses) |
| Quirks | Nibble addressing, BCD time encoding, 3 hardware revisions (C/D/E) with different CRC behavior |

**Status: Fully implemented** — current `LinkDriver` in `backend/app/protocol/`

---

#### Protocol: Vantage Serial

| Attribute | Value |
|-----------|-------|
| Connection | RS-232 serial or USB (virtual COM port) |
| Baud | 19200 8N1 (default, configurable: 1200–19200) |
| Handshake | Send `\n`, expect `\n\r` response (up to 3 retries) |
| Polling | `LOOP n` (99-byte packets) or `LPS bitmask n` (LOOP + LOOP2 alternating) |
| Packet size | LOOP: 99 bytes, LOOP2: 99 bytes (different field layout) |
| Archive | `DMPAFT` date-filtered dump via XMODEM-CRC pages (5 × 52-byte records per page) |
| Calibration | `EEBRD`/`EEBWR` for EEPROM, `BAR` command for barometer |
| Clock | `GETTIME`/`SETTIME` named commands |
| CRC | CCITT CRC-1021 on all responses |
| Quirks | LOOP2 requires firmware 1.90+ (VP2/Vue only, not VP1); LPS limited to ~220 records per batch; VP1 lacks `NVER` command; Rev A vs Rev B LOOP format (bar trend byte); Rev A vs Rev B archive records |
| Reference impl | weewx `vantage.py` driver |

**LOOP packet fields** (99 bytes): barometer trend, barometer, inside/outside temp, wind speed/dir, extra temps ×7, soil temps ×4, leaf temps ×4, inside/outside humidity, extra humidities ×7, rain rate, UV, solar radiation, storm rain, daily/monthly/yearly rain, daily/monthly/yearly ET, soil moistures ×4, leaf wetnesses ×4, forecast icons, sunrise/sunset.

**LOOP2 additions** (VP2/Vue only): 2-min wind avg, 10-min wind avg, 10-min gust + direction (all 0.1 mph resolution), dew point, heat index, wind chill, THSW index, gauge pressure, altimeter pressure.

**Archive record** (52 bytes): timestamp (date stamp + time stamp, 2 bytes each), outside/inside temp (hi/lo/avg), humidity, barometer, rain, wind (avg/hi), solar, UV, ET, soil/leaf data. Rev B adds high solar, high UV, forecast rule, leaf/soil temps.

---

#### Protocol: WeatherLink Live HTTP

| Attribute | Value |
|-----------|-------|
| Connection | WiFi / Ethernet, HTTP on port 80 |
| Baud | N/A |
| Handshake | None (stateless HTTP) |
| Polling | `GET /v1/current_conditions` — JSON response with all sensor data |
| Real-time | `GET /v1/real_time?duration=N` triggers UDP broadcast on port 22222 every 2.5s (wind + rain) |
| Archive | None (cloud-only via weatherlink.com v2 API) |
| Calibration | Cloud-managed, not writable locally |
| Clock | N/A (NTP-synced) |
| Quirks | Must poll no faster than every 10 seconds; 4 data structure types in JSON (ISS, leaf/soil, barometer, indoor); auto-discovery possible via mDNS |
| Reference impl | [weatherlink-live-local-api](https://github.com/weatherlink/weatherlink-live-local-api) |

---

#### Protocol: WeatherLink IP (TCP)

| Attribute | Value |
|-----------|-------|
| Connection | Ethernet, raw TCP on port 22222 |
| Baud | N/A (TCP) |
| Handshake | Same as Vantage Serial (`\n` wakeup) |
| Polling | Same command set as Vantage Serial |
| Archive | Same as Vantage Serial (`DMPAFT`) |
| Quirks | Must release TCP socket ~5s/min and ~60s/hr for device's own cloud uploads |
| Reference impl | weewx vantage driver (TCP mode) |

Effectively the Vantage Serial protocol over a TCP socket. Implementation reuses the Vantage parser with a TCP transport.

---

### Driver Phases

#### Phase 0: Abstraction Layer (prerequisite)

- Extract `StationDriver` ABC from current `LinkDriver`
- Create `SensorSnapshot` and `ArchiveRecord` canonical data classes
- Refactor `Poller` to consume `StationDriver` interface
- Add `extra_json` column to `SensorReadingModel`
- Driver factory in `logger_main.py` based on `station_driver_type` config
- Keep all existing functionality working throughout
- **Effort**: M
- **Files**: `protocol/base.py` (new), `protocol/link_driver.py`, `services/poller.py`, `logger_main.py`, `models/sensor_reading.py`

#### Phase 1: Vantage Serial Driver (VP1, VP2, Vue)

Highest priority — the Vantage Pro2 and Vue are the most widely used Davis stations.

- New `VantageDriver(StationDriver)` in `protocol/vantage/`
- Console wakeup (`\n` → `\n\r`)
- LOOP packet parser (99 bytes, Rev A + Rev B)
- LOOP2 packet parser (VP2/Vue with firmware 1.90+)
- `LPS` command for interleaved LOOP/LOOP2 polling
- `DMPAFT` archive retrieval with XMODEM-CRC page handling
- `EEBRD`/`EEBWR` for EEPROM config, `BAR` for barometer calibration
- `GETTIME`/`SETTIME` for clock sync
- `HILOWS` for daily/monthly/yearly extremes
- Auto-detect VP1 vs VP2 vs Vue via EEPROM station type byte
- `VER`/`NVER` firmware version reporting
- CRC validation on all responses (reuse existing `crc.py`)
- **Effort**: L
- **Prerequisites**: Phase 0
- **Reference**: Davis Serial Comm Ref v2.6.1, weewx `vantage.py`

#### Phase 2: WeatherLink Live HTTP Driver

Current-generation WiFi/Ethernet gateway — growing install base.

- New `WeatherLinkLiveDriver(StationDriver)` in `protocol/weatherlink_live/`
- HTTP client (`httpx`) polling `GET /v1/current_conditions`
- JSON response parsing (4 data structure types)
- Optional UDP listener for real-time wind/rain (2.5s updates)
- Auto-discovery via manual IP or mDNS
- No archive sync (cloud-only)
- No calibration write, no clock sync (cloud-managed)
- **Effort**: M
- **Prerequisites**: Phase 0

#### Phase 3: WeatherLink IP TCP Driver

Legacy network product — reuses Vantage protocol.

- Subclass or adapter around `VantageDriver` with TCP transport
- Same command set and parsing as Phase 1
- Connection yielding logic (release socket periodically)
- **Effort**: S
- **Prerequisites**: Phase 1

#### Phase 4: WeatherLink Console HTTP Driver

Newest Davis product — touchscreen console with WiFi.

- Similar to WeatherLink Live but newer API version
- May share base HTTP driver class with Phase 2
- **Effort**: S
- **Prerequisites**: Phase 2

### Compatibility Matrix

| Feature | Legacy (WMII etc.) | VP1 | VP2 | Vue | WL Live | WL IP | WL Console |
|---------|-------------------|-----|-----|-----|---------|-------|------------|
| Live polling | **Done** | Ph 1 | Ph 1 | Ph 1 | Ph 2 | Ph 3 | Ph 4 |
| Archive sync | **Done** | Ph 1 | Ph 1 | Ph 1 | No | Ph 3 | No |
| Calibration R/W | **Done** | Ph 1 | Ph 1 | Ph 1 | No | Ph 3 | No |
| Clock sync | **Done** | Ph 1 | Ph 1 | Ph 1 | N/A | Ph 3 | N/A |
| Rain reset | **Done** | Ph 1 | Ph 1 | Ph 1 | No | Ph 3 | No |
| LOOP2 data | N/A | No | Ph 1 | Ph 1 | N/A | Ph 3 | N/A |
| Hi/Low data | **Done** | Ph 1 | Ph 1 | Ph 1 | No | Ph 3 | No |
| Real-time wind | No | No | No | No | Ph 2 | No | Ph 4 |

---

## Future Manufacturers

When adding a new manufacturer, copy the template from Part 2 and create a new section. Planned candidates:

| Manufacturer | Key Products | Protocol Type | Priority |
|-------------|-------------|---------------|----------|
| Ecowitt | GW1000/GW2000, WS2900, HP2551 | HTTP/JSON (local API) | High |
| Ambient Weather | WS-2902, WS-5000 | HTTP (via Ecowitt firmware) | High |
| Oregon Scientific | WMR88, WMR200, WMRS200 | USB HID / serial | Low |
| Fine Offset | WH1080, WH2080, WH3081 | USB HID | Low |
| La Crosse | WS-2800, C84612 | USB HID | Low |
| Bloomsky | Sky 1/2, Storm | HTTP/JSON (cloud API) | Low |

Ecowitt/Ambient are likely the next highest-value targets after Davis, given their growing market share and well-documented local HTTP APIs.
