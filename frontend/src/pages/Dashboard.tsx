/**
 * Dashboard page — the persona composition wrapped in the theme's
 * paper-plate backdrop.  All layout + tile rendering lives in
 * ``dashboard/EverydayDashboard.tsx``; this file's one real job is
 * ``toDashboardData``, the single adapter that shapes our live weather
 * feeds into the ``DashboardData`` interface every tile reads from.
 *
 * Paper themes overlay two ornamental layers per ASSETS.md:
 *   - Glaisher gets a full-cover balloon-ascent photo at 0.12 opacity
 *   - Both paper themes get an instruments corner plate at ~0.09-0.10
 * Dark, light, classic ship with no dashboard-specific background.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import EverydayDashboard from "../dashboard/EverydayDashboard.tsx";
import { AgricultureDashboard } from "../dashboard/AgricultureDashboard.tsx";
import { WeatherNerdDashboard } from "../dashboard/WeatherNerdDashboard.tsx";
import type { DashboardData, NerdResolution } from "../dashboard/types.ts";
import { useTheme } from "../context/ThemeContext.tsx";
import { usePersona } from "../context/PersonaContext.tsx";
import { useWeatherData } from "../context/WeatherDataContext.tsx";
import {
  fetchForecast,
  fetchAstronomy,
  fetchHistory,
  fetchConfig,
  fetchSprayProducts,
  fetchSpraySchedules,
  fetchSprayOutcomes,
  evaluateSprayProduct,
  fetchSprayForecast,
  fetchSignalQuality,
  fetchSolarEnergyHistory,
  fetchMetar,
  fetchBarometerCalibration,
  fetchBarometerReference,
} from "../api/client.ts";
import type { SprayForecastRow } from "../api/client.ts";
import { scoreSprayHours, type SprayConstraints } from "../utils/gauges.ts";
import type {
  CurrentConditions,
  ForecastResponse,
  AstronomyResponse,
  LocalForecast,
  NWSPeriod,
  StationStatus as StationStatusType,
  HistoryPoint,
  SignalQuality,
  MetarReferenceResponse,
  SprayProduct,
  SprayEvaluation,
  SpraySchedule,
  SprayOutcome,
} from "../api/types.ts";

// Package version for the footer strip ("Kanfei v1.0.0 · …").  Same
// value the backend reads from ``backend/app/VERSION``; injected at
// build time via ``define`` in vite.config.ts as ``__KANFEI_VERSION__``.
declare const __KANFEI_VERSION__: string | undefined;
const APP_VERSION =
  typeof __KANFEI_VERSION__ === "string" && __KANFEI_VERSION__ ? __KANFEI_VERSION__ : "0.1.0";

/**
 * Small localStorage cache for the persona-gated fetches (spray,
 * signal-quality, solar-14d, METAR).  Populates ``useState`` inits so
 * refresh restores the last-known values immediately instead of
 * flashing em-dashes for the ~1 s each fetch takes.  Background fetch
 * then overwrites with fresh data on the next 5-min tick.
 *
 * Failure-safe: any parse / storage error returns null, and the
 * subsequent fetch fills in as usual.  Not versioned beyond the ``v1``
 * suffix in the key — a shape change bumps the key.
 */
function cacheLoad<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}
function cacheSave(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* quota / private mode — best-effort */
  }
}

/** Pull the closest usable METAR reference from the multi-station
 *  aggregate.  Returns null when location isn't configured or no
 *  station reported an altimeter in the current window. */
function pickNearestReference(
  resp: MetarReferenceResponse,
): { station: string; altimeterInHg: number } | null {
  if (!resp.location_configured) return null;
  for (const r of resp.references) {
    if (r.altimeter_inhg != null && Number.isFinite(r.altimeter_inhg)) {
      return { station: r.station_id, altimeterInHg: r.altimeter_inhg };
    }
  }
  return null;
}

/**
 * ISO timestamp → ``5:09 PM`` clock display.  Every ``…At`` field on
 * ``DashboardData`` is a display string, never an ISO — a raw ISO is
 * ~28 chars and breaks chip / row layouts.  ``primitives.fmtTime()`` in
 * the view is a defensive backstop; this is the primary formatter.
 */
function clock(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

/** 24-hour ``HH:MM`` variant.  Used for readouts that pair with
 *  the header and footer clocks (Peak-gust marker on the wind
 *  and drift-risk tiles).  Window readouts stay on ``clock()``'s
 *  12-hour output — Design v49 §3 keeps them as a spoken time
 *  the farmer reads as a plan. */
function clock24(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

/**
 * Barometer zone label — matches ``wheelDial()``'s zone words at
 * their sweep midpoints.  Below ~28.95 stormy, above ~30.56 set fair;
 * change / fair / rain bracket the typical range.
 */
function baroZone(inHg: number | null): string | null {
  if (inHg == null || !Number.isFinite(inHg)) return null;
  if (inHg < 28.95) return "STORMY";
  if (inHg < 29.48) return "RAIN";
  if (inHg < 30.03) return "CHANGE";
  if (inHg < 30.57) return "FAIR";
  return "SET FAIR";
}

/**
 * 3-hour barometric trend rate in inHg / 3h, computed from history
 * when the API doesn't report it (Kanfei currently ships only the
 * qualitative ``rising / falling / steady`` string).  Signed —
 * positive = rising.  Returns null if we don't have enough history.
 */
function trendPer3h(points: HistoryPoint[]): number | null {
  if (points.length < 2) return null;
  const now = Date.now();
  // Latest sample within the last 15 min
  let latest: HistoryPoint | null = null;
  for (let i = points.length - 1; i >= 0; i--) {
    const t = Date.parse(points[i].timestamp);
    if (now - t <= 15 * 60_000 && points[i].value != null) {
      latest = points[i];
      break;
    }
  }
  if (!latest || latest.value == null) return null;
  // Sample nearest 3 h ago (within a 30-min window)
  const target = Date.parse(latest.timestamp) - 3 * 60 * 60_000;
  let earlier: HistoryPoint | null = null;
  let earlierDelta = Infinity;
  for (const p of points) {
    if (p.value == null) continue;
    const delta = Math.abs(Date.parse(p.timestamp) - target);
    if (delta < earlierDelta && delta <= 30 * 60_000) {
      earlier = p;
      earlierDelta = delta;
    }
  }
  if (!earlier || earlier.value == null) return null;
  return Math.round((latest.value - earlier.value) * 1000) / 1000;
}

// Integrate 5-min rain rate samples into hourly totals (rate × dt, capped
// at 1 h per sample so a gap doesn't inflate one bar).  24 buckets,
// oldest first, keyed to the whole hour in the browser's local timezone.
function hourlyRainInches(points: HistoryPoint[]): (number | null)[] {
  if (!points.length) return Array<null>(24).fill(null);
  const buckets = new Map<number, number>();
  for (let i = 0; i < points.length; i++) {
    const p = points[i];
    if (p.value == null) continue;
    const t = Date.parse(p.timestamp);
    const hourStart = new Date(t);
    hourStart.setMinutes(0, 0, 0);
    const key = hourStart.getTime();
    const prev = i > 0 ? Date.parse(points[i - 1].timestamp) : t - 5 * 60_000;
    const dtHours = Math.min(Math.max((t - prev) / 3_600_000, 0), 1);
    buckets.set(key, (buckets.get(key) ?? 0) + p.value * dtHours);
  }
  // Emit 24 bins ending at the current hour, oldest first.
  const now = new Date();
  now.setMinutes(0, 0, 0);
  const bins: (number | null)[] = [];
  for (let i = 23; i >= 0; i--) {
    const key = now.getTime() - i * 3_600_000;
    const v = buckets.get(key);
    bins.push(v != null ? Math.round(v * 1000) / 1000 : null);
  }
  return bins;
}

interface AdapterSources {
  cc: CurrentConditions | null;
  status: StationStatusType | null;
  forecast: ForecastResponse | null;
  astronomy: AstronomyResponse | null;
  historyTemp: HistoryPoint[];
  historyDew: HistoryPoint[];
  historyBarometer: HistoryPoint[];
  historyThetaE: HistoryPoint[];
  hourlyRain: (number | null)[];
  /** Raw wind-direction samples over the last 4 h.  Feeds the wind-rose
   *  petals.  Empty until the first fetch resolves. */
  windDir4h: (number | null)[];
  siteName: string | null;
  spray: SprayAdapterInputs | null;
  baroOffsetInHg: number | null;
  signalWindow: { time: number; sample: SignalQuality }[];
  solar14d: (number | null)[];
  metar: string | null;
  baroRef: { station: string; altimeterInHg: number } | null;
  /** Which resolution the chart series were fetched at.  Echoed back into
   *  ``d.nerd.resolution`` so the button strip lights the right choice. */
  nerdResolution: NerdResolution;
  /** User's display-unit choice for pressure.  Fetched once from
   *  ``station_config`` and echoed into ``d.units.pressure``. */
  pressureUnit: 'inHg' | 'hPa';
}

interface SprayAdapterInputs {
  product: SprayProduct | null;
  evaluation: SprayEvaluation | null;
  schedules: SpraySchedule[];
  outcomes: SprayOutcome[];
  forecast: SprayForecastRow[];
  /** Wind gust readings for the last 4 h — bucketed into 2 mph bins
   * for the Drift-risk gust-frequency histogram (DIFF-3c).  Empty
   * when the endpoint returned no rows or the fetch failed. */
  gustHistory: (number | null)[];
}

/**
 * Bucket raw gust-mph readings into 12 fixed 2-mph bins for the
 * Drift-risk gust-frequency histogram (mock 3c, DIFF-3c).  Bin i
 * covers ``[2i, 2i+2)`` mph; readings ≥ 24 mph fall into the last
 * bin.  Nulls / non-finite values are skipped.
 */
function bucketGustReadings(readings: (number | null)[]): number[] {
  const bins = new Array<number>(12).fill(0);
  for (const r of readings) {
    if (r == null || !Number.isFinite(r) || r < 0) continue;
    const idx = Math.min(11, Math.floor(r / 2));
    bins[idx] += 1;
  }
  return bins;
}

/**
 * Bucket wind-direction samples into 16 wedges of 22.5° each for the
 * wind-rose petals.  Wedge 0 is centred on N (0°), wedge 4 on E, 8 on S,
 * 12 on W.  Returns normalised weights (max = 1); an all-nulls window
 * returns ``undefined`` so the tile falls back cleanly on ``??``.
 *
 * Design's default hardcoded weights implied count-based frequency
 * (all values in [0, 1]) — a speed-weighted rose is a different chart
 * ("wind energy per bearing") and is worth having, but not what the
 * mock shows.  Keep counts.
 */
function bucketWindDirection(readings: (number | null)[]): number[] | undefined {
  const bins = new Array<number>(16).fill(0);
  let total = 0;
  for (const r of readings) {
    if (r == null || !Number.isFinite(r)) continue;
    // Shift by 11.25° so wedge 0 straddles N (348.75-11.25) rather than
    // starting at N.  Modulo 360 to fold the E-of-W wraparound.
    const shifted = ((r + 11.25) % 360 + 360) % 360;
    const idx = Math.min(15, Math.floor(shifted / 22.5));
    bins[idx] += 1;
    total += 1;
  }
  if (!total) return undefined;
  const max = Math.max(...bins);
  return bins.map((n) => (max > 0 ? n / max : 0));
}

/** wind|temperature|humidity|rain_free → human label */
const SPRAY_CHECK_LABEL: Record<string, string> = {
  wind: "Wind",
  temperature: "Temperature",
  humidity: "Humidity",
  rain_free: "Rain-free",
};

/**
 * Extract the leading number from a backend check ``current_value``
 * string (e.g. ``"9 mph (gust)"`` → ``"9"``, ``"78.4°F"`` → ``"78.4"``).
 * Design REVIEW-19: the tile pairs ``value`` (bare reading) with
 * ``limit`` (constraint + unit); baking units into ``value`` duplicates
 * them and makes the column ragged.  Falls back to the raw string when
 * no leading number matches so we never blank a real display value.
 */
function sprayCheckValue(raw: string | null | undefined): string {
  if (!raw) return "—";
  const m = raw.match(/^[+\-]?\d+(?:\.\d+)?/);
  return m ? m[0] : raw;
}

/**
 * Preset product categories arrive as backend enum strings
 * (``fungicide_protectant``, ``insecticide_contact``, ``pgr``).  The
 * mock renders a humanised tail (``protectant`` / ``contact`` / ``pgr``);
 * strip the leading kind prefix and title-case what's left.
 */
function sprayCategoryLabel(raw: string): string {
  const tail = raw.replace(/^(fungicide|herbicide|insecticide)_/, "");
  if (!tail) return raw;
  return tail
    .split("_")
    .map((w) => (w.length <= 3 ? w.toUpperCase() : w[0].toUpperCase() + w.slice(1)))
    .join(" ");
}

/** Format a check's limit line ("≤ 10 mph", "40 – 90 °F", etc.). */
function sprayCheckLimit(name: string, product: SprayProduct | null): string {
  if (!product) return "";
  switch (name) {
    case "wind":
      return product.max_wind_mph != null ? `≤ ${product.max_wind_mph} mph` : "";
    case "temperature": {
      const lo = product.min_temp_f;
      const hi = product.max_temp_f;
      if (lo != null && hi != null) return `${lo} – ${hi} °F`;
      if (hi != null) return `≤ ${hi} °F`;
      if (lo != null) return `≥ ${lo} °F`;
      return "";
    }
    case "humidity": {
      const lo = product.min_humidity_pct;
      const hi = product.max_humidity_pct;
      if (lo != null && hi != null) return `${lo} – ${hi} %`;
      if (hi != null) return `≤ ${hi} %`;
      if (lo != null) return `≥ ${lo} %`;
      return "";
    }
    case "rain_free":
      return product.rain_free_hours != null ? `≥ ${product.rain_free_hours} h` : "";
    default:
      return "";
  }
}

/** Format an hour-of-day (0-23) as ``H:00 AM/PM`` — matches Design's
 *  ``bestWindowToday`` shape so the two window readouts read the same. */
function fmtHour12(hour: number): string {
  const h = ((hour % 24) + 24) % 24;
  const hh = h === 0 ? 12 : h > 12 ? h - 12 : h;
  const ap = h < 12 ? "AM" : "PM";
  return `${hh}:00 ${ap}`;
}

function formatScheduleWhen(dateStr: string, startTime: string): string {
  try {
    const d = new Date(`${dateStr}T${startTime}`);
    if (Number.isNaN(d.getTime())) return `${dateStr} ${startTime}`;
    return d.toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    });
  } catch {
    return `${dateStr} ${startTime}`;
  }
}

const SCHEDULE_STATUS: Record<string, "go" | "pending" | "nogo"> = {
  go: "go",
  no_go: "nogo",
  pending: "pending",
  applied: "go",
};

/** Classify a free-text weather forecast into one of three coarse bins
 *  (fair / unsettled / rain) so Zambretti and NWS sentences can be
 *  compared as agree / differ.  Order matters — "rain" wins over
 *  "unsettled" wins over "fair" ("less settled" contains both
 *  "settled" and its own negation). */
function classifyForecastText(text: string | null | undefined): 'fair' | 'unsettled' | 'rain' | null {
  if (!text) return null;
  const t = text.toLowerCase();
  if (/rain|shower|storm|thunder|drizzle/.test(t)) return 'rain';
  if (/unsettled|changeable|less settled|becoming.*(?:worse|less)/.test(t)) return 'unsettled';
  if (/fine|fair|settled|clear|sun/.test(t)) return 'fair';
  if (/cloud|overcast/.test(t)) return 'unsettled';
  return null;
}

function toDashboardData(s: AdapterSources): DashboardData {
  const cc = s.cc;
  const status = s.status;
  const astro = s.astronomy;
  const local = s.forecast?.local ?? null;
  const nwsCurrent = s.forecast?.nws?.periods?.[0] ?? null;
  const tempPts = s.historyTemp.map((p) => p.value);
  const dewPts = s.historyDew.map((p) => p.value);
  const finiteTemps = tempPts.filter((v): v is number => v != null && Number.isFinite(v));
  const avgTempF = finiteTemps.length
    ? Math.round((finiteTemps.reduce((a, b) => a + b, 0) / finiteTemps.length) * 10) / 10
    : null;

  // Suppress derived readings the backend fills in but that are meaningless at
  // the current conditions.  All three per Design REVIEW-11 ADAPTER.md:
  //   - heatIndex identical to feelsLike (the same call twice)
  //   - windChill above ~50 °F (undefined at warm temperatures)
  //   - gust below wind speed (either not wired or a stale window)
  const outsideTempF = cc?.temperature?.outside?.value ?? null;
  const feelsLikeRaw = cc?.derived?.feels_like?.value ?? null;
  const heatIndexRaw = cc?.derived?.heat_index?.value ?? null;
  const windChillRaw = cc?.derived?.wind_chill?.value ?? null;
  const heatIndexF =
    feelsLikeRaw != null && heatIndexRaw != null && Math.abs(feelsLikeRaw - heatIndexRaw) < 0.5
      ? null
      : heatIndexRaw;
  const windChillF = outsideTempF != null && outsideTempF > 50 ? null : windChillRaw;
  const speedMph = cc?.wind?.speed?.value ?? null;
  const gustRaw = cc?.wind?.gust?.value ?? null;
  const gustMph = speedMph != null && gustRaw != null && gustRaw <= speedMph ? null : gustRaw;

  return {
    units: {
      pressure: s.pressureUnit,
    },
    station: {
      // Prefer /api/station's station_name (public, no admin round-trip);
      // fall back to /api/config's city+state, then to the empty string
      // so Design's ``{d.station.name && …}`` gracefully hides the
      // separator instead of leaking undefined.
      name:
        (status as { station_name?: string } | null)?.station_name ||
        s.siteName ||
        "",
      elevationFt:
        (status as { elevation_ft?: number | null } | null)?.elevation_ft ?? null,
      intervalSeconds: status?.poll_interval ?? null,
      clock: status?.station_time ?? "",
      // 24-hour ``HH:MM`` — the persona footer prints this next to
      // the console clock, which is 24-hour too.  Two formats for
      // the same instant on a machine-provenance strip is confusing;
      // Design v48 §3.  H / L chips still use ``clock()``'s 12-hour
      // output, which is the user-facing setting.
      lastPoll: (() => {
        const iso = status?.last_poll;
        if (!iso) return "";
        const d = new Date(iso);
        return Number.isNaN(d.getTime())
          ? String(iso)
          : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
      })(),
      // Strip the ``(FW …)`` tail — the Weather Nerd + Everyday
      // footers append firmware as its own column, and a raw
      // ``Vantage Vue (FW 4.33)`` here doubles firmware to
      // ``VANTAGE VUE (FW 4.33) · 6351 · FW 4.33`` (DIFF-2b v27).
      console: (status?.type_name ?? "").replace(/\s*\(FW[^)]*\)\s*/i, "").trim(),
      model: status?.product_sku ?? "",
      firmware: status?.firmware_version ?? status?.firmware_date ?? "",
      transmittersOk:
        status?.battery?.transmitters_low != null
          ? status.battery.transmitters_low.length === 0
          : true,
      batteryVolts: status?.battery?.console_voltage ?? null,
      crcErrors: status?.crc_errors ?? 0,
      timeouts: status?.timeouts ?? 0,
      archiveRecords: status?.archive_records ?? null,
      appVersion: APP_VERSION,
    },
    outside: {
      tempF: outsideTempF,
      feelsLikeF: feelsLikeRaw,
      heatIndexF,
      windChillF,
      dewPointF: cc?.derived?.dew_point?.value ?? null,
      thetaEK: cc?.derived?.theta_e?.value ?? null,
      humidityPct: cc?.humidity?.outside?.value ?? null,
      insideTempF: cc?.temperature?.inside?.value ?? null,
      insideHumidityPct: cc?.humidity?.inside?.value ?? null,
      highF: cc?.daily_extremes?.outside_temp_hi?.value ?? null,
      highAt: clock(cc?.daily_extremes?.outside_temp_hi?.at),
      lowF: cc?.daily_extremes?.outside_temp_lo?.value ?? null,
      lowAt: clock(cc?.daily_extremes?.outside_temp_lo?.at),
    },
    barometer: {
      inHg: cc?.barometer?.value ?? null,
      hPa: cc?.barometer?.value != null ? cc.barometer.value * 33.8639 : null,
      // API doesn't currently ship trend_rate; compute it from the 24 h
      // barometer history (latest − 3 h ago).  Falls back to the raw
      // trend field if history isn't populated yet.
      trendInHgPer3h:
        cc?.barometer?.trend_rate ?? trendPer3h(s.historyBarometer),
      zone: baroZone(cc?.barometer?.value ?? null),
      todayHigh: cc?.daily_extremes?.barometer_hi?.value ?? null,
      todayHighAt: clock(cc?.daily_extremes?.barometer_hi?.at),
      todayLow: cc?.daily_extremes?.barometer_lo?.value ?? null,
      todayLowAt: clock(cc?.daily_extremes?.barometer_lo?.at),
    },
    wind: {
      speedMph,
      directionDeg: cc?.wind?.direction?.value ?? null,
      directionLabel: cc?.wind?.cardinal ?? null,
      gustMph,
      peakMph: cc?.daily_extremes?.wind_speed_hi?.value ?? null,
      peakAt: clock24(cc?.daily_extremes?.wind_speed_hi?.at),
      roseWeights: bucketWindDirection(s.windDir4h),
    },
    rain: {
      rateInPerHr: cc?.rain?.rate?.value ?? null,
      todayIn: cc?.rain?.daily?.value ?? null,
      yesterdayIn: cc?.rain?.yesterday?.value ?? null,
      yearIn: cc?.rain?.yearly?.value ?? null,
      yearSource: cc?.rain?.yearly?.source,
      hourlyIn: s.hourlyRain,
    },
    solar: {
      wm2: cc?.solar_radiation?.value ?? null,
      uvIndex: cc?.uv_index?.value ?? null,
      energyMJ: cc?.solar_energy_daily?.value ?? null,
      etIn: cc?.et_daily?.value ?? null,
    },
    forecast: {
      zambretti: local?.text ?? null,
      confidencePct: local?.confidence ?? null,
    },
    almanac: {
      sunrise: astro?.sun?.sunrise ?? null,
      sunset: astro?.sun?.sunset ?? null,
      dayLength: astro?.sun?.day_length ?? null,
      dayLengthDelta: astro?.sun?.day_change ?? null,
      moonPhase: astro?.moon?.phase ?? null,
      moonIlluminationPct: astro?.moon?.illumination ?? null,
    },
    history: {
      tempF: tempPts,
      dewPointF: dewPts,
      sampleCount: tempPts.length || null,
      avgTempF,
    },
    spray: buildSprayBlock(s.spray, cc),
    nerd: buildNerdBlock(cc, s.historyBarometer, s.historyThetaE, s.baroOffsetInHg, local, nwsCurrent, s.signalWindow, s.solar14d, s.metar, s.baroRef, s.nerdResolution),
  };
}

/**
 * Populate the Weather Nerd persona's ``nerd`` block from the same live
 * feeds the other tiles use.  Everything here is RE-EXPOSURE of an
 * existing server-side value or a client-side arithmetic on one — no
 * new backend physics.  Fields Design flagged as NEW (thetaEDelta,
 * agreementRate30d, baroVsReferenceInHg, solarEnergy14d, metar,
 * dbSizeMB, uploadTargets, ipcStatus) stay null for MVP and each tile
 * renders em-dashes rather than breaking.
 */
/** Vapour pressure e (hPa) from dew point °F, via Magnus formula. */
function vapourPressureHPa(dewPointF: number): number {
  const td = (dewPointF - 32) * (5 / 9); // → °C
  return 6.112 * Math.exp((17.67 * td) / (td + 243.5));
}

/** Mixing ratio in g/kg from dew point °F + station pressure inHg. */
function mixingRatioGKg(dewPointF: number | null, pressureInHg: number | null): number | null {
  if (dewPointF == null || pressureInHg == null) return null;
  const p_hPa = pressureInHg * 33.8639;
  const e = vapourPressureHPa(dewPointF);
  if (p_hPa <= e) return null;
  return 621.97 * (e / (p_hPa - e));
}

/** Lifted condensation level height, in feet AGL.  Espy's approximation:
 *  H(km) ≈ 0.125 × (T − Td) in °C.  Good to ~200 ft — plenty for a
 *  provenance line, and it fails safely to null when either input is null. */
function lclFt(tempF: number | null, dewPointF: number | null): number | null {
  if (tempF == null || dewPointF == null) return null;
  const t_c = (tempF - 32) * (5 / 9);
  const td_c = (dewPointF - 32) * (5 / 9);
  const h_km = 0.125 * (t_c - td_c);
  if (h_km < 0) return 0;
  return h_km * 3280.84;
}

/** Find the history point closest to the given ISO timestamp. */
function historyValueAt(points: HistoryPoint[], targetMs: number): number | null {
  if (!points.length) return null;
  let best: HistoryPoint | null = null;
  let bestDelta = Infinity;
  for (const p of points) {
    if (p.value == null) continue;
    const delta = Math.abs(Date.parse(p.timestamp) - targetMs);
    if (delta < bestDelta) {
      best = p;
      bestDelta = delta;
    }
  }
  // Guard: only trust a match within ±30 min of the target so a partial
  // history window doesn't return a wildly wrong "since 06Z" delta.
  if (!best || bestDelta > 30 * 60_000) return null;
  return best.value;
}

function buildNerdBlock(
  cc: CurrentConditions | null,
  historyBarometer: HistoryPoint[],
  historyThetaE: HistoryPoint[],
  baroOffsetInHg: number | null,
  local: LocalForecast | null,
  nwsCurrent: NWSPeriod | null,
  signalWindow: { time: number; sample: SignalQuality }[],
  solar14d: (number | null)[],
  metar: string | null,
  baroRef: { station: string; altimeterInHg: number } | null,
  nerdResolution: NerdResolution,
): DashboardData["nerd"] {
  const ex = cc?.daily_extremes ?? null;
  // Coarse-bin the Zambretti sentence and the current NWS forecast
  // text into fair / unsettled / rain; agree iff both land in the
  // same bin.  Null when either side can't be classified — the tile
  // omits the "· NWS agrees" clause rather than lying.
  const nwsAgrees = (() => {
    const zBin = classifyForecastText(local?.text ?? null);
    const nBin = classifyForecastText(nwsCurrent?.short_forecast ?? nwsCurrent?.text ?? null);
    if (!zBin || !nBin) return null;
    return zBin === nBin;
  })();
  return {
    // Pressure provenance.  Davis reports ``barometer`` as an ISA-
    // reduced-to-sea-level value already (user's configured
    // ``barometer_elevation_ft`` applied on the console), so:
    //   altimeter = the same value in inHg (that IS the altimeter
    //     setting — aviation and Davis both use ISA temperature)
    //   sea-level pressure = the same value converted to hPa.
    // Both trivial re-labelings of ``cc.barometer.value`` — no new
    // backend physics — but they satisfy the Weather Nerd provenance
    // line's intent: name each interpretation of the reading.  A
    // future PR that ingests a raw station-pressure column can
    // differentiate SLP (actual-temp) from altimeter (ISA) properly.
    altimeterInHg: cc?.barometer?.value ?? null,
    seaLevelHPa: cc?.barometer?.value != null ? cc.barometer.value * 33.8639 : null,

    // Theta-e provenance.
    //   thetaEDelta: current theta_e minus the 06Z reading from the
    //     24 h theta_e history.  Falls back to null when the history
    //     window doesn't reach 06Z yet (fresh start-of-day fetch) or
    //     the closest sample is >30 min from the target.
    //   mixingRatio: Magnus / Tetens on dew point + pressure.
    //   lcl: Espy's approximation (0.125 × T-Td, °C → km).  Both are
    //     accepted first-order formulas; good to within display noise.
    thetaEDelta: (() => {
      const now = cc?.derived?.theta_e?.value ?? null;
      if (now == null) return null;
      const sixZ = new Date();
      sixZ.setUTCHours(6, 0, 0, 0);
      // If it's before 06Z today, compare to yesterday's 06Z.
      if (Date.now() < sixZ.getTime()) sixZ.setUTCDate(sixZ.getUTCDate() - 1);
      const then = historyValueAt(historyThetaE, sixZ.getTime());
      return then != null ? now - then : null;
    })(),
    mixingRatioGKg: mixingRatioGKg(
      cc?.derived?.dew_point?.value ?? null,
      cc?.barometer?.value ?? null,
    ),
    lclFt: lclFt(
      cc?.temperature?.outside?.value ?? null,
      cc?.derived?.dew_point?.value ?? null,
    ),

    // Forecast agreement — Zambretti sentence is on d.forecast.
    // Comparing to NWS requires the NWS text-forecast fetch we don't do
    // yet; NEW work.
    nwsAgrees,
    agreementRate30d: null,

    // Reception — Davis RXCHECK's counters do NOT behave as the driver
    // docs claim ("since station midnight").  In practice the same
    // link reads 100% one poll and 80% the next, and the raw
    // ``packets_received`` walks up and down between fetches.  So:
    //  - ``pct`` is the average of the per-sample %s across the last
    //    ~1 h of client-buffered samples — noise smooths out, real
    //    dropouts still register.
    //  - the counters (received / missed / CRC / resyncs) are shown
    //    from the LATEST sample, unchanged; those are the numbers a
    //    station owner still reads to spot pathological jumps even
    //    though the total is misleading.
    // Null on empty window (persona just loaded, no successful fetch
    // yet, or anonymous / 503 / 501 for every sample so far).
    reception: (() => {
      if (!signalWindow.length) return null;
      const latest = signalWindow[signalWindow.length - 1].sample;
      const pcts: number[] = [];
      for (const { sample } of signalWindow) {
        const total = sample.packets_received + sample.missed;
        if (total > 0) pcts.push((100 * sample.packets_received) / total);
      }
      const pct = pcts.length ? pcts.reduce((a, b) => a + b, 0) / pcts.length : null;
      return {
        received: latest.packets_received,
        missed: latest.missed,
        crcErrors: latest.crc_errors,
        resyncs: latest.resync,
        pct,
        windowLabel: "last hour",
      };
    })(),

    // 24 h pressure series — same window shape as history.tempF, one
    // value per sample.  Feeds the multi-series chart's right axis.
    historyInHg: historyBarometer.map((p) => p.value),

    // Resolution echoes the state driving the chart-series fetch cycle.
    resolution: nerdResolution,

    // 14-day solar energy — one integrated value per local day from
    // ``/api/history/solar-energy`` (in the operator's preferred unit,
    // usually MJ/m²).  Oldest first; today is the last entry and is a
    // partial-day value that grows as the day progresses.
    solarEnergy14d: solar14d,

    // Console extremes — day from cc.daily_extremes, month from
    // cc.monthly_extremes, year from cc.yearly_extremes.  Backend
    // computes each from a period cutoff; null propagates as em-dash.
    extremes: ex
      ? {
          tempDayHigh: ex.outside_temp_hi?.value ?? null,
          tempDayLow: ex.outside_temp_lo?.value ?? null,
          tempMonthHigh: cc?.monthly_extremes?.outside_temp_hi?.value ?? null,
          tempMonthLow: cc?.monthly_extremes?.outside_temp_lo?.value ?? null,
          baroDayHigh: ex.barometer_hi?.value ?? null,
          baroDayLow: ex.barometer_lo?.value ?? null,
          baroYearHigh: cc?.yearly_extremes?.barometer_hi?.value ?? null,
          baroYearLow: cc?.yearly_extremes?.barometer_lo?.value ?? null,
          gustMonthMax: cc?.monthly_extremes?.wind_speed_hi?.value ?? null,
          rainYearIn: cc?.rain?.yearly?.value ?? null,
        }
      : null,

    // Calibration.  ``baroOffsetInHg`` comes from BARDATA (see the
    // persona effect); ``baroVsReferenceInHg`` is the signed delta
    // between our SLP and the nearest ICAO METAR's altimeter setting,
    // and ``referenceStation`` names that airport.  A green tone-gate
    // in the tile fires when |delta| ≤ 0.02 inHg (well-calibrated
    // console), warning otherwise.
    baroOffsetInHg,
    baroVsReferenceInHg:
      cc?.barometer?.value != null && baroRef
        ? cc.barometer.value - baroRef.altimeterInHg
        : null,
    referenceStation: baroRef?.station ?? null,

    // METAR-formatted current conditions from /api/metar, fetched
    // persona-gated.  The tile makes the block user-selectable so it
    // can be pasted into a decoder.
    metar,
    // Footer diagnostics — each is a separate fetch, deferred.
    dbSizeMB: null,
    uploadTargets: null,
    ipcStatus: null,
  };
}

/**
 * Shape the spray fetches into Design's ``DashboardData.spray`` block.
 * Every downstream field is null-tolerant so an unauthenticated visitor
 * (all spray endpoints 401 for anonymous) or a station without a
 * selected product still renders the layout with em-dashes.
 */
function buildSprayBlock(
  sp: SprayAdapterInputs | null,
  cc: CurrentConditions | null,
): DashboardData["spray"] {
  // Water fields come from ``/api/current`` (public); do not gate them
  // on the admin-only spray fetches.  Product / verdict / schedule /
  // applications DO gate on ``sp`` because they read the spray
  // endpoints — those all render em-dashes when ``sp`` is null.
  const empty: SprayAdapterInputs = {
    product: null,
    evaluation: null,
    schedules: [],
    outcomes: [],
    forecast: [],
    gustHistory: [],
  };
  const { product, evaluation, schedules, outcomes, forecast, gustHistory } = sp ?? empty;

  const verdict: "go" | "marginal" | "nogo" | null = evaluation
    ? evaluation.go
      ? "go"
      : "nogo"
    : null;

  const checks = evaluation
    ? evaluation.constraints.map((c) => ({
        name: c.name,
        label: SPRAY_CHECK_LABEL[c.name] ?? c.name,
        value: sprayCheckValue(c.current_value),
        limit: sprayCheckLimit(c.name, product),
        pass: c.passed,
      }))
    : [];

  const verdictNote =
    evaluation?.overall_detail ??
    (verdict === "go"
      ? "Conditions favour spraying now."
      : verdict === "nogo"
      ? "One or more checks fail — hold."
      : null);

  // Only upcoming rows belong under "Scheduled".  Completed /
  // cancelled rows go under Spray › Past sprays; showing them on the
  // dashboard's Scheduled section makes a stale row look like planned
  // work.  Matches the split in ``pages/Spray.tsx``.
  const upcomingSchedules = schedules.filter(
    (s) => s.status !== "completed" && s.status !== "cancelled",
  );
  const schedule = upcomingSchedules.slice(0, 4).map((s) => ({
    product: s.product_name,
    when: formatScheduleWhen(s.planned_date, s.planned_start),
    status: SCHEDULE_STATUS[s.status] ?? "pending",
  }));

  // Score the next 24 h forecast rows against this product's
  // constraints — the 24 h Spray Window strip.  Design's contract:
  // ``scoreSprayHours()`` (in utils/gauges.ts) owns the go/marginal/
  // nogo classification so the "within 1.5 mph of the limit" band
  // stays a UI tuning knob.
  const constraints: SprayConstraints | null = product
    ? {
        maxWind: product.max_wind_mph ?? 999,
        minTemp: product.min_temp_f ?? -100,
        maxTemp: product.max_temp_f ?? 200,
        minRh: product.min_humidity_pct ?? null,
        rainFreeHours: product.rain_free_hours ?? 0,
      }
    : null;
  const rainFreeHours = product?.rain_free_hours ?? 0;
  // Sort forecast rows by their absolute ``iso`` so a backend that
  // returns them out of order (or crosses midnight in a way ``hour``
  // alone can't represent) still orders correctly.  Truncate to
  // 24 rows starting at the first row with ``iso >= now`` — the
  // strip must always begin at "now", not at whatever the backend
  // decided the window opened at.  Design v49 §1.
  const scoredAll = constraints
    ? scoreSprayHours(
        forecast
          .slice()
          .sort((a, b) => (a.iso < b.iso ? -1 : a.iso > b.iso ? 1 : 0))
          .map((r, i, sortedRows) => {
            const ahead = sortedRows.slice(i, i + Math.max(1, rainFreeHours));
            const rainWithinWindow = ahead.some((row) => (row.precip ?? 0) > 0);
            return {
              at: r.iso,
              hour: r.hour,
              temp: r.temp ?? 0,
              wind: Math.max(r.wind ?? 0, r.gust ?? 0),
              rh: r.rh ?? 0,
              rainWithinWindow,
            };
          }),
        constraints,
      )
    : [];
  const nowMs = Date.now();
  const window = scoredAll
    .filter((c) => new Date(c.at).getTime() >= nowMs - 60 * 60 * 1000)
    .slice(0, 24)
    .map((c) => ({ at: c.at, hour: c.hour, label: c.label, state: c.state }));

  // Best / next windows read off ``at`` so a run that crosses
  // midnight can be named honestly ("Tomorrow 6:00 – 8:00 AM").
  // Both readouts stay in 12-hour spoken time — Design v49 §3 keeps
  // window figures as a plan a farmer reads, not a machine
  // timestamp.
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const startOfTomorrow = new Date(startOfToday.getTime() + 24 * 60 * 60 * 1000);
  const startOfDayAfter = new Date(startOfToday.getTime() + 48 * 60 * 60 * 1000);
  const dayPrefix = (atMs: number): string =>
    atMs >= startOfDayAfter.getTime()
      ? `${new Date(atMs).toLocaleDateString(undefined, { weekday: "short" })} `
      : atMs >= startOfTomorrow.getTime()
        ? "Tomorrow "
        : "";

  // Group ``window`` cells into contiguous ``go`` runs so the two
  // readouts can filter or seek by run.
  const goRuns: { start: Date; end: Date }[] = [];
  {
    let i = 0;
    while (i < window.length) {
      while (i < window.length && window[i].state !== "go") i++;
      if (i >= window.length) break;
      const start = new Date(window[i].at);
      let j = i;
      while (j + 1 < window.length && window[j + 1].state === "go") j++;
      // Run ends at the start of the hour after the last go cell.
      const end = new Date(new Date(window[j].at).getTime() + 60 * 60 * 1000);
      goRuns.push({ start, end });
      i = j + 1;
    }
  }
  const formatRun = (run: { start: Date; end: Date }): string =>
    `${dayPrefix(run.start.getTime())}${fmtHour12(run.start.getHours())} – ${fmtHour12(run.end.getHours())}`;

  // Next window is the first run whose START is in the future.  A
  // run currently open (start ≤ now < end) is described by the
  // ``caution`` line below and by ``bestWindowToday``; showing it
  // again as "Next window" would be redundant.
  const nextWindow = (() => {
    const run = goRuns.find((r) => r.start.getTime() > nowMs);
    return run ? formatRun(run) : null;
  })();

  const applications = outcomes.slice(0, 4).map((o) => ({
    product: o.product_name,
    date: o.logged_at
      ? new Date(o.logged_at).toLocaleDateString(undefined, {
          month: "short",
          day: "numeric",
        })
      : "—",
    stars: Math.max(0, Math.min(5, Math.round(o.effectiveness))),
    note: o.notes,
  }));

  const rainTodayIn = cc?.rain?.daily?.value ?? null;
  const rainWeekIn = cc?.rain?.weekly?.value ?? null;
  const etTodayIn = cc?.et_daily?.value ?? null;
  const etWeekIn = cc?.et_weekly?.value ?? null;
  const etMonthIn = cc?.et_monthly?.value ?? null;
  const etYearIn = cc?.et_yearly?.value ?? null;

  // Drift-rate kicker under Last applications (mock 3c).  Percentage
  // of past outcomes where the operator observed drift; SprayOutcome
  // stores this as a 0 / 1 bool-as-int.  Null when the log is empty
  // so the kicker collapses to just "LAST APPLICATIONS".
  const driftRatePct = outcomes.length
    ? (100 * outcomes.filter((o) => o.drift_observed).length) / outcomes.length
    : null;

  // Verdict-column caution note (mock 3c: "▲ Window closes 6:40 PM").
  // Show only when a run is currently open — start ≤ now < end.
  const caution = (() => {
    const open = goRuns.find((r) => r.start.getTime() <= nowMs && r.end.getTime() > nowMs);
    return open ? `Window closes ${fmtHour12(open.end.getHours())}` : null;
  })();

  // Product name may already contain the category ("Fungicide
  // (Protectant)") — sending both to the tile prints "Fungicide
  // (Protectant) — Protectant" per DIFF-3c.  Drop the category when
  // the humanised label already appears in the name (case-insensitive
  // substring); everything else keeps the "name — category" pattern.
  const categoryLabel = product ? sprayCategoryLabel(product.category) : null;
  const categoryRedundant =
    !!product &&
    !!categoryLabel &&
    product.name.toLowerCase().includes(categoryLabel.toLowerCase());

  // Best window today = the first go run whose START is on today's
  // date (local) AND whose END is still in the future.  If today has
  // no such run — either today's runs all closed before now, or the
  // window has no go cells at all today — say so explicitly.  A
  // window you can no longer use, printed in green at display size,
  // was the page's most confident-looking bad advice (Design v49 §1).
  const bestWindowToday = (() => {
    const today = goRuns.find(
      (r) => r.start.getTime() < startOfTomorrow.getTime() && r.end.getTime() > nowMs,
    );
    if (today) return formatRun(today);
    // ``None left today`` reserves the space so the SPRAY WINDOW
    // tile's grid doesn't reflow when the window closes for the day.
    return goRuns.some((r) => r.start.getTime() < startOfTomorrow.getTime())
      ? "None left today"
      : null;
  })();

  return {
    product: product
      ? {
          name: product.name,
          category: categoryRedundant ? null : categoryLabel,
        }
      : null,
    verdict,
    verdictNote,
    caution,
    checks,
    window,
    bestWindowToday,
    nextWindow,
    gustBins: bucketGustReadings(gustHistory),
    water: {
      // Water balance = rain - ET on a WEEKLY basis where possible;
      // today alone reads noisy on a day without rain (always negative).
      // Fall back to daily when the 7-day rollup isn't wired yet.
      balanceIn:
        rainWeekIn != null && etWeekIn != null
          ? rainWeekIn - etWeekIn
          : rainTodayIn != null && etTodayIn != null
          ? rainTodayIn - etTodayIn
          : null,
      rainTodayIn,
      rainWeekIn,
      etTodayIn,
      etWeekIn,
      etMonthIn,
      etYearIn,
      seasonRainIn: cc?.rain?.yearly?.value ?? null,
    },
    schedule,
    applications,
    driftRatePct,
  };
}

export default function Dashboard() {
  const { theme } = useTheme();
  const { persona } = usePersona();
  const { currentConditions, stationStatus } = useWeatherData();

  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [astronomy, setAstronomy] = useState<AstronomyResponse | null>(null);
  const [historyTemp, setHistoryTemp] = useState<HistoryPoint[]>([]);
  const [historyDew, setHistoryDew] = useState<HistoryPoint[]>([]);
  const [historyBarometer, setHistoryBarometer] = useState<HistoryPoint[]>([]);
  const [historyThetaE, setHistoryThetaE] = useState<HistoryPoint[]>([]);
  // 4 h of raw wind_direction readings feeds the wind-rose petals.  Window
  // matches the Weather Nerd "Wind rose · 4 h" kicker and the Agriculture
  // drift-risk 4 h shape; Everyday inherits the same weights.
  const [windDir4h, setWindDir4h] = useState<(number | null)[]>(
    () => cacheLoad<(number | null)[]>("kanfei.dashboard.windDir4h.v1") ?? [],
  );
  const [hourlyRain, setHourlyRain] = useState<(number | null)[]>(() => Array<null>(24).fill(null));
  const [siteName, setSiteName] = useState<string | null>(null);
  // User's display-unit preference for pressure — hPa or inHg.
  // Read once at startup from station_config; the barometer readouts
  // and the pressure column of the derived chart use it.
  const [pressureUnit, setPressureUnit] = useState<'inHg' | 'hPa'>(
    () => (cacheLoad<'inHg' | 'hPa'>('kanfei.dashboard.pressureUnit.v1') ?? 'inHg'),
  );
  const [spray, setSpray] = useState<SprayAdapterInputs | null>(() => cacheLoad<SprayAdapterInputs>("kanfei.dashboard.spray.v1"));
  // Weather Nerd chart resolution — persisted so the choice sticks across
  // refresh.  The window scales with the resolution so each choice returns a
  // legible number of points: Daily over 24 h is one bar, Hourly over 24 h is
  // twenty-four which is fine but wastes the visual budget.
  const [nerdResolution, setNerdResolution] = useState<NerdResolution>(
    () => (cacheLoad<NerdResolution>("kanfei.dashboard.nerdResolution.v1") ?? "5 min"),
  );

  // Every-5-min re-fetch for the slow-moving feeds.  currentConditions +
  // stationStatus already tick via the shared WeatherDataProvider.
  //
  // The chart series (temp / dew / baro / theta-e) fetch at whatever
  // resolution the Weather Nerd selector is set to; ``nerdResolution`` is a
  // dep so a selector click re-runs this immediately rather than waiting
  // for the next 5-min tick.  Wind direction and rain always fetch at a
  // rose-appropriate window regardless — they don't share the chart's
  // resolution.
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const end = new Date();
      // Window scales with resolution so each choice returns a legible number
      // of points.  Daily over 24 h is a single bar; Hourly over 24 h wastes
      // most of the visual budget on a low tick density.
      const windowHours: Record<NerdResolution, number> = {
        'Raw': 24,
        '5 min': 24,
        'Hourly': 24 * 7,
        'Daily': 24 * 30,
      };
      const apiRes: Record<NerdResolution, 'raw' | '5m' | 'hourly' | 'daily'> = {
        'Raw': 'raw',
        '5 min': '5m',
        'Hourly': 'hourly',
        'Daily': 'daily',
      };
      const start = new Date(end.getTime() - windowHours[nerdResolution] * 60 * 60_000);
      const windStart = new Date(end.getTime() - 4 * 60 * 60_000);
      const rainStart = new Date(end.getTime() - 24 * 60 * 60_000);
      const res = apiRes[nerdResolution];
      const [fc, astro, temp, dew, rain, baro, tE, wd] = await Promise.allSettled([
        fetchForecast(),
        fetchAstronomy(),
        fetchHistory("outside_temp", start.toISOString(), end.toISOString(), res),
        fetchHistory("dew_point", start.toISOString(), end.toISOString(), res),
        // Rain hovers over a fixed 24 h regardless of chart resolution — the
        // hourly-rain strip is a separate consumer with a fixed window.
        fetchHistory("rain_rate", rainStart.toISOString(), end.toISOString(), "5m"),
        fetchHistory("barometer", start.toISOString(), end.toISOString(), res),
        fetchHistory("theta_e", start.toISOString(), end.toISOString(), res),
        // Wind direction: raw over 4 h.  A 5-min average across a
        // window that swings from N to W would produce NW readings
        // that never happened — kills the rose's honesty.
        fetchHistory("wind_direction", windStart.toISOString(), end.toISOString(), "raw"),
      ]);
      if (cancelled) return;
      if (fc.status === "fulfilled") setForecast(fc.value);
      if (astro.status === "fulfilled") setAstronomy(astro.value);
      if (temp.status === "fulfilled") setHistoryTemp(temp.value.points ?? []);
      if (dew.status === "fulfilled") setHistoryDew(dew.value.points ?? []);
      if (rain.status === "fulfilled") setHourlyRain(hourlyRainInches(rain.value.points ?? []));
      if (baro.status === "fulfilled") setHistoryBarometer(baro.value.points ?? []);
      if (tE.status === "fulfilled") setHistoryThetaE(tE.value.points ?? []);
      if (wd.status === "fulfilled") {
        const dirs = (wd.value.points ?? []).map((p) => p.value);
        setWindDir4h(dirs);
        cacheSave("kanfei.dashboard.windDir4h.v1", dirs);
      }
    };
    load();
    const id = setInterval(load, 5 * 60_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [nerdResolution]);

  const handleNerdResolutionChange = useCallback((r: NerdResolution) => {
    setNerdResolution(r);
    cacheSave("kanfei.dashboard.nerdResolution.v1", r);
  }, []);

  // Site name lives in station_config; one-time fetch.  (Baro offset
  // was here too, but the ``barometer_offset_inhg`` config key doesn't
  // actually exist — the console's calibration value comes from
  // BARDATA / ``barcal_inhg`` and is fetched in the Weather Nerd
  // persona effect below.)
  useEffect(() => {
    let cancelled = false;
    fetchConfig()
      .then((items) => {
        if (cancelled) return;
        const nameItem = items.find((i) => i.key === "station_name");
        const cityItem = items.find((i) => i.key === "station_city");
        const stateItem = items.find((i) => i.key === "station_state");
        const parts: string[] = [];
        if (cityItem?.value) parts.push(String(cityItem.value));
        if (stateItem?.value) parts.push(String(stateItem.value));
        setSiteName(parts.join(", ") || (nameItem?.value ? String(nameItem.value) : null));
        // Display-unit preferences.  Barometer keeps both ``inHg``
        // and ``hPa`` on ``DashboardData.barometer``; the choice
        // controls which one leads the readout, not what we fetch.
        const pu = items.find((i) => i.key === "pressure_unit")?.value;
        if (pu === "hPa" || pu === "inHg") {
          setPressureUnit(pu);
          cacheSave("kanfei.dashboard.pressureUnit.v1", pu);
        }
      })
      .catch(() => { /* falls back to empty string / inHg default */ });
    return () => { cancelled = true; };
  }, []);
  const [baroOffsetInHg, setBaroOffsetInHg] = useState<number | null>(
    () => cacheLoad<number>("kanfei.dashboard.baroOffsetInHg.v1"),
  );
  // Closest METAR reference station + its altimeter setting, for the
  // "vs KTTA -0.012 in" row on the Weather Nerd extremes tile.
  const [baroRef, setBaroRef] = useState<
    { station: string; altimeterInHg: number } | null
  >(() => cacheLoad<{ station: string; altimeterInHg: number }>("kanfei.dashboard.baroRef.v1"));

  // Spray fetches — admin-only on the backend, so an anonymous visitor
  // 401s and ``spray`` stays null (Agriculture tiles render em-dashes).
  // Only fetched while on the Agriculture persona so private stations
  // running the other personas don't churn PUT /api/spray/evaluate on
  // the poll interval for a screen that isn't visible.
  useEffect(() => {
    // Off-persona: skip fetches, leave cached value in place so
    // switching back is instant (same treatment as Weather Nerd).
    if (persona !== "agriculture") return;
    let cancelled = false;
    const load = async () => {
      let products: SprayProduct[] = [];
      let evaluation: SprayEvaluation | null = null;
      let schedules: SpraySchedule[] = [];
      let outcomes: SprayOutcome[] = [];
      let forecastRows: SprayForecastRow[] = [];
      let gustHistory: (number | null)[] = [];
      try {
        products = await fetchSprayProducts();
      } catch {
        return; // 401 or offline; leave spray null
      }
      const product = products.find((p) => p.is_preset) ?? products[0] ?? null;
      const gustEnd = new Date();
      const gustStart = new Date(gustEnd.getTime() - 4 * 60 * 60_000);
      const [ev, sch, out, fc, gust] = await Promise.allSettled([
        product ? evaluateSprayProduct(product.id) : Promise.resolve(null),
        fetchSpraySchedules(),
        fetchSprayOutcomes(5),
        fetchSprayForecast(24),
        // The histogram is billed as "gust frequency" but we source
        // ``wind_speed`` here, not ``wind_gust``.  The Davis Vantage
        // LOOP2 ``wind_gust_10min`` field (offset 22, docs claim
        // tenths mph) on our Vue reads ~1 mph while the current
        // ``wind_speed`` at the same instant reads 11 mph — the field
        // is either broken on this hardware rev or scaled differently
        // than the manual says (see reference/vantage_dash_values.md:
        // where wire and manual conflict, wire wins).  ``wind_speed``
        // at the raw poll cadence IS the "gust events" a reader would
        // intuit from the chart; the peak matches what the Wind tile
        // reports.  See issue: kanfei-working/issues (LOOP2 wind_gust
        // investigation).
        fetchHistory("wind_speed", gustStart.toISOString(), gustEnd.toISOString(), "raw"),
      ]);
      if (cancelled) return;
      if (ev.status === "fulfilled") evaluation = ev.value;
      if (sch.status === "fulfilled") schedules = sch.value;
      if (out.status === "fulfilled") outcomes = out.value;
      if (fc.status === "fulfilled") forecastRows = fc.value.rows;
      if (gust.status === "fulfilled") gustHistory = (gust.value.points ?? []).map((p) => p.value);
      const next: SprayAdapterInputs = { product, evaluation, schedules, outcomes, forecast: forecastRows, gustHistory };
      setSpray(next);
      cacheSave("kanfei.dashboard.spray.v1", next);
    };
    load();
    const id = setInterval(load, 5 * 60_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [persona]);

  // Weather Nerd fetches — persona-gated, one 5-min cycle for all of
  // them.  Reception via ``/api/station/signal-quality`` (admin-gated,
  // briefly holds the serial lock via RXCHECK).  Solar-energy series
  // via ``/api/history/solar-energy`` (public, cheap).  Each catch
  // block leaves its slot null so the tile em-dashes cleanly.
  // Reception counters are noisy sample-to-sample — a single RXCHECK
  // doesn't behave as "since midnight" the way Davis docs claim, so
  // one refresh reads 100% and the next 80% for the same link.  We
  // buffer up to ~1 h of samples client-side (12 samples at the 5-min
  // fetch cadence) and let the adapter smooth the % across the window.
  const SIGNAL_WINDOW_MS = 60 * 60_000;
  // Hydrate from localStorage on mount so refresh doesn't flash em-dashes.
  const [signalWindow, setSignalWindow] = useState<
    { time: number; sample: SignalQuality }[]
  >(() => {
    const cached = cacheLoad<{ time: number; sample: SignalQuality }[]>("kanfei.dashboard.signalWindow.v1");
    if (!cached) return [];
    const now = Date.now();
    return cached.filter((s) => now - s.time <= SIGNAL_WINDOW_MS);
  });
  const [solar14d, setSolar14d] = useState<(number | null)[]>(
    () => cacheLoad<(number | null)[]>("kanfei.dashboard.solar14d.v1") ?? [],
  );
  const [metar, setMetar] = useState<string | null>(
    () => cacheLoad<string>("kanfei.dashboard.metar.v1"),
  );
  useEffect(() => {
    // Off-persona: skip fetches, but LEAVE state populated so switching
    // back is instant.  A subtly stale reading on re-entry is better
    // than a full em-dash-then-populate flash on every persona swap.
    if (persona !== "weather_nerd") return;
    let cancelled = false;

    // Admin fetches (signal-quality, barometer-calibration) each take
    // the serial lock briefly and compete both with the poller and
    // each other.  Serialise them and retry on 503/504 so one failed
    // sample doesn't leave the tile stuck on the previous value for
    // 5 min (or on em-dash for the first fetch cycle).  Public
    // fetches (solar, metar) run in parallel — they only touch the DB.
    const retryAdmin = async <T,>(fn: () => Promise<T>): Promise<T> => {
      const delays = [0, 700, 1500];
      let lastErr: unknown;
      for (const d of delays) {
        if (d) await new Promise((r) => setTimeout(r, d));
        try {
          return await fn();
        } catch (e) {
          lastErr = e;
          const status = (e as { status?: number })?.status;
          if (status === 401) throw e; // no point retrying auth
        }
      }
      throw lastErr;
    };

    const load = async () => {
      // ``barometer-reference`` is admin-gated (anonymous 401) but
      // doesn't touch the serial port — it calls aviationweather.gov
      // and reads the DB.  Safe to run in the public parallel group
      // alongside solar + metar.
      const [sun, met, ref] = await Promise.allSettled([
        fetchSolarEnergyHistory(14),
        fetchMetar(),
        fetchBarometerReference(),
      ]);
      if (cancelled) return;
      if (sun.status === "fulfilled") {
        const pts = sun.value.points.map((p) => p.value);
        setSolar14d(pts);
        cacheSave("kanfei.dashboard.solar14d.v1", pts);
      }
      if (met.status === "fulfilled") {
        const s = met.value.metar ?? null;
        setMetar(s);
        cacheSave("kanfei.dashboard.metar.v1", s);
      }
      if (ref.status === "fulfilled") {
        // Pick the closest usable reference (list is sorted by
        // distance); null-safe on empty / unconfigured.
        const nearest = pickNearestReference(ref.value);
        setBaroRef(nearest);
        cacheSave("kanfei.dashboard.baroRef.v1", nearest);
      }

      try {
        const s = await retryAdmin(fetchSignalQuality);
        if (cancelled) return;
        setSignalWindow((prev) => {
          const now = Date.now();
          const next = [...prev, { time: now, sample: s }];
          const trimmed = next.filter((x) => now - x.time <= SIGNAL_WINDOW_MS);
          cacheSave("kanfei.dashboard.signalWindow.v1", trimmed);
          return trimmed;
        });
      } catch { /* keep last-known, tile em-dashes only on truly empty state */ }

      try {
        const c = await retryAdmin(fetchBarometerCalibration);
        if (cancelled) return;
        // ``barcal_inhg`` from BARDATA is the user-configured barometer
        // calibration offset.  Admin-gated; anonymous 401 leaves last-
        // known value in place (tile em-dashes only if never populated).
        const off = c?.barcal_inhg ?? null;
        setBaroOffsetInHg(off);
        cacheSave("kanfei.dashboard.baroOffsetInHg.v1", off);
      } catch { /* keep last-known */ }
    };
    load();
    const id = setInterval(load, 5 * 60_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [persona]);

  const data = useMemo(
    () =>
      toDashboardData({
        cc: currentConditions,
        status: stationStatus,
        forecast,
        astronomy,
        historyTemp,
        historyDew,
        historyBarometer,
        historyThetaE,
        hourlyRain,
        windDir4h,
        siteName,
        spray,
        baroOffsetInHg,
        signalWindow,
        solar14d,
        metar,
        baroRef,
        nerdResolution,
        pressureUnit,
      }),
    [currentConditions, stationStatus, forecast, astronomy, historyTemp, historyDew, historyBarometer, historyThetaE, hourlyRain, windDir4h, siteName, spray, baroOffsetInHg, signalWindow, solar14d, metar, baroRef, nerdResolution, pressureUnit],
  );

  // Persona dispatch.  Each layout owns its plate, its scale unit, and
  // its own composition; they share primitives, tokens, and the
  // DashboardData contract.
  if (persona === "agriculture") {
    return <AgricultureDashboard d={data} themeLabel={theme.label} />;
  }
  if (persona === "weather_nerd") {
    return (
      <WeatherNerdDashboard
        d={data}
        themeLabel={theme.label}
        onResolutionChange={handleNerdResolutionChange}
      />
    );
  }
  return <EverydayDashboard d={data} themeLabel={theme.label} />;
}
