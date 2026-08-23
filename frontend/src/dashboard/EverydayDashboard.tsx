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
import { v, type, SectionLabel, TileHeading, Row, Tile, fmt, fmtInt, fmtTime, s, st, scaleVar, CONTENT_CAP } from './primitives';
import type { DashboardData } from './types';
import { PersonaFooter } from './PersonaFooter';
import {
  HeroTemperatureTile, DerivedConditionsTile, HistoryChartTile, BarometerTile,
  WindTile, RainTile, SolarUvTile, AlmanacTile, RainfallByHourTile,
} from './tiles';

const BAND_COLS = '739fr 547fr';
const BAND_GAP = 32;

export const EverydayDashboard: React.FC<{ d: DashboardData; themeLabel: string }> = ({
  d,
  themeLabel,
}) => (
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
        mock; see ADAPTER.md if the page currently shows a page-sized engraving. */}
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

/**
 * Console & link — 1d's station tile.
 *
 * A TWO-COLUMN ruled table (261.7px each, 24px column gap), eight labelled rows,
 * NOT the single flowing strip that shipped. Its own title is 'Console & link'.
 * The clock and last poll are rows here; the footer carries 'Last update' only.
 */
export const ConsoleAndLinkTile: React.FC<{ d: DashboardData }> = ({ d }) => {
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

  return (
    <Tile id="station-status">
      <TileHeading>Console &amp; link</TileHeading>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: s(24), rowGap: 0 }}>
        {rows.map(([label, value], i) => (
          <Row key={label} label={label} value={value} last={i >= rows.length - 2} />
        ))}
      </div>
    </Tile>
  );
};

export default EverydayDashboard;
