/**
 * FULL READOUT divider — Design v54 §3.
 *
 * Sits between each persona's reduced above-the-fold tile set and the
 * scrollable body at ≤768 px. Renders a 48 px full-width band on
 * ``surfaceSunken``, hairline top and bottom, holding ``FULL READOUT``
 * in ``sectionLabel`` (mono caps) with a dotted rule and a ``↓``.
 *
 * Not interactive. v54 §3: "tapping it may scroll, but the content
 * below is always in the document." That means no onClick, no
 * aria-expanded — the divider is chrome, not a control. The scroll
 * affordance is the ``↓`` glyph plus the natural browser scroll of
 * the below-divider content.
 *
 * Sized in natural px (48 for height, 10 for the label) per v54 §4 —
 * the phone tier bypasses ``s()`` and ``st()`` entirely.
 */
import React from 'react';

import { v } from './primitives';

export const FullReadoutDivider: React.FC = () => (
  <div
    role="separator"
    aria-label="Full readout below"
    style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: '12px',
      height: '48px',
      padding: '0 16px',
      background: v.sunken,
      borderTop: `${v.ruleHairWidth} solid ${v.ruleHair}`,
      borderBottom: `${v.ruleHairWidth} solid ${v.ruleHair}`,
      // Full-bleed inside the phone content wrapper (which sits on 16 px
      // side padding). The band reads across the full page width per
      // Design's mock, so we negate the wrapper padding.
      marginLeft: '-16px',
      marginRight: '-16px',
    }}
  >
    <span
      style={{
        fontFamily: "var(--type-sectionLabel-family, 'JetBrains Mono', monospace)",
        fontSize: '10px',
        fontWeight: 400,
        letterSpacing: '0.2em',
        textTransform: 'uppercase',
        color: v.textSecondary,
      }}
    >
      Full readout
    </span>
    <span
      aria-hidden
      style={{
        flex: 1,
        height: 0,
        borderTop: `${v.ruleHairWidth} ${v.ruleStyle} ${v.ruleHair}`,
      }}
    />
    <span
      aria-hidden
      style={{
        fontFamily: "var(--type-sectionLabel-family, 'JetBrains Mono', monospace)",
        fontSize: '12px',
        lineHeight: 1,
        color: v.textSecondary,
      }}
    >
      ↓
    </span>
  </div>
);

export default FullReadoutDivider;
