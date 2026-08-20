/**
 * Wheel barometer — Design v34 HIGHCHARTS.md tranche 3, styled-mode.
 *
 * Highcharts gauge in ``chart.styledMode: true``: every colour and
 * font lives in ``WheelBarometer.css`` against the theme's CSS
 * custom properties, and this file owns geometry (angles, radii,
 * ticks, dial widths).  The two-file split is the point — Design
 * can iterate on the visual identity in CSS without a code change,
 * and the paper themes' identity carries into the wheel without a
 * per-token JS bridge.
 *
 * The two spec calls Design flagged as easy to get wrong stay in
 * geometry, not style:
 *
 * - **``min: 28.5, max: 31.0`` is fixed**, NOT the day's swing.  A
 *   station's real daily variation is on the order of 0.2 inHg; a
 *   dial auto-scaled to the day would turn noise into drama.
 * - **``radius: '46%'`` on the trend dial + ``'66%'`` on the live
 *   one** — the short pale hand three hours back is what makes the
 *   dial show *movement* rather than a value.
 */

import { useMemo } from "react";
import Highcharts from "highcharts";
import "highcharts/highcharts-more";
// Highcharts' base styled-mode stylesheet ships class-name rules
// for every SVG element the library draws.  Import it once so the
// wheel picks up the neutral defaults; ``WheelBarometer.css`` then
// overrides the pieces we own.  Global import is fine — classic-
// mode consumers ignore the classes because they paint with inline
// attributes.
import "highcharts/css/highcharts.css";
import "./WheelBarometer.css";
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

export default function WheelBarometer({ inHg, trendInHgPer3h, size }: WheelBarometerProps) {
  const { themeName } = useTheme();

  const options = useMemo<Highcharts.Options | null>(() => {
    if (inHg == null || !Number.isFinite(inHg)) return null;
    const clampedNow = Math.max(MIN_INHG, Math.min(MAX_INHG, inHg));
    const trend3hAgo =
      trendInHgPer3h != null && Number.isFinite(trendInHgPer3h)
        ? Math.max(MIN_INHG, Math.min(MAX_INHG, inHg - trendInHgPer3h))
        : null;

    return {
      chart: {
        type: "gauge",
        // Styled mode: Highcharts stops emitting inline colour /
        // font attributes and every element carries a class name
        // instead.  Skinning happens in WheelBarometer.css.
        styledMode: true,
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
        // Two concentric ring backgrounds.  The CSS owns their
        // stroke + opacity; here we just declare the radii.  The
        // outer entry gets ``className: 'highcharts-pane-outer'``
        // so the stylesheet can distinguish the two.
        background: [
          {
            outerRadius: "100%",
            innerRadius: "99%",
            className: "highcharts-pane-outer",
          },
          {
            outerRadius: "78%",
            innerRadius: "77.5%",
          },
        ],
      },
      yAxis: {
        min: MIN_INHG,
        max: MAX_INHG,
        tickInterval: 0.5,
        minorTickInterval: 0.125,
        tickLength: 12,
        minorTickLength: 7,
        // Widths stay here — they're geometry.  Colours come from
        // the CSS.
        tickWidth: 1.6,
        minorTickWidth: 0.8,
        lineWidth: 0,
        labels: {
          distance: 18,
          formatter: function () {
            const v = typeof this.value === "number" ? this.value : Number(this.value);
            return v.toFixed(1);
          },
        },
        plotBands: ZONE_BANDS.map((band) => ({
          from: band.from,
          to: band.to,
          innerRadius: "55%",
          outerRadius: "62%",
          // Every band shares one class — the CSS gives them all
          // the same fill and the label text distinguishes the zones.
          className: "wheel-baro-zone",
        })),
      },
      tooltip: { enabled: false },
      series: [
        ...(trend3hAgo != null
          ? [{
              type: "gauge" as const,
              name: "trend",
              className: "wheel-baro-trend",
              data: [trend3hAgo],
              dial: {
                radius: "46%",
                baseWidth: 2,
                topWidth: 2,
                rearLength: "0%",
              },
              enableMouseTracking: false,
            }]
          : []),
        {
          type: "gauge" as const,
          name: "now",
          className: "wheel-baro-now",
          data: [clampedNow],
          dial: {
            radius: "66%",
            baseWidth: 3,
            topWidth: 1,
            rearLength: "0%",
          },
          pivot: { radius: 4 },
          enableMouseTracking: false,
        },
      ],
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inHg, trendInHgPer3h, size, themeName]);

  // Zone-name labels ride on chart.events.render — HC has no native
  // label-on-plotBand.  In styled mode the ``.css()`` call would be a
  // no-op; the label picks up its font/colour via a class on the
  // element instead (see WheelBarometer.css).
  const optionsWithLabels = useMemo<Highcharts.Options | null>(() => {
    if (!options) return null;
    return {
      ...options,
      chart: {
        ...options.chart,
        events: {
          render: function () {
            const chart = this as Highcharts.Chart & {
              _wheelBaroLabels?: Highcharts.SVGElement[];
            };
            if (chart._wheelBaroLabels) {
              for (const el of chart._wheelBaroLabels) el.destroy();
            }
            const labels: Highcharts.SVGElement[] = [];
            const cx = chart.plotLeft + chart.plotWidth / 2;
            // The gauge centres vertically with the pane at the
            // middle; 0.55 accounts for the 240° sweep leaving a
            // narrower top half than a full circle would.
            const cy = chart.plotTop + chart.plotHeight * 0.55;
            const r = Math.min(chart.plotWidth, chart.plotHeight) * 0.36;
            const sweepStart = -120;
            const sweepEnd = 120;
            for (const band of ZONE_BANDS) {
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
                  class: "wheel-baro-zone-label",
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

  // The ``wheel-barometer`` scope class is what the CSS keys on.
  return (
    <div className="wheel-barometer" style={{ width: size, height: size }}>
      <HighchartsReact highcharts={Highcharts} options={optionsWithLabels} />
    </div>
  );
}
