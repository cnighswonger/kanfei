/**
 * Wind rose dial — Design v35 WIND-ROSE.md.
 *
 * Dashboard-tile wind rose in ``chart.styledMode: true``: a 16-point
 * polar column with graduated-opacity petals and a live bearing
 * needle rendered on top via ``chart.events.render``.  Replaces the
 * SVG compass + rosePetals + needle rendering that lived in
 * ``utils/gauges.ts``.
 *
 * WIND-ROSE.md is explicit that the stacked speed-binned pattern
 * (16 × 5 = 80 wedges) stays as the large-size analysis variant —
 * below ~300 px it's texture, not data — and that the SVG's
 * opacity-varied petals + live needle is the right thing for the
 * three tile consumers (Everyday, Agriculture, Weather Nerd).
 *
 * The two-file split with ``WindRoseDial.css`` is the same as
 * ``WheelBarometer``: geometry here, identity in the stylesheet
 * against theme tokens.
 */

import { useMemo } from "react";
import Highcharts from "highcharts";
import "highcharts/highcharts-more";
import "highcharts/css/highcharts.css";
import "./WindRoseDial.css";
import { HighchartsReact } from "highcharts-react-official";
import { useTheme } from "../../context/ThemeContext.tsx";

interface WindRoseDialProps {
  /** 16-element histogram of wind-direction observations, N first. */
  roseWeights: number[] | undefined;
  /** Current bearing in degrees (0 = N, clockwise).  ``null`` hides
   *  the needle entirely (no vane, no reading). */
  directionDeg: number | null;
  /** Current wind speed in mph.  Below 1 mph is calm — the vane
   *  holds its last-known heading, and the needle dims but doesn't
   *  hide. */
  speedMph: number | null;
  size: number;
}

const CARDINALS = [
  "N", "NNE", "NE", "ENE",
  "E", "ESE", "SE", "SSE",
  "S", "SSW", "SW", "WSW",
  "W", "WNW", "NW", "NNW",
];

/** Petal floor: a zero-weight sector still shows a stub, so the rose
 *  reads as sixteen sectors rather than a partial fan.  Matches the
 *  SVG's 14/110 floor.  Opacity is the real signal — an empty
 *  sector's stub is nearly invisible. */
const PETAL_FLOOR = 0.14;

/** Axis max above 1 so a full-weight petal stops short of the rim
 *  (like the SVG's 100/110).  Inner ring at 0.82 lands the reference
 *  circle at ~0.75 r as the SVG had it. */
const AXIS_MAX = 1.1;
const INNER_RING = 0.82;

/** Six opacity tiers; the CSS owns the alpha ramp. */
const TIERS = 6;

/**
 * Needle path — one filled arrow: tip, two shoulders, short tail.
 * Built from the pane's own centre and radius so it can't drift
 * when ``size`` changes.  Category 0 (N) sits at the top with
 * ``pane.startAngle: 0``, so screen angle is bearing − 90°.
 */
function needlePath(cx: number, cy: number, r: number, bearingDeg: number): string {
  const a = ((bearingDeg - 90) * Math.PI) / 180;
  const p = (rad: number, off: number): [number, number] => {
    const perp = a + Math.PI / 2;
    return [
      cx + Math.cos(a) * rad + Math.cos(perp) * off,
      cy + Math.sin(a) * rad + Math.sin(perp) * off,
    ];
  };
  const [tx, ty] = p(r * 0.86, 0);
  const [lx, ly] = p(r * 0.16, -5);
  const [rx, ry] = p(r * 0.16, 5);
  const [bx, by] = p(-r * 0.12, 0);
  return `M ${tx} ${ty} L ${rx} ${ry} L ${bx} ${by} L ${lx} ${ly} Z`;
}

export default function WindRoseDial({
  roseWeights,
  directionDeg,
  speedMph,
  size,
}: WindRoseDialProps) {
  const { themeName } = useTheme();

  const options = useMemo<Highcharts.Options | null>(() => {
    if (!roseWeights || roseWeights.length === 0) return null;
    const peak = Math.max(...roseWeights, 0.0001);

    return {
      chart: {
        polar: true,
        type: "column",
        styledMode: true,
        height: size,
        width: size,
        spacing: [4, 4, 4, 4],
      },
      title: { text: undefined },
      credits: { enabled: false },
      legend: { enabled: false },
      tooltip: { enabled: false },
      exporting: { enabled: false },
      accessibility: {
        enabled: true,
        description:
          `Wind rose. Current bearing ${directionDeg ?? "unknown"} degrees, ` +
          `prevailing ${CARDINALS[roseWeights.indexOf(peak)] ?? "—"}.`,
      },
      pane: { size: "92%", startAngle: 0 },
      xAxis: {
        categories: CARDINALS,
        // ``on`` centres each petal AND each tick on its compass
        // point, rather than straddling the boundary between two.
        tickmarkPlacement: "on",
        tickInterval: 4, // majors at N / E / S / W
        minorTickInterval: 1, // minors at the other twelve
        tickLength: 10,
        minorTickLength: 6,
        tickPosition: "inside",
        minorTickPosition: "inside",
        gridLineWidth: 0, // no spokes — the SVG rose had none
        labels: {
          // Only the four cardinals get text; sixteen labels is
          // unreadable at 220 px.
          formatter: function () {
            const i = CARDINALS.indexOf(String(this.value));
            return i % 4 === 0 ? String(this.value) : "";
          },
          distance: 14,
        },
      },
      yAxis: {
        min: 0,
        max: AXIS_MAX,
        gridLineInterpolation: "polygon" as unknown as "circle",
        // Highcharts' polygon interpolation with 16 categories draws
        // as effectively a circle.  ``circle`` explicitly is not in
        // the type but is accepted at runtime; the polygon fallback
        // renders identically at 16 sides.
        tickPositions: [INNER_RING, AXIS_MAX],
        labels: { enabled: false },
        endOnTick: false,
        startOnTick: false,
        title: { text: undefined },
      },
      plotOptions: {
        column: {
          // Petals fill their full 22.5° sector and touch, as the
          // SVG wedges did.
          pointPadding: 0,
          groupPadding: 0,
          borderWidth: 0,
          animation: false,
        },
      },
      series: [{
        type: "column" as const,
        name: "Direction",
        className: "wind-rose-petals",
        enableMouseTracking: false,
        data: roseWeights.map((w) => {
          const norm = Math.max(0, Math.min(1, w / peak));
          return {
            y: PETAL_FLOOR + norm * (1 - PETAL_FLOOR),
            // colorIndex → .highcharts-color-N, which the CSS maps
            // to fill-opacity.
            colorIndex: Math.min(TIERS - 1, Math.floor(norm * TIERS)),
          };
        }),
      }],
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roseWeights, directionDeg, size, themeName]);

  // Needle overlay — rendered in ``chart.events.render`` because a
  // gauge dial can't share a chart with a polar column series.
  const optionsWithNeedle = useMemo<Highcharts.Options | null>(() => {
    if (!options) return null;
    return {
      ...options,
      chart: {
        ...options.chart,
        events: {
          render: function () {
            const chart = this as Highcharts.Chart & {
              _roseNeedle?: Highcharts.SVGElement[];
              pane?: Array<{ center: number[] }>;
            };
            if (chart._roseNeedle) {
              for (const el of chart._roseNeedle) el.destroy();
            }
            chart._roseNeedle = [];
            // No bearing at all — nothing to point.  Different from
            // calm: calm still has a heading (the last-known one).
            if (directionDeg == null) return;
            const pane = chart.pane?.[0];
            if (!pane) return;
            const [pcx, pcy, diameter] = pane.center as unknown as number[];
            const cx = chart.plotLeft + pcx;
            const cy = chart.plotTop + pcy;
            const r = diameter / 2;
            // Calm dims the needle; the readout still says a
            // heading because the vane holds its last-known one
            // when the anemometer stalls.
            const calm = (speedMph ?? 0) < 1 ? " is-calm" : "";
            chart._roseNeedle = [
              chart.renderer
                .path()
                .attr({
                  d: needlePath(cx, cy, r, directionDeg),
                  class: `wind-rose-needle${calm}`,
                  zIndex: 7,
                })
                .add(),
              chart.renderer
                .circle(cx, cy, 3.5)
                .attr({ class: `wind-rose-hub${calm}`, zIndex: 8 })
                .add(),
            ];
          },
        },
      },
    };
  }, [options, directionDeg, speedMph]);

  if (!optionsWithNeedle) {
    return (
      <div
        className="wind-rose"
        aria-hidden="true"
        style={{ width: size, height: size }}
      />
    );
  }

  return (
    <div
      className="wind-rose"
      aria-hidden="true"
      style={{ width: size, height: size }}
    >
      <HighchartsReact highcharts={Highcharts} options={optionsWithNeedle} />
    </div>
  );
}
