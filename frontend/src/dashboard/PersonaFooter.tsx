/**
 * Shared persona footer strip — the provenance line at the bottom of
 * every dashboard.
 *
 * Two problems this component exists to fix:
 *
 * 1. Each persona used to compose its own footer independently and
 *    printed a different subset of the station provenance fields:
 *    Everyday said ``Kanfei v1.0 · themeLabel · logged every 10 s``,
 *    Agriculture added ``console · FW · TX``, Weather nerd (per Design
 *    v46 §3) carried the complete strip.  A user switching personas
 *    saw three different provenance lines for the same station.
 *
 * 2. The wrapper's bottom padding used ``s(N)`` — the layout scale
 *    unit, which is derived from viewport height against each
 *    persona's own design height, so ``s(20)`` renders to a different
 *    physical pixel count on each of the three personas at the same
 *    viewport.  Even with ``margin-top: auto``, the footer's
 *    y-position drifted between personas.  ``st(N)`` uses ``--kt``,
 *    which is width-derived against the shared 1318 px content
 *    width, so identical physical px on every persona.
 *
 * All spacing here is expressed in ``st()``.  The persona wrappers
 * still pad their content in ``s()``, but the footer itself is now
 * consistent across all three.
 */

import React from 'react';
import { v, type, st, SectionLabel, fmtInt, CONTENT_CAP } from './primitives';
import type { DashboardData } from './types';
import { useIsMobile } from '../hooks/useIsMobile';

interface PersonaFooterProps {
  d: DashboardData;
  themeLabel: string;
  /** Persona-specific chips (Weather nerd's DB size, upload count,
   *  IPC status).  Render in the same mono-caps role as the shared
   *  chips, between ``archive`` and the theme label. */
  extraChips?: React.ReactNode;
}

/** Parse an ``HH:MM[:SS]`` string (the raw console clock format) to
 *  minute-of-day.  Returns null on missing / malformed input. */
const parseConsoleClock = (s: string | null | undefined): { hh: number; mm: number } | null => {
  if (!s) return null;
  const m = /^(\d{1,2}):(\d{2})/.exec(s);
  return m ? { hh: +m[1], mm: +m[2] } : null;
};

/** Wrapped signed drift in minutes on a 24-h clock — a console
 *  reading 23:58 against a browser at 00:03 is +5, not −1435. */
const wrappedDrift = (consoleMin: number, browserMin: number): number => {
  const raw = consoleMin - browserMin;
  if (raw > 720) return raw - 1440;
  if (raw < -720) return raw + 1440;
  return raw;
};

export const PersonaFooter: React.FC<PersonaFooterProps> = ({ d, themeLabel, extraChips }) => {
  const isMobile = useIsMobile();
  const consoleHM = parseConsoleClock(d.station.clock);
  const consoleStr = consoleHM
    ? `${String(consoleHM.hh).padStart(2, '0')}:${String(consoleHM.mm).padStart(2, '0')}`
    : '—';
  const now = new Date();
  const browserMin = now.getHours() * 60 + now.getMinutes();
  const driftMin = consoleHM ? wrappedDrift(consoleHM.hh * 60 + consoleHM.mm, browserMin) : null;
  const showDrift = driftMin != null && Math.abs(driftMin) >= 1;
  const warnDrift = driftMin != null && Math.abs(driftMin) >= 5;
  return (
  <div
    style={{
      display: 'flex',
      alignItems: 'center',
      gap: st(20),
      flexWrap: 'wrap',
      borderTop: `${v.ruleHairWidth} solid ${v.ruleHair}`,
      padding: `${st(12)} 0 0`,
      marginTop: 'auto',
      ...CONTENT_CAP,
    }}
  >
    <span
      style={{
        ...type('sectionLabel'),
        color: v.text,
        display: 'inline-flex',
        alignItems: 'center',
        gap: st(8),
      }}
    >
      <span
        aria-hidden
        style={{
          width: st(7),
          height: st(7),
          borderRadius: '50%',
          background: d.station.transmittersOk ? v.success : v.danger,
          display: 'inline-block',
        }}
      />
      {d.station.console ?? '—'}
      {d.station.model && ` · ${d.station.model}`}
      {d.station.firmware && ` · FW ${d.station.firmware}`}
    </span>
    <SectionLabel>
      archive {fmtInt(d.station.archiveRecords, ' rows')}
      {d.station.intervalSeconds != null && ` · ${Math.round(d.station.intervalSeconds / 60) || 1} min`}
    </SectionLabel>
    {extraChips}
    {themeLabel && <SectionLabel>{themeLabel}</SectionLabel>}
    {/* Clock line, all 24-hour, seconds and date dropped.
        ``station.clock`` was rendered as the console's raw
        ``HH:MM:SS`` while ``lastPoll`` went through
        ``toLocaleTimeString`` (12-hour) — two formats for the same
        instant, on the strip whose whole job is machine provenance.
        Naming the console-vs-browser drift turns what looked like a
        rendering lag into real station information.  Design v48 §3. */}
    {/* Phone drops the console-clock segment: it collides with the
        below-divider Console tile that carries the same field, and its
        null state renders a bare em-dash beside a populated last-poll,
        which reads as broken.  Desktop keeps the drift readout —
        that's where its width earns its own row. */}
    <SectionLabel style={{ marginLeft: 'auto' }}>
      {!isMobile && (
        <>
          console clock {consoleStr}
          {showDrift && (
            <span style={warnDrift ? { color: v.warning } : undefined}>
              {' · '}
              {Math.abs(driftMin!)} min {driftMin! > 0 ? 'ahead' : 'behind'}
            </span>
          )}
          {' · '}
        </>
      )}
      last poll {d.station.lastPoll || '—'}
    </SectionLabel>
  </div>
  );
};
