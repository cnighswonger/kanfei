# Field Naming Conventions

## Units in Field Names

Weather measurement fields include units to avoid ambiguity.

### Temperature
- `*_temp_f` - Fahrenheit
- `*_temp_c` - Celsius (if introduced)
- Other explicit forms: `dew_point_f`, `heat_index_f`, `wind_chill_f`

### Pressure
- `*_inHg` / `*_inhg` - Inches of mercury
- `*_hPa` - Hectopascals (if introduced)

Examples:
- `barometer_inHg` (ObservationReading)
- `pressure_inhg` (NearbyObservation)

### Humidity
- `*_pct` - Percent (0-100)

Examples:
- `outside_humidity_pct`
- `humidity_pct`

### Wind
- `*_mph` - Miles per hour
- `*_deg` - Degrees (0-359, where 0 is north)

Examples:
- `wind_speed_mph`
- `wind_direction_deg`
- `wind_dir_deg`

### Precipitation
- `*_in` - Inches
- `*_in_hr` - Inches per hour (rate)

Examples:
- `rain_daily_in`
- `rain_rate_in_hr`
- `precip_in`

### Radiation
- `*_wm2` - Watts per square meter

Example:
- `solar_radiation_wm2`

## Inside vs Outside Prefixes

- `outside_*` - External weather exposure
- `inside_*` - Indoor sensor values

Examples:
- `outside_temp_f` vs `inside_temp_f`
- `outside_humidity_pct` vs `inside_humidity_pct`

## Why This Matters

```python
# BAD (ambiguous)
reading.temperature
reading.pressure

# GOOD (explicit)
reading.outside_temp_f
reading.barometer_inHg
```

## Cross-Structure Mapping Rule

When converting between nearby-station and local-station types, map names intentionally:

| NearbyObservation | ObservationReading |
|---|---|
| `temp_f` | `outside_temp_f` |
| `humidity_pct` | `outside_humidity_pct` |
| `pressure_inhg` | `barometer_inHg` |
| `wind_dir_deg` | `wind_direction_deg` |
| `wind_speed_mph` | `wind_speed_mph` |
