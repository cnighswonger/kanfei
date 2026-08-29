/**
 * Weather nerd dashboard — mock 2b.
 *
 * Measured from the mock DOM. Same primitives, same tokens, same scale mechanism.
 *
 * Geometry (frame 1600×990, header 60, main padding 20px 24px 24px, gap 16):
 *   stat row   4 × 321    147     gap 16
 *   chart                 341
 *   three-up   406/406/487 293    gap 16
 *   footer                 42
 *   ─────────────────────────────
 *   main content          928     ← same as Agriculture, not Everyday's 1120
 *
 * The persona's premise: every tile here shows something DERIVED, not something a
 * sensor read directly. Pressure with its 3 h rate, theta-e, forecast agreement,
 * reception quality, calibration offset against a reference station, METAR. That's
 * why the four stat cards lead — they're the four numbers a station owner checks
 * to decide whether to trust the rest.
 */
import React from 'react';
import {
  v, type, s, st, fs, scaleVar, CONTENT_CAP, SectionLabel, TileHeading, Row, Tile, tnum, fmt, fmtInt, decimate, niceTicks, mType,
} from './primitives';
import type { DashboardData, NerdResolution } from './types';
import { useIsMobile } from '../hooks/useIsMobile';
import { useIsTablet } from '../hooks/useIsTablet';
import { PersonaFooter } from './PersonaFooter';
import { FullReadoutDivider } from './FullReadoutDivider';
import { pathFor } from '../utils/gauges';
import WindRoseDial from '../components/charts/WindRoseDial';

const DESIGN_HEIGHT = 928;

export const WeatherNerdDashboard: React.FC<{
  d: DashboardData;
  themeLabel: string;
  onResolutionChange?: (r: NerdResolution) => void;
}> = ({ d, themeLabel, onResolutionChange }) => {
  // v54 phase 3a: gate the right-side plate at phone width (§6).
  const isMobile = useIsMobile();
  const isTablet = useIsTablet();

  // v54 phase 3d: the phone composition leads with "what is the station
  // doing?" — pressure premise + Zambretti/NWS + theta-e | reception
  // paired row above the FULL READOUT divider; chart, wind table,
  // solar bars and extremes stack below.
  if (isMobile) {
    return (
      <WeatherNerdMobileShell
        d={d}
        themeLabel={themeLabel}
        onResolutionChange={onResolutionChange}
      />
    );
  }

  // v54 phase 4c: middle tier (content 769-1213 = viewport 989-1433)
  // pairs the desktop's four-up stat row into a 2×2 grid, drops the
  // chart to full width, and folds the three-up into a wind|solar
  // pair + full-width console-extremes (§8's "two plus one" rule).
  // ConsoleExtremesTile switches to single-column via ``compact`` per
  // §9 so year-highs and reference-station values don't clip.
  if (isTablet) {
    return (
      <WeatherNerdTabletShell
        d={d}
        themeLabel={themeLabel}
        onResolutionChange={onResolutionChange}
      />
    );
  }

  return (
  <main
    data-dashboard="weather_nerd"
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
        ...scaleVar(DESIGN_HEIGHT),
        // Bottom + side paddings in ``st()`` so the footer's
        // left, right and bottom edges match across personas.
        padding: `${s(20)} ${st(30)} ${st(20)}`,
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
      {/* Corner plate, right-anchored to the chart band.  v46 §2
          removed ``ConsoleExtremesTile``'s fill, so the old
          bottom-anchored plate now shows through the extremes table
          and the METAR block.  Move the plate up to sit against the
          chart tile only: ``top: s(163)`` = below the stat row + gap
          (147 + 16), ``height: s(340)`` = chart minHeight, so the
          plate's bottom edge lands at the chart / three-up boundary
          and never bleeds into the three-up's data.  Design v48 §4. */}
      {/* v54 §6: plate off at phone width. */}
      {!isMobile && (
      <div
        aria-hidden
        style={{
          position: 'absolute',
          right: 0,
          top: s(163),
          width: s(380),
          height: s(340),
          zIndex: -2,
          backgroundImage: 'var(--surface-plate)',
          backgroundSize: 'contain',
          backgroundPosition: 'right bottom',
          backgroundRepeat: 'no-repeat',
          opacity: 'var(--surface-plate-opacity, 0.10)',
          filter: 'var(--surface-plate-filter, none)',
          mixBlendMode: 'var(--surface-plate-blend, normal)' as React.CSSProperties['mixBlendMode'],
        }}
      />
      )}

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
      {/* ── stat row, 147 ─────────────────────────────────────────────────── */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: s(16),
          minHeight: s(147),
          // start, not stretch (Design v46 §2).  Borderless cells shouldn't
          // stretch — a stretched borderless cell opens margin-top: auto voids
          // inside itself.  The 'shared instrument-row height' argument only
          // held while the cells were boxes; once they aren't, stretch is the
          // wrong default.
          alignItems: 'start',
          ...CONTENT_CAP,
        }}
      >
        <PressureCard d={d} />
        <ThetaECard d={d} />
        <ForecastAgreementCard d={d} />
        <ReceptionCard d={d} />
      </div>

      {/* ── multi-series chart, 341 ───────────────────────────────────────── */}
      <NerdChartTile d={d} onResolutionChange={onResolutionChange} />

      {/* ── three-up, 293 ────────────────────────────────────────────────── */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '406fr 406fr 487fr',
          gap: s(16),
          minHeight: s(293),
          // start, not stretch (Design v46 §2).  With the tiles now
          // borderless — separated only by their TileHeading underlines —
          // stretching them would open margin-top: auto voids with no
          // box to contain them, exactly the failure mode the old
          // comment warned against for open rows.
          alignItems: 'start',
          ...CONTENT_CAP,
        }}
      >
        <WindRoseTile d={d} />
        <SolarEnergyTile d={d} />
        <ConsoleExtremesTile d={d} />
      </div>
      </div>

      {/* Shared provenance strip — see ``PersonaFooter.tsx``.  Weather
          nerd carries three extra chips (DB size, upload targets, IPC
          status) that the other personas don't have. */}
      <PersonaFooter
        d={d}
        themeLabel={themeLabel}
        extraChips={
          <>
            {d.nerd?.dbSizeMB != null && <SectionLabel>DB {fmt(d.nerd.dbSizeMB, 1, ' MB')}</SectionLabel>}
            {d.nerd?.uploadTargets && <SectionLabel>{d.nerd.uploadTargets} uploading</SectionLabel>}
            {d.nerd?.ipcStatus && <SectionLabel>{d.nerd.ipcStatus}</SectionLabel>}
          </>
        }
      />
    </div>
  </main>
  );
};

/* ────────────────────────────────────────────────────────── the stat cards */

/**
 * Stat card. Four lines: kicker, big derived figure, a mono qualifier in a
 * meaningful colour, then one line of plain-language provenance.
 *
 * That last line is the persona's whole point — a nerd wants to know *how* the
 * number was arrived at, so every card says where it came from.
 */
/** Four derived readouts in one scanning row — hairline-separated,
 *  no boxes.  Design v46 §2 applies v45's flat-cell treatment here:
 *  bordered cards on ``v.surface`` read as four clickable things,
 *  which they are not.  ``border: 'none'`` is set explicitly because
 *  ``Tile`` publishes ``border: var(--tile-border, none)`` and the
 *  dark theme fills that token — an implicit-omit would re-box the
 *  cells on that theme. */
const StatCell: React.FC<{
  id: string;
  kicker: string;
  first?: boolean;
  children: React.ReactNode;
}> = ({ id, kicker, first, children }) => (
  <Tile
    id={id}
    style={{
      border: 'none',
      borderLeft: first ? 'none' : `${v.ruleHairWidth} solid ${v.ruleHair}`,
      background: 'none',
      padding: `${s(4)} ${s(20)} ${s(4)} ${first ? '0px' : s(20)}`,
      gap: s(4),
    }}
  >
    <SectionLabel>{kicker}</SectionLabel>
    {children}
  </Tile>
);

/**
 * The one headline figure per card.
 *
 * ``display``, not ``mono`` — matching Everyday's hero temperature and
 * Agriculture's NO-GO and water-balance figures.  The mocks draw a
 * consistent distinction:
 *
 *   serif italic  = the screen's headline or verdict figure
 *   mono tabular  = instrument readouts, tables, axes
 *
 * Built as mono, this screen was the only one of the three with no serif
 * numerals anywhere, so Glaisher's Notebook lost its voice on exactly one
 * persona.  These four cards ARE this screen's headline figures — it has
 * no single hero — so they take the display role.
 *
 * No fontWeight override: IM Fell English ships in one weight, and IBM
 * Plex Mono is loaded at 400/500/600 only, so the old ``fontWeight: 700``
 * was being synthesised by the browser — a smeared faux-bold that read
 * as a fourth typeface.
 */
const BigFigure: React.FC<{ children: React.ReactNode; color?: string; size?: number }> = ({ children, color = v.text, size = 28 }) => (
  <div style={{ ...type('display', fs(size)), ...tnum, color, lineHeight: 1.05 }}>{children}</div>
);

/** Plain-language provenance line — body 11px, secondary ink. */
const Provenance: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ ...type('body', fs(11)), color: v.textSecondary, lineHeight: 1.4, textWrap: 'pretty' }}>{children}</div>
);

export const PressureCard: React.FC<{ d: DashboardData }> = ({ d }) => {
  const t = d.barometer.trendInHgPer3h;
  const arrow = t == null ? '' : t > 0.005 ? '↑' : t < -0.005 ? '↓' : '→';
  const pu = d.units.pressure;
  const main = pu === 'hPa' ? d.barometer.hPa : d.barometer.inHg;
  const mainDigits = pu === 'hPa' ? 1 : 2;
  const trendConverted = t == null ? null : pu === 'hPa' ? t * 33.8639 : t;
  const trendDigits = pu === 'hPa' ? 1 : 3;
  const trendUnit = pu === 'hPa' ? 'hPa' : 'in';
  return (
    <StatCell id="nerd-pressure" kicker="Pressure" first>
      {/* Pressure with its 3-h rate is the persona's premise number;
          it leads the stat row at ``fs(44)`` (Design v46 §8).  User's
          unit choice controls which of ``inHg`` / ``hPa`` leads. */}
      <BigFigure size={44}>{fmt(main, mainDigits)}</BigFigure>
      {/* Rate is neutral in ink — ``success``/``danger`` on this
          screen mean station health (reception %, transmitters ok,
          calibration tolerance).  Falling pressure is weather, not
          a fault; colouring it red was the dashboard editorialising.
          The ↑ ↓ → glyph carries direction unambiguously
          (Design v46 §9). */}
      <div style={{ ...type('mono', fs(12)), ...tnum, color: v.textSecondary }}>
        {trendConverted == null
          ? '—'
          : `${arrow} ${trendConverted > 0 ? '+' : ''}${trendConverted.toFixed(trendDigits)} ${trendUnit}/3h`}
      </div>
      {/* ``hPa`` (or the alternate) prints unconditionally — it's a
          unit conversion of the display figure, not a duplicate.
          Altimeter and SLP filter out when they agree with the
          station reading at rounding precision so the line stops
          restating the display figure twice more.  Design v48 §2
          filter kept for altimeter / SLP; v50 §6 restored the
          alternate-unit line that over-suppressed under v48 §2. */}
      <Provenance>
        {[
          pu === 'hPa'
            ? d.barometer.inHg != null && `${fmt(d.barometer.inHg, 2)} inHg`
            : d.barometer.hPa != null && `${fmt(d.barometer.hPa, 1)} hPa`,
          d.nerd?.altimeterInHg != null &&
            Math.abs(d.nerd.altimeterInHg - (d.barometer.inHg ?? 0)) >= 0.005 &&
            `altimeter ${fmt(d.nerd.altimeterInHg, 2)} inHg`,
          d.nerd?.seaLevelHPa != null &&
            Math.abs(d.nerd.seaLevelHPa - (d.barometer.hPa ?? 0)) >= 0.05 &&
            `SLP ${fmt(d.nerd.seaLevelHPa, 1)} hPa`,
        ].filter(Boolean).join(' · ')}
      </Provenance>
    </StatCell>
  );
};

export const ThetaECard: React.FC<{ d: DashboardData }> = ({ d }) => (
  <StatCell id="nerd-theta-e" kicker="Theta-E">
    <BigFigure>{fmt(d.outside.thetaEK, 1)}</BigFigure>
    <div style={{ ...type('mono', fs(12)), ...tnum, color: v.textSecondary }}>
      K
      {d.nerd?.thetaEDelta != null && ` · ${d.nerd.thetaEDelta > 0 ? '+' : ''}${fmt(d.nerd.thetaEDelta, 1)} since 06Z`}
    </div>
    <Provenance>
      Equivalent potential temperature · from temp, dew point and pressure
      {d.nerd?.mixingRatioGKg != null && ` · mixing ratio ${fmt(d.nerd.mixingRatioGKg, 1)} g/kg`}
      {d.nerd?.lclFt != null && ` · LCL ~${fmtInt(d.nerd.lclFt)} ft`}
    </Provenance>
  </StatCell>
);

export const ForecastAgreementCard: React.FC<{ d: DashboardData }> = ({ d }) => (
  <StatCell id="nerd-agreement" kicker="Zambretti / NWS">
    {/* Zambretti sentence — italic serif, same voice as the hero
        Zambretti and Spray's verdictNote.  The rest of the stat
        row is display-scale figures; this card's headline is a
        sentence, and ``type('title')`` is the sentence form of
        the same italic-serif voice (Design v46 §8). */}
    <div style={{ ...type('title'), color: v.text, lineHeight: 1.2, textWrap: 'pretty' }}>
      {d.forecast.zambretti ?? '—'}
    </div>
    <div style={{ ...type('mono', fs(12)), ...tnum, color: v.accent }}>
      {d.forecast.confidencePct != null && `${Math.round(d.forecast.confidencePct)}% confidence`}
      {d.nerd?.nwsAgrees != null && ` · NWS ${d.nerd.nwsAgrees ? 'agrees' : 'differs'}`}
    </div>
    {d.nerd?.agreementRate30d != null && (
      <Provenance>Zambretti and NWS have agreed {Math.round(d.nerd.agreementRate30d)}% of the last 30 days</Provenance>
    )}
  </StatCell>
);

export const ReceptionCard: React.FC<{ d: DashboardData }> = ({ d }) => {
  const r = d.nerd?.reception;
  const pct = r?.pct ?? null;
  const tone = pct == null ? v.text : pct >= 98 ? v.success : pct >= 92 ? v.warning : v.danger;
  return (
    <StatCell id="nerd-reception" kicker={`Reception · ${r?.windowLabel ?? 'last hour'}`}>
      <BigFigure color={tone}>
        {pct == null ? '—' : fmt(pct, 1)}
        {pct != null && <span style={{ ...type('display', fs(16)), color: v.textSecondary }}>%</span>}
      </BigFigure>
      {/* Counter line carries its own scope word — the kicker
          ``windowLabel`` describes the percentage above (which is
          averaged over that window in the adapter), but ``received``
          / ``missed`` / ``CRC`` / ``resync`` are the console's raw
          RXCHECK totals since last reset.  Without ``since reset``,
          23,078 received under a ``last hour`` kicker read as an
          impossible number.  Design v48 §1. */}
      <div style={{ ...type('mono', fs(11)), ...tnum, color: v.textSecondary }}>
        {fmtInt(r?.received, ' received since reset')} · {fmtInt(r?.missed, ' missed')} · CRC {r?.crcErrors ?? '—'} · resync{' '}
        {r?.resyncs ?? '—'}
      </div>
    </StatCell>
  );
};

/* ─────────────────────────────────────────────── the multi-series chart */

const CW = 660, CH = 250, PL = 52, PT = 14, PB = 26;
/** Gridlines stop short of the gutter: at 3× horizontal scale a line
 *  ending flush against a label reads as an extra character ("90"
 *  became "9I" in review). */
const GRID_INSET = 8;

export const NerdChartTile: React.FC<{
  d: DashboardData;
  onResolutionChange?: (r: NerdResolution) => void;
  style?: React.CSSProperties;
  compact?: boolean;
}> = ({ d, onResolutionChange, style, compact }) => {
  const PR = 52;
  // Bin to ~600 points first — see decimate() in primitives.tsx.  Raw
  // 8k-sample series at 0.1 °F resolution over ~2000 px would render
  // as a staircase, not a trace.
  const temps = decimate(d.history.tempF).filter((n): n is number => n != null);
  const dews = decimate(d.history.dewPointF).filter((n): n is number => n != null);
  // Pressure comes off the console in 0.01 inHg steps — a typical
  // 0.2 in daily span holds only ~20 distinct values.  Binned to 600
  // each value repeats ~30× and draws as a stair-step tread.  200 is
  // enough to render smoothly without over-plotting.
  const pu = d.units.pressure;
  const baroInHg = decimate(d.nerd?.historyInHg ?? [], 200).filter((n): n is number => n != null);
  // Honor the user's unit choice on the right axis.  Convert once at
  // series construction; the rest of the axis math (pad, lo/hi, tick
  // formatting) then works in whatever unit the reader picked.
  const baro = pu === 'hPa' ? baroInHg.map((v) => v * 33.8639) : baroInHg;
  const baroTickDigits = pu === 'hPa' ? 1 : 2;
  const baroFallbackLo = pu === 'hPa' ? 29.8 * 33.8639 : 29.8;
  const baroFallbackHi = pu === 'hPa' ? 30.2 * 33.8639 : 30.2;
  const baroMinPad = pu === 'hPa' ? 0.04 * 33.8639 : 0.04;

  // Temperature and dew point share a domain; pressure gets its own right axis —
  // a 0.35 inHg span and a 30 °F span cannot share a scale meaningfully.
  const all = [...temps, ...dews];
  const pad = all.length ? Math.max(2, (Math.max(...all) - Math.min(...all)) * 0.12) : 2;
  const lo = all.length ? Math.min(...all) - pad : 0;
  const hi = all.length ? Math.max(...all) + pad : 1;
  const bPad = baro.length ? Math.max(baroMinPad, (Math.max(...baro) - Math.min(...baro)) * 0.2) : baroMinPad;
  const bLo = baro.length ? Math.min(...baro) - bPad : baroFallbackLo;
  const bHi = baro.length ? Math.max(...baro) + bPad : baroFallbackHi;

  const t = temps.length ? pathFor(temps, PL, CW - PR, PT, CH - PB, lo, hi) : null;
  const dw = dews.length ? pathFor(dews, PL, CW - PR, PT, CH - PB, lo, hi) : null;
  const bp = baro.length ? pathFor(baro, PL, CW - PR, PT, CH - PB, bLo, bHi) : null;

  // Round-number ticks, not equal divisions of the data range — see niceTicks().
  //
  // ``inPlot()`` is a guard, not decoration: a tick whose mapped y falls
  // outside the plot box must not render.  In an earlier render a stray
  // ``1`` appeared between the 90 and 80 labels — an out-of-domain tick
  // drawn at a position no gridline occupied, which reads as a rendering
  // fault rather than an axis.  Same guard fixes the right axis, which
  // was showing only 30.00 and 29.90 where a 0.05 step over that range
  // should give four or five.
  //
  // ``all.length`` / ``baro.length`` gates:  don't emit fallback ticks
  // (``lo=0, hi=1`` → ``[0.0, 0.2, 0.4, ..., 1.0]`` rendered as
  // ``"0","0","0","1","1","1"`` with COLLIDING keys) before the fetch
  // resolves.  Duplicate keys make React reconcile-by-position, which
  // in turn leaves those fallback spans in the DOM after real data
  // arrives — Chris caught four stray ``0``/``1`` labels on the temp
  // axis in the 17:xx render.
  const inPlot = (y: number) => y >= PT - 1 && y <= CH - PB + 1;
  const left = all.length
    ? niceTicks(lo, hi, 5)
        .map((val, i) => ({
          key: `T${i}`,
          y: (CH - PB) - ((val - lo) / (hi - lo)) * (CH - PB - PT),
          label: fmt(val, 0),
        }))
        .filter((g) => inPlot(g.y))
    : [];
  // Phone strips the whole-inch part (``.20``, ``.15``, ``.10``) so
  // the label fits its narrow right band without overrunning the
  // plot; the whole-inch mark (``30.00``) reads from the emphasized
  // gridline drawn at that tick.  hPa keeps its full label — its
  // whole-part transitions are meaningful context, not a fixed
  // 30/29 boundary.
  const stripWhole = compact && pu !== 'hPa';
  const right = baro.length
    ? niceTicks(bLo, bHi, 5)
        .map((val, i) => {
          const full = val.toFixed(baroTickDigits);
          return {
            key: `P${i}`,
            y: (CH - PB) - ((val - bLo) / (bHi - bLo)) * (CH - PB - PT),
            label: stripWhole ? full.replace(/^\d+\./, '.') : full,
            whole: val === Math.round(val),
          };
        })
        .filter((g) => inPlot(g.y))
    : [];

  return (
    <Tile
      id="nerd-chart"
      style={{
        border: `${v.ruleHairWidth} solid ${v.ruleHair}`,
        background: v.surface,
        borderRadius: v.radiusCard,
        padding: `${s(18)} ${s(20)}`,
        gap: s(10),
        minHeight: s(341),
        ...CONTENT_CAP,
        ...style,
      }}
    >
      {/* Sentence-case serif italic heading + underline rule via
          ``TileHeading``, with the resolution + CSV controls floated
          right along the same baseline (Design v46 §1). */}
      {/* Heading stacks over the controls at phone width — the flat
          "heading | 4 buttons + CSV" row wraps to a 4-line ladder at
          328 px and the buttons collide with the CSV emphasis; stacked
          the heading owns its line and the controls own theirs. */}
      <TileHeading style={{ display: 'flex', flexDirection: compact ? 'column' : 'row', alignItems: compact ? 'flex-start' : 'baseline', justifyContent: 'space-between', gap: compact ? s(8) : s(16), fontSize: compact ? '15px' : undefined }}>
        {/* At phone the serif italic heading wrapped even after
            shortening to ``Temp, dew & pressure · 24 h`` because
            TileHeading's ``type('title')`` on the mobile shell resolves
            to 17 px raw and the two-word tail ``· 24 h`` orphaned to a
            new line.  Explicit 15 px override + ``whiteSpace: nowrap``
            forces a single line — the heading is short enough that
            clipping shouldn't happen at 336 content width. */}
        <span style={compact ? { whiteSpace: 'nowrap' } : undefined}>{compact ? 'Temp, dew & pressure · 24 h' : 'Temperature, dew point & pressure · 24 h'}</span>
        <div style={{ display: 'flex', gap: s(10), alignItems: 'baseline', flexWrap: 'wrap' }}>
          <ChartButtonGroup>
            {(['Raw', '5 min', 'Hourly', 'Daily'] as const).map((label, i) => {
              const active = label === (d.nerd?.resolution ?? '5 min');
              return (
                <ChartButton
                  key={label}
                  segmented
                  first={i === 0}
                  active={active}
                  onClick={onResolutionChange ? () => onResolutionChange(label) : undefined}
                >
                  {label}
                </ChartButton>
              );
            })}
          </ChartButtonGroup>
          <ChartButton emphasis>CSV</ChartButton>
        </div>
      </TileHeading>

      {/*
        Two layers, deliberately:
        ① an SVG of PATHS ONLY, stretched with preserveAspectRatio="none" so the
          traces fill whatever width the tile has;
        ② axis labels as HTML, positioned by percentage.

        Text must never live inside a non-uniformly stretched SVG. In the first
        render this tile had no height bound, so the SVG grew to its own 660:250
        aspect (~504px tall), the whole viewBox scaled ~2x, and the axis numerals
        rendered at roughly 24px — the chart swallowed the page and the three-up
        band fell off the bottom. Bounding the height fixes the size; splitting the
        text out fixes the distortion permanently.
      */}
      <div style={{ position: 'relative', height: s(250), minHeight: s(250), background: v.chart.surface }}>
        <svg
          viewBox={`0 0 ${CW} ${CH}`}
          preserveAspectRatio="none"
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', display: 'block' }}
        >
          {/* ``vectorEffect="non-scaling-stroke"`` on every stroked element —
              preserveAspectRatio="none" scales x ~3× more than y, so without it
              strokes draw 3× thicker horizontally than vertically and joins look
              lumpy.  With it, widths are in screen px and traces read evenly. */}
          {left.map((g, i) => (
            <line key={`g${i}`} x1={PL + GRID_INSET} y1={g.y} x2={CW - PR - GRID_INSET} y2={g.y} stroke={v.chart.gridMinor} strokeWidth={1} vectorEffect="non-scaling-stroke" />
          ))}
          {/* Emphasized gridline at whole-inch pressure ticks when the
              label ladder has dropped the whole part — the operator
              reads ``.20 / .15 / .10 / .05 / .00 / .95`` as the ladder
              and this line names which whole inch they're centred on. */}
          {stripWhole && bp && right.filter((g) => g.whole).map((g) => (
            <line key={`w${g.key}`} x1={PL + GRID_INSET} y1={g.y} x2={CW - PR - GRID_INSET} y2={g.y} stroke={v.chart.trace} strokeWidth={1.2} opacity={0.35} vectorEffect="non-scaling-stroke" />
          ))}
          {bp && (
            <path d={bp.line} fill="none" stroke={v.chart.trace} strokeWidth={1.4} strokeDasharray="5 3" opacity={0.9} vectorEffect="non-scaling-stroke" />
          )}
          {dw && (
            <path d={dw.line} fill="none" stroke={v.chart.traceSecondary} strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
          )}
          {t && (
            <path d={t.line} fill="none" stroke={v.accent} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
          )}
          <line x1={PL} y1={CH - PB} x2={CW - PR} y2={CH - PB} stroke={v.ruleHair} strokeWidth={1} vectorEffect="non-scaling-stroke" />
        </svg>

        {/* left axis — temperature and dew point share it.  ``nowrap`` is
            load-bearing: the label container is only PL/CW ≈ 7.9 % of the
            chart's width, and on a narrow viewport that's tight enough
            that ``100`` at sectionLabel size + letter-spacing wraps
            character-by-character to ``1`` / ``0`` / ``0`` stacked
            vertically — Chris caught that in the 16:14 render. */}
        {left.map((g) => (
          <span
            key={g.key}
            style={{
              ...type('sectionLabel'),
              color: v.chart.axis,
              position: 'absolute',
              left: 0,
              width: `${(PL / CW) * 100}%`,
              top: `${(g.y / CH) * 100}%`,
              transform: 'translateY(-50%)',
              textAlign: 'right',
              paddingRight: s(8),
              boxSizing: 'border-box',
              whiteSpace: 'nowrap',
            }}
          >
            {g.label}
          </span>
        ))}

        {/* right axis — colour-keyed to the pressure trace, so no legend entry has
            to explain which axis belongs to which series.  ``nowrap`` for the
            same reason as the left axis. */}
        {bp &&
          right.map((g) => (
            <span
              key={g.key}
              style={{
                ...type('sectionLabel'),
                color: v.chart.trace,
                position: 'absolute',
                right: 0,
                width: `${(PR / CW) * 100}%`,
                top: `${(g.y / CH) * 100}%`,
                transform: 'translateY(-50%)',
                paddingLeft: s(8),
                boxSizing: 'border-box',
                whiteSpace: 'nowrap',
              }}
            >
              {g.label}
            </span>
          ))}

        {/* x axis */}
        <div
          style={{
            position: 'absolute',
            left: `${(PL / CW) * 100}%`,
            right: `${(PR / CW) * 100}%`,
            bottom: s(4),
            display: 'flex',
            justifyContent: 'space-between',
            ...type('sectionLabel'),
            color: v.chart.axis,
          }}
        >
          <span>−24h</span><span>−18</span><span>−12</span><span>−6</span><span>now</span>
        </div>
      </div>

      <div style={{ display: 'flex', gap: s(18), alignItems: 'center', flexWrap: 'wrap' }}>
        <LegendKey color={v.accent}>Temperature °F</LegendKey>
        <LegendKey color={v.chart.traceSecondary}>Dew point °F</LegendKey>
        <LegendKey color={v.chart.trace} dashed>
          Pressure {pu}, right axis
        </LegendKey>
        <SectionLabel style={{ marginLeft: 'auto' }}>
          {fmtInt(d.history.sampleCount, ' samples')} · drag to zoom
        </SectionLabel>
      </div>
    </Tile>
  );
};

/**
 * A legend is justified HERE and nowhere else on the dashboard: three series on
 * two axes can't be disambiguated by a header line alone.
 */
const LegendKey: React.FC<{ color: string; dashed?: boolean; children: React.ReactNode }> = ({ color, dashed, children }) => (
  <span style={{ ...type('sectionLabel'), color: v.textSecondary, display: 'inline-flex', alignItems: 'center', gap: s(6) }}>
    <span
      style={{
        width: st(14),
        height: st(2),
        background: dashed ? `repeating-linear-gradient(90deg, ${color} 0 4px, transparent 4px 7px)` : color,
        display: 'inline-block',
      }}
    />
    {children}
  </span>
);

/** ChartButton, two modes (Design v46 §7):
 *
 * ``segmented`` (default in the resolution group) — the button
 * lives inside a shared bordered container.  No per-button
 * border except a left hairline divider between siblings.  Active
 * = accent text + a 2 px accent bottom border via inset box-shadow
 * (so it sits over the container's own bottom border rather than
 * pushing everything below down by 2 px).  Inactive =
 * ``textSecondary`` on transparent.  Kills the filled-copper
 * primary that put the page's strongest contrast on its weakest
 * control.
 *
 * ``emphasis`` (CSV, sitting outside the group) — a standalone
 * bordered chip.  A different kind of action (export, not a
 * view-mode toggle), so the treatment is different and it's
 * placed after a ``s(10)`` gap outside the segmented container.
 */
const ChartButton: React.FC<{
  active?: boolean;
  segmented?: boolean;
  first?: boolean;
  emphasis?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
}> = ({ active, segmented, first, emphasis, onClick, children }) => (
  <button
    type="button"
    onClick={onClick}
    style={{
      ...type('sectionLabel', fs(12)),
      letterSpacing: 'normal',
      textTransform: 'none',
      padding: `${s(5)} ${s(12)}`,
      borderRadius: segmented ? 0 : 'var(--radius-control, 0px)',
      border: segmented
        ? 'none'
        : `${v.ruleHairWidth} solid ${v.ruleHair}`,
      borderLeft: segmented && !first
        ? `${v.ruleHairWidth} solid ${v.ruleHair}`
        : undefined,
      background: 'transparent',
      color: active ? v.accent : emphasis ? v.text : v.textSecondary,
      fontWeight: active ? 600 : 400,
      boxShadow: segmented && active
        ? `inset 0 -2px 0 ${v.accent}`
        : 'none',
      cursor: 'pointer',
    }}
  >
    {children}
  </button>
);

/** Bordered container around the segmented resolution buttons.
 *  ``flex-wrap`` at phone so ``Raw / 5 min / Hourly / Daily`` can
 *  wrap into two rows inside the same bordered group rather than
 *  overrunning the tile edge. */
const ChartButtonGroup: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div
    style={{
      display: 'inline-flex',
      flexWrap: 'wrap',
      border: `${v.ruleHairWidth} solid ${v.ruleHair}`,
      borderRadius: 'var(--radius-control, 0px)',
    }}
  >
    {children}
  </div>
);

/* ───────────────────────────────────────────────────────── the three-up */

/** 16 compass sectors, north-first clockwise — matches
 *  ``bucketWindDirection()`` in ``Dashboard.tsx`` and ``CARDINALS``
 *  in ``WindRoseDial.tsx``.  Kept adjacent to the caption that
 *  consumes it so a future divergence would be obvious. */
const ROSE_DIRS = [
  'N','NNE','NE','ENE','E','ESE','SE','SSE',
  'S','SSW','SW','WSW','W','WNW','NW','NNW',
];

/** Peak sector in a normalised rose-weights array.  Returns null if
 *  the series is empty or all-zero (no data yet).  ``% 16`` rounds
 *  the bucket index; the input is 16-long so it's a passthrough,
 *  but the form is robust to any future re-bucketing.  Design v47 §1. */
const dominantSector = (weights: (number | null | undefined)[] | null | undefined): string | null => {
  if (!weights?.length) return null;
  let best = -1, at = -1;
  weights.forEach((w, i) => { if (w != null && w > best) { best = w; at = i; } });
  return best > 0 && at >= 0 ? ROSE_DIRS[Math.round((at / weights.length) * 16) % 16] : null;
};

export const WindRoseTile: React.FC<{ d: DashboardData; compact?: boolean }> = ({ d, compact }) => {
  return (
    <Tile
      id="nerd-wind-rose"
      style={{
        padding: `${s(18)} ${s(20)}`,
        gap: s(10),
      }}
    >
      <TileHeading>Wind rose · 4 h</TileHeading>
      {/* Radial dial off at phone — v55 §5: nothing radial survives
          below 768.  The caption below already carries dominant sector,
          mean and peak, so the text does the tile's whole job when the
          graphic can't; promote it in compact from a small caption to
          the tile body so it doesn't read as an orphan below empty
          space. */}
      {!compact && (
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <WindRoseDial
            roseWeights={d.wind.roseWeights}
            directionDeg={d.wind.directionDeg}
            speedMph={d.wind.speedMph}
            size={250}
          />
        </div>
      )}
      <SectionLabel style={{ textAlign: 'center' }}>
        {/* Dominant sector derives from the same ``roseWeights``
            series that drew the petals, not from ``directionLabel``
            (which is the *instantaneous* vane reading and, when the
            Vue anemometer stalls at 1 mph mean, a held value rather
            than a current one).  A caption computed from the graphic
            can't contradict it — Design v47 §1. */}
        {dominantSector(d.wind.roseWeights)
          ? `${dominantSector(d.wind.roseWeights)} dominant`
          : 'no prevailing direction'}
        {d.wind.speedMph != null && ` · ${fmt(d.wind.speedMph, 0)} mph mean`}
        {d.wind.peakMph != null && ` · ${fmt(d.wind.peakMph, 0)} peak`}
      </SectionLabel>
    </Tile>
  );
};

export const SolarEnergyTile: React.FC<{ d: DashboardData }> = ({ d }) => {
  const days = d.nerd?.solarEnergy14d ?? [];
  const max = Math.max(1, ...days.map((n) => n ?? 0));
  const W = 450, H = 100;
  return (
    <Tile
      id="nerd-solar"
      style={{
        padding: `${s(18)} ${s(20)}`,
        gap: s(10),
      }}
    >
      <TileHeading>Solar energy · 14 days</TileHeading>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display: 'block', width: '100%', height: s(118) }}>
        {/* Index from the end so ``today`` is always the rightmost
            slot regardless of how much history the adapter returns —
            a short series (say 9 of 14) reads as absent bars on the
            left, not a mid-chart highlight labelled 'today'.  ``rx``
            dropped because the SVG is ``preserveAspectRatio="none"``,
            which turns a uniform corner radius into an ellipse. */}
        {Array.from({ length: 14 }, (_, i) => {
          const val = days[days.length - 14 + i] ?? 0;
          const h = val > 0 ? (val / max) * 76 : 0;
          return (
            <rect
              key={i}
              x={i * 32 + 2}
              y={82 - h}
              width={24}
              height={h}
              fill={v.warning}
              opacity={i === 13 ? 1 : 0.55}
            />
          );
        })}
        <line x1={0} y1={82} x2={W} y2={82} stroke={v.ruleHair} strokeWidth={1} />
      </svg>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <SectionLabel>13 days ago</SectionLabel>
        <SectionLabel>today {fmt(days[days.length - 1] ?? null, 2, ' MJ/m²')}</SectionLabel>
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: s(10),
          paddingTop: s(10),
          borderTop: `${v.ruleHairWidth} ${v.ruleStyle} ${v.ruleHair}`,
        }}
      >
        <div>
          <SectionLabel>UV now</SectionLabel>
          <div style={{ ...type('mono', fs(20)), ...tnum, color: v.warning }}>{fmt(d.solar.uvIndex)}</div>
        </div>
        <div>
          <SectionLabel>Solar now</SectionLabel>
          <div style={{ ...type('mono', fs(20)), ...tnum, color: v.warning }}>{fmtInt(d.solar.wm2)}</div>
        </div>
      </div>
    </Tile>
  );
};

export const ConsoleExtremesTile: React.FC<{ d: DashboardData; compact?: boolean }> = ({ d, compact }) => {
  const e = d.nerd?.extremes;
  const pairs: [string, React.ReactNode][] = [
    ['Temp, day', e ? `${fmt(e.tempDayHigh, 1)} / ${fmt(e.tempDayLow, 1)}` : '—'],
    ['Temp, month', e ? `${fmt(e.tempMonthHigh, 1)} / ${fmt(e.tempMonthLow, 1)}` : '—'],
    ['Baro, day', e ? `${fmt(e.baroDayHigh, 2)} / ${fmt(e.baroDayLow, 2)}` : '—'],
    ['Baro, year', e ? `${fmt(e.baroYearHigh, 2)} / ${fmt(e.baroYearLow, 2)}` : '—'],
    ['Gust, month', e ? fmt(e.gustMonthMax, 0, ' mph') : '—'],
    ['Rain, year', e ? fmt(e.rainYearIn, 2, ' in') : '—'],
  ];

  return (
    <Tile
      id="nerd-extremes"
      style={{
        padding: `${s(18)} ${s(20)}`,
        gap: s(10),
      }}
    >
      <TileHeading>Console extremes &amp; calibration</TileHeading>

      {/* Two columns of ruled rows — the mock's 212/212 split.  v54
          §9 collapses this to single-column at phone and tablet tiers
          because the right-column values (year highs/lows, ``vs KHRJ``)
          clip inside the tighter cells; ``compact`` gets the pair
          grid to ``1fr`` and lets it flow as 8 hairline-separated rows. */}
      <div style={{ display: 'grid', gridTemplateColumns: compact ? '1fr' : '1fr 1fr', columnGap: s(20) }}>
        {/* No ``last`` on the pairs rows — the table continues below
            with ``Baro offset`` and ``vs reference``, so dropping a
            hairline here made the third visual row look like the end
            and the two calibration rows look like a second table. */}
        {pairs.map(([label, value]) => (
          <Row key={label} label={label} value={value} />
        ))}
        <Row
          label="Baro offset"
          value={
            d.nerd?.baroOffsetInHg == null
              ? '—'
              : `${d.nerd.baroOffsetInHg > 0 ? '+' : ''}${d.nerd.baroOffsetInHg.toFixed(3)} in`
          }
          valueColor={v.accent}
          // ``last`` here was correct for the 2-col grid where this
          // row and ``vs reference`` shared the visual bottom row.  In
          // compact (1-col) flow this is the seventh of eight rows, so
          // suppressing its rule leaves a gap before the final row.
          // Codex R1 on #517.
          last={!compact}
        />
        <Row
          label={d.nerd?.referenceStation ? `vs ${d.nerd.referenceStation}` : 'vs reference'}
          value={
            d.nerd?.baroVsReferenceInHg == null
              ? '—'
              : `${d.nerd.baroVsReferenceInHg > 0 ? '+' : '−'}${Math.abs(d.nerd.baroVsReferenceInHg).toFixed(3)} in`
          }
          valueColor={
            d.nerd?.baroVsReferenceInHg == null
              ? v.text
              : Math.abs(d.nerd.baroVsReferenceInHg) <= 0.02
              ? v.success
              : v.warning
          }
          last
        />
      </div>

      {/* METAR line: mono, ``userSelect: 'all'`` so it copies as one
          string.  Sunken fill kept (Design v46 §4) as the visible
          target for the select, but border + borderRadius dropped —
          once the tile is open, that inner box was the only remaining
          card on this section and read as the tile's own frame.
          ``marginTop: auto`` removed too: a start-aligned borderless
          tile is content-height, so the auto-push has nothing to do. */}
      <div style={{ paddingTop: s(10), borderTop: `${v.ruleHairWidth} ${v.ruleStyle} ${v.ruleHair}` }}>
        <SectionLabel style={{ marginBottom: s(6) }}>METAR output</SectionLabel>
        <div
          style={{
            ...type('mono', fs(12)),
            color: v.text,
            background: v.sunken,
            padding: `${s(10)} ${s(12)}`,
            letterSpacing: '0.3px',
            wordBreak: 'break-word',
            userSelect: 'all',
          }}
        >
          {d.nerd?.metar ?? '—'}
        </div>
      </div>
    </Tile>
  );
};

/* ─────────────────────────────────────────────── phone composition (v54 §2) */

/**
 * Weather nerd at ≤768 px. Rebuilt for the "what is the station
 * doing?" question (v54 §2): pressure premise + 3 h rate + hPa
 * alternate, then the Zambretti sentence with NWS agreement, then a
 * paired theta-e | reception row.  Reception is above the divider
 * because it's the one item that tells you whether to trust
 * everything below it (v54 §2).
 *
 * Below the divider, the chart, wind table, solar bars and console
 * extremes stack in the order they read left-to-right on desktop —
 * v54 §5 explicitly keeps the 24 h temp/dew line AND the 14-day
 * solar bars because both fit 328 px and are the point of their
 * tiles.  The wind rose stays too (the dial-replacement rule
 * applies to the above-divider only; the reader has scrolled past
 * the summary by then).
 */
const WeatherNerdMobileShell: React.FC<{
  d: DashboardData;
  themeLabel: string;
  onResolutionChange?: (r: NerdResolution) => void;
}> = ({ d, themeLabel, onResolutionChange }) => {
  const pu = d.units.pressure;
  const main = pu === 'hPa' ? d.barometer.hPa : d.barometer.inHg;
  const mainDigits = pu === 'hPa' ? 1 : 2;
  const t = d.barometer.trendInHgPer3h;
  const arrow = t == null ? '' : t > 0.005 ? '↑' : t < -0.005 ? '↓' : '→';
  const trendConverted = t == null ? null : pu === 'hPa' ? t * 33.8639 : t;
  const trendDigits = pu === 'hPa' ? 1 : 3;
  const trendUnit = pu === 'hPa' ? 'hPa' : 'in';
  const altValue =
    pu === 'hPa'
      ? d.barometer.inHg != null && `${fmt(d.barometer.inHg, 2)} inHg`
      : d.barometer.hPa != null && `${fmt(d.barometer.hPa, 1)} hPa`;

  const reception = d.nerd?.reception ?? null;
  const rPct = reception?.pct ?? null;
  const rTone =
    rPct == null ? v.text : rPct >= 98 ? v.success : rPct >= 92 ? v.warning : v.danger;

  const kicker = [
    _nerdKickerDate(new Date()),
    d.station.console,
    d.station.elevationFt != null ? `${Math.round(d.station.elevationFt)} ft` : null,
  ].filter(Boolean).join(' · ');

  return (
    <main
      data-dashboard="weather_nerd"
      data-mobile
      style={{
        ['--k' as string]: '1px',
        ['--kt' as string]: '1px',
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0,
        flex: 1,
        minHeight: 0,
        overflowY: 'auto',
        // v55 §1 belt-and-braces: any residual fixed pixel width
        // inside a reused tile clips to the viewport rather than
        // shifting the whole document horizontally.
        overflowX: 'hidden',
        // Any scroll-into-view or hash-anchor jump inside this shell
        // leaves the top row clear of the fixed AppShell header.
        scrollPaddingTop: '60px',
        // 12 px horizontal (down from 16) buys 8 px of content width
        // where the tiles need it — 328 → 336 at 360-viewport phones.
        padding: '16px 12px',
        boxSizing: 'border-box',
        gap: '20px',
      }}
    >
      {/* Title + kicker (v54 §7). Header no longer carries the date at
          phone width (this phase), so the kicker is the only place the
          date lives now — matches Everyday / Agriculture. */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <h2 style={{ ...mType('pageTitle'), color: v.text, margin: 0 }}>Station Readout</h2>
        <div style={{ ...mType('sectionLabel'), color: v.textSecondary }}>{kicker}</div>
      </div>

      {/* Pressure premise (v54 §2 leads the nerd persona). */}
      <section style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <div style={{ ...mType('sectionLabel'), color: v.textSecondary }}>Pressure</div>
        <div style={{ ...mType('premiseFigure'), color: v.text, lineHeight: 0.95 }}>
          {fmt(main, mainDigits)}
        </div>
        <div style={{ ...mType('monoRow'), color: v.textSecondary }}>
          {trendConverted == null
            ? '—'
            : `${arrow} ${trendConverted > 0 ? '+' : ''}${trendConverted.toFixed(trendDigits)} ${trendUnit}/3h`}
          {altValue && `   ${altValue}`}
        </div>
      </section>

      {/* Zambretti + NWS agreement — italic serif sentence in the same
          voice as Everyday's hero Zambretti and Agriculture's verdict
          note. */}
      <section style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <div style={{ ...mType('sectionLabel'), color: v.textSecondary }}>Zambretti / NWS</div>
        <div style={{ ...mType('noteTitle'), color: v.text, lineHeight: 1.2 }}>
          {d.forecast.zambretti ?? '—'}
        </div>
        <div style={{ ...mType('sectionLabel'), color: v.accent }}>
          {d.forecast.confidencePct != null && `${Math.round(d.forecast.confidencePct)}% confidence`}
          {d.nerd?.nwsAgrees != null && ` · NWS ${d.nerd.nwsAgrees ? 'agrees' : 'differs'}`}
        </div>
      </section>

      {/* Theta-e | Reception paired row.  Reception is above the divider
          because if it's bad, everything else is suspect (v54 §2). */}
      <section style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <div style={{ ...mType('sectionLabel'), color: v.textSecondary }}>Theta-e</div>
          <div style={{ ...mType('secondaryFigure'), color: v.text, lineHeight: 1 }}>
            {fmt(d.outside.thetaEK, 1)}{' '}
            <span style={{ ...mType('sectionLabel'), color: v.textSecondary }}>K</span>
          </div>
          {d.nerd?.thetaEDelta != null && (
            <div style={{ ...mType('sectionLabel'), color: v.textSecondary }}>
              {d.nerd.thetaEDelta > 0 ? '+' : ''}
              {fmt(d.nerd.thetaEDelta, 1)} since 06Z
            </div>
          )}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <div style={{ ...mType('sectionLabel'), color: v.textSecondary }}>
            Reception · {reception?.windowLabel ?? '1 h'}
          </div>
          <div style={{ ...mType('secondaryFigure'), color: rTone, lineHeight: 1 }}>
            {rPct == null ? '—' : fmt(rPct, 1)}
            {rPct != null && (
              <span style={{ ...mType('sectionLabel'), color: v.textSecondary }}> %</span>
            )}
          </div>
          {(reception?.crcErrors != null || reception?.resyncs != null) && (
            <div style={{ ...mType('sectionLabel'), color: v.textSecondary }}>
              {reception?.crcErrors != null && `CRC ${reception.crcErrors}`}
              {reception?.crcErrors != null && reception?.resyncs != null && ' · '}
              {reception?.resyncs != null && `Resync ${reception.resyncs}`}
            </div>
          )}
        </div>
      </section>

      <FullReadoutDivider />

      {/* Below-divider: the existing chart + tiles at natural-px scale
          (same --k/--kt hoist as the other personas).  Order matches
          the mock top-to-bottom: chart, wind table, solar bars,
          console extremes + METAR (owned by ConsoleExtremesTile). */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', minWidth: 0 }}>
        <NerdChartTile d={d} onResolutionChange={onResolutionChange} compact />
        <WindRoseTile d={d} compact />
        <SolarEnergyTile d={d} />
        <ConsoleExtremesTile d={d} compact />
      </div>

      <PersonaFooter
        d={d}
        themeLabel={themeLabel}
        extraChips={
          <>
            {d.nerd?.dbSizeMB != null && <SectionLabel>DB {fmt(d.nerd.dbSizeMB, 1, ' MB')}</SectionLabel>}
            {d.nerd?.uploadTargets && <SectionLabel>{d.nerd.uploadTargets} uploading</SectionLabel>}
            {d.nerd?.ipcStatus && <SectionLabel>{d.nerd.ipcStatus}</SectionLabel>}
          </>
        }
      />
    </main>
  );
};

function _nerdKickerDate(d: Date): string {
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

/* ─────────────────────────────────────────────── tablet composition (v54 §8) */

/**
 * Weather Nerd at content-769–1213 (viewport 989–1433 with the fixed
 * 220 px sidebar).  §8 rule for this persona: "four-up hero becomes
 * 2×2, the chart full width, the three-up becomes two plus one."
 *
 *   header row (title | kicker)     — full width
 *   pressure  | theta-e             — stat 2×2, row 1
 *   agreement | reception           — stat 2×2, row 2
 *   chart                           — full width
 *   wind rose | solar               — three-up "two"
 *   console extremes                — three-up "one" (full width),
 *                                     compact prop → single column
 *                                     per §9 so year highs and
 *                                     ``vs KHRJ`` don't clip
 *
 * Uses the same ``--k`` / ``--kt`` = ``1px`` hoist as the phone
 * shell.  Right-side corner plate off — its positioning is tied to
 * ``scaleVar(928)``, which the tablet shell bypasses.
 */
const WeatherNerdTabletShell: React.FC<{
  d: DashboardData;
  themeLabel: string;
  onResolutionChange?: (r: NerdResolution) => void;
}> = ({ d, themeLabel, onResolutionChange }) => {
  const kicker = [
    d.station.name,
    d.station.console,
    d.station.elevationFt != null ? `${Math.round(d.station.elevationFt)} ft` : null,
  ].filter(Boolean).join(' · ');

  return (
    <main
      data-dashboard="weather_nerd"
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
        <h2 style={{ ...type('heading'), color: v.text, margin: 0 }}>Station Readout</h2>
        <SectionLabel>{kicker}</SectionLabel>
      </div>

      {/* 2×2 stat grid.  Each cell keeps the ``StatCell`` treatment:
          borderless, hairline-separated on non-first columns.  At
          natural px the ``first`` prop still drops the left border on
          cells in the first column of each row. */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 0, rowGap: 16, alignItems: 'start' }}>
        <PressureCard d={d} />
        <ThetaECard d={d} />
        <ForecastAgreementCard d={d} />
        <ReceptionCard d={d} />
      </div>

      {/* Chart — full width per §8.  Explicit minHeight so the plot
          area doesn't collapse (same lesson as #516 R1 on Everyday). */}
      <NerdChartTile d={d} onResolutionChange={onResolutionChange} style={{ minHeight: 341 }} />

      {/* Three-up "two" — wind rose | solar bars.  Both stay per
          v54 §5: "Two charts stay ... the 24 h temp/dew line ... and
          the 14-day solar bars."  Wind rose likewise stays below the
          divider on phone; here it's above the "one" full-width row. */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', alignItems: 'start' }}>
        <WindRoseTile d={d} />
        <SolarEnergyTile d={d} />
      </div>

      {/* Three-up "one" — console extremes full width, compact so the
          8 rows lay out one-per-line (§9). */}
      <ConsoleExtremesTile d={d} compact />

      <PersonaFooter
        d={d}
        themeLabel={themeLabel}
        extraChips={
          <>
            {d.nerd?.dbSizeMB != null && <SectionLabel>DB {fmt(d.nerd.dbSizeMB, 1, ' MB')}</SectionLabel>}
            {d.nerd?.uploadTargets && <SectionLabel>{d.nerd.uploadTargets} uploading</SectionLabel>}
            {d.nerd?.ipcStatus && <SectionLabel>{d.nerd.ipcStatus}</SectionLabel>}
          </>
        }
      />
    </main>
  );
};

export default WeatherNerdDashboard;
