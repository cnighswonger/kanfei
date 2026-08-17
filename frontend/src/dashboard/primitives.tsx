/**
 * Shared primitives. Everything visual on the dashboard is built from these five,
 * which is what keeps the paper themes and the dark theme from drifting apart.
 *
 * ── TOKEN MAP ────────────────────────────────────────────────────────────────
 * `v()` is the ONLY place CSS custom property names appear. If your
 * `applyThemeToDOM()` publishes different names, change them here and nowhere
 * else. Names below match handoff/themes/README.md step 1.
 */
import React from 'react';

/**
 * ── SCALE ────────────────────────────────────────────────────────────────────
 *
 * The mock is a 1600×1180 composition — main content 1318×1120. Pinning it in
 * absolute px means that on a bigger screen the type reads small AND the fixed
 * heights stop short of the viewport, leaving dead space under the footer. Two
 * symptoms, one cause.
 *
 * `s(n)` expresses every size as n × `--k`, a px-valued scale unit derived from the
 * viewport height against the mock's 1120px of main content:
 *
 *     --k: clamp(0.92px, calc((100vh - var(--chrome-height, 94px)) / 1120), 1.5px)
 *
 * ⚠ Deliberately `vh`, NOT `cqh`. Container query units need a definite height on
 * the container; the app shell's <main> is content-sized, so `100cqh` was invalid,
 * the whole clamp() collapsed, and `--k` silently fell back to 1px — which is
 * precisely the dead space that was left under the footer. `vh` is always definite.
 *
 * `--chrome-height` is everything vertical the dashboard does NOT own: the 60px
 * header plus the ~34px status bar. The shell should set it; 94px is the default.
 *
 * Height-based, not width-based: the vertical budget must fit exactly, and scaling
 * by width on a wide monitor overshoots into a scrollbar. Widths stay fluid (`fr`,
 * `100%`), so the page still fills horizontally.
 *
 * Dividing a length by a number yields a length, so `--k` is a px value and
 * `calc(14 * var(--k))` resolves — the sizes below are unitless multipliers.
 */
export const s = (n: number): string => `calc(${n} * var(--k, 1px))`;

/** Type scale — use for every font-size. Falls back to the layout unit. */
export const st = (n: number): string => `calc(${n} * var(--kt, var(--k, 1px)))`;

/**
 * ⚠ ONE scale factor for every persona.
 *
 * An earlier version derived `--k` from each layout's own design height — 1120 for
 * Everyday, 928 for Agriculture. That makes body text render 16px on one persona
 * and 19px on the other in the same window, and inflates the shorter composition's
 * type by ~20%: the blown-up look on Agriculture.
 *
 * Type and spacing must be identical across personas, so `--k` always comes from
 * the CANONICAL 1120px frame. A shorter composition absorbs its residual height in
 * whichever band carries slack (`flex: 1`), never in its font sizes.
 */
const CANONICAL_WIDTH = 1318;
// `--kt`'s clamp is anchored to a canonical height, NOT each persona's
// own design height.  This is why: `--k` differs by persona (Everyday
// 1120, Agriculture 928), and if the `--kt` clamp uses `var(--k)` for
// its floor and cap, then at any viewport where the width-derived middle
// value falls below the floor, `--kt` collapses to `--k` — and now
// `--kt` differs by persona too, i.e. same body text is ~20% bigger on
// Agriculture than on Everyday at Chris's typical viewport.
// Using the taller layout's height as the canonical means both
// personas produce identical `--kt` regardless of viewport.
const CANONICAL_HEIGHT_FOR_TYPE = 1120;

/**
 * TWO scale units, split by axis — this is the decomposition that works.
 *
 * `--k` (LAYOUT) comes from height, against **this layout's own** design height:
 * Everyday 1120, Agriculture 928. Each composition then fills its viewport exactly,
 * with no leftover band and no tile stretched past its content. Layout scale
 * differing between personas is invisible; it just means each fits.
 *
 * `--kt` (TYPE) comes from width, against the shared 1318px content width, so text
 * is the same size on every persona. Perceived text size tracks how *wide* a
 * display is, not how tall — scaling type by height is why fonts kept reading small
 * on the large monitor.
 *
 * `--kt` is floored / capped against a canonical (1120-derived) `--k`
 * — NOT this persona's `--k`.  Anchoring the clamp bounds to each
 * persona's own `--k` reintroduces exactly the persona-dependent type
 * we're trying to avoid: at narrow / short viewports the width-derived
 * middle value falls below the floor and `--kt` collapses back to
 * `--k`, which now differs by persona.  The cap keeps type from
 * outgrowing tiles on any layout.
 *
 * Earlier attempts got this backwards in both directions: per-layout type (which
 * made body text 16px on one persona and 19px on another) and then global layout
 * height (which left Agriculture 217px short and dumped the slack into one
 * flex band, opening the voids under Drift risk and Water balance).
 */
export const scaleVar = (designHeight: number): React.CSSProperties => {
  const canonicalK = `calc((100vh - var(--chrome-height, 94px)) / ${CANONICAL_HEIGHT_FOR_TYPE})`;
  return {
    ['--k' as string]:
      `clamp(0.92px, calc((100vh - var(--chrome-height, 94px)) / ${designHeight}), 1.8px)`,
    ['--kt' as string]:
      `clamp(${canonicalK}, calc((100vw - var(--sidebar-width, 220px)) / ${CANONICAL_WIDTH}), calc(${canonicalK} * 1.35))`,
  };
};

/** Everyday's wrapper — 1120px of main content. */
export const SCALE_VAR: React.CSSProperties = scaleVar(1120);

/**
 * Content width cap.
 *
 * ⚠ Uses `--kt` (shared, width-derived), NOT `--k` (per-layout,
 * height-derived).  With `--k` the cap resolves differently on each
 * persona — 1600 × 1.11 = 1781px on Everyday against 1600 × 1.34 =
 * 2150px on Agriculture — so the two dashboards render at visibly
 * different widths in the same window.  Anything shared between
 * personas must key off the shared unit.
 *
 * The mock is a ~1320px-wide composition; much past that,
 * ``space-between`` rows push their label and value to opposite ends
 * of a very wide column and stop reading as rows at all.  Capping
 * preserves the mock's proportions at any window width.
 */
export const CONTENT_CAP: React.CSSProperties = {
  maxWidth: st(1600),
  marginLeft: 'auto',
  marginRight: 'auto',
  width: '100%',
};

/**
 * ⚠ EVERY token has a hard fallback.
 *
 * `var(--x)` with no fallback is INVALID when --x isn't published: the property
 * silently inherits instead. That is exactly how three rounds of "the fonts are
 * off" happened — `--type-sectionLabel-*` wasn't being published, so every tile
 * heading fell back to body sans in sentence case instead of tracked mono caps.
 *
 * The fallbacks below are mock 1d's measured values. The design therefore renders
 * correctly even if the theme publishes nothing, and a theme can still override
 * any single token.
 */
const PAPER = {
  ink: '#3a2d1d',
  inkSoft: 'rgba(58,45,29,0.84)',
  inkFaint: 'rgba(58,45,29,0.62)',
  paper: '#ebdfc1',
  sunken: '#dccfa9',
  accent: '#a85f24',
  rule: 'rgba(58,45,29,0.24)',
};

export const v = {
  bg: `var(--color-bg, ${PAPER.paper})`,
  surface: 'var(--color-bg-card, transparent)',
  sunken: `var(--color-surface-sunken, ${PAPER.sunken})`,
  text: `var(--color-text, ${PAPER.ink})`,
  textSecondary: `var(--color-text-secondary, ${PAPER.inkSoft})`,
  textMuted: `var(--color-text-muted, ${PAPER.inkFaint})`,
  accent: `var(--color-accent, ${PAPER.accent})`,
  success: 'var(--color-success, #4e5a2b)',
  warning: `var(--color-warning, ${PAPER.accent})`,
  danger: 'var(--color-danger, #963a2a)',
  sky: 'var(--color-sky, #3f5d7a)',
  /** Strong rule: solid 1.6px ink — the divider under a tile heading. */
  rule: `var(--rule-strong, ${PAPER.ink})`,
  ruleWidth: 'var(--rule-strong-width, 1.6px)',
  /** Hairline: dotted 0.8px on the paper themes, solid on dark. */
  ruleHair: `var(--rule-hair, ${PAPER.rule})`,
  ruleHairWidth: 'var(--rule-hair-width, 0.8px)',
  ruleStyle: 'var(--rule-style, dotted)',
  radiusCard: 'var(--radius-card, 0px)',
  needle: `var(--color-barometer-needle, ${PAPER.accent})`,
  gaugeTrack: `var(--color-gauge-track, ${PAPER.rule})`,
  chart: {
    trace: `var(--chart-trace, ${PAPER.accent})`,
    traceShadow: 'var(--chart-trace-shadow, rgba(58,45,29,0.35))',
    traceSecondary: 'var(--chart-trace-secondary, #3f5d7a)',
    gridMinor: 'var(--chart-grid-minor, rgba(58,45,29,0.10))',
    gridMajor: 'var(--chart-grid-major, rgba(58,45,29,0.20))',
    surface: `var(--chart-surface, ${PAPER.sunken})`,
    axis: `var(--chart-axis, ${PAPER.inkSoft})`,
    rain: 'var(--chart-series-rain, #3f5d7a)',
  },
};

/**
 * Type roles. Never set font-family, font-size or font-style directly on a
 * dashboard element — pick a role. The six roles and which element takes which
 * are specified in handoff/REVIEW-04-fit-and-type.md.
 *
 * `italic` comes from the token, so IM Fell English and Source Serif render
 * italic on the paper themes while Inter stays upright on dark — without any
 * per-theme conditional in component code.
 */
export type Role = 'display' | 'heading' | 'title' | 'body' | 'mono' | 'sectionLabel';

/** Measured from mock 1d. Sizes are unitless multipliers of `--k` (see `s`). */
const ROLE: Record<Role, {
  family: string; size: number; weight: number; style: string; tracking: string; transform: string;
}> = {
  display:      { family: "'Source Serif 4', Georgia, serif", size: 104, weight: 600, style: 'italic', tracking: 'normal', transform: 'none' },
  heading:      { family: "'Source Serif 4', Georgia, serif", size: 30,  weight: 600, style: 'italic', tracking: 'normal', transform: 'none' },
  title:        { family: "'Source Serif 4', Georgia, serif", size: 17,  weight: 600, style: 'italic', tracking: 'normal', transform: 'none' },
  body:         { family: "'Inter', sans-serif",              size: 14,  weight: 400, style: 'normal', tracking: 'normal', transform: 'none' },
  mono:         { family: "'JetBrains Mono', monospace",      size: 14,  weight: 400, style: 'normal', tracking: 'normal', transform: 'none' },
  sectionLabel: { family: "'JetBrains Mono', monospace",      size: 10,  weight: 400, style: 'normal', tracking: '0.2em',  transform: 'uppercase' },
};

export const type = (role: Role, overrides: React.CSSProperties = {}): React.CSSProperties => {
  const f = ROLE[role];
  return {
    fontFamily: `var(--type-${role}-family, ${f.family})`,
    fontSize: `var(--type-${role}-size, ${st(f.size)})`,
    fontWeight: `var(--type-${role}-weight, ${f.weight})` as unknown as number,
    fontStyle: `var(--type-${role}-style, ${f.style})`,
    letterSpacing: `var(--type-${role}-tracking, ${f.tracking})`,
    textTransform: `var(--type-${role}-transform, ${f.transform})` as React.CSSProperties['textTransform'],
    ...overrides,
  };
};

/** Scaled font-size override, for the handful of one-off sizes in the mock. */
export const fs = (n: number): React.CSSProperties => ({ fontSize: st(n) });

/** Tabular figures — mandatory on any value that updates live, or rows jitter. */
export const tnum: React.CSSProperties = { fontVariantNumeric: 'tabular-nums' };

/** Em-dash for missing data. Never render a 0 for an absent reading. */
export const fmt = (n: number | null | undefined, digits = 1, suffix = ''): string =>
  n == null || Number.isNaN(n) ? '—' : `${n.toFixed(digits)}${suffix}`;

export const fmtInt = (n: number | null | undefined, suffix = ''): string =>
  n == null || Number.isNaN(n) ? '—' : `${Math.round(n).toLocaleString()}${suffix}`;

/**
 * Clock time only, from either a display string or an ISO timestamp.
 *
 * Defensive on purpose: the API returns full ISO strings
 * ('2026-08-16T17:09:15.978925Z') and a raw one is ~28 characters, which blows
 * every chip and status row out of its tile. Formatting belongs in the adapter,
 * but a display component must never be the reason a layout breaks — so any
 * ISO-looking value gets reduced to '5:09 PM' here as well.
 */
export const fmtTime = (s: string | null | undefined): string => {
  if (!s) return '—';
  if (!/\d{4}-\d{2}-\d{2}T/.test(s)) return s;   // already display-formatted
  const d = new Date(s);
  return Number.isNaN(d.getTime())
    ? s
    : d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
};

/* ──────────────────────────────────────────────────────────────── components */

/**
 * Tile shell. Paper themes get square corners and no fill from their tokens, dark
 * gets a card — one component, no branching.
 *
 * `height` is explicit and comes from TILE-CONTRACT.md. It is not a minimum: the
 * content was authored to fit. If real data overflows, say so rather than growing
 * the tile — the column totals are what keep the page off the scrollbar.
 */
export const Tile: React.FC<{
  id: string;
  /** Prefer minHeight from the layout — a fixed height clips grown text. */
  height?: number | string;
  style?: React.CSSProperties;
  children: React.ReactNode;
}> = ({ id, height, style, children }) => (
  <section
    data-tile-id={id}
    style={{
      height,
      display: 'flex',
      flexDirection: 'column',
      gap: s(8),
      minWidth: 0,
      padding: 'var(--tile-padding, 0)',
      background: 'var(--tile-bg, transparent)',
      border: 'var(--tile-border, none)',
      borderRadius: v.radiusCard,
      ...style,
    }}
  >
    {children}
  </section>
);

/**
 * Tile heading — serif italic, sentence case, with its OWN 0.8px solid underline.
 *
 * ⚠ This is the default for a tile, NOT <SectionLabel>. In mock 1d every tile
 * heading is the `title` role in sentence case: 'Rain ledger', 'Almanac for
 * today', 'Console & link'. Mono caps are for KICKERS only — the small label above
 * the hero numeral, unit captions, and axis labels. Using SectionLabel for tile
 * headings makes the whole page read as a machine readout instead of a log.
 */
export const TileHeading: React.FC<{
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ children, style }) => (
  <div
    style={{
      ...type('title'),
      color: v.text,
      paddingBottom: s(5),
      borderBottom: `${v.ruleHairWidth} solid ${v.rule}`,
      ...style,
    }}
  >
    {children}
  </div>
);

/** Tracked mono caps — kickers, unit captions, axis labels. Not tile headings. */
export const SectionLabel: React.FC<{
  children: React.ReactNode;
  color?: string;
  style?: React.CSSProperties;
}> = ({ children, color = v.textSecondary, style }) => (
  <div style={{ ...type('sectionLabel'), color, ...style }}>{children}</div>
);

/**
 * Ruled row — label left in secondary ink, value right in mono. The dashboard's
 * default way to show a labelled number; five of these is a table.
 *
 * ~30px tall with a hairline under it. The last row in a group passes `last` to
 * drop its rule.
 */
export const Row: React.FC<{
  label: React.ReactNode;
  value: React.ReactNode;
  valueColor?: string;
  last?: boolean;
}> = ({ label, value, valueColor = v.text, last }) => (
  <div
    style={{
      display: 'flex',
      alignItems: 'baseline',
      justifyContent: 'space-between',
      gap: s(12),
      padding: `${s(7)} 0`,
      borderBottom: last ? 'none' : `${v.ruleHairWidth} ${v.ruleStyle} ${v.ruleHair}`,
    }}
  >
    <span style={{ ...type('body'), color: v.textSecondary }}>{label}</span>
    <span style={{ ...type('mono'), ...tnum, color: valueColor }}>{value}</span>
  </div>
);

/** Section divider under a tile heading — solid 1.6px ink, not the hairline. */
export const Rule: React.FC<{ strong?: boolean }> = ({ strong }) => (
  <div
    style={{
      borderBottom: strong
        ? `${v.ruleWidth} solid ${v.rule}`
        : `${v.ruleHairWidth} ${v.ruleStyle} ${v.ruleHair}`,
    }}
  />
);
