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
import { useEffect, useMemo, useState } from "react";
import EverydayDashboard from "../dashboard/EverydayDashboard.tsx";
import { AgricultureDashboard } from "../dashboard/AgricultureDashboard.tsx";
import type { DashboardData } from "../dashboard/types.ts";
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
} from "../api/client.ts";
import type {
  CurrentConditions,
  ForecastResponse,
  AstronomyResponse,
  StationStatus as StationStatusType,
  HistoryPoint,
  SprayProduct,
  SprayEvaluation,
  SpraySchedule,
  SprayOutcome,
} from "../api/types.ts";

/**
 * Theme → dashboard title-row label.  Paper themes lead the title row
 * with the theme name ("The Mammoth's Log · Sanford, NC · 412 ft");
 * non-paper themes just use the station name.  Design REVIEW-12.
 */
const THEME_LABEL: Record<string, string | undefined> = {
  glaisher: "Glaisher's Notebook",
  mammoth: "The Mammoth's Log",
};

// Package version for the footer strip ("Kanfei v1.0.0 · …").  Same
// value the backend reads from ``backend/app/VERSION``; injected at
// build time via ``define`` in vite.config.ts as ``__KANFEI_VERSION__``.
declare const __KANFEI_VERSION__: string | undefined;
const APP_VERSION =
  typeof __KANFEI_VERSION__ === "string" && __KANFEI_VERSION__ ? __KANFEI_VERSION__ : "0.1.0";

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
  hourlyRain: (number | null)[];
  siteName: string | null;
  spray: SprayAdapterInputs | null;
}

interface SprayAdapterInputs {
  product: SprayProduct | null;
  evaluation: SprayEvaluation | null;
  schedules: SpraySchedule[];
  outcomes: SprayOutcome[];
}

/** wind|temperature|humidity|rain_free → human label */
const SPRAY_CHECK_LABEL: Record<string, string> = {
  wind: "Wind",
  temperature: "Temperature",
  humidity: "Humidity",
  rain_free: "Rain-free",
};

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

function toDashboardData(s: AdapterSources): DashboardData {
  const cc = s.cc;
  const status = s.status;
  const astro = s.astronomy;
  const local = s.forecast?.local ?? null;
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
      lastPoll: clock(status?.last_poll) ?? "",
      console: status?.type_name ?? "",
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
      peakAt: clock(cc?.daily_extremes?.wind_speed_hi?.at),
    },
    rain: {
      rateInPerHr: cc?.rain?.rate?.value ?? null,
      todayIn: cc?.rain?.daily?.value ?? null,
      yesterdayIn: cc?.rain?.yesterday?.value ?? null,
      yearIn: cc?.rain?.yearly?.value ?? null,
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
  if (!sp) return undefined;
  const { product, evaluation, schedules, outcomes } = sp;

  const verdict: "go" | "marginal" | "nogo" | null = evaluation
    ? evaluation.go
      ? "go"
      : "nogo"
    : null;

  const checks = evaluation
    ? evaluation.constraints.map((c) => ({
        name: c.name,
        label: SPRAY_CHECK_LABEL[c.name] ?? c.name,
        value: c.current_value || "—",
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

  const schedule = schedules.slice(0, 4).map((s) => ({
    product: s.product_name,
    when: formatScheduleWhen(s.planned_date, s.planned_start),
    status: SCHEDULE_STATUS[s.status] ?? "pending",
  }));

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
  const etTodayIn = cc?.et_daily?.value ?? null;
  const etMonthIn = cc?.et_monthly?.value ?? null;
  const etYearIn = cc?.et_yearly?.value ?? null;

  return {
    product: product ? { name: product.name, category: product.category } : null,
    verdict,
    verdictNote,
    caution: null,
    checks,
    window: [],
    bestWindowToday: evaluation?.optimal_window
      ? `${evaluation.optimal_window.start} – ${evaluation.optimal_window.end}`
      : null,
    nextWindow: null,
    gustBins: [],
    water: {
      balanceIn:
        rainTodayIn != null && etTodayIn != null ? rainTodayIn - etTodayIn : null,
      rainTodayIn,
      rainWeekIn: null,
      etTodayIn,
      etWeekIn: null,
      etMonthIn,
      etYearIn,
      seasonRainIn: cc?.rain?.yearly?.value ?? null,
    },
    schedule,
    applications,
    driftRatePct: null,
  };
}

export default function Dashboard() {
  const { themeName } = useTheme();
  const { persona } = usePersona();
  const { currentConditions, stationStatus } = useWeatherData();

  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [astronomy, setAstronomy] = useState<AstronomyResponse | null>(null);
  const [historyTemp, setHistoryTemp] = useState<HistoryPoint[]>([]);
  const [historyDew, setHistoryDew] = useState<HistoryPoint[]>([]);
  const [historyBarometer, setHistoryBarometer] = useState<HistoryPoint[]>([]);
  const [hourlyRain, setHourlyRain] = useState<(number | null)[]>(() => Array<null>(24).fill(null));
  const [siteName, setSiteName] = useState<string | null>(null);
  const [spray, setSpray] = useState<SprayAdapterInputs | null>(null);

  // Every-5-min re-fetch for the slow-moving feeds.  currentConditions +
  // stationStatus already tick via the shared WeatherDataProvider.
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const end = new Date();
      const start = new Date(end.getTime() - 24 * 60 * 60_000);
      const [fc, astro, temp, dew, rain, baro] = await Promise.allSettled([
        fetchForecast(),
        fetchAstronomy(),
        fetchHistory("outside_temp", start.toISOString(), end.toISOString(), "5m"),
        fetchHistory("dew_point", start.toISOString(), end.toISOString(), "5m"),
        fetchHistory("rain_rate", start.toISOString(), end.toISOString(), "5m"),
        fetchHistory("barometer", start.toISOString(), end.toISOString(), "5m"),
      ]);
      if (cancelled) return;
      if (fc.status === "fulfilled") setForecast(fc.value);
      if (astro.status === "fulfilled") setAstronomy(astro.value);
      if (temp.status === "fulfilled") setHistoryTemp(temp.value.points ?? []);
      if (dew.status === "fulfilled") setHistoryDew(dew.value.points ?? []);
      if (rain.status === "fulfilled") setHourlyRain(hourlyRainInches(rain.value.points ?? []));
      if (baro.status === "fulfilled") setHistoryBarometer(baro.value.points ?? []);
    };
    load();
    const id = setInterval(load, 5 * 60_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // Site name lives in station_config; one-time fetch is fine.
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
      })
      .catch(() => { /* falls back to empty string in adapter */ });
    return () => { cancelled = true; };
  }, []);

  // Spray fetches — admin-only on the backend, so an anonymous visitor
  // 401s and ``spray`` stays null (Agriculture tiles render em-dashes).
  // Only fetched while on the Agriculture persona so private stations
  // running the other personas don't churn PUT /api/spray/evaluate on
  // the poll interval for a screen that isn't visible.
  useEffect(() => {
    if (persona !== "agriculture") {
      setSpray(null);
      return;
    }
    let cancelled = false;
    const load = async () => {
      let products: SprayProduct[] = [];
      let evaluation: SprayEvaluation | null = null;
      let schedules: SpraySchedule[] = [];
      let outcomes: SprayOutcome[] = [];
      try {
        products = await fetchSprayProducts();
      } catch {
        return; // 401 or offline; leave spray null
      }
      const product = products.find((p) => p.is_preset) ?? products[0] ?? null;
      const [ev, sch, out] = await Promise.allSettled([
        product ? evaluateSprayProduct(product.id) : Promise.resolve(null),
        fetchSpraySchedules(),
        fetchSprayOutcomes(5),
      ]);
      if (cancelled) return;
      if (ev.status === "fulfilled") evaluation = ev.value;
      if (sch.status === "fulfilled") schedules = sch.value;
      if (out.status === "fulfilled") outcomes = out.value;
      setSpray({ product, evaluation, schedules, outcomes });
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
        hourlyRain,
        siteName,
        spray,
      }),
    [currentConditions, stationStatus, forecast, astronomy, historyTemp, historyDew, historyBarometer, hourlyRain, siteName, spray],
  );

  // Persona dispatch — Weather Nerd lands as its own composition later.
  // Each layout owns its plate, its scale unit, and its own composition;
  // they share primitives, tokens, and the DashboardData contract.
  if (persona === "agriculture") {
    return <AgricultureDashboard d={data} themeLabel={THEME_LABEL[themeName]} />;
  }
  return <EverydayDashboard d={data} themeLabel={THEME_LABEL[themeName]} />;
}
