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
import type { DashboardData } from "../dashboard/types.ts";
import { useTheme } from "../context/ThemeContext.tsx";
import { usePersona } from "../context/PersonaContext.tsx";
import { useWeatherData } from "../context/WeatherDataContext.tsx";
import {
  fetchForecast,
  fetchAstronomy,
  fetchHistory,
  fetchConfig,
} from "../api/client.ts";
import type {
  CurrentConditions,
  ForecastResponse,
  AstronomyResponse,
  StationStatus as StationStatusType,
  HistoryPoint,
} from "../api/types.ts";

interface DashboardHeroConfig {
  cover?: { image: string; opacity: number; position?: string };
  corner?: { image: string; opacity: number; width: number; height: number };
}

const DASHBOARD_HERO: Record<string, DashboardHeroConfig | null> = {
  glaisher: {
    cover: { image: "/glaisher-ascent-1862.jpg", opacity: 0.12, position: "center" },
    corner: { image: "/glaisher-instruments.png", opacity: 0.1, width: 400, height: 280 },
  },
  mammoth: {
    corner: { image: "/glaisher-instruments.png", opacity: 0.09, width: 400, height: 280 },
  },
  dark: null,
  light: null,
  classic: null,
};

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
  hourlyRain: (number | null)[];
  siteName: string | null;
}

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

  return {
    station: {
      name: s.siteName ?? "",
      elevationFt: null,
      intervalSeconds: status?.poll_interval ?? null,
      clock: status?.station_time ?? "",
      lastPoll: status?.last_poll ?? "",
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
    },
    outside: {
      tempF: cc?.temperature?.outside?.value ?? null,
      feelsLikeF: cc?.derived?.feels_like?.value ?? null,
      heatIndexF: cc?.derived?.heat_index?.value ?? null,
      windChillF: cc?.derived?.wind_chill?.value ?? null,
      dewPointF: cc?.derived?.dew_point?.value ?? null,
      thetaEK: cc?.derived?.theta_e?.value ?? null,
      humidityPct: cc?.humidity?.outside?.value ?? null,
      insideTempF: cc?.temperature?.inside?.value ?? null,
      insideHumidityPct: cc?.humidity?.inside?.value ?? null,
      highF: cc?.daily_extremes?.outside_temp_hi?.value ?? null,
      highAt: cc?.daily_extremes?.outside_temp_hi?.at ?? null,
      lowF: cc?.daily_extremes?.outside_temp_lo?.value ?? null,
      lowAt: cc?.daily_extremes?.outside_temp_lo?.at ?? null,
    },
    barometer: {
      inHg: cc?.barometer?.value ?? null,
      hPa: cc?.barometer?.value != null ? cc.barometer.value * 33.8639 : null,
      trendInHgPer3h: cc?.barometer?.trend_rate ?? null,
      zone: null,
      todayHigh: cc?.daily_extremes?.barometer_hi?.value ?? null,
      todayHighAt: cc?.daily_extremes?.barometer_hi?.at ?? null,
      todayLow: cc?.daily_extremes?.barometer_lo?.value ?? null,
      todayLowAt: cc?.daily_extremes?.barometer_lo?.at ?? null,
    },
    wind: {
      speedMph: cc?.wind?.speed?.value ?? null,
      directionDeg: cc?.wind?.direction?.value ?? null,
      directionLabel: cc?.wind?.cardinal ?? null,
      gustMph: cc?.wind?.gust?.value ?? null,
      peakMph: cc?.daily_extremes?.wind_speed_hi?.value ?? null,
      peakAt: cc?.daily_extremes?.wind_speed_hi?.at ?? null,
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
  const [hourlyRain, setHourlyRain] = useState<(number | null)[]>(() => Array<null>(24).fill(null));
  const [siteName, setSiteName] = useState<string | null>(null);

  // Every-5-min re-fetch for the slow-moving feeds.  currentConditions +
  // stationStatus already tick via the shared WeatherDataProvider.
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const end = new Date();
      const start = new Date(end.getTime() - 24 * 60 * 60_000);
      const [fc, astro, temp, dew, rain] = await Promise.allSettled([
        fetchForecast(),
        fetchAstronomy(),
        fetchHistory("outside_temp", start.toISOString(), end.toISOString(), "5m"),
        fetchHistory("dew_point", start.toISOString(), end.toISOString(), "5m"),
        fetchHistory("rain_rate", start.toISOString(), end.toISOString(), "5m"),
      ]);
      if (cancelled) return;
      if (fc.status === "fulfilled") setForecast(fc.value);
      if (astro.status === "fulfilled") setAstronomy(astro.value);
      if (temp.status === "fulfilled") setHistoryTemp(temp.value.points ?? []);
      if (dew.status === "fulfilled") setHistoryDew(dew.value.points ?? []);
      if (rain.status === "fulfilled") setHourlyRain(hourlyRainInches(rain.value.points ?? []));
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

  const data = useMemo(
    () =>
      toDashboardData({
        cc: currentConditions,
        status: stationStatus,
        forecast,
        astronomy,
        historyTemp,
        historyDew,
        hourlyRain,
        siteName,
      }),
    [currentConditions, stationStatus, forecast, astronomy, historyTemp, historyDew, hourlyRain, siteName],
  );

  const hero = DASHBOARD_HERO[themeName] ?? null;
  // Agriculture + Weather Nerd land as their own compositions later.
  void persona;

  return (
    <>
      {hero?.cover && (
        <div
          aria-hidden="true"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 0,
            backgroundImage: `url(${hero.cover.image})`,
            backgroundSize: "cover",
            backgroundPosition: hero.cover.position ?? "center",
            backgroundRepeat: "no-repeat",
            opacity: hero.cover.opacity,
            pointerEvents: "none",
          }}
        />
      )}
      {hero?.corner && (
        <div
          aria-hidden="true"
          style={{
            position: "fixed",
            right: 0,
            bottom: 0,
            width: `min(${hero.corner.width}px, 100vw)`,
            aspectRatio: `${hero.corner.width} / ${hero.corner.height}`,
            maxHeight: `${hero.corner.height}px`,
            zIndex: 0,
            backgroundImage: `url(${hero.corner.image})`,
            backgroundSize: "contain",
            backgroundPosition: "right bottom",
            backgroundRepeat: "no-repeat",
            opacity: hero.corner.opacity,
            pointerEvents: "none",
          }}
        />
      )}
      <EverydayDashboard d={data} />
    </>
  );
}
