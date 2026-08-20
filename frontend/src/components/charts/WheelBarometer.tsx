/**
 * Wheel barometer — Design v34 HIGHCHARTS.md tranche 3.
 *
 * Highcharts gauge replacement for ``utils/gauges.ts:wheelDial``.  A
 * 240° sweep opens downward from 8 o'clock to 4 o'clock through the
 * top, showing barometric pressure over a fixed 28.5–31.0 inHg range
 * with plotBand zones (STORMY / RAIN / CHANGE / FAIR / SET FAIR) and
 * two dials: a pale trend hand for the value three hours ago and an
 * accent live needle for the current reading.
 *
 * Both design decisions the spec calls out as easy to get wrong:
 *
 * - **``min: 28.5, max: 31.0`` is fixed**, NOT the day's swing.  A
 *   station's real daily variation is on the order of 0.2 inHg; a
 *   dial auto-scaled to the day would turn noise into drama.  The
 *   fixed meteorological range is what makes needle position
 *   meaningful.
 * - **``radius: '46%'`` on the trend dial + ``'66%'`` on the live
 *   one** — the pale short hand three hours back is what makes the
 *   dial show *movement* rather than a value.
 */

import { useMemo } from "react";
import Highcharts from "highcharts";
import "highcharts/highcharts-more";
import { HighchartsReact } from "highcharts-react-official";
import { useTheme } from "../../context/ThemeContext.tsx";

interface WheelBarometerProps {
  /** Current pressure in inHg. */
  inHg: number | null;
  /** Trend in inHg per 3 h.  Used to derive the trend-dial value
   *  (three-hours-ago = now − trend); ``null`` hides the trend dial. */
  trendInHgPer3h: number | null;
  size: number;
}

/** Fixed meteorological range — HIGHCHARTS.md decision, not defaults. */
const MIN_INHG = 28.5;
const MAX_INHG = 31.0;

const ZONE_BANDS = [
  { from: 28.5, to: 29.0, label: "STORMY" },
  { from: 29.0, to: 29.5, label: "RAIN" },
  { from: 29.5, to: 30.0, label: "CHANGE" },
  { from: 30.0, to: 30.5, label: "FAIR" },
  { from: 30.5, to: 31.0, label: "SET FAIR" },
];

function readToken(name: string, fallback: string): string {
  if (typeof document === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

export default function WheelBarometer({ inHg, trendInHgPer3h, size }: WheelBarometerProps) {
  const { themeName } = useTheme();

  const options = useMemo<Highcharts.Options | null>(() => {
    if (inHg == null || !Number.isFinite(inHg)) return null;
    const clampedNow = Math.max(MIN_INHG, Math.min(MAX_INHG, inHg));
    const trend3hAgo =
      trendInHgPer3h != null && Number.isFinite(trendInHgPer3h)
        ? Math.max(MIN_INHG, Math.min(MAX_INHG, inHg - trendInHgPer3h))
        : null;

    const ink = readToken("--color-text", "#3a2d1d");
    const inkSoft = readToken("--color-text-secondary", "rgba(58,45,29,0.84)");
    const accent = readToken("--color-accent", "#a85f24");
    const surface = readToken("--chart-surface", "#dccfa9");
    const gridMinor = readToken("--chart-grid-minor", "rgba(58,45,29,0.10)");

    return {
      chart: {
        type: "gauge",
        backgroundColor: "transparent",
        // Room for the zone labels that sit outside the tick ring.
        spacing: [4, 4, 4, 4],
        height: size,
        width: size,
      },
      title: { text: undefined },
      credits: { enabled: false },
      accessibility: { enabled: false },
      pane: {
        // 240° sweep opening downward — 8 o'clock to 4 o'clock
        // through 12.  Highcharts pane angles run from 12 o'clock
        // clockwise, so ``-120`` = 8 o'clock, ``120`` = 4 o'clock.
        startAngle: -120,
        endAngle: 120,
        background: [{ backgroundColor: "transparent", borderWidth: 0 }],
      },
      yAxis: {
        min: MIN_INHG,
        max: MAX_INHG,
        tickInterval: 0.5,
        minorTickInterval: 0.125,
        tickLength: 12,
        minorTickLength: 7,
        tickWidth: 1.6,
        minorTickWidth: 0.8,
        tickColor: ink,
        minorTickColor: inkSoft,
        lineWidth: 0,
        labels: {
          distance: 18,
          style: {
            color: inkSoft,
            fontFamily: readToken("--type-mono-family", "'JetBrains Mono', monospace"),
            fontSize: "11px",
          },
          formatter: function () {
            const v = typeof this.value === "number" ? this.value : Number(this.value);
            return v.toFixed(1);
          },
        },
        // Zone bands sit as an inner ring at ~57 % radius.  Colours
        // stay in the theme's palette — every band picks up the same
        // ``chart-surface`` fill; the label text is what identifies
        // each zone, not a colour code (Design v34 spec).
        plotBands: ZONE_BANDS.map((band) => ({
          from: band.from,
          to: band.to,
          color: gridMinor,
          innerRadius: "55%",
          outerRadius: "62%",
        })),
      },
      tooltip: { enabled: false },
      series: [
        // Trend hand three hours back — the short pale dial.  Its
        // whole job is to make the live needle read as *moving*
        // rather than as an absolute value.  Hidden entirely when
        // trend is unavailable.
        ...(trend3hAgo != null
          ? [{
              type: "gauge" as const,
              name: "trend",
              data: [trend3hAgo],
              dial: {
                radius: "46%",
                backgroundColor: inkSoft,
                baseWidth: 2,
                topWidth: 2,
                rearLength: "0%",
              },
              pivot: { radius: 0 },
              enableMouseTracking: false,
            }]
          : []),
        {
          type: "gauge" as const,
          name: "now",
          data: [clampedNow],
          dial: {
            radius: "66%",
            backgroundColor: accent,
            baseWidth: 3,
            topWidth: 1,
            rearLength: "0%",
          },
          pivot: {
            radius: 4,
            backgroundColor: accent,
            borderColor: surface,
            borderWidth: 1,
          },
          enableMouseTracking: false,
        },
      ],
      // Zone name labels ride on chart.events.render — HC has no
      // native label-on-plotBand.  Positioned at the mid-angle of
      // each band on an inner ring so they read as scale, not chrome.
      // Recomputed on every render so a resize or theme change lands
      // labels correctly.
      chart_render: undefined, // (docstring anchor; real handler below)
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inHg, trendInHgPer3h, size, themeName]);

  // Attach the zone-label renderer via chart.events.render.  Kept in
  // an effect-free useMemo so React doesn't recreate the callback per
  // paint and Highcharts doesn't re-bind it.
  const optionsWithLabels = useMemo<Highcharts.Options | null>(() => {
    if (!options) return null;
    const inkFaint = readToken("--color-text-muted", "rgba(58,45,29,0.62)");
    const mono = readToken("--type-mono-family", "'JetBrains Mono', monospace");
    return {
      ...options,
      chart: {
        ...options.chart,
        events: {
          render: function () {
            const chart = this as Highcharts.Chart & {
              _wheelBaroLabels?: Highcharts.SVGElement[];
            };
            // Clean up any prior labels from a previous render so we
            // don't stack copies on resize / rescale.
            if (chart._wheelBaroLabels) {
              for (const el of chart._wheelBaroLabels) el.destroy();
            }
            const labels: Highcharts.SVGElement[] = [];
            const cx = chart.plotLeft + chart.plotWidth / 2;
            // Pane bottom sits below the plot centre — Highcharts
            // draws the gauge centred vertically with the pane at
            // the middle.  Approximate the geometric centre as
            // (plotLeft + plotWidth/2, plotTop + plotHeight * 0.55)
            // — the 0.55 accounts for the 240° sweep leaving a
            // narrower top half than a full circle would.
            const cy = chart.plotTop + chart.plotHeight * 0.55;
            const r = Math.min(chart.plotWidth, chart.plotHeight) * 0.36;
            const sweepStart = -120;
            const sweepEnd = 120;
            for (const band of ZONE_BANDS) {
              // Value → angle mapping across the -120..120 sweep.
              const mid = (band.from + band.to) / 2;
              const t = (mid - MIN_INHG) / (MAX_INHG - MIN_INHG);
              const angleDeg = sweepStart + t * (sweepEnd - sweepStart);
              const angleRad = (angleDeg - 90) * Math.PI / 180;
              const x = cx + Math.cos(angleRad) * r;
              const y = cy + Math.sin(angleRad) * r;
              const label = chart.renderer
                .text(band.label, x, y)
                .attr({
                  "text-anchor": "middle",
                  "dominant-baseline": "middle",
                })
                .css({
                  color: inkFaint,
                  fontFamily: mono,
                  fontSize: "8px",
                  letterSpacing: "1.4px",
                })
                .add();
              labels.push(label);
            }
            chart._wheelBaroLabels = labels;
          },
        },
      },
    };
  }, [options]);

  if (!optionsWithLabels) {
    return (
      <div style={{ width: size, height: size }} aria-hidden="true" />
    );
  }

  return (
    <div style={{ width: size, height: size }}>
      <HighchartsReact highcharts={Highcharts} options={optionsWithLabels} />
    </div>
  );
}
