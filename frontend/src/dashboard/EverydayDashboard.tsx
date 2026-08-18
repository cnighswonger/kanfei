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
 * Geometry (frame 1600×1180, header 60, main padding 24px 30px 20px, gap 20):
 *   title row              51
 *   band A   739 / 547    787     left gap 20, right gap 18
 *   band B   739 / 547    150
 *   footer                 27
 */
import React from 'react';
import { v, type, SectionLabel, TileHeading, Row, Tile, tnum, fmt, fmtInt, fmtTime, s, scaleVar, CONTENT_CAP } from './primitives';
import type { DashboardData } from './types';
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
    }}
  >
    <div
      style={{
        ...scaleVar(1120),
        padding: `${s(24)} ${s(30)} ${s(20)}`,
        display: 'flex',
        flexDirection: 'column',
        gap: s(20),
        position: 'relative',
        isolation: 'isolate',
        minWidth: 0,
        boxSizing: 'border-box',
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
        bottom: s(60),
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

    {/* ── band A, 787 ─────────────────────────────────────────────────────── */}
    <div data-band="a" style={{ display: 'grid', gridTemplateColumns: BAND_COLS, gap: s(BAND_GAP), alignItems: 'start', ...CONTENT_CAP }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: s(20), minWidth: 0 }}>
        <div style={{ display: 'flex', gap: s(28), minHeight: s(205) }}>
          <HeroTemperatureTile d={d} style={{ width: s(340), flexShrink: 0 }} />
          <DerivedConditionsTile d={d} style={{ flex: 1, minWidth: 0 }} />
        </div>

        <HistoryChartTile d={d} style={{ minHeight: s(269) }} />

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: s(24), minHeight: s(159), alignItems: 'start' }}>
          {/* 1d titles this 'Rain ledger', not 'Rain' */}
          <RainTile d={d} title="Rain ledger" />
          <SolarUvTile d={d} />
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: s(18), minWidth: 0 }}>
        <BarometerTile d={d} style={{ minHeight: s(280) }} />
        <WindTile d={d} style={{ minHeight: s(220) }} />
        <AlmanacTile d={d} style={{ minHeight: s(159) }} />
      </div>
    </div>

    {/* ── band B, 150 ─────────────────────────────────────────────────────── */}
    <div data-band="b" style={{ display: 'grid', gridTemplateColumns: BAND_COLS, gap: s(BAND_GAP), minHeight: s(150), alignItems: 'start', ...CONTENT_CAP }}>
      <RainfallByHourTile d={d} />
      <ConsoleAndLinkTile d={d} />
    </div>

    {/* ── footer strip, 27 ────────────────────────────────────────────────── */}
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        borderTop: `${v.ruleWidth} solid ${v.rule}`,
        paddingTop: s(8),
        ...CONTENT_CAP,
      }}
    >
      <SectionLabel>
        Kanfei v{d.station.appVersion ?? '1.0.0'} · {themeLabel}
        {d.station.intervalSeconds != null && ` · logged every ${d.station.intervalSeconds} s`}
      </SectionLabel>
      <span style={{ ...type('sectionLabel'), ...tnum, color: v.textMuted }}>
        Last update {fmtTime(d.station.lastPoll)}
      </span>
    </div>
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
