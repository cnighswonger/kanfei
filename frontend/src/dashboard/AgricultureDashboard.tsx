/**
 * Agriculture dashboard — mock 3c (The Mammoth's Log).
 *
 * Measured from the mock DOM. Same primitives, same theme tokens, same scale
 * mechanism as Everyday — only the tile set and the composition differ.
 *
 * Geometry (frame 1600×990, header 60, main padding 22px 28px 20px, gap 16):
 *   title row              46
 *   band A   694 / 604    287     gap 24
 *   band B   3 × 425      478     gap 24
 *   footer                 27
 *   ────────────────────────────
 *   main content          928     ← the scale divisor, NOT 1120
 *
 * ⚠ The Agriculture frame is shorter than Everyday's, so it passes 928 to
 * `scaleVar()`. Reusing Everyday's 1120 would render this layout ~17% small.
 */
import React from 'react';
import {
  v, type, s, st, scaleVar, CONTENT_CAP, SectionLabel, TileHeading, Row, Tile,
  tnum, fmt, fmtInt, fmtTime, fs,
} from './primitives';
import type { DashboardData } from './types';
import { COMPASS_NAME } from './tiles';
import { PersonaFooter } from './PersonaFooter';
import WindRoseDial from '../components/charts/WindRoseDial';

export const AgricultureDashboard: React.FC<{ d: DashboardData; themeLabel: string }> = ({
  d,
  themeLabel,
}) => (
  <main
    data-dashboard="agriculture"
    style={{
      minWidth: 0,
      overflow: 'hidden',
      // Fill the shell's main area — see EverydayDashboard.
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
    }}
  >
    <div
      style={{
        ...scaleVar(928),
        // Bottom + side paddings in ``st()`` so the footer's
        // left, right and bottom edges match across personas.
        padding: `${s(22)} ${st(30)} ${st(20)}`,
        display: 'flex',
        flexDirection: 'column',
        gap: s(16),
        position: 'relative',
        isolation: 'isolate',
        minWidth: 0,
        boxSizing: 'border-box',
        // Fill the shell main area — see EverydayDashboard.
        flex: 1,
        minHeight: 0,
      }}
    >
      {/* Agriculture's plate — the consent engraving sits behind the
          advisory.  Design v49 §4: clip to the upper band and drop
          opacity to Everyday's 0.09.  Previously the plate ran the
          full height at 0.13 and washed the drift-risk, water-balance
          and field-schedule readouts (v46/v45 removed the tile fills
          that used to hide it).  ``bottom: 50%`` cuts the plate off
          above the lower band; ``contain`` at ``50% 15%`` keeps it
          anchored near the top of that remaining strip. */}
      <div
        aria-hidden
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: '50%',
          zIndex: -2,
          backgroundImage: 'var(--surface-plate-wide, var(--surface-plate))',
          backgroundSize: 'contain',
          backgroundPosition: '50% 15%',
          backgroundRepeat: 'no-repeat',
          opacity: 0.09,
          filter: 'sepia(0.55) contrast(1.05) saturate(0.9)',
          mixBlendMode: 'multiply',
        }}
      />

      {/* Content region — see EverydayDashboard for the rationale. */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          gap: s(16),
        }}
      >
      {/* ── title row, 46 ─────────────────────────────────────────────────── */}
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
        <h2 style={{ ...type('heading'), color: v.text, margin: 0 }}>Spray Advisory</h2>
        <SectionLabel>
          {d.station.name ?? '—'}
          {d.station.elevationFt != null && ` · ${Math.round(d.station.elevationFt)} ft`}
          {' · Open-Meteo hourly'}
        </SectionLabel>
      </div>

      {/* ── band A, 287 ───────────────────────────────────────────────────── */}
      {/* stretch, not start: band A tiles are BORDERED, and a row of boxes at
          unequal heights reads as sloppy — sharing a height lets the tallest
          content set it. Band B below is borderless and uses 'start'. */}
      <div style={{ display: 'grid', gridTemplateColumns: '694fr 604fr', gap: s(24), minHeight: s(287), alignItems: 'stretch', ...CONTENT_CAP }}>
        <SprayVerdictTile d={d} />
        <SprayWindowTile d={d} />
      </div>

      {/* ── band B, 478 ───────────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: s(24), minHeight: s(478), alignItems: 'start', ...CONTENT_CAP }}>
        <DriftRiskTile d={d} />
        <WaterBalanceTile d={d} />
        <FieldScheduleTile d={d} />
      </div>
      </div>

      {/* Shared provenance strip — see ``PersonaFooter.tsx``. */}
      <PersonaFooter d={d} themeLabel={themeLabel} />
    </div>
  </main>
);

/**
 * A window is a range of two times. The API hands back
 * '2026-08-16T19:00:00-04:00 – 2026-08-16T20:00:00-04:00' (60 characters), which
 * wraps to two lines and dwarfs its own label. Reduce each end to clock time.
 * Formatting belongs in the adapter; this is the guard.
 */
const fmtRange = (r: string | null | undefined): string => {
  if (!r) return '—';
  const parts = r.split(/\s*[–—-]\s*(?=\d{4}-)/);
  return parts.length === 2 ? `${fmtTime(parts[0])} – ${fmtTime(parts[1])}` : fmtTime(r);
};

/* ──────────────────────────────────────────────────── 1. verdict + checks */

/** Check names from spray_engine.py, in the order the mock lists them. */
const CHECK_ORDER: [string, string][] = [
  ['wind', 'Wind'],
  ['temperature', 'Temperature'],
  ['humidity', 'Humidity'],
  ['rain_free', 'Rain-free'],
];

/**
 * Pass/fail indicator for a check row.
 *
 * ✓ and ✕ set inline at row-value size are thin, light strokes on a paper ground
 * with an engraving behind it — legible in the mock's flat 1600px frame, not on a
 * real display. Set them a size up, at weight 700, in a fixed-width slot so all
 * four align down the column regardless of how long each limit string is.
 */
const CheckMark: React.FC<{ pass: boolean }> = ({ pass }) => (
  <span
    aria-label={pass ? 'passes' : 'fails'}
    style={{
      display: 'inline-block',
      width: s(20),
      marginLeft: s(4),
      textAlign: 'right',
      fontSize: st(17.5),
      fontWeight: 700,
      lineHeight: 1,
      color: pass ? v.success : v.danger,
    }}
  >
    {pass ? '✓' : '✕'}
  </span>
);

const VERDICT_TONE = (verdict: string | null | undefined) =>
  verdict === 'go' ? 'success' : verdict === 'marginal' ? 'warning' : 'danger';

export const SprayVerdictTile: React.FC<{ d: DashboardData }> = ({ d }) => {
  const sp = d.spray;
  // Boxed: band A tiles carry a solid 0.8px rule and 18/20 padding in
  // the mock.  Transparent fill — the rule alone is the container.
  // Band B tiles are open sections with no border, divided by their
  // heading underlines.
  return (
    <Tile
      id="spray-verdict"
      style={{
        border: `${v.ruleHairWidth} solid ${v.ruleHair}`,
        padding: `${s(18)} ${s(20)}`,
        gap: s(12),
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: s(12) }}>
        <SectionLabel>Product</SectionLabel>
        <span style={{ ...type('body', fs(12.5)), color: v.text }}>
          {/* The em-dash clause only appears when there IS a category — otherwise
              the line reads 'Fungicide (Protectant) — null'. */}
          {sp?.product
            ? [sp.product.name, sp.product.category].filter(Boolean).join(' — ')
            : '—'}
        </span>
      </div>

      {/* Verdict: serif italic 54px in the semantic colour.
          MARGINAL is the widest state at eight glyphs; the slot is
          pinned to that width so shorter states (GO, NO-GO) don't
          reflow the sentence beside them.  A layout that moves when
          the answer changes reads worse than one that runs slightly
          loose (Design v45 q1). */}
      <div style={{ display: 'flex', alignItems: 'center', gap: s(18) }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: s(4), minWidth: st(240) }}>
          {/* State the basis in the kicker so the reader knows this
              verdict scores live station values — the forecast strip
              on the right carries its own kicker for Open-Meteo
              hourly.  Two labelled instruments that can differ
              honestly, not one screen contradicting itself
              (Design v49 §2). */}
          <SectionLabel>Product · Station now</SectionLabel>
          <span
            style={{
              ...type('display', fs(54)),
              color: v[VERDICT_TONE(sp?.verdict) as 'success' | 'warning' | 'danger'],
              lineHeight: 1,
              display: 'inline-block',
            }}
          >
            {sp?.verdict ? sp.verdict.toUpperCase().replace('NOGO', 'NO-GO') : '—'}
          </span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: s(4), minWidth: 0 }}>
          {/* Verdict sentence — italic serif ~17 px, same voice as
              the hero Zambretti sentence (Design v45 q3). */}
          <span style={{ ...type('title', fs(17)), color: v.text, lineHeight: 1.2 }}>
            {sp?.verdictNote ?? 'No product selected'}
          </span>
          {/* Caution — an actionable constraint read immediately
              before deciding to spray.  Mono ~11 px, sentence case,
              copper marker at line head.  Not tracked caps (those
              are reserved for fixed metadata like model or window). */}
          {sp?.caution && (
            <span style={{ ...type('mono', fs(11)), color: v.text, letterSpacing: '0.2px', lineHeight: 1.4 }}>
              <span style={{ color: v.accent, marginRight: s(4) }}>▲</span>
              {sp.caution}
            </span>
          )}
        </div>
      </div>

      {/* All FOUR checks, always — see CHECK_ORDER. A product with no humidity
          constraint still gets its row, marked 'no limit'. Omitting it is
          ambiguous (did it pass, or was it not evaluated?) and it makes the tile
          change height from one product to the next. */}
      <div>
        {CHECK_ORDER.map(([name, label], i) => {
          const c = sp?.checks.find((x) => x.name === name);
          return (
            <Row
              key={name}
              label={label}
              value={
                c ? (
                  <>
                    {c.value} <span style={{ color: v.textMuted }}>{c.limit}</span>
                    <CheckMark pass={c.pass} />
                  </>
                ) : (
                  <span style={{ color: v.textMuted }}>no limit</span>
                )
              }
              last={i === CHECK_ORDER.length - 1}
            />
          );
        })}
      </div>
    </Tile>
  );
};

/* ───────────────────────────────────────────────────── 2. 24 h window strip */

export const SprayWindowTile: React.FC<{ d: DashboardData }> = ({ d }) => {
  const cells = d.spray?.window ?? [];
  const W = 640, H = 84;
  const tone = { go: v.success, marginal: v.warning, nogo: v.danger };

  return (
    <Tile
      id="spray-window"
      style={{
        border: `${v.ruleHairWidth} solid ${v.ruleHair}`,
        padding: `${s(18)} ${s(20)}`,
        gap: s(10),
      }}
    >
      <SectionLabel>Forecast · Next 24 hours</SectionLabel>

      {/* Cells at FULL opacity — any wash puts the scale out of step with its own
          legend swatches below. */}
      <svg viewBox={`0 0 ${W} ${H}`} style={{ display: 'block', width: '100%', height: s(84) }}>
        {cells.map((c, i) => (
          <rect key={i} x={i * 26.5} y={8} width={23} height={42} rx={1} fill={tone[c.state]} />
        ))}
        <line x1={0} y1={54} x2={W - 4} y2={54} stroke={v.ruleHair} strokeWidth={1} />
        {cells.map((c, i) =>
          i % 3 === 0 ? (
            <text key={`t${i}`} x={i * 26.5 + 11} y={74} textAnchor="middle" style={type('sectionLabel')} fill={v.chart.axis}>
              {c.label}
            </text>
          ) : null,
        )}
      </svg>

      <div style={{ display: 'flex', gap: s(16) }}>
        {([['Go', 'success'], ['Marginal', 'warning'], ['Blocked', 'danger']] as const).map(([label, key]) => (
          <span key={label} style={{ ...type('sectionLabel'), color: v.textSecondary, display: 'inline-flex', alignItems: 'center', gap: s(6) }}>
            <span style={{ width: s(9), height: s(9), background: v[key], display: 'inline-block' }} />
            {label}
          </span>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: s(14), marginTop: 'auto', paddingTop: s(10), borderTop: `${v.ruleHairWidth} ${v.ruleStyle} ${v.ruleHair}` }}>
        <div>
          <SectionLabel>Best window today</SectionLabel>
          {/* Green only for a real, still-usable window.  A past
              state ("None left today") stays in secondary ink so
              the page's most confident element isn't advice you
              can no longer act on (Design v49 §1). */}
          <div
            style={{
              ...type('mono', fs(17)),
              ...tnum,
              color: d.spray?.bestWindowToday && d.spray.bestWindowToday !== 'None left today'
                ? v.success
                : v.textSecondary,
            }}
          >
            {fmtRange(d.spray?.bestWindowToday)}
          </div>
        </div>
        <div>
          <SectionLabel>Next window</SectionLabel>
          <div style={{ ...type('mono', fs(17)), ...tnum, color: v.text }}>{fmtRange(d.spray?.nextWindow)}</div>
        </div>
      </div>
    </Tile>
  );
};

/* ─────────────────────────────────────────────────────────── 3. drift risk */

export const DriftRiskTile: React.FC<{ d: DashboardData }> = ({ d }) => {
  const bins = d.spray?.gustBins ?? [];
  const max = Math.max(1, ...bins);

  return (
    <Tile id="drift-risk" style={{ gap: s(8) }}>
      <TileHeading>Drift risk</TileHeading>

      <div style={{ display: 'flex', alignItems: 'center', gap: s(10), minHeight: s(180) }}>
        <div style={{ flexShrink: 0 }}>
          <WindRoseDial
            roseWeights={d.wind.roseWeights}
            directionDeg={d.wind.directionDeg}
            speedMph={d.wind.speedMph}
            size={250}
          />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: s(5), minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: s(6) }}>
            <span style={{ ...type('mono', fs(24)), ...tnum, color: v.text }}>{fmt(d.wind.speedMph, 0)}</span>
            <SectionLabel>mph {d.wind.directionLabel ?? ''}</SectionLabel>
          </div>
          {/* Direction detail + peak/gust — same shape as the
              Everyday wind tile.  Mono sub-line in secondary for
              context, mono value line with primary values and
              secondary times. */}
          <div style={{ paddingTop: s(9), borderTop: `${v.ruleHairWidth} ${v.ruleStyle} ${v.ruleHair}`, display: 'flex', flexDirection: 'column', gap: s(7) }}>
            {(d.wind.directionLabel || d.wind.directionDeg != null) && (
              <div style={{ ...type('mono', fs(11)), ...tnum, color: v.textSecondary, letterSpacing: '0.4px' }}>
                {d.wind.directionLabel && (COMPASS_NAME[d.wind.directionLabel] ?? d.wind.directionLabel)}
                {d.wind.directionLabel && d.wind.directionDeg != null && ' · '}
                {d.wind.directionDeg != null && `${Math.round(d.wind.directionDeg)}°`}
              </div>
            )}
            {/* Narrow readout column — stack Peak and Gust as two
                lines rather than forcing them onto one row with
                nowrap.  Value primary, time secondary; matches the
                Everyday wind tile's ink discipline without its
                width assumption. */}
            {d.wind.peakMph != null && (
              <div style={{ ...type('mono', fs(11)), ...tnum, color: v.text, letterSpacing: '0.6px' }}>
                Peak {fmt(d.wind.peakMph, 0)}{' '}
                {d.wind.peakAt && (
                  <span style={{ color: v.textSecondary }}>{fmtTime(d.wind.peakAt)}</span>
                )}
              </div>
            )}
            {d.wind.gustMph != null && (
              <div style={{ ...type('mono', fs(11)), ...tnum, color: v.text, letterSpacing: '0.6px' }}>
                Gust {fmt(d.wind.gustMph, 0)}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* viewBox matches the tile's own width (425 in the mock) so the bars span
          it. A 270-wide viewBox letterboxed into a wide column, leaving the
          histogram floating small and off-centre. */}
      <svg viewBox="0 0 425 100" style={{ display: 'block', width: '100%', height: s(82), marginTop: 'auto' }}>
        {bins.map((n, i) => {
          const h = (n / max) * 74;
          return <rect key={i} x={i * 47 + 4} y={80 - h} width={38} height={h} rx={1} fill={v.warning} opacity={0.75} />;
        })}
        <line x1={0} y1={80} x2={425} y2={80} stroke={v.ruleHair} strokeWidth={1} />
        {bins.map((_, i) => (
          <text key={`x${i}`} x={i * 47 + 23} y={94} textAnchor="middle" style={type('sectionLabel')} fill={v.chart.axis}>
            {i * 2 + 2}
          </text>
        ))}
      </svg>
      <SectionLabel style={{ textAlign: 'center' }}>wind frequency, mph, last 4 h</SectionLabel>
    </Tile>
  );
};

/* ────────────────────────────────────────────────────── 4. water balance */

export const WaterBalanceTile: React.FC<{ d: DashboardData }> = ({ d }) => {
  const w = d.spray?.water;
  const bal = w?.balanceIn ?? null;
  const bars = d.rain.hourlyIn ?? [];
  const max = Math.max(0.05, ...bars.map((n) => n ?? 0));

  return (
    <Tile id="water-balance" style={{ gap: s(8) }}>
      <TileHeading>Water balance</TileHeading>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: s(8), minHeight: s(44) }}>
        <span style={{ ...type('display', fs(44)), color: bal != null && bal < 0 ? v.danger : v.success, lineHeight: 1 }}>
          {bal == null ? '—' : `${bal < 0 ? '−' : '+'}${Math.abs(bal).toFixed(2)}`}
        </span>
        <SectionLabel>in, rain − ET, 7 days</SectionLabel>
      </div>

      <div>
        <Row label="Rain today / week" value={`${fmt(w?.rainTodayIn, 2)} / ${fmt(w?.rainWeekIn, 2)} in`} valueColor={v.sky} />
        <Row label="ET today / week" value={`${fmt(w?.etTodayIn, 3)} / ${fmt(w?.etWeekIn, 2)} in`} />
        <Row label="ET month / year" value={`${fmt(w?.etMonthIn, 3)} / ${fmt(w?.etYearIn, 3)} in`} />
        <Row label="Season rain" value={fmt(w?.seasonRainIn, 2, ' in')} last />
      </div>

      <svg viewBox="0 0 620 76" preserveAspectRatio="none" style={{ display: 'block', width: '100%', height: s(60), marginTop: 'auto' }}>
        {Array.from({ length: 24 }, (_, i) => {
          const val = bars[i] ?? 0;
          const h = val > 0 ? Math.max(2, (val / max) * 56) : 0;
          return <rect key={i} x={i * 25.8 + 2} y={58 - h} width={18} height={h} rx={1} fill={v.chart.rain} />;
        })}
        <line x1={0} y1={58} x2={620} y2={58} stroke={v.ruleHair} strokeWidth={1} />
      </svg>
      <div style={{ display: 'flex', justifyContent: 'space-between', ...type('sectionLabel'), color: v.chart.axis }}>
        <span>24h ago</span>
        <span>{max > 0.001 ? `${fmt(max, 2)} in peak` : 'no rain recorded'}</span>
        <span>now</span>
      </div>
    </Tile>
  );
};

/* ─────────────────────────────────────────────────── 5. field & schedule */

const STATUS_TONE = { go: 'success', pending: 'textSecondary', nogo: 'danger' } as const;

export const FieldScheduleTile: React.FC<{ d: DashboardData }> = ({ d }) => {
  const sp = d.spray;
  const cells: [string, React.ReactNode, string?][] = [
    ['Air', fmt(d.outside.tempF, 1, '°'), undefined],
    ['Humidity', fmt(d.outside.humidityPct, 0, '%'), undefined],
    ['Dew point', fmt(d.outside.dewPointF, 1, '°'), v.sky],
    ['Solar', fmtInt(d.solar.wm2), v.warning],
  ];

  return (
    <Tile id="field-schedule" style={{ gap: s(8) }}>
      <TileHeading>Field &amp; schedule</TileHeading>

      {/* Flat scan grid, four across — vertical hairlines separate the
          cells on their inner edges; no outer box, no fill.  Bordered
          boxes read as clickable, which these are not.  ``align-items:
          start`` so a borderless row starts at its content rather than
          stretching and opening voids inside cells (Design v45 q2). */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', alignItems: 'start' }}>
        {cells.map(([label, value, tone], i) => (
          <div
            key={label}
            style={{
              padding: `${s(2)} ${s(10)}`,
              minHeight: s(48),
              borderLeft: i === 0 ? 'none' : `${v.ruleHairWidth} ${v.ruleStyle} ${v.ruleHair}`,
            }}
          >
            <SectionLabel>{label}</SectionLabel>
            <div style={{ ...type('mono', fs(20)), ...tnum, color: tone ?? v.text }}>{value}</div>
          </div>
        ))}
      </div>

      <div>
        <SectionLabel style={{ marginBottom: s(6) }}>Scheduled</SectionLabel>
        {(sp?.schedule ?? []).map((r, i) => (
          <Row
            key={`${r.product}${i}`}
            label={`${r.product} · ${r.when}`}
            value={
              <span style={{ color: v[STATUS_TONE[r.status]] }}>
                {r.status === 'nogo' ? 'No-go' : r.status === 'go' ? 'Go' : 'Pending'}
              </span>
            }
            last={i === (sp?.schedule.length ?? 0) - 1}
          />
        ))}
      </div>

      <div style={{ marginTop: 'auto' }}>
        <SectionLabel style={{ marginBottom: s(6) }}>
          Last applications{sp?.driftRatePct != null && ` · ${Math.round(sp.driftRatePct)}% drift rate`}
        </SectionLabel>
        {(sp?.applications ?? []).map((a, i) => (
          <Row
            key={`${a.product}${i}`}
            label={`${a.product} · ${a.date}`}
            value={
              <span style={{ color: a.note ? v.danger : v.success }}>
                {'★'.repeat(Math.max(0, Math.min(5, a.stars)))}
                {a.note && ` ${a.note}`}
              </span>
            }
            last={i === (sp?.applications.length ?? 0) - 1}
          />
        ))}
      </div>
    </Tile>
  );
};

export default AgricultureDashboard;
