/**
 * Wheel barometer — Design v43 (14a).
 *
 * One label system on the plate: three numerals in the pockets the
 * sweep cannot reach (28.5 / 30.0 / 31.0).  Zone words moved off
 * the plate and into a separate strip beneath (see
 * ``BarometerZoneStrip`` in the tile).  One copper arc over the
 * currently-active zone replaces the old zone annulus + word ring.
 *
 * The ordering rule that v39–v42 kept missing:
 * **needle tip < numeral inner bound.**  Labels sit outboard of
 * the sweep; the pointer never strikes them.  Enforced here as
 * ``RING.needle < RING.numeralInner``.
 *
 * All geometry in fractions of the pane radius R (which equals the
 * chart's radius since pane.size = 100 %) so the same table holds at
 * any size.
 */

import { useEffect, useMemo, useRef, useState } from "react";
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
  /** Initial drawing precision in viewBox units (Design v43 step 6).
   *  Physical size comes from the parent — the instrument fills its
   *  container and a ``ResizeObserver`` re-renders HC when the
   *  container's actual pixel size changes.  ``size`` is used only as
   *  the first-render seed before the observer fires. */
  size: number;
}

/** Fixed meteorological range — HIGHCHARTS.md decision, not defaults. */
const MIN_INHG = 28.5;
const MAX_INHG = 31.0;

/**
 * Radial geometry, as fractions of the pane radius R.  Design v43
 * DIFF-barometer-v43.md.  Ordered outside-in; the invariant that
 * matters across every render is ``needle < numeralInner`` —
 * numerals sit outboard of the sweep so the pointer cannot strike
 * them.  Values pulled directly from Design's measurable mock
 * (baro-14a.html); do not tune individually.
 */
const RING = {
  rim: 0.962,            // hairline circle, weight-bearing edge
  numeralCenter: 0.820,  // label anchor radius — mock's actual glyph centre
  // ``activeArc`` sits so its INNER edge kisses ``tickOuter``: arc
  // inner = activeArc − activeArcWidth/2 = 0.720.  The mock's tick
  // outer tips just touch the arc's inner edge; keep the two
  // constrained together on any future re-tune.
  activeArc: 0.737,      // centre of the copper active-zone arc
  activeArcWidth: 0.033,
  tickOuter: 0.720,      // axis line — ticks draw inward from here
  majorTick: 0.095,      // length inward, as fraction of R
  minorTick: 0.048,
  needle: 0.648,         // tip radius — MUST be inboard of numeral glyph
  needleTail: 0.133,
  hub: 0.044,            // copper disc at the centre
  hubPip: 0.015,         // paper pip inset on the hub (Design 14a)
  numeralSize: 0.086,    // font-size, in fractions of R
} as const;

// Enforce the ordering rule at import time.  A future edit that
// crosses these two values would silently re-introduce the
// needle-strikes-numeral bug that v39–v42 kept chasing.  The real
// clearance is `numeralCenter - numeralSize/2`, so the invariant
// checks against the numeral's inner glyph edge, not its centre.
if (RING.needle >= RING.numeralCenter - RING.numeralSize / 2) {
  throw new Error(
    "WheelBarometer: needle tip must sit inboard of numeral inner edge.",
  );
}

const ZONE_BANDS = [
  { from: 28.5, to: 29.0, label: "STORMY" },
  { from: 29.0, to: 29.5, label: "RAIN" },
  { from: 29.5, to: 30.0, label: "CHANGE" },
  { from: 30.0, to: 30.5, label: "FAIR" },
  { from: 30.5, to: 31.0, label: "SET FAIR" },
];

/** The zone containing ``value`` — single source of truth used by
 *  the active-arc plotBand, the "Zone: fair" readout sentence, and
 *  the strip's active-cell highlight. */
export function activeZone(value: number | null): typeof ZONE_BANDS[number] | null {
  if (value == null || !Number.isFinite(value)) return null;
  for (const band of ZONE_BANDS) {
    if (value >= band.from && value < band.to) return band;
  }
  return value >= MAX_INHG ? ZONE_BANDS[ZONE_BANDS.length - 1] : null;
}

export { ZONE_BANDS, MIN_INHG, MAX_INHG };

/** All six majors get numerals — needle tip at 0.648 R sits 0.129 R
 *  inboard of the numeral glyph edge at 0.777 R, so pointer/label
 *  collision is structurally impossible and the plate reads as a
 *  proper meteorological scale rather than three landmarks with a
 *  perceived bulge in the middle. */

export default function WheelBarometer({ inHg, trendInHgPer3h, size }: WheelBarometerProps) {
  const { themeName } = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const [renderSize, setRenderSize] = useState<number>(size);

  // Container-fill (Design v43 step 6): watch the parent's physical
  // width in device px and re-render HC when it changes.  Everything
  // downstream (RING radii, tickLength, pivot.radius) scales with
  // ``renderSize`` — one scale system, no ``--k`` threading through
  // instrument code.  Strokes that must stay 1 device px are already
  // pinned via ``vector-effect: non-scaling-stroke`` in the CSS.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = Math.round(entry.contentRect.width);
        if (w > 0) {
          setRenderSize((prev) => (Math.abs(w - prev) > 1 ? w : prev));
        }
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const options = useMemo<Highcharts.Options | null>(() => {
    if (inHg == null || !Number.isFinite(inHg)) return null;
    const clampedNow = Math.max(MIN_INHG, Math.min(MAX_INHG, inHg));
    const trend3hAgo =
      trendInHgPer3h != null && Number.isFinite(trendInHgPer3h)
        ? Math.max(MIN_INHG, Math.min(MAX_INHG, inHg - trendInHgPer3h))
        : null;

    const R = renderSize / 2;
    const zone = activeZone(clampedNow);

    // HC gauge draws its axis line on the pane rim; making the pane
    // radius equal to ``tickOuter * R`` puts the tick ring on the
    // pane's edge.  Everything else expresses its radius as a
    // percentage of that pane radius via ``pctOfPane``.
    const paneSizePct = RING.tickOuter * 100;
    const pctOfPane = (r: number) => `${(r / RING.tickOuter) * 100}%`;

    // Angle for a value on the [-120°, +120°] sweep.  Shared by the
    // custom needle and the custom active arc so the two can't drift.
    const angleForValue = (v: number) =>
      (-120 + ((v - MIN_INHG) / (MAX_INHG - MIN_INHG)) * 240) * (Math.PI / 180);

    // Custom render hook — draws the copper active arc, the live
    // needle, and the hub + paper pip as raw SVG (Design mock
    // topology).  HC's own plotBand annulus, ``.wheel-baro-now``
    // dial polygon, and pivot are hidden via CSS.  Keeps the trend
    // hand as a HC dial (design keeps trend as an optional aux
    // series; #2 of Chris' fix-list is out of scope).
    const drawOverlay = function (this: unknown) {
      const chart = this as any;
      const paneObj = chart?.pane?.[0];
      const paneCenter = paneObj?.center;
      if (!paneCenter || paneCenter.length < 3) return;
      // ``paneObj.center`` = [cx, cy, size] where ``size`` is the
      // pane DIAMETER in pixels.  (yAxis.len on a gauge returns the
      // axis arc length, not the pane radius — do not use it here.)
      // paneObj.center coords are relative to the plot area; shift
      // by (plotLeft, plotTop) so they land in the SVG's own
      // coordinate system where chart.renderer draws.
      const [rawCx, rawCy, paneSizePx] = paneCenter;
      const cx = rawCx + (chart.plotLeft ?? 0);
      const cy = rawCy + (chart.plotTop ?? 0);
      const paneR = paneSizePx / 2;
      if (!paneR) return;
      const R_ = paneR / RING.tickOuter;

      if (chart._baroOverlay) {
        chart._baroOverlay.destroy();
      }
      const g = chart.renderer.g("wheel-baro-overlay").add();
      chart._baroOverlay = g;

      // Active-zone arc — stroked <path> at r=activeArc, thickness
      // = activeArcWidth * R.  Matches the mock's <path> stroke
      // (uniform crisp line, not an annulus fill).
      if (zone) {
        const a0 = angleForValue(zone.from);
        const a1 = angleForValue(zone.to);
        const arcR = RING.activeArc * R_;
        const x0 = cx + arcR * Math.sin(a0);
        const y0 = cy - arcR * Math.cos(a0);
        const x1 = cx + arcR * Math.sin(a1);
        const y1 = cy - arcR * Math.cos(a1);
        const largeArc = a1 - a0 > Math.PI ? 1 : 0;
        chart.renderer
          .path([
            "M", x0, y0,
            "A", arcR, arcR, 0, largeArc, 1, x1, y1,
          ])
          .attr({
            "stroke-width": RING.activeArcWidth * R_,
            "stroke-linecap": "butt",
          })
          .addClass("wheel-baro-custom-arc")
          .add(g);
      }

      // Live needle — a straight line with round caps.  Runs from
      // (−needleTail * R) behind the hub out to (+needle * R) at
      // the tip.
      const aNow = angleForValue(clampedNow);
      const sinN = Math.sin(aNow);
      const cosN = Math.cos(aNow);
      const tipX = cx + RING.needle * R_ * sinN;
      const tipY = cy - RING.needle * R_ * cosN;
      const backX = cx - RING.needleTail * R_ * sinN;
      const backY = cy + RING.needleTail * R_ * cosN;
      chart.renderer
        .path(["M", backX, backY, "L", tipX, tipY])
        .attr({
          "stroke-width": 2.4,
          "stroke-linecap": "round",
        })
        .addClass("wheel-baro-custom-needle")
        .add(g);

      // Hub + pip — copper disc with a paper-colour dot inset.
      chart.renderer
        .circle(cx, cy, RING.hub * R_)
        .addClass("wheel-baro-custom-hub")
        .add(g);
      chart.renderer
        .circle(cx, cy, RING.hubPip * R_)
        .addClass("wheel-baro-custom-pip")
        .add(g);
    };

    return {
      chart: {
        type: "gauge",
        styledMode: true,
        spacing: [4, 4, 4, 4],
        height: renderSize,
        width: renderSize,
        events: {
          render: drawOverlay,
        },
      },
      title: { text: undefined },
      credits: { enabled: false },
      accessibility: { enabled: false },
      exporting: { enabled: false },
      pane: {
        startAngle: -120,
        endAngle: 120,
        size: `${paneSizePct}%`,
        background: [
          {
            outerRadius: pctOfPane(RING.rim),
            innerRadius: pctOfPane(RING.rim),
            className: "wheel-baro-rim",
          },
        ],
      },
      yAxis: {
        min: MIN_INHG,
        max: MAX_INHG,
        // HC gauge yAxes default to ``offset: '-20%'`` (RadialAxis.js
        // line 218), which pushes the axis line — and therefore the
        // tick ring — 20 % of the pane radius inboard of the rim.
        // That silently subverts the RING geometry: a ``tickOuter``
        // of 0.720 rendered at 0.577 R.  Force to 0 so the tick
        // ring lands exactly where ``pane.size`` places the pane rim.
        offset: 0,
        tickInterval: 0.5,
        // HC's radial-axis wrapper forces ``minorTickInterval`` to
        // ``'auto'`` on gauge yAxes unless ``minorTicks`` is set
        // explicitly (see RadialAxis.js wrapAxisGetMinorTickInterval).
        // ``auto`` then divides ``tickInterval`` by the default
        // ``minorTicksPerMajor: 10``, which drew 50 minor ticks vs
        // the mock's 20.  Both flags must be set together.
        minorTicks: true,
        minorTickInterval: 0.1,
        // Tick lengths are in px; convert from the R-fraction spec.
        tickLength: RING.majorTick * R,
        minorTickLength: RING.minorTick * R,
        tickWidth: 1.4,
        minorTickWidth: 0.8,
        lineWidth: 0,
        // HC's ``labels.distance`` positions the label centre, not
        // its inner envelope.  Mock's numerals sit at r ≈ 0.82 R
        // (glyph centre); distance = numeralCenter − tickOuter.
        // Constant across the three visible angles — mock spread
        // is 0.79 – 0.82 R across 30.0 / 28.5 / 31.0, all within
        // 3 px at any realistic size, so no per-numeral rewrite.
        labels: {
          distance: (RING.numeralCenter - RING.tickOuter) * R,
          formatter: function () {
            const v = typeof this.value === "number" ? this.value : Number(this.value);
            return v.toFixed(1);
          },
        },
        tickPosition: "inside",
        minorTickPosition: "inside",
        // No plotBands — the active-zone arc is drawn by the custom
        // render hook so it renders as a crisp stroke, not a wide
        // annulus fill.  Endpoints still derive from ``activeZone``.
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
                // Trend hand at same ratio-of-needle as the SVG dial
                // used (0.46/0.66 ≈ 0.70 of needle length).
                radius: `${(RING.needle * 0.70 / RING.tickOuter) * 100}%`,
                baseWidth: 2,
                topWidth: 2,
                rearLength: "0%",
              },
              dataLabels: { enabled: false },
              enableMouseTracking: false,
            }]
          : []),
        {
          // The now-series stays in the chart so HC keeps a valid
          // data point for the axis, but the dial + pivot are hidden
          // via CSS — the visible needle and hub come from the
          // custom render hook above.
          type: "gauge" as const,
          name: "now",
          className: "wheel-baro-now",
          data: [clampedNow],
          dial: {
            radius: pctOfPane(RING.needle),
            baseWidth: 2.4,
            topWidth: 2.4,
            rearLength: pctOfPane(RING.needleTail),
          },
          pivot: {
            radius: RING.hub * R,
          },
          dataLabels: { enabled: false },
          enableMouseTracking: false,
        },
      ],
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inHg, trendInHgPer3h, renderSize, themeName]);

  // Container-fill: outer div stretches to whatever slot the tile
  // hands us (Design v43 step 6).  The tile is authoritative for
  // physical size via its own ``s()`` unit; the instrument brings no
  // intrinsic dimensions of its own.
  const containerStyle: React.CSSProperties = {
    width: "100%",
    height: "100%",
  };

  if (!options) {
    return (
      <div
        ref={containerRef}
        className="wheel-barometer"
        aria-hidden="true"
        style={containerStyle}
      />
    );
  }

  return (
    <div
      ref={containerRef}
      className="wheel-barometer"
      aria-hidden="true"
      aria-label={
        inHg != null
          ? `Barometric pressure ${inHg.toFixed(2)} inches of mercury, zone ${activeZone(inHg)?.label.toLowerCase() ?? ""}.`
          : undefined
      }
      style={containerStyle}
    >
      <HighchartsReact highcharts={Highcharts} options={options} />
    </div>
  );
}
