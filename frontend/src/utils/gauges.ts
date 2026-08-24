/**
 * Chart geometry — the part prose specs can't carry.
 *
 * Design v34/v35 HIGHCHARTS.md tranches 3 + 4 retired every gauge /
 * dial / arc drawing function that once lived here.  What's left is
 * the trace + grid + scoring geometry Highcharts doesn't replace:
 *
 * - ``pathFor`` builds an SVG polyline path for a value series (still
 *   used by the small SVG trend widgets in tiles.tsx and Weather
 *   Nerd's temp/dew/baro three-up chart).
 * - ``ledgerGrid`` builds the 12×9 rule grid overlaid on those traces.
 * - ``scoreSprayHours`` rates a 24 h forecast against agricultural
 *   spray constraints — pure data, no rendering.
 * - ``makeTimeAxis`` / ``bodyArc`` / ``moonTerminator`` power the
 *   astronomy day-arc plate and moon-phase diagram: diagrams, not
 *   charts, and Highcharts has no sensible expression for either.
 *
 * Retired in tranche 4 (2026-08-20): ``wheelDial`` (→
 * WheelBarometer.tsx), ``compass`` + ``rosePetals`` (→
 * WindRoseDial.tsx), ``humidityArc`` / ``uvArc`` (unused after the
 * gauge redesign).  Their theme-side ``DialRatios`` /
 * ``DEFAULT_DIAL`` / ``WheelDial`` companion types went with them.
 */

export interface Point { x: number; y: number }
export interface Tick { x1: number; y1: number; x2: number; y2: number; sw?: number }
export interface Label extends Point { label: string }

const r2 = (n: number) => Math.round(n * 100) / 100;

/* ─────────────────────────────────────────────────────────────────────── traces */

/**
 * Map a value series into an SVG path inside a box. Returns the polyline, a
 * closed area path for fills, and the last point so a live marker can sit on the
 * trace rather than being positioned independently.
 *
 * ⚠ Always take a live marker from `.last` (or by sampling this same function).
 * Every data-accuracy defect found in design review came from computing a marker
 * separately from the curve it sits on.
 */
export function pathFor(
  vals: number[], x0: number, x1: number, yTop: number, yBot: number, minV: number, maxV: number,
) {
  const n = vals.length - 1;
  const pts = vals.map((v, i) => ({
    x: r2(x0 + ((x1 - x0) * i) / n),
    y: r2(yBot - ((v - minV) / (maxV - minV)) * (yBot - yTop)),
  }));
  return {
    line: pts.map((p, i) => `${i ? 'L' : 'M'}${p.x} ${p.y}`).join(' '),
    area: `${pts.map((p, i) => `${i ? 'L' : 'M'}${p.x} ${p.y}`).join(' ')} L${pts[n].x} ${yBot} L${pts[0].x} ${yBot} Z`,
    last: pts[n],
    points: pts,
  };
}

/**
 * Ledger grid for the paper themes' 24 h trace — pale horizontals with a
 * stronger midline, faint hour verticals every 4th emphasised. Draw the trace
 * twice: an ink shadow at ~0.35 opacity and 2.4px under the accent stroke at
 * 1.8px. That doubling is what makes it look like ink on ruled paper rather than
 * a line on a chart.
 */
export function ledgerGrid(w: number, h: number) {
  const hRules: { y: number; op: number }[] = [];
  const vRules: { x: number; op: number }[] = [];
  for (let i = 1; i <= 9; i++) hRules.push({ y: r2((h * i) / 10), op: i === 5 ? 0.32 : 0.18 });
  for (let i = 0; i <= 12; i++) vRules.push({ x: r2((w * i) / 12), op: i % 4 === 0 ? 0.14 : 0.06 });
  return { hRules, vRules };
}

/* ──────────────────────────────────────────────────────── spray window (agri) */

export interface SprayConstraints {
  maxWind: number;
  minTemp: number;
  maxTemp: number;
  minRh?: number | null;
  rainFreeHours?: number;
}

export interface SprayCell {
  /** Absolute start-of-hour instant, ISO string.  The renderer must
   *  order cells by ``at`` and never re-derive order from ``hour`` —
   *  a 24-hour window crossing midnight has two of each clock hour
   *  and the older one is unrepresentable without a date.  Design
   *  v49 §1. */
  at: string;
  hour: number; label: string;
  state: 'go' | 'marginal' | 'nogo';
  fails: string[];
  wind: number; temp: number; rh: number;
}

/**
 * Score N hourly forecast rows against one product's constraints, the way
 * `spray_engine.py` evaluates Open-Meteo hourly data. Check names match the
 * backend exactly (`wind`, `temperature`, `humidity`, `rain_free`) so the UI can
 * show the same reason strings the API returns.
 *
 * `marginal` has no backend equivalent — it's a UI affordance for "passes now but
 * within 1.5 mph or 3 °F of a limit", which is what makes the strip actionable
 * rather than just binary.
 *
 * Colour comes from the active theme's `success` / `warning` / `danger`, and the
 * cells must be drawn at **full opacity** — any wash puts the scale visibly out
 * of step with its own legend swatches.
 */
export function scoreSprayHours(
  rows: { at: string; hour: number; temp: number; wind: number; rh: number; rainWithinWindow: boolean }[],
  c: SprayConstraints,
): SprayCell[] {
  return rows.map((row) => {
    const fails: string[] = [];
    if (row.wind > c.maxWind) fails.push('wind');
    if (row.temp < c.minTemp || row.temp > c.maxTemp) fails.push('temperature');
    if (c.minRh != null && row.rh < c.minRh) fails.push('humidity');
    if (row.rainWithinWindow) fails.push('rain_free');
    const near = !fails.length && (row.wind > c.maxWind - 1.5 || row.temp > c.maxTemp - 3);
    const h = row.hour;
    return {
      at: row.at,
      hour: h,
      label: `${h % 12 === 0 ? 12 : h % 12}${h < 12 ? 'a' : 'p'}`,
      state: fails.length ? 'nogo' : near ? 'marginal' : 'go',
      fails,
      wind: row.wind, temp: row.temp, rh: row.rh,
    };
  });
}

/* ────────────────────────────────────────────────────────────────── astronomy */

/**
 * One shared time axis for the Astronomy day plate. Every arc, band, and marker
 * on that panel must map through this function — independent computation is what
 * produced every defect review caught there.
 *
 * Hours past midnight in, x in. Pass hours > 24 for after-midnight events
 * (moonset at 1:12 AM is hour 25.2).
 */
export function makeTimeAxis(riseH: number, setH: number, xAtRise: number, xAtSet: number) {
  const pxPerH = (xAtSet - xAtRise) / (setH - riseH);
  return (hour: number) => r2(xAtRise + (hour - riseH) * pxPerH);
}

/**
 * Sun/moon arc over the horizon. `nowH` is sampled from the same sine that draws
 * the path, so the live marker sits on the curve by construction.
 *
 * A body whose set time falls outside the plate simply runs off the edge — clip
 * it, don't compress the arc to fit. Compressing implies a set time that isn't
 * real.
 */
export function bodyArc(
  riseH: number, setH: number, peakY: number, horizonY: number,
  nowH: number, axis: (h: number) => number,
  clip: { min: number; max: number } = { min: -10, max: 1e6 },
) {
  const pts: Point[] = [];
  const n = 90;
  for (let i = 0; i <= n; i++) {
    const f = i / n;
    const x = axis(riseH + (setH - riseH) * f);
    if (x < clip.min || x > clip.max) continue;
    pts.push({ x, y: r2(horizonY - Math.sin(f * Math.PI) * (horizonY - peakY)) });
  }
  const nf = (nowH - riseH) / (setH - riseH);
  return {
    path: pts.map((p, i) => `${i ? 'L' : 'M'}${p.x} ${p.y}`).join(' '),
    nowX: axis(nowH),
    nowY: r2(horizonY - Math.sin(nf * Math.PI) * (horizonY - peakY)),
  };
}

/**
 * Moon terminator offset for a lit fraction k (0–1): `d = r(1 − 2k)`.
 * Returns the ellipse centre x for a moon drawn at (cx, cy) with radius r.
 * Positioning this by eye is how a "71% waxing gibbous" label ends up next to a
 * graphic showing something else.
 */
export function moonTerminator(cx: number, r: number, k: number) {
  return { ellipseCx: r2(cx + r * (1 - 2 * k)), rx: r2(Math.abs(r * (1 - 2 * k))) };
}
