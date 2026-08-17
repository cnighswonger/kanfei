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
  v, type, s, st, fs, scaleVar, CONTENT_CAP, SectionLabel, Row, Tile, tnum, fmt, fmtInt, fmtTime,
} from './primitives';
import type { DashboardData } from './types';
import { compass, rosePetals, pathFor } from '../utils/gauges';

const DESIGN_HEIGHT = 928;

export const WeatherNerdDashboard: React.FC<{ d: DashboardData; themeLabel?: string }> = ({
  d,
  themeLabel,
}) => (
  <main data-dashboard="weather_nerd" style={{ minWidth: 0, overflow: 'hidden' }}>
    <div
      style={{
        ...scaleVar(DESIGN_HEIGHT),
        padding: `${s(20)} ${s(24)} ${s(24)}`,
        display: 'flex',
        flexDirection: 'column',
        gap: s(16),
        position: 'relative',
        isolation: 'isolate',
        minWidth: 0,
        boxSizing: 'border-box',
      }}
    >
      {/* Corner plate, as Everyday — this screen is dense, so the engraving stays
          out of the way rather than sitting behind the whole page. */}
      <div
        aria-hidden
        style={{
          position: 'absolute',
          right: 0,
          bottom: s(60),
          width: s(380),
          height: s(260),
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

      {/* ── stat row, 147 ─────────────────────────────────────────────────── */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: s(16),
          minHeight: s(147),
          // stretch, not start: the four cards read as one instrument row, so they
          // share a height. They grow together if any provenance line wraps.
          alignItems: 'stretch',
          ...CONTENT_CAP,
        }}
      >
        <PressureCard d={d} />
        <ThetaECard d={d} />
        <ForecastAgreementCard d={d} />
        <ReceptionCard d={d} />
      </div>

      {/* ── multi-series chart, 341 ───────────────────────────────────────── */}
      <NerdChartTile d={d} />

      {/* ── three-up, 293 ────────────────────────────────────────────────── */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '406fr 406fr 487fr',
          gap: s(16),
          minHeight: s(293),
          alignItems: 'start',
          ...CONTENT_CAP,
        }}
      >
        <WindRoseTile d={d} />
        <SolarEnergyTile d={d} />
        <ConsoleExtremesTile d={d} />
      </div>

      {/* ── footer strip, 42 ─────────────────────────────────────────────── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: s(20),
          flexWrap: 'wrap',
          border: `${v.ruleHairWidth} solid ${v.ruleHair}`,
          borderRadius: v.radiusCard,
          padding: `${s(12)} ${s(18)}`,
          ...CONTENT_CAP,
        }}
      >
        <span style={{ ...type('sectionLabel'), color: v.text, display: 'inline-flex', alignItems: 'center', gap: s(8) }}>
          <span
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
        {d.nerd?.dbSizeMB != null && <SectionLabel>DB {fmt(d.nerd.dbSizeMB, 1, ' MB')}</SectionLabel>}
        {d.nerd?.uploadTargets && <SectionLabel>{d.nerd.uploadTargets} uploading</SectionLabel>}
        {d.nerd?.ipcStatus && <SectionLabel>{d.nerd.ipcStatus}</SectionLabel>}
        {themeLabel && <SectionLabel>{themeLabel}</SectionLabel>}
        <SectionLabel style={{ marginLeft: 'auto' }}>
          clock {d.station.clock ?? '—'} · last poll {fmtTime(d.station.lastPoll)}
        </SectionLabel>
      </div>
    </div>
  </main>
);

/* ────────────────────────────────────────────────────────── the stat cards */

/**
 * Stat card. Four lines: kicker, big derived figure, a mono qualifier in a
 * meaningful colour, then one line of plain-language provenance.
 *
 * That last line is the persona's whole point — a nerd wants to know *how* the
 * number was arrived at, so every card says where it came from.
 */
const StatCard: React.FC<{
  id: string;
  kicker: string;
  children: React.ReactNode;
}> = ({ id, kicker, children }) => (
  <Tile
    id={id}
    style={{
      border: `${v.ruleHairWidth} solid ${v.ruleHair}`,
      background: v.surface,
      borderRadius: v.radiusCard,
      padding: `${s(16)} ${s(18)}`,
      gap: s(4),
    }}
  >
    <SectionLabel>{kicker}</SectionLabel>
    {children}
  </Tile>
);

const BigFigure: React.FC<{ children: React.ReactNode; color?: string }> = ({ children, color = v.text }) => (
  <div style={{ ...type('mono', { ...fs(34), fontWeight: 700 }), ...tnum, color, lineHeight: 1.05 }}>{children}</div>
);

/** Plain-language provenance line — body 11px, secondary ink. */
const Provenance: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ ...type('body', fs(11)), color: v.textSecondary, lineHeight: 1.4, textWrap: 'pretty' }}>{children}</div>
);

export const PressureCard: React.FC<{ d: DashboardData }> = ({ d }) => {
  const t = d.barometer.trendInHgPer3h;
  const tone = t == null ? v.textSecondary : t > 0.005 ? v.success : t < -0.005 ? v.danger : v.textSecondary;
  const arrow = t == null ? '' : t > 0.005 ? '↑' : t < -0.005 ? '↓' : '→';
  return (
    <StatCard id="nerd-pressure" kicker="Pressure">
      <BigFigure>{fmt(d.barometer.inHg, 2)}</BigFigure>
      <div style={{ ...type('mono', fs(12)), ...tnum, color: tone }}>
        {t == null ? '—' : `${arrow} ${t > 0 ? '+' : ''}${t.toFixed(3)} in/3h`}
      </div>
      <Provenance>
        {fmt(d.barometer.hPa, 1, ' hPa')}
        {d.nerd?.altimeterInHg != null && ` · altimeter ${fmt(d.nerd.altimeterInHg, 2)}`}
        {d.nerd?.seaLevelHPa != null && ` · SLP ${fmt(d.nerd.seaLevelHPa, 1)}`}
      </Provenance>
    </StatCard>
  );
};

export const ThetaECard: React.FC<{ d: DashboardData }> = ({ d }) => (
  <StatCard id="nerd-theta-e" kicker="Theta-E">
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
  </StatCard>
);

export const ForecastAgreementCard: React.FC<{ d: DashboardData }> = ({ d }) => (
  <StatCard id="nerd-agreement" kicker="Zambretti / NWS">
    <div style={{ ...type('body', fs(17)), color: v.text, lineHeight: 1.25, textWrap: 'pretty' }}>
      {d.forecast.zambretti ?? '—'}
    </div>
    <div style={{ ...type('mono', fs(12)), ...tnum, color: v.accent }}>
      {d.forecast.confidencePct != null && `${Math.round(d.forecast.confidencePct)}% confidence`}
      {d.nerd?.nwsAgrees != null && ` · NWS ${d.nerd.nwsAgrees ? 'agrees' : 'differs'}`}
    </div>
    {d.nerd?.agreementRate30d != null && (
      <Provenance>Zambretti and NWS have agreed {Math.round(d.nerd.agreementRate30d)}% of the last 30 days</Provenance>
    )}
  </StatCard>
);

export const ReceptionCard: React.FC<{ d: DashboardData }> = ({ d }) => {
  const r = d.nerd?.reception;
  const pct = r?.pct ?? null;
  const tone = pct == null ? v.text : pct >= 98 ? v.success : pct >= 92 ? v.warning : v.danger;
  return (
    <StatCard id="nerd-reception" kicker="Reception since midnight">
      <BigFigure color={tone}>
        {pct == null ? '—' : fmt(pct, 1)}
        {pct != null && <span style={{ ...fs(14), color: v.textSecondary }}>%</span>}
      </BigFigure>
      <div style={{ ...type('mono', fs(11)), ...tnum, color: v.textSecondary }}>
        {fmtInt(r?.received, ' received')} · {fmtInt(r?.missed, ' missed')} · CRC {r?.crcErrors ?? '—'} · resync{' '}
        {r?.resyncs ?? '—'}
      </div>
    </StatCard>
  );
};

/* ─────────────────────────────────────────────── the multi-series chart */

const CW = 660, CH = 250, PL = 46, PR = 46, PT = 14, PB = 26;

export const NerdChartTile: React.FC<{ d: DashboardData }> = ({ d }) => {
  const temps = d.history.tempF.filter((n): n is number => n != null);
  const dews = d.history.dewPointF.filter((n): n is number => n != null);
  const baro = (d.nerd?.historyInHg ?? []).filter((n): n is number => n != null);

  // Temperature and dew point share a domain; pressure gets its own right axis —
  // a 0.35 inHg span and a 30 °F span cannot share a scale meaningfully.
  const all = [...temps, ...dews];
  const pad = all.length ? Math.max(2, (Math.max(...all) - Math.min(...all)) * 0.12) : 2;
  const lo = all.length ? Math.min(...all) - pad : 0;
  const hi = all.length ? Math.max(...all) + pad : 1;
  const bPad = baro.length ? Math.max(0.04, (Math.max(...baro) - Math.min(...baro)) * 0.2) : 0.1;
  const bLo = baro.length ? Math.min(...baro) - bPad : 29.8;
  const bHi = baro.length ? Math.max(...baro) + bPad : 30.2;

  const t = temps.length ? pathFor(temps, PL, CW - PR, PT, CH - PB, lo, hi) : null;
  const dw = dews.length ? pathFor(dews, PL, CW - PR, PT, CH - PB, lo, hi) : null;
  const bp = baro.length ? pathFor(baro, PL, CW - PR, PT, CH - PB, bLo, bHi) : null;

  const yTicks = 4;
  const left = Array.from({ length: yTicks + 1 }, (_, i) => {
    const val = lo + ((hi - lo) * i) / yTicks;
    return { y: (CH - PB) - ((val - lo) / (hi - lo)) * (CH - PB - PT), label: fmt(val, 0) };
  });
  const right = Array.from({ length: yTicks + 1 }, (_, i) => {
    const val = bLo + ((bHi - bLo) * i) / yTicks;
    return { y: (CH - PB) - ((val - bLo) / (bHi - bLo)) * (CH - PB - PT), label: val.toFixed(2) };
  });

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
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: s(16) }}>
        <SectionLabel>Temperature, dew point &amp; pressure · 24 h</SectionLabel>
        {/* Resolution + export, from the existing History page controls. */}
        <div style={{ display: 'flex', gap: s(6) }}>
          {(['Raw', '5 min', 'Hourly', 'Daily'] as const).map((label) => {
            const active = label === (d.nerd?.resolution ?? '5 min');
            return (
              <ChartButton key={label} active={active}>
                {label}
              </ChartButton>
            );
          })}
          <ChartButton emphasis>CSV</ChartButton>
        </div>
      </div>

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
          {left.map((g, i) => (
            <line key={`g${i}`} x1={PL} y1={g.y} x2={CW - PR} y2={g.y} stroke={v.chart.gridMinor} strokeWidth={0.8} />
          ))}
          {bp && <path d={bp.line} fill="none" stroke={v.chart.trace} strokeWidth={1.6} strokeDasharray="5 3" opacity={0.9} />}
          {dw && <path d={dw.line} fill="none" stroke={v.chart.traceSecondary} strokeWidth={1.8} />}
          {t && <path d={t.line} fill="none" stroke={v.accent} strokeWidth={2.4} strokeLinecap="round" />}
          <line x1={PL} y1={CH - PB} x2={CW - PR} y2={CH - PB} stroke={v.ruleHair} strokeWidth={0.8} />
        </svg>

        {/* left axis — temperature and dew point share it */}
        {left.map((g) => (
          <span
            key={`L${g.label}`}
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
            }}
          >
            {g.label}
          </span>
        ))}

        {/* right axis — colour-keyed to the pressure trace, so no legend entry has
            to explain which axis belongs to which series */}
        {bp &&
          right.map((g) => (
            <span
              key={`R${g.label}`}
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
          Pressure inHg, right axis
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

const ChartButton: React.FC<{ active?: boolean; emphasis?: boolean; children: React.ReactNode }> = ({
  active,
  emphasis,
  children,
}) => (
  <button
    type="button"
    style={{
      ...type('sectionLabel', fs(12)),
      letterSpacing: 'normal',
      textTransform: 'none',
      padding: `${s(5)} ${s(12)}`,
      borderRadius: 'var(--radius-control, 0px)',
      border: `${v.ruleHairWidth} solid ${active ? v.accent : v.ruleHair}`,
      background: active ? v.accent : v.sunken,
      color: active ? v.bg : emphasis ? v.text : v.textSecondary,
      fontWeight: active ? 600 : 400,
      cursor: 'pointer',
    }}
  >
    {children}
  </button>
);

/* ───────────────────────────────────────────────────────── the three-up */

export const WindRoseTile: React.FC<{ d: DashboardData }> = ({ d }) => {
  const c = compass(130, 122, 92, 112);
  const petals = rosePetals(130, 122, 84, d.wind.roseWeights);
  const showNeedle = (d.wind.speedMph ?? 0) >= 1 && d.wind.directionDeg != null;
  return (
    <Tile
      id="nerd-wind-rose"
      style={{
        border: `${v.ruleHairWidth} solid ${v.ruleHair}`,
        background: v.surface,
        borderRadius: v.radiusCard,
        padding: `${s(18)} ${s(20)}`,
        gap: s(10),
      }}
    >
      <SectionLabel>Wind rose · 4 h</SectionLabel>
      <svg viewBox="0 -12 260 262" width="100%" height={s(210)} style={{ display: 'block' }}>
        <circle cx={130} cy={122} r={104} fill={v.chart.surface} stroke={v.ruleHair} strokeWidth={1} />
        {petals.map((p, i) => (
          <path key={i} d={p.d} fill={v.accent} opacity={p.op} />
        ))}
        {c.ticks.map((k, i) => (
          <line key={i} x1={k.x1} y1={k.y1} x2={k.x2} y2={k.y2} stroke={v.text} strokeOpacity={0.55} strokeWidth={k.sw} />
        ))}
        {c.labels.map((l, i) => (
          <text key={i} x={l.x} y={l.y} textAnchor="middle" style={type('sectionLabel')} fill={v.textSecondary}>
            {l.label}
          </text>
        ))}
        {showNeedle && (
          // SVG ``transform`` attribute — see PR 50 note.  CSS transforms
          // on SVG children only work in Chromium; the attribute form is
          // portable across browsers.
          <g transform={`rotate(${d.wind.directionDeg} 130 122)`}>
            <line x1={130} y1={150} x2={130} y2={46} stroke={v.needle} strokeWidth={3} strokeLinecap="round" />
            <polygon points="130,36 121,52 139,52" fill={v.needle} />
          </g>
        )}
      </svg>
      <SectionLabel style={{ textAlign: 'center' }}>
        {d.wind.directionLabel ? `${d.wind.directionLabel} dominant` : 'no prevailing direction'}
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
        border: `${v.ruleHairWidth} solid ${v.ruleHair}`,
        background: v.surface,
        borderRadius: v.radiusCard,
        padding: `${s(18)} ${s(20)}`,
        gap: s(10),
      }}
    >
      <SectionLabel>Solar energy · 14 days</SectionLabel>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" width="100%" height={s(118)} style={{ display: 'block' }}>
        {Array.from({ length: 14 }, (_, i) => {
          const val = days[i] ?? 0;
          const h = val > 0 ? (val / max) * 76 : 0;
          return (
            <rect
              key={i}
              x={i * 32 + 2}
              y={82 - h}
              width={24}
              height={h}
              rx={2}
              fill={v.warning}
              opacity={i === days.length - 1 ? 1 : 0.55}
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

export const ConsoleExtremesTile: React.FC<{ d: DashboardData }> = ({ d }) => {
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
        border: `${v.ruleHairWidth} solid ${v.ruleHair}`,
        background: v.surface,
        borderRadius: v.radiusCard,
        padding: `${s(18)} ${s(20)}`,
        gap: s(10),
      }}
    >
      <SectionLabel>Console extremes &amp; calibration</SectionLabel>

      {/* Two columns of ruled rows — the mock's 212/212 split. */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: s(20) }}>
        {pairs.map(([label, value], i) => (
          <Row key={label} label={label} value={value} last={i >= pairs.length - 2} />
        ))}
        <Row
          label="Baro offset"
          value={
            d.nerd?.baroOffsetInHg == null
              ? '—'
              : `${d.nerd.baroOffsetInHg > 0 ? '+' : ''}${d.nerd.baroOffsetInHg.toFixed(3)} in`
          }
          valueColor={v.accent}
          last
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

      {/* The METAR line: a mono block on the sunken ground, selectable as one
          string so it can be copied into a decoder. */}
      <div style={{ marginTop: 'auto', paddingTop: s(10), borderTop: `${v.ruleHairWidth} ${v.ruleStyle} ${v.ruleHair}` }}>
        <SectionLabel style={{ marginBottom: s(6) }}>METAR output</SectionLabel>
        <div
          style={{
            ...type('mono', fs(12)),
            color: v.text,
            background: v.sunken,
            border: `${v.ruleHairWidth} solid ${v.ruleHair}`,
            borderRadius: v.radiusCard,
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

export default WeatherNerdDashboard;
