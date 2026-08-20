/**
 * Wheel barometer — Design v34 HIGHCHARTS.md tranche 3, styled-mode.
 *
 * Highcharts gauge in ``chart.styledMode: true``: every colour and
 * font lives in ``WheelBarometer.css`` against the theme's CSS
 * custom properties, and this file owns geometry (angles, radii,
 * ticks, dial widths, zone-ring boundaries).  The two-file split is
 * the point — Design can iterate on the visual identity in CSS
 * without a code change.
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

/**
 * Zone ring boundaries.  Ratios of the pane radius.  Stated as
 * constants so plot bands, hairline separators and the label ring
 * all read the same numbers — Design v35 DIFF-barometer-beta69.md P1.
 */
const ZONE_RING_INNER = 0.55;
const ZONE_RING_OUTER = 0.62;
const ZONE_RING_MID = (ZONE_RING_INNER + ZONE_RING_OUTER) / 2;

/**
 * Rim ring radii (fraction of pane radius).  0.967 outer + 0.887
 * inner match the SVG barometer's ``gradOuter`` / ``gradInner``
 * theme ratios so the two renderings are interchangeable.
 */
const RIM_OUTER = 0.967;
const RIM_INNER = 0.887;

/**
 * Half-width in inHg of the hairline separators between zones.
 * ~1 px at a 260 px gauge; Design's Option B: instead of five
 * contiguous same-fill bands (which read as one continuous arc),
 * four thin separators mark the four boundaries and the ring is
 * *implied* by its divisions, not by a fill.
 */
const SEPARATOR_HALFWIDTH = 0.004;

const ZONE_BANDS = [
  { from: 28.5, to: 29.0, label: "STORMY" },
  { from: 29.0, to: 29.5, label: "RAIN" },
  { from: 29.5, to: 30.0, label: "CHANGE" },
  { from: 30.0, to: 30.5, label: "FAIR" },
  { from: 30.5, to: 31.0, label: "SET FAIR" },
];

function zoneAt(value: number): string {
  for (const band of ZONE_BANDS) {
    if (value >= band.from && value < band.to) return band.label.toLowerCase();
  }
  return value >= MAX_INHG ? ZONE_BANDS[ZONE_BANDS.length - 1].label.toLowerCase() : "";
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

    return {
      chart: {
        type: "gauge",
        // Styled mode: Highcharts stops emitting inline colour /
        // font attributes and every element carries a class name.
        styledMode: true,
        spacing: [4, 4, 4, 4],
        height: size,
        width: size,
      },
      title: { text: undefined },
      credits: { enabled: false },
      // Design v35 review: gauge doesn't need the full a11y module,
      // but silently disabling it isn't defensible either.  The
      // wrapper div carries ``aria-hidden`` and the readout column
      // beside the tile is the accessible content.
      accessibility: { enabled: false },
      // Kill the export burger — Design flagged it as the highest-
      // contrast element in the tile in the beta69 review.  History
      // still exports; that's the one opt-in.
      exporting: { enabled: false },
      pane: {
        // 240° sweep opening downward — 8 o'clock to 4 o'clock
        // through 12.  Highcharts pane angles run from 12 o'clock
        // clockwise, so ``-120`` = 8 o'clock, ``120`` = 4 o'clock.
        startAngle: -120,
        endAngle: 120,
        // 92 % pane fills the available square more than HC's 85 %
        // default and gives the ticks + numerals room to breathe.
        // Design v38 DIFF-barometer-radial.md.
        size: "92%",
        // Two concentric hairline rings.  Both pane.background
        // entries render as zero-width bands; the CSS strokes them
        // with the theme's rule / grid tokens.  Design v35 P4:
        // ratios come from the theme's ``dial`` group so the SVG
        // and HC renderings stay interchangeable.
        background: [
          {
            outerRadius: `${RIM_OUTER * 100}%`,
            innerRadius: `${RIM_OUTER * 100}%`,
            className: "wheel-baro-rim-outer",
          },
          {
            outerRadius: `${RIM_INNER * 100}%`,
            innerRadius: `${RIM_INNER * 100}%`,
            className: "wheel-baro-rim-inner",
          },
        ],
      },
      yAxis: {
        min: MIN_INHG,
        max: MAX_INHG,
        tickInterval: 0.5,
        minorTickInterval: 0.125,
        // Radial budget — Design v38 DIFF-barometer-radial.md.  The
        // dial has four label / graduation / rim systems competing
        // in the same radial band; the budget lets each ring own
        // its own range without collision.  Percentages of pane
        // radius, from rim in:
        //   96.7 %  outer rim stroke
        //   88.7 → 96.7 %  graduations (majors span, minors half)
        //   88.7 %  inner rim stroke
        //   ~78 %  numerals
        //   66 → 72 %  empty ring (breathing room)
        //   58.5 %  zone-name labels
        //   0 → 66 %  needle sweep (live @ 66 %, trend @ 46 %)
        // The tick lengths below are chosen so majors stop at the
        // inner rim and minors stop half-way to the numeral ring;
        // both draw inward from the axis line at 96.7 %.
        tickLength: 10,
        minorTickLength: 5,
        tickWidth: 1.6,
        minorTickWidth: 1,
        lineWidth: 0,
        labels: {
          // Negative distance = inside the axis line.  ``-24`` lands
          // numerals near 78 % of radius on a 260 px face — inside
          // the inner rim, outside the empty ring.
          distance: -24,
          formatter: function () {
            const v = typeof this.value === "number" ? this.value : Number(this.value);
            return v.toFixed(1);
          },
        },
        tickPosition: "inside",
        minorTickPosition: "inside",
        // Hairline separators, NOT contiguous fills.  Five same-fill
        // bands read as one unbroken arc (Design v35 P0); four
        // narrow separators at the four boundaries divide the ring
        // by implication and let the ring itself stay empty.
        plotBands: ZONE_BANDS.slice(1).map((band) => ({
          from: band.from - SEPARATOR_HALFWIDTH,
          to: band.from + SEPARATOR_HALFWIDTH,
          innerRadius: `${ZONE_RING_INNER * 100}%`,
          outerRadius: `${ZONE_RING_OUTER * 100}%`,
          className: "wheel-baro-separator",
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
              // No data label on either dial — the readout column
              // beside the gauge is the value; the dial is position.
              dataLabels: { enabled: false },
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
          dataLabels: { enabled: false },
          enableMouseTracking: false,
        },
      ],
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inHg, trendInHgPer3h, size, themeName]);

  // Zone-name labels ride on chart.events.render — HC has no native
  // label-on-plotBand.  Design v35 P1: read geometry from ``pane.center``
  // + the axis's own ``startAngleRad`` / ``endAngleRad`` so a size /
  // sweep / pane change moves bands and labels together.
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
              pane?: Array<{ center: number[] }>;
            };
            if (chart._wheelBaroLabels) {
              for (const el of chart._wheelBaroLabels) el.destroy();
            }
            const pane = chart.pane?.[0];
            const axis = chart.yAxis?.[0] as Highcharts.Axis & {
              startAngleRad: number;
              endAngleRad: number;
            };
            if (!pane || !axis) {
              chart._wheelBaroLabels = [];
              return;
            }
            // pane.center is [x, y, diameter, innerDiameter] in
            // plot-area pixels.  ``startAngleRad`` already carries
            // the -90° offset (0 rad points up), so no extra rotation.
            const [pcx, pcy, diameter] = pane.center as unknown as number[];
            const cx = chart.plotLeft + pcx;
            const cy = chart.plotTop + pcy;
            const rLabel = (diameter / 2) * ZONE_RING_MID;
            const a0 = axis.startAngleRad;
            const a1 = axis.endAngleRad;
            const labels = ZONE_BANDS.map((band) => {
              const mid = (band.from + band.to) / 2;
              const t = (mid - MIN_INHG) / (MAX_INHG - MIN_INHG);
              const ang = a0 + t * (a1 - a0);
              const x = cx + Math.cos(ang) * rLabel;
              // +3 nudges the baseline to optical centre;
              // dominant-baseline is unreliable in the Highcharts
              // renderer across browsers.
              const y = cy + Math.sin(ang) * rLabel + 3;
              return chart.renderer
                .text(band.label, x, y)
                .attr({
                  "text-anchor": "middle",
                  class: "wheel-baro-zone-label",
                })
                .add();
            });
            chart._wheelBaroLabels = labels;
          },
        },
      },
    };
  }, [options]);

  if (!optionsWithLabels) {
    return (
      <div
        className="wheel-barometer"
        aria-hidden="true"
        style={{ width: size, height: size }}
      />
    );
  }

  return (
    <div
      className="wheel-barometer"
      aria-hidden="true"
      aria-label={
        inHg != null
          ? `Barometric pressure ${inHg.toFixed(2)} inches of mercury, zone ${zoneAt(inHg)}.`
          : undefined
      }
      style={{ width: size, height: size }}
    >
      <HighchartsReact highcharts={Highcharts} options={optionsWithLabels} />
    </div>
  );
}
