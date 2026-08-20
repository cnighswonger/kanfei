/**
 * History page — Design v34 HISTORY.md tranches 2a + 2b.
 *
 * One chart replacing eight.  The rail's Series list is both the
 * plot control and a live-value readout; any subset of eight series
 * can plot at once.  Pressure lands on the right yAxis with a
 * dashed stroke; every other series shares the left yAxis.  The
 * Highcharts navigator handles arbitrary-window selection (Design's
 * v35 HIGHCHARTS.md superseded the RangeStrip snippet with the
 * navigator).  CSV / PNG exports pipe through Highcharts'
 * ``exportData`` module so they follow the visible window and the
 * enabled series without a bespoke endpoint.
 */

import { Fragment, useState, useMemo, useRef, useEffect } from "react";
import Highcharts from "highcharts";
import "highcharts/modules/exporting";
import "highcharts/modules/export-data";
import { HighchartsReact } from "highcharts-react-official";
import { useMultiHistoricalData } from "../hooks/useMultiHistoricalData.ts";
import { useWeatherData } from "../context/WeatherDataContext.tsx";
import { UNIT_LABELS } from "../utils/constants.ts";
import { getHighchartsTimeConfig, resolveTimezone } from "../utils/timezone.ts";
import { useIsMobile } from "../hooks/useIsMobile.ts";

/**
 * Series definition — the eight rows in the Series rail.  ``rightAxis``
 * marks the series that lives on the pressure axis; everything else
 * shares the primary left axis (mixed units in the shared case is a
 * known limitation, accepted for tranche 2b because the default
 * temp/dew/pressure trio is Design's canonical case).
 */
interface SeriesDef {
  id: string;
  label: string;
  sensor: string;
  unit: string;
  colorVar: string;
  rightAxis?: boolean;
  live: (cc: import("../api/types.ts").CurrentConditions | null) => number | null;
}

const SERIES: SeriesDef[] = [
  {
    id: "temperature",
    label: "Temperature",
    sensor: "temperature_outside",
    unit: "F",
    colorVar: "--chart-series-temp",
    live: (cc) => cc?.temperature?.outside?.value ?? null,
  },
  {
    id: "dew_point",
    label: "Dew point",
    sensor: "dew_point",
    unit: "F",
    colorVar: "--chart-series-dew",
    live: (cc) => cc?.derived?.dew_point?.value ?? null,
  },
  {
    id: "pressure",
    label: "Pressure",
    sensor: "barometer",
    unit: "inHg",
    colorVar: "--chart-series-pressure",
    rightAxis: true,
    live: (cc) => cc?.barometer?.value ?? null,
  },
  {
    id: "humidity",
    label: "Humidity",
    sensor: "humidity_outside",
    unit: "%",
    colorVar: "--chart-series-humidity",
    live: (cc) => cc?.humidity?.outside?.value ?? null,
  },
  {
    id: "wind_speed",
    label: "Wind speed",
    sensor: "wind_speed",
    unit: "mph",
    colorVar: "--chart-series-wind",
    live: (cc) => cc?.wind?.speed?.value ?? null,
  },
  {
    id: "rain",
    label: "Rain",
    sensor: "rain_daily",
    unit: "in",
    colorVar: "--chart-series-rain",
    live: (cc) => cc?.rain?.daily?.value ?? null,
  },
  {
    id: "solar",
    label: "Solar / UV",
    sensor: "solar_radiation",
    unit: "W/m²",
    colorVar: "--chart-series-solar",
    live: (cc) => cc?.solar_radiation?.value ?? null,
  },
  {
    id: "et",
    label: "ET",
    sensor: "et_daily",
    unit: "in",
    colorVar: "--chart-series-et",
    live: (cc) => cc?.et_daily?.value ?? null,
  },
];

const DEFAULT_ACTIVE = new Set(["temperature", "dew_point", "pressure"]);

type Preset = "24h" | "7d" | "30d" | "year" | "custom";
type Resolution = "raw" | "5m" | "hourly" | "daily";

const PRESET_HOURS: Record<Exclude<Preset, "custom">, number> = {
  "24h": 24,
  "7d": 168,
  "30d": 720,
  "year": 8760,
};

function presetRange(preset: Preset): { start: string; end: string } {
  const now = new Date();
  const end = now.toISOString();
  const hours = preset === "custom" ? 24 : PRESET_HOURS[preset];
  const start = new Date(now.getTime() - hours * 3_600_000).toISOString();
  return { start, end };
}

const PRESETS: { key: Preset; label: string }[] = [
  { key: "24h", label: "24 h" },
  { key: "7d", label: "7 days" },
  { key: "30d", label: "30 days" },
  { key: "year", label: "Year" },
  { key: "custom", label: "Custom" },
];

const RESOLUTIONS: { key: Resolution; label: string }[] = [
  { key: "raw", label: "Raw" },
  { key: "5m", label: "5 min" },
  { key: "hourly", label: "Hourly" },
  { key: "daily", label: "Daily" },
];

// Compact number formatting for the rail and extremes readouts.
function fmtValue(n: number | null | undefined, unit: string): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const digits = unit === "inHg" ? 2 : unit === "%" || unit === "mph" || unit === "W/m²" ? 0 : 1;
  return `${n.toFixed(digits)} ${UNIT_LABELS[unit] ?? unit}`.trim();
}

// Find the timestamp of the earliest point matching a target value.
// The summary API returns min/max as bare numbers; the extremes table's
// ``When`` column needs a timestamp, and walking the points is cheap
// enough at the sizes we deal with (~2000 max after resolution
// bucketing).
function findTimestampAt(points: import("../api/types.ts").HistoryPoint[], target: number | null): string | null {
  if (target == null) return null;
  for (const p of points) {
    if (p.value != null && Math.abs(p.value - target) < 1e-9) return p.timestamp;
  }
  return null;
}

function fmtWhen(iso: string | null, tz: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (!Number.isFinite(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    timeZone: tz,
  });
}

export default function History() {
  const isMobile = useIsMobile();
  const { currentConditions } = useWeatherData();

  const [preset, setPreset] = useState<Preset>("24h");
  const [resolution, setResolution] = useState<Resolution>("5m");
  const [activeSet, setActiveSet] = useState<Set<string>>(new Set(DEFAULT_ACTIVE));

  const [overlayDayNight, setOverlayDayNight] = useState(false);
  const [overlayRainEvents, setOverlayRainEvents] = useState(false);
  const [overlaySameWeekLastYear, setOverlaySameWeekLastYear] = useState(false);

  const { start, end } = useMemo(() => presetRange(preset), [preset]);

  const activeSeries = useMemo(
    () => SERIES.filter((s) => activeSet.has(s.id)),
    [activeSet],
  );
  const activeSensors = useMemo(
    () => activeSeries.map((s) => s.sensor),
    [activeSeries],
  );

  const { series: fetched, loading, error } = useMultiHistoricalData(
    activeSensors,
    start,
    end,
    resolution,
  );

  const tz = resolveTimezone();
  const chartRef = useRef<HighchartsReact.RefObject>(null);

  // Total point count across every active series' returned points.
  // Feeds the rail's ``resolution`` note ("2,016 points at 5-minute
  // buckets. Raw would draw 60,480.") — an operator sees whether the
  // resolution actually shrank the payload.
  const totalPoints = useMemo(() => {
    let n = 0;
    for (const [, s] of fetched) n += s.data.length;
    return n;
  }, [fetched]);

  const chartOptions: Highcharts.Options = useMemo(() => {
    // Read the theme's chart-series colours as concrete strings.
    // ``highchartsTheme()`` is already installed via ThemeContext, so
    // the axis/grid/tooltip skinning comes from there — this block
    // only overrides the per-series colour cycle so an operator's
    // series identity matches the rail swatches.
    const readColor = (v: string): string => {
      if (typeof document === "undefined") return "";
      return getComputedStyle(document.documentElement).getPropertyValue(v).trim();
    };

    const hcSeries: Highcharts.SeriesOptionsType[] = activeSeries.map((def) => {
      const points = fetched.get(def.sensor)?.data ?? [];
      const data: [number, number | null][] = points
        .map((p) => {
          const x = new Date(p.timestamp).getTime();
          if (!Number.isFinite(x)) return null;
          const y = p.value != null && Number.isFinite(p.value) ? p.value : null;
          return [x, y] as [number, number | null];
        })
        .filter((pt): pt is [number, number | null] => pt !== null);
      const color = readColor(def.colorVar) || readColor("--chart-trace") || "#a85f24";
      return {
        type: "line" as const,
        name: def.label,
        data,
        color,
        yAxis: def.rightAxis ? 1 : 0,
        // Dashed on the right axis so a user reading the plot knows
        // which trace speaks pressure units without hunting for a
        // legend — matches the HIGHCHARTS.md guidance for right-axis
        // series.
        dashStyle: def.rightAxis ? ("Dash" as const) : ("Solid" as const),
        lineWidth: 1.8,
        marker: { enabled: false },
      };
    });

    return {
      time: getHighchartsTimeConfig(),
      chart: {
        height: isMobile ? 320 : 400,
        zooming: { type: "x" as const },
      },
      accessibility: { enabled: false },
      xAxis: { type: "datetime" as const, crosshair: true },
      yAxis: [
        {
          title: { text: undefined },
          opposite: false,
        },
        {
          title: { text: undefined },
          opposite: true,
          gridLineWidth: 0,
        },
      ],
      legend: { enabled: false },
      tooltip: {
        shared: true,
        xDateFormat: "%b %e, %Y %l:%M %p",
      },
      // Navigator: Highcharts' built-in brush.  Design's HISTORY.md v35
      // supersedes the RangeStrip snippet with this.
      navigator: {
        enabled: !isMobile,
        adaptToUpdatedData: true,
        maskFill: "rgba(154,110,43,0.14)",
        outlineColor: "var(--color-accent, #9a6e2b)",
      },
      scrollbar: { enabled: false },
      // Export module — Highcharts adds a burger menu by default; hide
      // it because Design ships CSV / PNG as explicit buttons in the
      // title row.  We call ``chart.exportChart`` / ``chart.downloadCSV``
      // from those buttons directly.
      exporting: { enabled: true, buttons: { contextButton: { enabled: false } } },
      series: hcSeries,
    };
  }, [activeSeries, fetched, isMobile]);

  // The exporting + export-data modules both extend Highcharts.Chart
  // at runtime but the typings don't merge in the ambient .d.ts,
  // so the calls go through a narrow cast.
  const handleExportPNG = () => {
    const c = chartRef.current?.chart as unknown as
      | { exportChart?: (opt: { type: string }, extra?: unknown) => void }
      | undefined;
    c?.exportChart?.({ type: "image/png" }, {});
  };
  const handleExportCSV = () => {
    const c = chartRef.current?.chart as unknown as
      | { downloadCSV?: () => void }
      | undefined;
    c?.downloadCSV?.();
  };

  // Force the chart to reflow whenever the container width changes —
  // Highcharts otherwise keeps its initial width until the window
  // resizes, so switching series or resolution can leave a chart
  // narrower than the card.
  useEffect(() => {
    chartRef.current?.chart?.reflow();
  }, [activeSensors.length, resolution, preset]);

  const toggleSeries = (id: string) => {
    setActiveSet((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // ── styles ───────────────────────────────────────────────────────

  const cardStyle: React.CSSProperties = {
    border: "0.8px solid var(--color-border)",
    background: "var(--color-bg-card, transparent)",
    padding: "18px 20px",
  };

  const sectionLabel: React.CSSProperties = {
    fontFamily: "var(--font-mono, var(--font-body))",
    fontSize: "calc(10px * var(--font-scale))",
    letterSpacing: "1.6px",
    textTransform: "uppercase",
    color: "var(--color-text-muted)",
    margin: "0 0 10px 0",
  };

  const seriesRow = (active: boolean): React.CSSProperties => ({
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "10px",
    width: "100%",
    padding: "9px 11px",
    background: "transparent",
    border: "none",
    cursor: "pointer",
    textAlign: "left",
    borderBottom: `0.8px solid var(--rule-hair, rgba(58,45,29,0.10))`,
    color: active ? "var(--color-text)" : "var(--color-text-secondary)",
  });

  const swatch = (color: string, active: boolean): React.CSSProperties => ({
    width: "10px",
    height: "10px",
    flexShrink: 0,
    background: active ? color : "transparent",
    border: active ? "none" : `1px solid var(--rule-hair, rgba(58,45,29,0.22))`,
  });

  const presetButton = (active: boolean): React.CSSProperties => ({
    fontFamily: "var(--font-body)",
    fontSize: "calc(12.5px * var(--font-scale))",
    padding: "7px 12px",
    height: "30px",
    background: active ? "var(--color-text)" : "var(--color-bg-secondary)",
    color: active ? "var(--color-bg)" : "var(--color-text)",
    border: active
      ? `0.8px solid var(--color-accent)`
      : `0.8px solid var(--rule-hair, rgba(58,45,29,0.22))`,
    cursor: "pointer",
    borderRadius: 0,
  });

  const resolutionButton = (active: boolean): React.CSSProperties => ({
    ...presetButton(active),
    padding: "6px 10px",
  });

  const chartHeaderLine = activeSeries.length === 0
    ? "No series selected"
    : activeSeries.map((s) => s.label).join(", ");

  // ── render ───────────────────────────────────────────────────────

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        flex: 1,
        minHeight: 0,
        padding: isMobile ? "12px 12px 16px" : "20px 26px 22px",
        gap: "16px",
      }}
    >
      {/* Title row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "16px",
          flexWrap: "wrap",
          padding: "0 0 12px 0",
          borderBottom: "1.6px solid var(--color-text)",
        }}
      >
        <h2
          style={{
            margin: 0,
            fontFamily: "var(--font-heading)",
            fontStyle: "italic",
            fontSize: "calc(26px * var(--font-scale))",
            color: "var(--color-text)",
          }}
        >
          History
        </h2>
        {totalPoints > 0 && (
          <span style={sectionLabel}>
            {totalPoints.toLocaleString()} records
          </span>
        )}
        <div style={{ marginLeft: "auto", display: "flex", gap: "8px", flexWrap: "wrap" }}>
          {PRESETS.map((p) => (
            <button
              key={p.key}
              type="button"
              style={presetButton(preset === p.key)}
              onClick={() => setPreset(p.key)}
            >
              {p.label}
            </button>
          ))}
          <span style={{ width: "14px" }} aria-hidden="true" />
          <button type="button" style={presetButton(false)} onClick={handleExportCSV}>CSV</button>
          <button type="button" style={presetButton(false)} onClick={handleExportPNG}>PNG</button>
        </div>
      </div>

      {/* Body: rail + chart column */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: isMobile ? "1fr" : "250px 1fr",
          gap: "20px",
          flex: 1,
          minHeight: 0,
          overflow: "auto",
          alignItems: "start",
        }}
      >
        {/* Rail column */}
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          <div>
            <div style={sectionLabel}>Series</div>
            {SERIES.map((s) => {
              const isActive = activeSet.has(s.id);
              const live = fmtValue(s.live(currentConditions), s.unit);
              return (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => toggleSeries(s.id)}
                  style={seriesRow(isActive)}
                  aria-pressed={isActive}
                >
                  <span style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0 }}>
                    <span style={swatch(`var(${s.colorVar}, var(--chart-trace, #a85f24))`, isActive)} />
                    <span style={{ fontFamily: "var(--font-body)", fontSize: "calc(13px * var(--font-scale))" }}>
                      {s.label}
                    </span>
                  </span>
                  <span
                    style={{
                      fontFamily: "var(--font-mono, var(--font-body))",
                      fontSize: "calc(12.5px * var(--font-scale))",
                      fontVariantNumeric: "tabular-nums",
                      color: isActive ? "var(--color-text)" : "var(--color-text-muted)",
                    }}
                  >
                    {live}
                  </span>
                </button>
              );
            })}
          </div>

          <div>
            <div style={sectionLabel}>Resolution</div>
            <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
              {RESOLUTIONS.map((r) => (
                <button
                  key={r.key}
                  type="button"
                  style={resolutionButton(resolution === r.key)}
                  onClick={() => setResolution(r.key)}
                >
                  {r.label}
                </button>
              ))}
            </div>
            <div
              style={{
                ...sectionLabel,
                marginTop: "8px",
                marginBottom: 0,
                textTransform: "none",
                letterSpacing: 0,
              }}
            >
              {totalPoints > 0
                ? `${totalPoints.toLocaleString()} points at ${resolution === "raw" ? "raw" : resolution} resolution.`
                : loading
                ? "Loading…"
                : "No points."}
            </div>
          </div>

          <div>
            <div style={sectionLabel}>Overlay</div>
            <label style={{ display: "flex", alignItems: "center", gap: "8px", padding: "5px 0", cursor: "pointer" }}>
              <input type="checkbox" checked={overlayDayNight} onChange={(e) => setOverlayDayNight(e.target.checked)} />
              <span style={{ fontFamily: "var(--font-body)", fontSize: "calc(13px * var(--font-scale))" }}>
                Day / night shading
              </span>
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: "8px", padding: "5px 0", cursor: "pointer" }}>
              <input type="checkbox" checked={overlayRainEvents} onChange={(e) => setOverlayRainEvents(e.target.checked)} />
              <span style={{ fontFamily: "var(--font-body)", fontSize: "calc(13px * var(--font-scale))" }}>
                Rain events
              </span>
            </label>
            <label
              style={{ display: "flex", alignItems: "center", gap: "8px", padding: "5px 0", cursor: "not-allowed", opacity: 0.55 }}
              title="Needs 12 months of archive. Available after 2027-01-01."
            >
              <input type="checkbox" checked={overlaySameWeekLastYear} onChange={(e) => setOverlaySameWeekLastYear(e.target.checked)} disabled />
              <span style={{ fontFamily: "var(--font-body)", fontSize: "calc(13px * var(--font-scale))" }}>
                Same week last year
              </span>
            </label>
          </div>
        </div>

        {/* Chart column */}
        <div style={{ display: "flex", flexDirection: "column", gap: "20px", minWidth: 0 }}>
          <div style={cardStyle}>
            <div style={{ fontFamily: "var(--font-body)", fontSize: "calc(15px * var(--font-scale))", color: "var(--color-text)", marginBottom: "8px" }}>
              {chartHeaderLine}
              <span style={{ ...sectionLabel, display: "inline", marginLeft: "12px" }}>
                {PRESETS.find((p) => p.key === preset)?.label}
              </span>
            </div>
            {loading && (
              <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: isMobile ? 320 : 400 }}>
                <div
                  style={{
                    width: "36px",
                    height: "36px",
                    border: "3px solid var(--color-border)",
                    borderTopColor: "var(--color-accent)",
                    borderRadius: "50%",
                    animation: "spin 0.8s linear infinite",
                  }}
                />
                <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
              </div>
            )}
            {error && (
              <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", height: isMobile ? 320 : 400, gap: "8px" }}>
                <span style={{ color: "var(--color-danger)" }}>Failed to load data</span>
                <span style={{ color: "var(--color-text-muted)", fontSize: "calc(13px * var(--font-scale))" }}>{error}</span>
              </div>
            )}
            {!loading && !error && activeSeries.length === 0 && (
              <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: isMobile ? 320 : 400, color: "var(--color-text-muted)" }}>
                Select one or more series from the rail.
              </div>
            )}
            {!loading && !error && activeSeries.length > 0 && (
              <HighchartsReact ref={chartRef} highcharts={Highcharts} options={chartOptions} />
            )}
          </div>

          <div style={cardStyle}>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: isMobile ? "1fr 1fr" : "231px 178px 178px 178px 178px",
                gap: "10px",
                fontFamily: "var(--font-body)",
                alignItems: "baseline",
              }}
            >
              <div style={sectionLabel}>Metric</div>
              {!isMobile && (
                <>
                  <div style={sectionLabel}>High</div>
                  <div style={sectionLabel}>When</div>
                  <div style={sectionLabel}>Low</div>
                  <div style={sectionLabel}>When</div>
                </>
              )}
              {activeSeries.map((def) => {
                const s = fetched.get(def.sensor);
                const hiTs = findTimestampAt(s?.data ?? [], s?.summary?.max ?? null);
                const loTs = findTimestampAt(s?.data ?? [], s?.summary?.min ?? null);
                return (
                  <Fragment key={def.id}>
                    <div style={{ fontSize: "calc(13px * var(--font-scale))" }}>{def.label}</div>
                    {!isMobile && (
                      <>
                        <div style={{ fontFamily: "var(--font-mono, var(--font-body))", fontVariantNumeric: "tabular-nums" }}>
                          {fmtValue(s?.summary?.max ?? null, def.unit)}
                        </div>
                        <div style={{ fontFamily: "var(--font-mono, var(--font-body))", color: "var(--color-text-muted)" }}>
                          {fmtWhen(hiTs, tz)}
                        </div>
                        <div style={{ fontFamily: "var(--font-mono, var(--font-body))", fontVariantNumeric: "tabular-nums" }}>
                          {fmtValue(s?.summary?.min ?? null, def.unit)}
                        </div>
                        <div style={{ fontFamily: "var(--font-mono, var(--font-body))", color: "var(--color-text-muted)" }}>
                          {fmtWhen(loTs, tz)}
                        </div>
                      </>
                    )}
                    {isMobile && (
                      <div style={{ fontFamily: "var(--font-mono, var(--font-body))" }}>
                        H {fmtValue(s?.summary?.max ?? null, def.unit)} · L {fmtValue(s?.summary?.min ?? null, def.unit)}
                      </div>
                    )}
                  </Fragment>
                );
              })}
              {activeSeries.length === 0 && (
                <div style={{ gridColumn: "1 / -1", color: "var(--color-text-muted)", fontSize: "calc(13px * var(--font-scale))" }}>
                  No series selected.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
