/**
 * History page — Design v34 HISTORY.md tranche 2a.
 *
 * The visual frame Design specced: a 250 px control rail on the left,
 * chart + extremes cards on the right, and a title row that carries
 * the preset buttons + CSV/PNG exports.  The rail's series list
 * doubles as a live readout — each row shows the current value even
 * when the series isn't plotted.
 *
 * Scope kept small this round (2a): the chart still plots one sensor
 * at a time (single-select radio behaviour under the multi-toggle
 * visual affordance).  Tranche 2b lands the multi-series dual-axis
 * chart, the Highcharts navigator (replacing Design's RangeStrip
 * snippet), the resolution-selector wiring (fixes the 8,125-points-
 * for-a-288-point-view bug), CSV/PNG via exportData, and the
 * ``Same week last year`` gate on data availability.
 */

import { useState, useMemo } from "react";
import Highcharts from "highcharts";
import { HighchartsReact } from "highcharts-react-official";
import { useHistoricalData } from "../hooks/useHistoricalData.ts";
import { useWeatherData } from "../context/WeatherDataContext.tsx";
import { UNIT_LABELS } from "../utils/constants.ts";
import { getHighchartsTimeConfig, resolveTimezone } from "../utils/timezone.ts";
import { computeYAxisScale } from "../utils/chartScaling.ts";
import { useIsMobile } from "../hooks/useIsMobile.ts";

/**
 * Series definition — the eight rows in the Series rail.  Each entry
 * says how to plot the series (``sensor`` key for
 * ``useHistoricalData``, ``unit`` for axis / tooltip suffix) and how
 * to pull its live value out of ``currentConditions`` for the rail
 * readout.  Colours are the theme's ``--chart-series-*`` tokens.
 */
interface SeriesDef {
  id: string;
  label: string;
  sensor: string;
  unit: string;
  color: string;
  /** Reads the current live value from CurrentConditions for the rail. */
  live: (cc: import("../api/types.ts").CurrentConditions | null) => number | null;
}

const SERIES: SeriesDef[] = [
  {
    id: "temperature",
    label: "Temperature",
    sensor: "temperature_outside",
    unit: "F",
    color: "var(--chart-series-temp, #4c8dff)",
    live: (cc) => cc?.temperature?.outside?.value ?? null,
  },
  {
    id: "dew_point",
    label: "Dew point",
    sensor: "dew_point",
    unit: "F",
    color: "var(--chart-series-dew, #5ec9a7)",
    live: (cc) => cc?.derived?.dew_point?.value ?? null,
  },
  {
    id: "pressure",
    label: "Pressure",
    sensor: "barometer",
    unit: "inHg",
    color: "var(--chart-series-pressure, #f5c451)",
    live: (cc) => cc?.barometer?.value ?? null,
  },
  {
    id: "humidity",
    label: "Humidity",
    sensor: "humidity_outside",
    unit: "%",
    color: "var(--chart-series-humidity, #b28dff)",
    live: (cc) => cc?.humidity?.outside?.value ?? null,
  },
  {
    id: "wind_speed",
    label: "Wind speed",
    sensor: "wind_speed",
    unit: "mph",
    color: "var(--chart-series-wind, #ff7a6b)",
    live: (cc) => cc?.wind?.speed?.value ?? null,
  },
  {
    id: "rain",
    label: "Rain",
    sensor: "rain_daily",
    unit: "in",
    color: "var(--chart-series-rain, #3ddc84)",
    live: (cc) => cc?.rain?.daily?.value ?? null,
  },
  {
    id: "solar",
    label: "Solar / UV",
    sensor: "solar_radiation",
    unit: "W/m²",
    color: "var(--chart-series-solar, #f0a020)",
    live: (cc) => cc?.solar_radiation?.value ?? null,
  },
  {
    id: "et",
    label: "ET",
    sensor: "et_daily",
    unit: "in",
    color: "var(--chart-series-et, #a0a0a0)",
    live: (cc) => cc?.et_daily?.value ?? null,
  },
];

// DEFAULT_ACTIVE lands in tranche 2b when the rail switches from
// single-select to a Set<string> — the three default-on series
// (``temperature``, ``dew_point``, ``pressure``) will populate the
// chart on first mount.

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

// Compact number formatting for the rail's live-value readout.  Long
// integers (rain-yearly counts, solar radiation) get 0 decimals; the
// rest get 1 or 2 depending on unit convention (pressure runs to 2).
function fmtValue(n: number | null, unit: string): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const digits = unit === "inHg" ? 2 : unit === "%" || unit === "mph" || unit === "W/m²" ? 0 : 1;
  return `${n.toFixed(digits)} ${UNIT_LABELS[unit] ?? unit}`.trim();
}

export default function History() {
  const isMobile = useIsMobile();
  const { currentConditions } = useWeatherData();

  const [preset, setPreset] = useState<Preset>("24h");
  const [resolution, setResolution] = useState<Resolution>("5m");
  // Phase 2a: rail is single-select under the multi-toggle affordance.
  // Phase 2b flips this to a ``Set<string>`` and drives a dual-axis
  // multi-series chart; the initial value stays ``temperature`` so
  // the same code path handles first-load without special-casing.
  const [activeSeries, setActiveSeries] = useState<string>("temperature");

  // Overlay checkboxes are visual scaffolding this round — the state
  // is held so Phase 2b can wire it to the chart without changing the
  // component shape.
  const [overlayDayNight, setOverlayDayNight] = useState(false);
  const [overlayRainEvents, setOverlayRainEvents] = useState(false);
  const [overlaySameWeekLastYear, setOverlaySameWeekLastYear] = useState(false);

  const { start, end } = useMemo(() => presetRange(preset), [preset]);

  const activeSeriesDef = SERIES.find((s) => s.id === activeSeries) ?? SERIES[0];
  const { data, summary, loading, error } = useHistoricalData(
    activeSeriesDef.sensor,
    start,
    end,
    resolution,
  );

  const tz = resolveTimezone();

  const chartOptions: Highcharts.Options = useMemo(() => {
    const seriesData: [number, number | null][] = data
      .map((p) => {
        const x = new Date(p.timestamp).getTime();
        if (!Number.isFinite(x)) return null;
        const y = p.value != null && Number.isFinite(p.value) ? p.value : null;
        return [x, y] as [number, number | null];
      })
      .filter((pt): pt is [number, number | null] => pt !== null);

    const yValues: number[] = [];
    if (summary?.min != null) yValues.push(summary.min);
    if (summary?.max != null) yValues.push(summary.max);
    if (yValues.length === 0) {
      for (const [, y] of seriesData) if (y != null && Number.isFinite(y)) yValues.push(y);
    }
    const yScale = computeYAxisScale(activeSeriesDef.sensor, yValues);
    const unitLabel = UNIT_LABELS[activeSeriesDef.unit] ?? ` ${activeSeriesDef.unit}`;

    return {
      time: getHighchartsTimeConfig(),
      chart: {
        type: "areaspline",
        height: isMobile ? 280 : 400,
        zooming: { type: "x" },
        ...(isMobile ? { spacing: [8, 4, 8, 4] } : {}),
      },
      accessibility: { enabled: false },
      xAxis: { type: "datetime", crosshair: true },
      yAxis: {
        title: isMobile ? { text: undefined } : { text: activeSeriesDef.label },
        softMin: yScale.softMin,
        softMax: yScale.softMax,
        ...(yScale.tickInterval != null && { tickInterval: yScale.tickInterval }),
      },
      tooltip: {
        shared: true,
        valueSuffix: unitLabel,
        xDateFormat: "%b %e, %Y %l:%M %p",
      },
      plotOptions: {
        areaspline: {
          fillOpacity: 0.15,
          lineWidth: 2,
          marker: { enabled: false, radius: 3 },
          states: { hover: { lineWidth: 3 } },
          threshold: null,
        },
      },
      series: [
        {
          type: "areaspline" as const,
          name: activeSeriesDef.label,
          data: seriesData,
          // Series colour comes from the ``chart-series-*`` token via a
          // getComputedStyle read (avoids the ``var()``-into-Highcharts
          // pitfall from HIGHCHARTS.md).  Fall back to the theme's
          // trace token, which is always concrete.
          color: (typeof document !== "undefined"
            ? getComputedStyle(document.documentElement).getPropertyValue(
                `--chart-series-${activeSeriesDef.id === "temperature" ? "temp" : activeSeriesDef.id}`,
              ).trim()
            : "") || getComputedStyle(document.documentElement).getPropertyValue("--chart-trace").trim() || "#a85f24",
        },
      ],
    };
  }, [data, summary, activeSeriesDef, tz, isMobile]);

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
    border: active ? "none" : `1px solid var(--rule-hair, rgba(58,45,29,0.20))`,
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

  const exportLink = (): React.CSSProperties => ({
    ...presetButton(false),
    textDecoration: "none",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
  });

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
        {summary?.count != null && (
          <span style={sectionLabel}>
            {summary.count.toLocaleString()} records
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
          <a
            href={`/api/export?sensors=${encodeURIComponent(activeSeriesDef.sensor)}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&resolution=${encodeURIComponent(resolution)}`}
            download
            style={exportLink()}
          >
            CSV
          </a>
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
          {/* Series block — borderless.  Rail rows double as a live
              readout: every series shows its current value even when
              the row isn't the selected plot (tranche 2b flips this
              from single-select to multi-toggle). */}
          <div>
            <div style={sectionLabel}>Series</div>
            {SERIES.map((s) => {
              const isActive = s.id === activeSeries;
              const live = fmtValue(s.live(currentConditions), s.unit);
              return (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setActiveSeries(s.id)}
                  style={seriesRow(isActive)}
                >
                  <span
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      minWidth: 0,
                    }}
                  >
                    <span style={swatch(s.color, isActive)} />
                    <span
                      style={{
                        fontFamily: "var(--font-body)",
                        fontSize: "calc(13px * var(--font-scale))",
                      }}
                    >
                      {s.label}
                    </span>
                  </span>
                  <span
                    style={{
                      fontFamily: "var(--font-mono, var(--font-body))",
                      fontSize: "calc(12.5px * var(--font-scale))",
                      fontVariantNumeric: "tabular-nums",
                      color: isActive
                        ? "var(--color-text)"
                        : "var(--color-text-muted)",
                    }}
                  >
                    {live}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Resolution block — borderless. */}
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
              {summary?.count != null
                ? `${summary.count.toLocaleString()} points at ${resolution === "raw" ? "raw" : resolution} resolution.`
                : "Loading…"}
            </div>
          </div>

          {/* Overlay block — borderless.  Checkboxes hold state for
              Phase 2b; Same-week-last-year is disabled with reason
              until the archive spans 12 months. */}
          <div>
            <div style={sectionLabel}>Overlay</div>
            <label style={{ display: "flex", alignItems: "center", gap: "8px", padding: "5px 0", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={overlayDayNight}
                onChange={(e) => setOverlayDayNight(e.target.checked)}
              />
              <span style={{ fontFamily: "var(--font-body)", fontSize: "calc(13px * var(--font-scale))" }}>
                Day / night shading
              </span>
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: "8px", padding: "5px 0", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={overlayRainEvents}
                onChange={(e) => setOverlayRainEvents(e.target.checked)}
              />
              <span style={{ fontFamily: "var(--font-body)", fontSize: "calc(13px * var(--font-scale))" }}>
                Rain events
              </span>
            </label>
            <label
              style={{ display: "flex", alignItems: "center", gap: "8px", padding: "5px 0", cursor: "not-allowed", opacity: 0.55 }}
              title="Needs 12 months of archive. Available after 2027-01-01."
            >
              <input
                type="checkbox"
                checked={overlaySameWeekLastYear}
                onChange={(e) => setOverlaySameWeekLastYear(e.target.checked)}
                disabled
              />
              <span style={{ fontFamily: "var(--font-body)", fontSize: "calc(13px * var(--font-scale))" }}>
                Same week last year
              </span>
            </label>
          </div>
        </div>

        {/* Chart column: chart + extremes cards.  Range strip is
            deferred to tranche 2b (Highcharts navigator, not the
            RangeStrip snippet). */}
        <div style={{ display: "flex", flexDirection: "column", gap: "20px", minWidth: 0 }}>
          <div style={cardStyle}>
            <div style={{ fontFamily: "var(--font-body)", fontSize: "calc(15px * var(--font-scale))", color: "var(--color-text)", marginBottom: "8px" }}>
              {activeSeriesDef.label}
              <span style={{ ...sectionLabel, display: "inline", marginLeft: "12px" }}>
                {PRESETS.find((p) => p.key === preset)?.label}
              </span>
            </div>
            {loading && (
              <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: isMobile ? 280 : 400 }}>
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
              <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", height: isMobile ? 280 : 400, gap: "8px" }}>
                <span style={{ color: "var(--color-danger)" }}>Failed to load data</span>
                <span style={{ color: "var(--color-text-muted)", fontSize: "calc(13px * var(--font-scale))" }}>{error}</span>
              </div>
            )}
            {!loading && !error && data.length === 0 && (
              <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: isMobile ? 280 : 400, color: "var(--color-text-muted)" }}>
                No data available for the selected range.
              </div>
            )}
            {!loading && !error && data.length > 0 && (
              <HighchartsReact highcharts={Highcharts} options={chartOptions} />
            )}
          </div>

          {/* Extremes card.  Phase 2a shows the summary's high/low for
              the selected series only — Phase 2b lets multi-series
              enabled state drive one row per active series. */}
          <div style={cardStyle}>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: isMobile ? "1fr 1fr" : "231px 178px 178px 178px 178px",
                gap: "10px",
                fontFamily: "var(--font-body)",
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
              <div style={{ fontSize: "calc(13px * var(--font-scale))" }}>
                {activeSeriesDef.label}
              </div>
              {!isMobile && (
                <>
                  <div style={{ fontFamily: "var(--font-mono, var(--font-body))", fontVariantNumeric: "tabular-nums" }}>
                    {summary?.max != null ? fmtValue(summary.max, activeSeriesDef.unit) : "—"}
                  </div>
                  <div style={{ fontFamily: "var(--font-mono, var(--font-body))", color: "var(--color-text-muted)" }}>
                    —
                  </div>
                  <div style={{ fontFamily: "var(--font-mono, var(--font-body))", fontVariantNumeric: "tabular-nums" }}>
                    {summary?.min != null ? fmtValue(summary.min, activeSeriesDef.unit) : "—"}
                  </div>
                  <div style={{ fontFamily: "var(--font-mono, var(--font-body))", color: "var(--color-text-muted)" }}>
                    —
                  </div>
                </>
              )}
              {isMobile && (
                <div style={{ fontFamily: "var(--font-mono, var(--font-body))" }}>
                  {summary?.max != null ? `H ${fmtValue(summary.max, activeSeriesDef.unit)}` : "—"}
                  {" · "}
                  {summary?.min != null ? `L ${fmtValue(summary.min, activeSeriesDef.unit)}` : "—"}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
