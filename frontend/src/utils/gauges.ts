/**
 * Gauge and chart geometry primitives.  Pure functions: numbers in,
 * plain coordinate objects out; render the output as SVG.  Ported
 * verbatim from Design's handoff (``handoff/geometry/gauges.ts``) so
 * the values that render on paper themes match the mocks.  Ratio
 * constants come from each theme's ``dial`` group — pass ``theme.dial``.
 */

export interface DialRatios {
  gradOuter: number;
  gradInner: number;
  numeral: number;
  zone: number;
  needle: number;
  trendHand: number;
}

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

export interface WheelDial {
  cx: number; cy: number;
  rimOuter: number; rimInner: number;
  major: Tick[]; minor: Tick[];
  numerals: Label[]; zones: Label[];
  tip: Point; trend: Point;
}

/**
 * Wheel barometer: 240° sweep starting at −210° (opens downward like a
 * real aneroid), fixed 28.5–31.0 inHg range so needle position stays
 * meaningful, 21 graduations with every 4th major, zone words on the
 * ``zone`` ring, live needle + a pale trend hand ~3 h behind.
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

/**
 * 16-point compass.  ``labelR`` must be OUTSIDE ``outerR`` or the
 * cardinal letters overlap the ticks and become illegible — in the
 * mocks ``outerR`` 74 pairs with ``labelR`` 92; 80 pairs with 98.
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
 * Wind-rose petals — one wedge per 16th, radius proportional to sector
 * weight, opacity double-encodes to keep light sectors visible.  Petals
 * start at r=14, not 0, so faint sectors don't collapse into the hub.
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

/**
 * Paper-theme 24 h chart ledger overlay: pale horizontals with a
 * stronger midline, faint hour verticals every 4th emphasised.  Ink
 * shadow + accent stroke doubling is what makes the trace read as ink
 * on ruled paper.
 */
export function ledgerGrid(w: number, h: number) {
  const hRules: { y: number; op: number }[] = [];
  const vRules: { x: number; op: number }[] = [];
  for (let i = 1; i <= 9; i++) hRules.push({ y: r2((h * i) / 10), op: i === 5 ? 0.32 : 0.18 });
  for (let i = 0; i <= 12; i++) vRules.push({ x: r2((w * i) / 12), op: i % 4 === 0 ? 0.14 : 0.06 });
  return { hRules, vRules };
}
