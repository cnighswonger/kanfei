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

/** Measured from mock 1d. These ARE the design; the vars only allow overrides. */
const ROLE: Record<Role, {
  family: string; size: string; weight: number; style: string; tracking: string; transform: string;
}> = {
  display:      { family: "'Source Serif 4', Georgia, serif", size: '104px', weight: 600, style: 'italic', tracking: 'normal', transform: 'none' },
  heading:      { family: "'Source Serif 4', Georgia, serif", size: '30px',  weight: 600, style: 'italic', tracking: 'normal', transform: 'none' },
  title:        { family: "'Source Serif 4', Georgia, serif", size: '17px',  weight: 600, style: 'italic', tracking: 'normal', transform: 'none' },
  body:         { family: "'Inter', sans-serif",              size: '14px',  weight: 400, style: 'normal', tracking: 'normal', transform: 'none' },
  mono:         { family: "'JetBrains Mono', monospace",      size: '14px',  weight: 400, style: 'normal', tracking: 'normal', transform: 'none' },
  sectionLabel: { family: "'JetBrains Mono', monospace",      size: '10px',  weight: 400, style: 'normal', tracking: '2px',    transform: 'uppercase' },
};

export const type = (role: Role, overrides: React.CSSProperties = {}): React.CSSProperties => {
  const f = ROLE[role];
  return {
    fontFamily: `var(--type-${role}-family, ${f.family})`,
    fontSize: `var(--type-${role}-size, ${f.size})`,
    fontWeight: `var(--type-${role}-weight, ${f.weight})` as unknown as number,
    fontStyle: `var(--type-${role}-style, ${f.style})`,
    letterSpacing: `var(--type-${role}-tracking, ${f.tracking})`,
    textTransform: `var(--type-${role}-transform, ${f.transform})` as React.CSSProperties['textTransform'],
    ...overrides,
  };
};

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
  height?: number;
  style?: React.CSSProperties;
  children: React.ReactNode;
}> = ({ id, height, style, children }) => (
  <section
    data-tile-id={id}
    style={{
      height,
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
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
      paddingBottom: 5,
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
      gap: 12,
      padding: '7px 0',
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
