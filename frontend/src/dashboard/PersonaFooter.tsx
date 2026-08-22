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
import { v, type, st, SectionLabel, fmtInt, fmtTime, CONTENT_CAP } from './primitives';
import type { DashboardData } from './types';

interface PersonaFooterProps {
  d: DashboardData;
  themeLabel: string;
  /** Persona-specific chips (Weather nerd's DB size, upload count,
   *  IPC status).  Render in the same mono-caps role as the shared
   *  chips, between ``archive`` and the theme label. */
  extraChips?: React.ReactNode;
}

export const PersonaFooter: React.FC<PersonaFooterProps> = ({ d, themeLabel, extraChips }) => (
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
    <SectionLabel style={{ marginLeft: 'auto' }}>
      clock {d.station.clock ?? '—'} · last poll {fmtTime(d.station.lastPoll)}
    </SectionLabel>
  </div>
);
