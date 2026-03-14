/**
 * Y-axis scaling utility for Highcharts.
 *
 * Returns softMin/softMax so the axis tightens to data but auto-expands
 * if actual values exceed the computed bounds (no clipping).
 */

export interface YAxisScale {
  softMin: number;
  softMax: number;
  tickInterval?: number;
}

type ScaleCategory =
  | "temperature"
  | "humidity"
  | "wind_speed"
  | "wind_direction"
  | "barometer"
  | "rain"
  | "solar_radiation"
  | "uv_index"
  | "generic";

const SENSOR_CATEGORY: Record<string, ScaleCategory> = {
  // History page naming
  temperature_inside: "temperature",
  temperature_outside: "temperature",
  heat_index: "temperature",
  dew_point: "temperature",
  wind_chill: "temperature",
  feels_like: "temperature",
  humidity_inside: "humidity",
  humidity_outside: "humidity",
  wind_speed: "wind_speed",
  wind_direction: "wind_direction",
  barometer: "barometer",
  rain_daily: "rain",
  rain_yearly: "rain",
  rain_rate: "rain",
  solar_radiation: "solar_radiation",
  uv_index: "uv_index",
  // Dashboard tileRegistry naming
  outside_temp: "temperature",
  inside_temp: "temperature",
  outside_humidity: "humidity",
  inside_humidity: "humidity",
  rain_total: "rain",
};

function inferCategory(sensor: string): ScaleCategory {
  const s = sensor.toLowerCase();
  if (s.includes("temp") || s.includes("heat") || s.includes("chill") || s.includes("dew") || s.includes("feels"))
    return "temperature";
  if (s.includes("humid")) return "humidity";
  if (s.includes("wind") && s.includes("dir")) return "wind_direction";
  if (s.includes("wind")) return "wind_speed";
  if (s.includes("baro") || s.includes("pressure")) return "barometer";
  if (s.includes("rain") || s.includes("precip")) return "rain";
  if (s.includes("solar") || s.includes("radiation")) return "solar_radiation";
  if (s.includes("uv")) return "uv_index";
  return "generic";
}

export function computeYAxisScale(sensor: string, values: number[]): YAxisScale {
  const finite = values.filter(Number.isFinite);
  if (finite.length === 0) return { softMin: 0, softMax: 10 };

  const dataMin = Math.min(...finite);
  const dataMax = Math.max(...finite);
  const category = SENSOR_CATEGORY[sensor] ?? inferCategory(sensor);

  switch (category) {
    case "temperature":
      return scaleTemperature(dataMin, dataMax);
    case "humidity":
      return scaleHumidity(dataMin, dataMax);
    case "wind_speed":
      return scaleFloorZero(dataMin, dataMax, 10, 5);
    case "wind_direction":
      return { softMin: 0, softMax: 360, tickInterval: 90 };
    case "barometer":
      return scaleBarometer(dataMin, dataMax);
    case "rain":
      return scaleFloorZero(dataMin, dataMax, 0.1, 0.05);
    case "solar_radiation":
      return scaleFloorZero(dataMin, dataMax, 100, 50);
    case "uv_index":
      return scaleFloorZero(dataMin, dataMax, 2, 1);
    case "generic":
    default:
      return scaleGeneric(dataMin, dataMax);
  }
}

function scaleTemperature(dataMin: number, dataMax: number): YAxisScale {
  const PAD = 5;
  const MIN_SPAN = 10;
  const range = dataMax - dataMin;
  const center = (dataMin + dataMax) / 2;
  if (range < MIN_SPAN) {
    return {
      softMin: Math.floor(center - MIN_SPAN / 2),
      softMax: Math.ceil(center + MIN_SPAN / 2),
    };
  }
  return {
    softMin: Math.floor(dataMin - PAD),
    softMax: Math.ceil(dataMax + PAD),
  };
}

function scaleHumidity(dataMin: number, dataMax: number): YAxisScale {
  const PAD = 5;
  const MIN_SPAN = 10;
  const range = dataMax - dataMin;
  const center = (dataMin + dataMax) / 2;
  let lo: number, hi: number;
  if (range < MIN_SPAN) {
    lo = center - MIN_SPAN / 2;
    hi = center + MIN_SPAN / 2;
  } else {
    lo = dataMin - PAD;
    hi = dataMax + PAD;
  }
  return {
    softMin: Math.max(0, Math.floor(lo)),
    softMax: Math.min(100, Math.ceil(hi)),
  };
}

function scaleBarometer(dataMin: number, dataMax: number): YAxisScale {
  const PAD = 0.1;
  const MIN_SPAN = 0.5;
  const range = dataMax - dataMin;
  const center = (dataMin + dataMax) / 2;
  let lo: number, hi: number;
  if (range < MIN_SPAN) {
    lo = center - MIN_SPAN / 2;
    hi = center + MIN_SPAN / 2;
  } else {
    lo = dataMin - PAD;
    hi = dataMax + PAD;
  }
  return {
    softMin: Math.floor(lo * 20) / 20,
    softMax: Math.ceil(hi * 20) / 20,
    tickInterval: 0.1,
  };
}

function scaleFloorZero(
  _dataMin: number,
  dataMax: number,
  minSpan: number,
  pad: number,
): YAxisScale {
  const hi = Math.max(dataMax + pad, minSpan);
  return {
    softMin: 0,
    softMax: Math.ceil(hi * 100) / 100,
  };
}

function scaleGeneric(dataMin: number, dataMax: number): YAxisScale {
  const range = dataMax - dataMin;
  const pad = Math.max(range * 0.1, 0.5);
  const MIN_SPAN = 10;
  const center = (dataMin + dataMax) / 2;
  if (range < MIN_SPAN) {
    return {
      softMin: Math.floor(center - MIN_SPAN / 2),
      softMax: Math.ceil(center + MIN_SPAN / 2),
    };
  }
  return {
    softMin: Math.floor(dataMin - pad),
    softMax: Math.ceil(dataMax + pad),
  };
}
