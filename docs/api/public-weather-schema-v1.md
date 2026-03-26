# Public Weather Data Schema (v1)

The canonical JSON schema for public weather data output from Kanfei. Used by the push export, REST API, MQTT publish, and embeddable widgets.

## Endpoint

```
GET /api/public/weather
```

No authentication required.

## Response

```json
{
  "station": {
    "name": "My Weather Station",
    "latitude": 35.33,
    "longitude": -97.49,
    "elevation_ft": 1200
  },
  "current": {
    "temp_f": 72.5,
    "temp_c": 22.5,
    "humidity": 55,
    "dewpoint_f": 55.8,
    "dewpoint_c": 13.2,
    "wind_mph": 10,
    "wind_kmh": 16.1,
    "wind_dir": 225,
    "wind_dir_str": "SW",
    "wind_gust_mph": 15,
    "barometer_inhg": 29.92,
    "barometer_hpa": 1013.2,
    "rain_rate_in": 0.0,
    "rain_rate_mm": 0.0,
    "rain_day_in": 0.12,
    "rain_day_mm": 3.0,
    "solar_radiation": 850,
    "uv_index": 5.2,
    "feels_like_f": 72.5,
    "feels_like_c": 22.5,
    "heat_index_f": null,
    "heat_index_c": null,
    "wind_chill_f": null,
    "wind_chill_c": null,
    "pressure_trend": "steady"
  },
  "daily": {
    "temp_high_f": 78.1,
    "temp_low_f": 62.4,
    "temp_high_c": 25.6,
    "temp_low_c": 16.9,
    "wind_high_mph": 22,
    "rain_total_in": 0.12,
    "rain_total_mm": 3.0
  },
  "meta": {
    "timestamp": "2026-03-26T15:30:00+00:00",
    "station_type": "Davis Vantage Pro2",
    "software": "Kanfei",
    "software_version": "0.1.0",
    "api_version": "1"
  }
}
```

## Design decisions

### Both imperial and metric

Every measurement is provided in both unit systems. Consumers don't need to convert — pick the field that matches your locale. This avoids rounding errors from client-side conversion and makes the schema usable worldwide.

### Null for absent sensors

Fields are `null` when the sensor is absent or the reading is invalid (e.g., `solar_radiation` on a station without a solar sensor, `wind_chill` when conditions don't warrant it). Consumers should handle null gracefully.

### Location precision

`station.latitude` and `station.longitude` are provided at the precision stored in the database (typically 4-6 decimal places from the setup wizard). A future `public_data_location_precision` config option will allow rounding to protect exact home location.

### Station name

`station.name` defaults to "Kanfei Weather Station" if not configured. Users can set a custom name in Settings.

### Versioning

`meta.api_version` is `"1"`. If the schema changes in a breaking way, the version number increments. Consumers should check this field.

## Embedding example

```html
<div id="weather"></div>
<script>
fetch('https://your-server:8000/api/public/weather')
  .then(r => r.json())
  .then(d => {
    document.getElementById('weather').innerHTML =
      `${d.current.temp_f}°F, ${d.current.humidity}% humidity, ` +
      `wind ${d.current.wind_dir_str} ${d.current.wind_mph} mph`;
  });
</script>
```
