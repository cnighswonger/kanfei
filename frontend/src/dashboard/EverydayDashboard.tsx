/**
 * The Mammoth's Log — Everyday dashboard, mock 1d.
 *
 * Measured from the mock DOM. The composition is IDENTICAL to 1c (Glaisher's
 * Notebook) — Outside Air top-left, barometer top-right — because the paper themes
 * were deliberately synced to the Almanac arrangement. Only the token table and
 * four labelled details differ, all of them below.
 *
 * So: one layout component serves both paper themes. Do NOT fork this file per
 * theme; the theme supplies the fonts, rules, and inks.
 *
 * Geometry (frame 1600×1240, header 60, main padding 24px 30px 20px, gap 20).
 * The declared band heights below are LIVE-DOM measurements from the
 * authenticated view — the mock's numbers (787 / 150) undercounted every tile
 * once real data landed, and the scaleVar / minHeight budget was ~90 px light
 * so ``overflow: hidden`` on the content region clipped Console clock and Last
 * poll off the last tile.  Design v50 §1 remeasured against HEAD; update these
 * numbers again if a tile's content shape changes.
 *
 *   title row               51
 *   band A   739 / 547    ~845    left column taller: hero 270 + chart 357 + rain/solar 178 (+2*gap 40)
 *   band B   739 / 547    ~182    Console & link, 8 rows in 2 cols
 *   footer                  27
 */
import React from 'react';
import { v, type, SectionLabel, TileHeading, Row, Tile, fmt, fmtInt, fmtTime, s, st, scaleVar, mType, CONTENT_CAP } from './primitives';
import type { DashboardData } from './types';
import { PersonaFooter } from './PersonaFooter';
import { useIsMobile } from '../hooks/useIsMobile';
import { useIsTablet } from '../hooks/useIsTablet';
import { FullReadoutDivider } from './FullReadoutDivider';
import {
  HeroTemperatureTile, DerivedConditionsTile, HistoryChartTile, BarometerTile,
  WindTile, RainTile, SolarUvTile, AlmanacTile, RainfallByHourTile,
} from './tiles';

const BAND_COLS = '739fr 547fr';
const BAND_GAP = 32;

export const EverydayDashboard: React.FC<{ d: DashboardData; themeLabel: string }> = ({
  d,
  themeLabel,
}) => {
  // v54 phase 3a: gate the corner plate at phone width (§6). Above
  // 768 px behaves exactly as before.
  const isMobile = useIsMobile();
  const isTablet = useIsTablet();

  // v54 phase 3b: phone tier is an entirely different composition
  // — reduced tile set above a FULL READOUT divider, the existing
  // desktop tiles single-column below, all sized in natural px
  // (--k / --kt bypassed). Everything above 768 px keeps the
  // desktop layout untouched.
  if (isMobile) {
    return <EverydayMobileShell d={d} themeLabel={themeLabel} />;
  }

  // v54 phase 4b: middle tier (content 769-1213 = viewport 989-1433)
  // pairs the desktop's three-up right column of band A into a
  // two-column composition at natural type sizes, with the chart
  // full-width beneath.  Same tile bodies as desktop, rearranged
  // per §8.
  if (isTablet) {
    return <EverydayTabletShell d={d} themeLabel={themeLabel} />;
  }

  return (
  <main
    data-dashboard="everyday"
    style={{
      // No container-type: --k is derived from vh, which is always definite.
      // main just must not clip or stretch its child.
      minWidth: 0,
      overflow: 'hidden',
      // Fill the shell's main area so the inner scale wrapper can
      // grow to that exact height via ``flex: 1``.  Without this,
      // the persona sizes to its content and the footer sits at
      // whatever y the content stack ends at — which differs by
      // persona at any viewport where ``--k`` isn't the same for
      // all three (the floor-clamp region around 900-1200 vh).
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
    }}
  >
    <div
      style={{
        // Design height was declared 1120 against the mock, but every
        // band-A tile renders taller with live data — hero row ~270 vs
        // s(205), history chart ~357 vs s(269), rain/solar ~178 vs
        // s(159); Console & link's eight rows in a 2-col grid come
        // out at ~182 against s(150).  Total ~1230 in design space
        // against a 1120 budget, so ``overflow: hidden`` on the
        // content-region was clipping Console clock and Last poll off
        // the last tile.  Bumped to 1240 (measured 1230, rounded up
        // to the next 10) per Design v50 §1.
        ...scaleVar(1240),
        // Bottom + side paddings in ``st()`` so the footer's left,
        // right and bottom edges land at the same physical pixels
        // across personas (``s()`` is per-persona ``--k``, ``st()``
        // is shared ``--kt``).  Top padding stays per-persona.
        padding: `${s(24)} ${st(30)} ${st(20)}`,
        display: 'flex',
        flexDirection: 'column',
        gap: s(20),
        position: 'relative',
        isolation: 'isolate',
        minWidth: 0,
        boxSizing: 'border-box',
        // Fill the shell's main area exactly (not the viewport
        // minus a fallback chrome).  Combined with the parent
        // ``flex: 1`` above and the content-region wrapper below
        // (which absorbs overflow), the footer always sits at the
        // shell main's bottom edge regardless of persona content
        // height or ``--k`` clamp state.
        //
        // ``minHeight: 0`` is what makes ``flex: 1`` actually
        // constrain the wrapper to its allocated space — flex
        // items default to ``min-height: auto`` (content-sized),
        // so without this the wrapper grows past its allocation
        // whenever its content is taller.
        flex: 1,
        minHeight: 0,
      }}
    >
    {/* Corner plate — 400×280, bottom-right of MAIN, behind content.
        Not full-bleed, not on body, not position:fixed. Exact values from the
        mock; see ADAPTER.md if the page currently shows a page-sized engraving.

        v54 §6: off at phone width. At 328 px of content width there is
        no empty ground for a watermark to fall on, so any opacity puts
        it under a number. */}
    {!isMobile && (
      <div
        aria-hidden
        style={{
          position: 'absolute',
          right: 0,
          // Raised from ``bottom: s(60)`` — the plate at 400×280 sat
          // under band B's Console & link readouts (``Product 6351``,
          // ``Console battery 4.66 V``).  ``s(200)`` clears the band
          // B tiles and keeps the plate at the top of band B's row
          // (Design v50 §9).
          bottom: s(200),
          width: s(400),
          height: s(280),
          zIndex: -1,
          backgroundImage: 'var(--surface-plate)',
          backgroundSize: 'contain',
          backgroundPosition: 'right bottom',
          backgroundRepeat: 'no-repeat',
          opacity: 0.09,
          filter: 'sepia(0.62) contrast(1.05) saturate(0.85)',
          mixBlendMode: 'multiply',
        }}
      />
    )}

    {/* Content region — takes the flex slack from the outer wrapper
        and clips anything past its own height (viewports too short
        to fit the composition).  ``PersonaFooter`` is the next
        sibling and so always sits at the shell-main bottom edge,
        regardless of whether the content ran short of that height
        (footer pushed down by content-region's ``flex: 1``) or over
        (content-region clips, footer stays in view). */}
    <div
      style={{
        flex: 1,
        minHeight: 0,
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        gap: s(20),
      }}
    >
    {/* ── title row, 51 — carries a solid 1.6px rule beneath it ───────────── */}
    <div
      style={{
        display: 'flex',
        alignItems: 'baseline',
        justifyContent: 'space-between',
        gap: s(24),
        paddingBottom: s(8),
        borderBottom: `${v.ruleWidth} solid ${v.rule}`,
        ...CONTENT_CAP,
      }}
    >
      <h2 style={{ ...type('heading'), color: v.text, margin: 0 }}>Current Conditions</h2>
      {/* The theme name leads this line, then station and elevation. The render
          was showing only '· every 10 s' because station.name was null. */}
      <SectionLabel>
        {themeLabel}
        {d.station.name && ` · ${d.station.name}`}
        {d.station.elevationFt != null && ` · ${Math.round(d.station.elevationFt)} ft`}
      </SectionLabel>
    </div>

    {/* ── band A, ~845 (left column taller than right at start-align) ────── */}
    <div data-band="a" style={{ display: 'grid', gridTemplateColumns: BAND_COLS, gap: s(BAND_GAP), alignItems: 'start', ...CONTENT_CAP }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: s(20), minWidth: 0 }}>
        <div style={{ display: 'flex', gap: s(28), minHeight: s(270) }}>
          <HeroTemperatureTile d={d} style={{ width: s(340), flexShrink: 0 }} />
          <DerivedConditionsTile d={d} style={{ flex: 1, minWidth: 0 }} />
        </div>

        <HistoryChartTile d={d} style={{ minHeight: s(357) }} />

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: s(24), minHeight: s(178), alignItems: 'start' }}>
          {/* 1d titles this 'Rain ledger', not 'Rain' */}
          <RainTile d={d} title="Rain ledger" />
          <SolarUvTile d={d} />
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: s(18), minWidth: 0 }}>
        <BarometerTile d={d} style={{ minHeight: s(320) }} />
        <WindTile d={d} style={{ minHeight: s(250) }} />
        <AlmanacTile d={d} style={{ minHeight: s(159) }} />
      </div>
    </div>

    {/* ── band B, ~182 (Console & link, 8 rows in a 2-col grid) ─────────── */}
    <div data-band="b" style={{ display: 'grid', gridTemplateColumns: BAND_COLS, gap: s(BAND_GAP), minHeight: s(182), alignItems: 'start', ...CONTENT_CAP }}>
      <RainfallByHourTile d={d} />
      <ConsoleAndLinkTile d={d} />
    </div>
    </div>

    {/* Provenance strip — shared across the three personas so the
        same station reports the same fields regardless of view.
        See ``PersonaFooter.tsx`` for why spacing is in ``st()``. */}
    <PersonaFooter d={d} themeLabel={themeLabel} />
    </div>
  </main>
  );
};

// ─────────────────────────────────────────────────────────────── Mobile shell

/**
 * Everyday mobile tree — v54 phase 3b as revised by v55.
 *
 * ≤ 768 px: an entirely different composition than desktop.  Above
 * a FULL READOUT divider live four reduced blocks sized in natural
 * px per v54 §2: title + date/elevation kicker, hero air temp
 * (heroFigure) with RH/feels/dew on one mono line, Zambretti + hi/lo
 * chips, and a wind|rain paired row.
 *
 * Below the divider, the DETAIL tiles stack single-column, each
 * rendered inside a ``--k: 1px, --kt: 1px`` wrapper so
 * ``s(n)`` / ``st(n)`` resolve to natural px instead of the vh-clamp
 * floor.
 *
 * **The divider is a scroll marker, not two régimes.**  v55 §régime
 * makes this explicit: §4-§6 and §9 (natural px, no dials, no plate,
 * no pair grids) apply to the WHOLE phone document.  v54 phase 3b
 * originally read the divider as separating "reduced above" from
 * "desktop composition below," which reinstated the wheel, the rose,
 * the 2-col Console & link table and a duplicate hero.  Phase 5a
 * (#519) corrects the reading:
 *
 * - ``HeroTemperatureTile`` is NOT in the below-divider stream — it
 *   duplicates the above-divider reduced set (v55 item 2).
 * - ``BarometerTile``, ``WindTile`` and ``ConsoleAndLinkTile`` are
 *   rendered in ``compact`` mode below the divider: no dial, no
 *   rose, no 2-column pair grid (v55 items 3-4).
 * - ``overflowX: 'hidden'`` on this wrapper is a floor for any
 *   residual fixed pixel width so it clips a tile instead of shifting
 *   the whole document (v55 item 1).
 */
const EverydayMobileShell: React.FC<{ d: DashboardData; themeLabel: string }> = ({
  d,
  themeLabel,
}) => {
  const t = d.outside;
  const w = d.wind;
  const r = d.rain;
  const f = d.forecast;

  // Kicker: AUG 26, 2026 · <station> · 266 ft. Date leads per v54 §7.
  const kicker = [
    _fmtKickerDate(new Date()),
    d.station.name,
    d.station.elevationFt != null ? `${Math.round(d.station.elevationFt)} ft` : null,
  ].filter(Boolean).join(' · ');

  return (
    <main
      data-dashboard="everyday"
      data-mobile
      style={{
        // Bypass the scale units entirely at phone width. Every child
        // ``s(n)`` / ``st(n)`` now resolves to ``n px``.
        ['--k' as string]: '1px',
        ['--kt' as string]: '1px',
        // The mobile wrapper OWNS the vertical scroll; it's the shell
        // above (AppShell.tsx) that's flex: 1, and we take that height
        // then let the natural content flow past it.
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0,
        flex: 1,
        minHeight: 0,
        overflowY: 'auto',
        // Any scroll-into-view or hash-anchor jump inside this shell
        // leaves the top row clear of the fixed AppShell header (60 px
        // on paper themes; 56 + 4 gap on non-paper).
        scrollPaddingTop: '60px',
        // v55 §1 belt-and-braces: any residual fixed pixel width
        // inside a reused tile clips to the viewport rather than
        // shifting the whole document horizontally.  The individual
        // width sources have compact-mode gates (dial, rose, pair
        // grids), but this stops a missed one from becoming a
        // page-wide scrollbar.
        overflowX: 'hidden',
        // 12 px horizontal (down from 16) buys 8 px of content width
        // where the tiles need it — 328 → 336 at 360-viewport phones.
        padding: '16px 12px',
        boxSizing: 'border-box',
        gap: '20px',
      }}
    >
      {/* Title + kicker (v54 §7). Header stays showing the date until
          phase 3d drops it — no visible gap during 3b/3c. */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <h2 style={{ ...mType('pageTitle'), color: v.text, margin: 0 }}>Current Conditions</h2>
        <div style={{ ...mType('sectionLabel'), color: v.textSecondary }}>
          {kicker}
        </div>
      </div>

      {/* Hero air temperature (v54 §2: what is it like right now?) */}
      <section style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <div style={{ ...mType('sectionLabel'), color: v.textSecondary }}>Outside air</div>
        <div style={{ ...mType('heroFigure'), color: v.text, lineHeight: 0.95 }}>
          {fmt(t.tempF, 1)} <span style={{ ...mType('secondaryFigure'), color: v.accent }}>°F</span>
        </div>
        <div style={{ ...mType('monoRow'), color: v.text }}>
          RH {fmtInt(t.humidityPct, '%')}
          {t.feelsLikeF != null && ` · Feels ${fmt(t.feelsLikeF, 0)}°`}
          {t.dewPointF != null && ` · Dew ${fmt(t.dewPointF, 0)}°`}
        </div>
      </section>

      {/* Zambretti + hi/lo chips */}
      <section style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <div style={{ ...mType('noteTitle'), color: v.text }}>
          {f.zambretti ?? '—'}
        </div>
        {f.confidencePct != null && (
          <div style={{ ...mType('sectionLabel'), color: v.textSecondary }}>
            Zambretti · {f.confidencePct}% confidence
          </div>
        )}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          <MChip label="High" value={t.highF} tone={v.danger} />
          <MChip label="Low"  value={t.lowF}  tone={v.sky} />
        </div>
      </section>

      {/* Wind | Rain paired row (v54 §5: dial → number) */}
      <section style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <div style={{ ...mType('sectionLabel'), color: v.textSecondary }}>Wind</div>
          <div style={{ ...mType('secondaryFigure'), color: v.text, lineHeight: 1 }}>
            {fmtInt(w.speedMph)} <span style={{ ...mType('sectionLabel'), color: v.textSecondary }}>MPH {w.directionLabel ?? ''}</span>
          </div>
          {w.peakMph != null && (
            <div style={{ ...mType('sectionLabel'), color: v.textSecondary }}>
              Peak {fmtInt(w.peakMph)} · {fmtTime(w.peakAt)}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <div style={{ ...mType('sectionLabel'), color: v.textSecondary }}>Rain today</div>
          <div style={{ ...mType('secondaryFigure'), color: v.text, lineHeight: 1 }}>
            {fmt(r.todayIn, 2)} <span style={{ ...mType('sectionLabel'), color: v.textSecondary }}>IN</span>
          </div>
          <div style={{ ...mType('sectionLabel'), color: v.textSecondary }}>
            Rate {fmt(r.rateInPerHr, 2)} in/hr
          </div>
        </div>
      </section>

      <FullReadoutDivider />

      {/* Below-divider: single column of DETAIL tiles at natural-px
          scale.  v55 régime: the whole document below 768 follows
          §4-§6/§9 — natural px, no dials, no plate, no pair grids —
          not just the above-divider selection.
          v55 §2: ``HeroTemperatureTile`` is excluded because the
          above-divider set already renders the same hero + Zambretti
          + hi/lo chips inline.  The reduced set is a SELECTION, not
          a preview.
          v55 §5: ``BarometerTile`` / ``WindTile`` render in
          ``compact`` mode (dial and rose suppressed).
          v55 §9: ``ConsoleAndLinkTile`` collapses to single-column
          via ``compact`` too. */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', minWidth: 0 }}>
        <DerivedConditionsTile d={d} compact />
        <HistoryChartTile d={d} compact />
        <RainTile d={d} title="Rain ledger" />
        <SolarUvTile d={d} compact />
        <BarometerTile d={d} compact />
        <WindTile d={d} compact />
        <AlmanacTile d={d} />
        <RainfallByHourTile d={d} compact />
        <ConsoleAndLinkTile d={d} compact />
      </div>

      <PersonaFooter d={d} themeLabel={themeLabel} />
    </main>
  );
};

// Tone mirrors desktop ``Chip`` in ``tiles.tsx``: high in ``v.danger``
// warmth, low in ``v.sky`` cool, so the pair carries the same reading
// on phone that the paper header does on desktop.
const MChip: React.FC<{ label: string; value: number | null; tone?: string }> = ({ label, value, tone }) => (
  <div
    style={{
      border: `${v.ruleHairWidth} solid ${v.ruleHair}`,
      borderRadius: '2px',
      padding: '6px 10px',
      display: 'flex',
      alignItems: 'baseline',
      justifyContent: 'space-between',
      gap: '8px',
    }}
  >
    <span style={{ ...mType('sectionLabel'), color: v.textSecondary }}>{label}</span>
    <span style={{ ...mType('monoRow'), color: tone ?? v.text }}>
      {fmt(value, 0)}°
    </span>
  </div>
);

/* ─────────────────────────────────────────────── tablet composition (v54 §8) */

/**
 * Everyday at content-769–1213 (viewport 989–1433 with the fixed
 * 220 px sidebar).  §8 rule for this persona: "band A becomes hero
 * | derived+barometer with the chart full-width beneath; band B's
 * three tiles become two plus one."
 *
 *   header row (title | kicker)        — full width
 *   hero        | derived + barometer  — band A rearranged
 *   chart                              — full width
 *   rain        | solar                — band A's ledger row
 *   wind        | almanac              — the three-up "two-plus-one"
 *                                        pair, with rainfall/console
 *                                        below covering the "one"
 *   rainfall by hour                   — full width
 *   console & link                     — full width
 *
 * Uses the same ``--k`` / ``--kt`` = ``1px`` hoist as the phone
 * shell so the reused tiles render at their designed proportions
 * rather than the vh-clamped floor.  Corner plate off at this tier
 * — its ``top: s(60), right: 0`` positioning is tied to the
 * ``scaleVar(1120)`` outer wrapper which the shell bypasses.
 */
const EverydayTabletShell: React.FC<{ d: DashboardData; themeLabel: string }> = ({
  d,
  themeLabel,
}) => {
  // Kicker matches the desktop title row: date · station · elevation.
  // Header still carries date+time on tablet (phase 3d only drops it
  // at phone), so this repeats the date the way desktop does.
  const kicker = [
    _fmtKickerDate(new Date()),
    d.station.name,
    d.station.elevationFt != null ? `${Math.round(d.station.elevationFt)} ft` : null,
  ].filter(Boolean).join(' · ');

  return (
    <main
      data-dashboard="everyday"
      data-tablet
      style={{
        ['--k' as string]: '1px',
        ['--kt' as string]: '1px',
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0,
        flex: 1,
        minHeight: 0,
        overflowY: 'auto',
        padding: '20px 24px 24px',
        boxSizing: 'border-box',
        gap: '20px',
      }}
    >
      {/* Header row — full width, hairline under. */}
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          gap: '24px',
          paddingBottom: '8px',
          borderBottom: `${v.ruleWidth} solid ${v.rule}`,
        }}
      >
        <h2 style={{ ...type('heading'), color: v.text, margin: 0 }}>Current Conditions</h2>
        <SectionLabel>{kicker}</SectionLabel>
      </div>

      {/* Band A rearranged: hero | (derived + barometer stacked).
          alignItems: start so the right column's stacked height
          doesn't force the hero to grow. */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', alignItems: 'start' }}>
        <HeroTemperatureTile d={d} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', minWidth: 0 }}>
          <DerivedConditionsTile d={d} />
          <BarometerTile d={d} />
        </div>
      </div>

      {/* Chart — full width per §8.  Explicit minHeight because
          HistoryChartTile's plot area is a flex:1 child; without a
          parent height, it collapses to ~61 px of just the heading
          (Codex R1 on #516).  357 matches the desktop path's
          ``minHeight: s(357)`` (which resolves to 357 px at kt=1). */}
      <HistoryChartTile d={d} style={{ minHeight: 357 }} />

      {/* Ledger row — the existing 2-col rain / solar pair from
          desktop's band A left column. */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', alignItems: 'start' }}>
        <RainTile d={d} title="Rain ledger" />
        <SolarUvTile d={d} />
      </div>

      {/* Wind | Almanac — the "two" of the three-up "two-plus-one"
          from desktop's right column of band A.  Barometer was the
          "one" but it's already been pulled up alongside derived. */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', alignItems: 'start' }}>
        <WindTile d={d} />
        <AlmanacTile d={d} />
      </div>

      {/* Band B — both tiles full width at this content width.  The
          rainfall-by-hour tile is a horizontal strip and reads
          better wide; console-and-link's two-column internal grid
          works fine at any content width ≥ ~500 px. */}
      <RainfallByHourTile d={d} />
      <ConsoleAndLinkTile d={d} />

      <PersonaFooter d={d} themeLabel={themeLabel} />
    </main>
  );
};

function _fmtKickerDate(d: Date): string {
  // "Aug 26, 2026" → sectionLabel CSS uppercases to "AUG 26, 2026"
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

/**
 * Console & link — 1d's station tile.
 *
 * A TWO-COLUMN ruled table (261.7px each, 24px column gap), eight labelled rows,
 * NOT the single flowing strip that shipped. Its own title is 'Console & link'.
 * The clock and last poll are rows here; the footer carries 'Last update' only.
 */
export const ConsoleAndLinkTile: React.FC<{ d: DashboardData; compact?: boolean }> = ({ d, compact }) => {
  // Named ``stn`` so it doesn't shadow the ``s(n)`` scale helper used
  // for the ``columnGap: s(24)`` below.
  const stn = d.station;
  const rows: [string, React.ReactNode][] = [
    ['Firmware', stn.firmware],
    ['Product', stn.model],
    ['Transmitters', <span style={{ color: stn.transmittersOk ? v.success : v.danger }}>{stn.transmittersOk ? 'OK' : 'FAULT'}</span>],
    ['Console battery', fmt(stn.batteryVolts, 2, ' V')],
    ['CRC / timeouts', `${stn.crcErrors} / ${stn.timeouts}`],
    ['Archive records', fmtInt(stn.archiveRecords)],
    ['Console clock', stn.clock ?? '—'],
    ['Last poll', fmtTime(stn.lastPoll)],
  ];

  // v55 §9 / item 4: at phone width the pair grid collapses to a
  // single column of eight hairline-separated rows.  In the 2-col
  // grid the "last row" is the final 2 items; in the 1-col flow it's
  // just the final item.
  const cols = compact ? '1fr' : '1fr 1fr';
  const isLast = (i: number) =>
    compact ? i === rows.length - 1 : i >= rows.length - 2;

  return (
    <Tile id="station-status">
      <TileHeading>Console &amp; link</TileHeading>
      <div style={{ display: 'grid', gridTemplateColumns: cols, columnGap: s(24), rowGap: 0 }}>
        {rows.map(([label, value], i) => (
          <Row key={label} label={label} value={value} last={isLast(i)} />
        ))}
      </div>
    </Tile>
  );
};

export default EverydayDashboard;
