# Field Naming Conventions

## Storage: SI Units

All sensor data is stored internally in **SI units** as integers (tenths for precision). Drivers convert from their native format to SI at the parse boundary. Everything downstream (poller, calculations, DB) assumes SI.

### Internal (DB / SensorSnapshot) field names

Field names do **not** include unit suffixes — the unit is always SI.

| Field | Unit | Storage |
|-------|------|---------|
| `inside_temp`, `outside_temp` | °C | tenths °C (e.g., 241 = 24.1°C) |
| `dew_point`, `heat_index`, `wind_chill`, `feels_like` | °C | tenths °C |
| `theta_e` | K | tenths K |
| `barometer` | hPa | tenths hPa (e.g., 10132 = 1013.2 hPa) |
| `wind_speed`, `wind_gust` | m/s | tenths m/s |
| `wind_direction` | degrees | 0–359 |
| `inside_humidity`, `outside_humidity` | % | 0–100 |
| `rain_rate` | mm/hr | tenths mm/hr |
| `rain_total`, `rain_yearly` | mm | tenths mm |
| `solar_radiation` | W/m² | whole W/m² |
| `uv_index` | index | tenths |
| `soil_temp` | °C | °C (float) |

### SensorSnapshot (driver output)

`SensorSnapshot` is the canonical dataclass returned by every driver's `poll()` method. Values are SI floats (not tenths) — the poller multiplies by 10 for DB storage.

```python
# SensorSnapshot fields (SI, whole floats)
snapshot.outside_temp    # °C
snapshot.barometer       # hPa
snapshot.wind_speed      # m/s
snapshot.rain_rate       # mm/hr
```

## Display: Conversion at the Boundary

Conversion from SI to display units happens **only** at the API/broadcast boundary, via `sensor_meta.convert()` or the unit converter functions in `utils/units.py`.

| SI (internal) | Imperial (display) | Metric (display) |
|---------------|-------------------|-------------------|
| tenths °C | °F | °C |
| tenths hPa | inHg | hPa |
| tenths m/s | mph | km/h |
| tenths mm | in | mm |

### Where conversion happens

- `poller._snapshot_to_dict()` — WebSocket broadcast to frontend
- `sensor_meta.convert()` — API responses from DB values
- `public_data.build_public_data()` — public API (includes both imperial and metric)
- `aprs.py`, `cwop.py`, `wunderground.py` — upload services convert internally

### Where conversion does NOT happen

- DB reads/writes — always SI tenths
- `calculations.py` — accepts SI tenths, converts internally where needed
- Driver → SensorSnapshot — driver outputs SI, poller stores directly

## Inside vs Outside Prefixes

- `outside_*` — external weather exposure
- `inside_*` — indoor sensor values

Examples:
- `outside_temp` vs `inside_temp`
- `outside_humidity` vs `inside_humidity`

## Public Data API

The `PublicWeatherData` schema (used by push export, REST API, MQTT) includes **both** imperial and metric in every field:

```json
{
  "current": {
    "temp_f": 75.2,
    "temp_c": 24.0,
    "humidity": 62,
    "wind_speed_mph": 8,
    "wind_speed_kmh": 12.9,
    "pressure_inhg": 30.02,
    "pressure_hpa": 1016.6
  }
}
```

Public API field names **do** include unit suffixes since consumers need to know what they're getting.

## Why This Matters

```python
# BAD — ambiguous, assumes display units
reading.temperature_f
reading.barometer_inHg

# GOOD — SI internal, no unit suffix needed
reading.outside_temp      # always °C
reading.barometer         # always hPa

# Convert at the boundary
from app.models.sensor_meta import convert
display_temp = convert("outside_temp", raw_db_value)  # → °F
```
