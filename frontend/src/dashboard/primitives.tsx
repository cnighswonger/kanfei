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

export const v = {
  bg: 'var(--color-bg)',
  surface: 'var(--color-bg-card)',
  sunken: 'var(--color-surface-sunken)',
  text: 'var(--color-text)',
  textSecondary: 'var(--color-text-secondary)',
  textMuted: 'var(--color-text-muted)',
  accent: 'var(--color-accent)',
  success: 'var(--color-success)',
  warning: 'var(--color-warning)',
  danger: 'var(--color-danger)',
  sky: 'var(--color-sky)',
  rule: 'var(--rule-strong)',
  ruleHair: 'var(--rule-hair)',
  ruleStyle: 'var(--rule-style, solid)',
  radiusCard: 'var(--radius-card)',
  needle: 'var(--color-barometer-needle, var(--color-accent))',
  gaugeTrack: 'var(--color-gauge-track)',
  chart: {
    trace: 'var(--chart-trace)',
    traceShadow: 'var(--chart-trace-shadow)',
    traceSecondary: 'var(--chart-trace-secondary)',
    gridMinor: 'var(--chart-grid-minor)',
    gridMajor: 'var(--chart-grid-major)',
    surface: 'var(--chart-surface)',
    axis: 'var(--chart-axis, var(--color-text-muted))',
    rain: 'var(--chart-series-rain)',
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

export const type = (role: Role, overrides: React.CSSProperties = {}): React.CSSProperties => ({
  fontFamily: `var(--type-${role}-family)`,
  fontSize: `var(--type-${role}-size)`,
  fontWeight: `var(--type-${role}-weight)` as unknown as number,
  fontStyle: `var(--type-${role}-style, normal)`,
  letterSpacing: `var(--type-${role}-tracking, 0)`,
  textTransform: `var(--type-${role}-transform, none)` as React.CSSProperties['textTransform'],
  ...overrides,
});

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

/** Tracked mono caps. Every tile heading and every unit caption is one of these. */
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
      borderBottom: last ? 'none' : `1px ${v.ruleStyle} ${v.ruleHair}`,
    }}
  >
    <span style={{ ...type('body'), color: v.textSecondary }}>{label}</span>
    <span style={{ ...type('mono'), ...tnum, color: valueColor }}>{value}</span>
  </div>
);

/** Section divider under a tile heading — the strong rule, not the hairline. */
export const Rule: React.FC<{ strong?: boolean }> = ({ strong }) => (
  <div style={{ borderBottom: `1px ${v.ruleStyle} ${strong ? v.rule : v.ruleHair}` }} />
);
