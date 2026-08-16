/**
 * Gauge and chart geometry — the part prose specs can't carry.
 *
 * Every function is pure: numbers in, plain coordinate objects out. No React, no
 * three.js, no charting library. Render the output with whatever you like; the
 * mock renders it as inline SVG.
 *
 * WHY THIS FILE EXISTS
 * The screen specs describe what each tile *shows*. They cannot describe a dial's
 * sweep, its tick radii, or where a needle pivots — so a reimplementation from
 * prose alone produces flat cards with numbers in them. That is the failure this
 * module prevents. These are the exact values the mocks render.
 *
 * Ratio constants live in each theme's `dial` group (`gradOuter`, `gradInner`,
 * `numeral`, `zone`, `needle`, `trendHand`) so a theme can retune the dial
 * without touching this file. Pass `theme.dial` as the last argument.
 */

export interface DialRatios {
  gradOuter: number;
  gradInner: number;
  numeral: number;
  zone: number;
  needle: number;
  trendHand: number;
}

/** The shipping ratios, if you need a default. Same in all five themes. */
export const DEFAULT_DIAL: DialRatios = {
  gradOuter: 0.967,
  gradInner: 0.887,
  numeral: 0.747,
  zone: 0.573,
  needle: 0.66,
  trendHand: 0.46,
};

export interface Point { x: number; y: number }
export interface Tick { x1: number; y1: number; x2: number; y2: number; sw?: number }
export interface Label extends Point { label: string }

const r2 = (n: number) => Math.round(n * 100) / 100;

/* ────────────────────────────────────────────────────────────── barometer dial */

export interface WheelDial {
  cx: number; cy: number;
  rimOuter: number; rimInner: number;
  major: Tick[]; minor: Tick[];
  numerals: Label[]; zones: Label[];
  tip: Point; trend: Point;
}

/**
 * Wheel barometer — the Everyday dashboard's hero, and the single element that
 * most defines the redesign. Ported from `BarometerDial()` in
 * kanfei-phone-sensor `docs/mocks/v1-instrument.jsx`.
 *
 * A **240° sweep starting at −210°** (so it opens downward, like a real aneroid),
 * 21 graduations with every 4th major, numerals every major, five named pressure
 * zones on an inner ring, and a pale trend hand 3 h behind the live needle.
 *
 * Range is 28.5–31.0 inHg. That is deliberate: a station's real daily swing is
 * ~0.2 in, so a dial scaled to the day would read as noise. The fixed
 * meteorological range is what makes the needle position meaningful.
 *
 * Render order matters — rim pair, minor ticks, major ticks, numerals, zones,
 * trend hand, needle, hub cap. Drawing the needle before the ticks looks wrong.
 */
export function wheelDial(
  value: number,
  size: number,
  d: DialRatios = DEFAULT_DIAL,
): WheelDial {
  const r = size / 2, cx = r, cy = r;
  const SWEEP_START = -210, SWEEP_RANGE = 240;
  const LO = 28.5, HI = 31.0;

  const frac = Math.max(0, Math.min(1, (value - LO) / (HI - LO)));
  const angleAt = (f: number) => SWEEP_START + SWEEP_RANGE * f;
  const polar = (deg: number, radius: number): Point => {
    const a = (deg * Math.PI) / 180;
    return { x: r2(cx + radius * Math.cos(a)), y: r2(cy + radius * Math.sin(a)) };
  };

  const major: Tick[] = [], minor: Tick[] = [], numerals: Label[] = [];
  for (let i = 0; i <= 20; i++) {
    const f = i / 20, a = angleAt(f), isMajor = i % 4 === 0;
    const p1 = polar(a, r - 5);
    const p2 = polar(a, isMajor ? r - 17 : r - 12);
    (isMajor ? major : minor).push({ x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y, sw: isMajor ? 2 : 1 });
    if (isMajor) {
      const lp = polar(a, r * d.numeral);
      numerals.push({ x: lp.x, y: r2(lp.y + 4), label: (LO + f * (HI - LO)).toFixed(1) });
    }
  }

  // Zone names sit on their own ring, well inside the numerals, or they collide.
  const zones: Label[] = ([
    ['STORMY', 0.08], ['RAIN', 0.28], ['CHANGE', 0.5], ['FAIR', 0.72], ['SET FAIR', 0.93],
  ] as [string, number][]).map(([label, f]) => {
    const p = polar(angleAt(f), r * d.zone);
    return { label, x: p.x, y: r2(p.y + 3) };
  });

  return {
    cx, cy,
    rimOuter: r2(r * d.gradOuter),
    rimInner: r2(r * d.gradInner),
    major, minor, numerals, zones,
    tip: polar(angleAt(frac), r * d.needle),
    trend: polar(angleAt(Math.max(0, frac - 0.12)), r * d.trendHand),
  };
}

/* ───────────────────────────────────────────────────────── compass + wind rose */

/**
 * 16-point compass, ported from the shipping `WindCompass.tsx`. Ticks step by
 * 22.5° from north; every 4th is major (cardinal) and gets a label, every 2nd is
 * mid-length.
 *
 * ⚠ `labelR` must be **outside** `outerR`, or the cardinal letters overlap the
 * tick marks and become illegible. In the mocks `outerR` 74 pairs with `labelR`
 * 92; 80 pairs with 98. This was a real defect found in review — don't tighten it.
 */
export function compass(cx: number, cy: number, outerR: number, labelR: number) {
  const CARDINALS = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'];
  const ticks: Tick[] = [], labels: Label[] = [];
  CARDINALS.forEach((label, i) => {
    const rad = ((i * 22.5 - 90) * Math.PI) / 180;
    const major = i % 4 === 0, mid = i % 2 === 0;
    const inner = major ? outerR - 14 : mid ? outerR - 10 : outerR - 6;
    ticks.push({
      x1: r2(cx + inner * Math.cos(rad)), y1: r2(cy + inner * Math.sin(rad)),
      x2: r2(cx + outerR * Math.cos(rad)), y2: r2(cy + outerR * Math.sin(rad)),
      sw: major ? 2 : 1,
    });
    if (major) labels.push({ label, x: r2(cx + labelR * Math.cos(rad)), y: r2(cy + labelR * Math.sin(rad) + 4) });
  });
  return { ticks, labels };
}

/**
 * Wind-rose petals — one wedge per 16th, radius proportional to how much of the
 * window blew from that sector. Feed it a normalised 16-element distribution
 * (max = 1); `weights` here is a 4 h sample with a WSW-dominant pattern.
 *
 * Petals start at r=14, not 0, so light sectors stay visible instead of
 * collapsing into the hub. Opacity tracks weight as well as radius — the double
 * encoding is what makes the prevailing direction readable at a glance.
 */
export function rosePetals(cx: number, cy: number, maxR: number, weights?: number[]) {
  const w = weights ?? [0.05,0.04,0.03,0.03,0.05,0.06,0.08,0.10,0.18,0.34,0.62,1.0,0.78,0.42,0.20,0.09];
  return w.map((weight, i) => {
    const a0 = ((i * 22.5 - 11.25 - 90) * Math.PI) / 180;
    const a1 = ((i * 22.5 + 11.25 - 90) * Math.PI) / 180;
    const r = 14 + weight * (maxR - 14);
    const x0 = r2(cx + r * Math.cos(a0)), y0 = r2(cy + r * Math.sin(a0));
    const x1 = r2(cx + r * Math.cos(a1)), y1 = r2(cy + r * Math.sin(a1));
    return {
      d: `M ${cx} ${cy} L ${x0} ${y0} A ${r} ${r} 0 0 1 ${x1} ${y1} Z`,
      op: r2(0.12 + weight * 0.5),
    };
  });
}

/* ──────────────────────────────────────────────────────────────── half-circle arcs */

/**
 * Humidity arc — left-to-right semicircle, matching the shipping
 * `HumidityGauge.tsx` mapping. Colour interpolates cool→warm across 60–100%.
 */
export function humidityArc(value: number, lo = 0, hi = 100) {
  const cx = 150, cy = 120, r = 108, sw = 18;
  const pt = (f: number, radius: number): Point => {
    const a = Math.PI * (1 - f);
    return { x: r2(cx + radius * Math.cos(a)), y: r2(cy - radius * Math.sin(a)) };
  };
  const arc = (f0: number, f1: number) => {
    const p0 = pt(f0, r), p1 = pt(f1, r);
    return `M ${p0.x} ${p0.y} A ${r} ${r} 0 ${f1 - f0 >= 0.999 ? 1 : 0} 1 ${p1.x} ${p1.y}`;
  };
  const span = hi - lo;
  const frac = Math.max(0, Math.min(1, (value - lo) / span));
  const ticks: { lx: number; ly: number; label: string }[] = [];
  for (let v = lo; v <= hi; v += 5) {
    const p = pt((v - lo) / span, r - sw - 8);
    ticks.push({ lx: p.x, ly: r2(p.y + 3), label: String(v) });
  }
  const t = (value - 60) / 40;
  return {
    trackPath: arc(0, 1),
    fillPath: arc(0, frac),
    ticks,
    color: `rgb(${Math.round(34 - 10 * t)}, ${Math.round(150 + 50 * t)}, ${Math.round(200 + 40 * t)})`,
  };
}

/** UV arc — 0–14 across the top half. Same construction, smaller radius. */
export function uvArc(uv: number, cx = 90, cy = 94, r = 58) {
  const pt = (f: number): Point => {
    const a = Math.PI * (1 - f);
    return { x: r2(cx + r * Math.cos(a)), y: r2(cy - r * Math.sin(a)) };
  };
  const arc = (f0: number, f1: number) => {
    const p0 = pt(f0), p1 = pt(f1);
    return `M ${p0.x} ${p0.y} A ${r} ${r} 0 ${f1 - f0 >= 0.999 ? 1 : 0} 1 ${p1.x} ${p1.y}`;
  };
  return { trackPath: arc(0, 1), fillPath: arc(0, Math.min(uv / 14, 0.998)) };
}

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
  rows: { hour: number; temp: number; wind: number; rh: number; rainWithinWindow: boolean }[],
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
