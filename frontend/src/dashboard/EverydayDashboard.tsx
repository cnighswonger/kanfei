/**
 * Everyday dashboard — the composition, transcribed from the mock's measured DOM.
 *
 * This file IS the layout spec. Every number here was read off the rendered mock
 * (see TILE-CONTRACT.md); none of it is computed, and nothing decides a height at
 * runtime. If a height needs to change, it changes here, visibly, in one place.
 *
 * Structure (frame 1600×1180, header 60):
 *   title row              48
 *   band A   739 / 547     795
 *   band B   739 / 547     145
 *   footer                  26
 */
import React from 'react';
import { v, type, SectionLabel, tnum } from './primitives';
import type { DashboardData } from './types';
import {
  HeroTemperatureTile, DerivedConditionsTile, HistoryChartTile, BarometerTile,
  WindTile, RainTile, SolarUvTile, AlmanacTile, RainfallByHourTile, StationStatusTile,
} from './tiles';

/** Column ratio, as fr so it scales below 1600 while holding 739:547. */
const BAND_COLS = '739fr 547fr';
const BAND_GAP = 32;

export const EverydayDashboard: React.FC<{ d: DashboardData }> = ({ d }) => (
  <main
    data-dashboard="everyday"
    style={{
      padding: '22px 28px 20px',
      display: 'flex',
      flexDirection: 'column',
      gap: 20,
      // The plate is a page background owned by the theme; the dashboard must not
      // reserve space for it. Content ends where content ends.
      position: 'relative',
      isolation: 'isolate',
      minWidth: 0,
    }}
  >
    {/* ── title row, 48 ───────────────────────────────────────────────────── */}
    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 24 }}>
      <h2 style={{ ...type('heading'), color: v.text, margin: 0 }}>Current conditions</h2>
      <SectionLabel>
        {d.station.name}
        {d.station.elevationFt != null && ` · ${Math.round(d.station.elevationFt)} ft`}
        {d.station.intervalSeconds != null && ` · every ${d.station.intervalSeconds} s`}
      </SectionLabel>
    </div>

    {/* ── band A, 795 ─────────────────────────────────────────────────────── */}
    <div data-band="a" style={{ display: 'grid', gridTemplateColumns: BAND_COLS, gap: BAND_GAP, alignItems: 'start' }}>
      {/* left column — gap 20 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20, minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 28, height: 204 }}>
          <HeroTemperatureTile d={d} style={{ width: 340, flexShrink: 0 }} />
          <DerivedConditionsTile d={d} style={{ flex: 1, minWidth: 0 }} />
        </div>

        <HistoryChartTile d={d} style={{ height: 268 }} />

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, height: 157 }}>
          <RainTile d={d} />
          <SolarUvTile d={d} />
        </div>
      </div>

      {/* right column — gap 18, and the taller of the two: 280+220+157 sets band A */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 18, minWidth: 0 }}>
        <BarometerTile d={d} style={{ height: 280 }} />
        <WindTile d={d} style={{ height: 220 }} />
        <AlmanacTile d={d} style={{ height: 157 }} />
      </div>
    </div>

    {/* ── band B, 145 ─────────────────────────────────────────────────────── */}
    <div data-band="b" style={{ display: 'grid', gridTemplateColumns: BAND_COLS, gap: BAND_GAP, height: 145 }}>
      <RainfallByHourTile d={d} />
      <StationStatusTile d={d} />
    </div>

    {/* ── footer strip, 26 ────────────────────────────────────────────────── */}
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        borderTop: `1px ${v.ruleStyle} ${v.rule}`,
        paddingTop: 8,
      }}
    >
      <SectionLabel>
        {d.station.console} {d.station.model} · FW {d.station.firmware} ·{' '}
        <span style={{ color: d.station.transmittersOk ? v.success : v.danger }}>
          TX {d.station.transmittersOk ? 'ok' : 'fault'}
        </span>
      </SectionLabel>
      <span style={{ ...type('sectionLabel'), ...tnum, color: v.textMuted }}>
        Clock {d.station.clock} · last poll {d.station.lastPoll}
      </span>
    </div>
  </main>
);

export default EverydayDashboard;
