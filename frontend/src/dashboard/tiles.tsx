/**
 * The ten dashboard tiles, finished. Drop in as-is.
 *
 * Rules these encode, so they can't drift again:
 *  - Content is TOP-LEFT aligned. Nothing is centred. Centring is what made the
 *    last three renders look like a settings form instead of an instrument panel.
 *  - Labels are <SectionLabel> (mono caps). Values are mono, tabular. Prose and
 *    the one hero numeral are serif italic via their type roles.
 *  - Every colour is a token from `v`. No literal hex anywhere in this file.
 *  - Heights come from the parent layout (TILE-CONTRACT.md), never from content.
 */
import React from 'react';
import { Tile, TileHeading, SectionLabel, Row, Rule, v, type, tnum, fmt, fmtInt, fmtTime, s, fs, decimate } from './primitives';
import type { DashboardData } from './types';
import { pathFor, ledgerGrid } from '../utils/gauges';
import WheelBarometer, { ZONE_BANDS, MIN_INHG, MAX_INHG, activeZone } from '../components/charts/WheelBarometer';
import WindRoseDial from '../components/charts/WindRoseDial';

/* ───────────────────────────────────────────────────── 1. hero temperature */

export const HeroTemperatureTile: React.FC<{ d: DashboardData; style?: React.CSSProperties }> = ({ d, style }) => (
  <Tile id="outside-temp" style={style}>
    <SectionLabel>Outside air</SectionLabel>
    {/* baseline-aligned value + unit; unit is the display role at 36px, not a caption */}
    <div style={{ display: 'flex', alignItems: 'baseline', gap: s(6), marginTop: s(-6) }}>
      <span style={{ ...type('display'), ...tnum, color: v.text, lineHeight: 0.88 }}>
        {fmt(d.outside.tempF)}
      </span>
      <span style={{ ...type('display', fs(36)), color: v.accent }}>
        °F
      </span>
    </div>

    {d.forecast.zambretti && (
      <div style={{ ...type('title'), color: v.text, lineHeight: 1.25, textWrap: 'pretty' }}>
        {d.forecast.zambretti}
      </div>
    )}
    <SectionLabel>
      Zambretti{d.forecast.confidencePct != null && ` · ${Math.round(d.forecast.confidencePct)}% confidence`}
    </SectionLabel>

    {/* high/low chips sit directly under the confidence label. flexShrink:0 and
        NO overflow clip — an earlier overflow:hidden here sliced the chips in
        half rather than fitting them. Each chip truncates its own timestamp
        instead. */}
    <div style={{ display: 'flex', gap: s(8), marginTop: s(2), minWidth: 0, flexShrink: 0 }}>
      <Chip label="High" value={fmt(d.outside.highF, 1, '°')} at={d.outside.highAt} tone={v.danger} />
      <Chip label="Low" value={fmt(d.outside.lowF, 1, '°')} at={d.outside.lowAt} tone={v.sky} />
    </div>
  </Tile>
);

const Chip: React.FC<{ label: string; value: string; at?: string | null; tone: string }> = ({ label, value, at, tone }) => (
  <span
    style={{
      ...type('mono'),
      ...tnum,
      display: 'inline-flex',
      alignItems: 'baseline',
      gap: s(6),
      padding: `${s(3)} ${s(8)}`,
      color: tone,
      border: `1px solid ${v.ruleHair}`,
      borderRadius: 'var(--radius-control, 0px)',
      whiteSpace: 'nowrap',
      minWidth: 0,
      textOverflow: 'ellipsis',
    }}
  >
    <span style={{ ...type('sectionLabel'), color: v.textSecondary }}>{label}</span>
    {value}
    {at && <span style={{ color: v.textMuted }}>{fmtTime(at)}</span>}
  </span>
);

/* ────────────────────────────────────────────────── 2. derived conditions */

export const DerivedConditionsTile: React.FC<{ d: DashboardData; style?: React.CSSProperties }> = ({ d, style }) => (
  <Tile id="derived-conditions" style={style}>
    <TileHeading>Derived conditions</TileHeading>
    {/* A left-aligned ruled table. Five rows, ~30px each — NOT a centred 2-up grid. */}
    <div>
      <Row label="Feels like" value={fmt(d.outside.feelsLikeF, 1, ' °F')} />
      <Row label="Heat index" value={fmt(d.outside.heatIndexF, 1, ' °F')} />
      <Row label="Dew point" value={fmt(d.outside.dewPointF, 1, ' °F')} valueColor={v.sky} />
      <Row label="Wind chill" value={fmt(d.outside.windChillF, 1, ' °F')} />
      <Row label="Theta-e" value={fmt(d.outside.thetaEK, 1, ' K')} last />
    </div>
  </Tile>
);

/* ─────────────────────────────────────────────────────── 3. history chart */

const CHART_W = 700;
const CHART_H = 196;

export const HistoryChartTile: React.FC<{ d: DashboardData; style?: React.CSSProperties }> = ({ d, style }) => {
  // Bin to ~600 points before drawing.  Over-plotting a ~2000px trace
  // with 8,000+ raw samples of 0.1 °F resolution renders as a
  // staircase; averaging into pixel-width bins keeps the shape and
  // removes the artefact.  See ``decimate`` in primitives.tsx.
  const temps = decimate(d.history.tempF).filter((n): n is number => n != null);
  const dews = decimate(d.history.dewPointF).filter((n): n is number => n != null);
  if (!temps.length) {
    return (
      <Tile id="history-chart" style={style}>
        <TileHeading>Temperature &amp; dew point, 24 hours</TileHeading>
        <Empty>No history yet</Empty>
      </Tile>
    );
  }

  // ⚠ Domain spans BOTH series, then pads. Computing it from temperature alone is
  // what pushed the dew-point line off the bottom of the plot.
  const all = [...temps, ...dews];
  const pad = Math.max(2, (Math.max(...all) - Math.min(...all)) * 0.12);
  const lo = Math.min(...all) - pad;
  const hi = Math.max(...all) + pad;

  const t = pathFor(temps, 0, CHART_W, 6, CHART_H - 6, lo, hi);
  const dew = dews.length ? pathFor(dews, 0, CHART_W, 6, CHART_H - 6, lo, hi) : null;
  const grid = ledgerGrid(CHART_W, CHART_H);

  return (
    <Tile id="history-chart" style={style}>
      {/* Heading is serif italic sentence case; the range line is mono, to its
          right. No legend pills, no y-axis column. */}
      <TileHeading style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: s(16) }}>
        <span>Temperature &amp; dew point, 24 hours</span>
        <span style={{ ...type('mono'), ...tnum, color: v.textSecondary }}>
          {fmt(Math.min(...temps))}–{fmt(Math.max(...temps))} °F
          {d.history.avgTempF != null && ` · avg ${fmt(d.history.avgTempF)}°`}
          {d.history.sampleCount != null && ` · ${fmtInt(d.history.sampleCount)} samples`}
        </span>
      </TileHeading>

      <div style={{ background: v.chart.surface, flex: 1, minHeight: 0 }}>
        <svg
          viewBox={`0 0 ${CHART_W} ${CHART_H}`}
          preserveAspectRatio="none"
          style={{ display: 'block', width: '100%', height: '100%' }}
        >
          {grid.hRules.map((g, i) => (
            <line key={`h${i}`} x1={0} y1={g.y} x2={CHART_W} y2={g.y}
                  stroke={g.op > 0.25 ? v.chart.gridMajor : v.chart.gridMinor} strokeWidth={0.6} />
          ))}
          {grid.vRules.map((g, i) => (
            <line key={`v${i}`} x1={g.x} y1={0} x2={g.x} y2={CHART_H}
                  stroke={g.op > 0.1 ? v.chart.gridMajor : v.chart.gridMinor} strokeWidth={0.4} />
          ))}

          {/* dew point: solid, secondary trace colour. Not dashed, not saturated.
              ``vectorEffect="non-scaling-stroke"`` on every path here — the SVG
              uses ``preserveAspectRatio="none"`` and scales x ~3× more than y, so
              without it a stroke draws ~3× thicker horizontally than vertically. */}
          {dew && <path d={dew.line} fill="none" stroke={v.chart.traceSecondary} strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />}

          {/* temperature drawn twice — ink shadow under accent. This doubling is
              what makes it read as ink on paper rather than a line on a screen. */}
          <path d={t.line} fill="none" stroke={v.chart.traceShadow} strokeWidth={2.4} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
          <path d={t.line} fill="none" stroke={v.chart.trace} strokeWidth={1.8} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />

          <circle cx={t.last.x} cy={t.last.y} r={3.5} fill={v.chart.surface} stroke={v.chart.trace} strokeWidth={1.8} />
        </svg>
      </div>

      {/* Five relative labels. Not eleven absolute datetimes. */}
      <div style={{ display: 'flex', justifyContent: 'space-between', ...type('sectionLabel'), color: v.chart.axis }}>
        <span>−24h</span><span>−18</span><span>−12</span><span>−6</span><span>now</span>
      </div>
    </Tile>
  );
};

/* ─────────────────────────────────────────────────────────── 4. barometer */

export const BarometerTile: React.FC<{ d: DashboardData; style?: React.CSSProperties }> = ({ d, style }) => {
  // Dial size dropped 260 → 210 in Design v43 to make room for the
  // zone strip below.  Numerals + zone words no longer share the
  // plate — words leave for the strip; three numerals remain on
  // the dial in pockets the needle sweep cannot reach.
  const size = 210;
  const trend = d.barometer.trendInHgPer3h;
  const arrow = trend == null ? '' : trend > 0.005 ? '↑ rising' : trend < -0.005 ? '↓ falling' : '→ steady';
  const zone = activeZone(d.barometer.inHg);

  return (
    <Tile id="barometer" style={style}>
      <div style={{ display: 'flex', alignItems: 'center', gap: s(10), flex: 1, minHeight: 0 }}>
        {/* Container-fill wrapper (Design v43 step 6): tile owns
            physical size in ``s()`` units (viewport-scaled); the
            instrument fills 100 % of the slot and rebuilds via
            ResizeObserver when the wrapper changes size.  Kills the
            raw-pixel gap that made the dial drift from the tile at
            other viewport heights. */}
        <div style={{ width: s(size), aspectRatio: '1', flexShrink: 0 }}>
          <WheelBarometer
            inHg={d.barometer.inHg}
            trendInHgPer3h={d.barometer.trendInHgPer3h}
            size={size}
          />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: s(5), minWidth: 0 }}>
          <div style={{ ...type('title'), color: v.text }}>Barometer</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: s(6) }}>
            <span style={{ ...type('mono', fs(34)), ...tnum, color: v.text, lineHeight: 1 }}>
              {fmt(d.barometer.inHg, 2)}
            </span>
            <SectionLabel>inHg</SectionLabel>
          </div>
          <SectionLabel color={v.accent}>
            {arrow}{trend != null && ` · ${trend > 0 ? '+' : ''}${trend.toFixed(3)} in / 3h`}
          </SectionLabel>
          {/* hPa summary + today's H/L, Design v43.  Zone name lives
              on the dial + strip; the readout drops it to avoid
              triplicating the same word.  Everything mono 11 px in
              secondary ink except the values (H 30.04 / L 29.97),
              which stay in primary so the row has hierarchy. */}
          <div style={{ marginTop: 'auto', paddingTop: s(9), borderTop: `${v.ruleHairWidth} ${v.ruleStyle} ${v.ruleHair}`, display: 'flex', flexDirection: 'column', gap: s(7) }}>
            {d.barometer.hPa != null && (
              <div style={{ ...type('mono', fs(11)), ...tnum, color: v.textSecondary, letterSpacing: '0.4px' }}>
                {fmt(d.barometer.hPa, 1)} hPa · sea-level
              </div>
            )}
            <div style={{ ...type('mono', fs(11)), ...tnum, color: v.text, whiteSpace: 'nowrap', letterSpacing: '0.6px' }}>
              H {fmt(d.barometer.todayHigh, 2)}{' '}
              <span style={{ color: v.textSecondary }}>{fmtTime(d.barometer.todayHighAt)}</span>
              {'  '}L {fmt(d.barometer.todayLow, 2)}{' '}
              <span style={{ color: v.textSecondary }}>{fmtTime(d.barometer.todayLowAt)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Zone strip — full tile width, five cells, columns weighted
          by each zone's share of the 2.5-inHg range so the strip is
          a legend AND an unrolled scale.  Active cell picks up the
          copper wash + a 2 px copper rule on its top edge
          overlapping the strip's 1 px separator.  Design v43. */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: ZONE_BANDS.map(
            (b) => `${((b.to - b.from) / (MAX_INHG - MIN_INHG)).toFixed(3)}fr`,
          ).join(' '),
          borderTop: `${v.ruleHairWidth} ${v.ruleStyle} ${v.ruleHair}`,
          marginTop: s(8),
        }}
      >
        {ZONE_BANDS.map((b, i) => {
          const isActive = zone?.label === b.label;
          return (
            <div
              key={b.label}
              style={{
                ...type('sectionLabel'),
                padding: `${s(6)} 0`,
                textAlign: 'center',
                color: isActive ? v.accent : v.textSecondary,
                opacity: isActive ? 1 : 0.55,
                background: isActive
                  ? `color-mix(in oklab, var(--color-accent) 8%, transparent)`
                  : 'transparent',
                borderTop: isActive
                  ? `2px solid var(--color-accent)`
                  : 'none',
                marginTop: isActive ? '-2px' : 0,
                borderLeft: i === 0 ? 'none' : `${v.ruleHairWidth} ${v.ruleStyle} ${v.ruleHair}`,
              }}
            >
              {b.label}
            </div>
          );
        })}
      </div>
    </Tile>
  );
};

/* ────────────────────────────────────────────────────────────────── 5. wind */

export const WindTile: React.FC<{ d: DashboardData; style?: React.CSSProperties }> = ({ d, style }) => {
  const SIZE = 250;

  return (
    <Tile id="wind" style={style}>
      {/* Compass first, title inside the readout column — same pattern as the
          barometer.  Design v35 T3 swapped the SVG compass + rosePetals +
          needle for the Highcharts WindRoseDial; the readout column
          below is unchanged. */}
      <div style={{ display: 'flex', alignItems: 'center', gap: s(10), flex: 1, minHeight: 0 }}>
        <WindRoseDial
          roseWeights={d.wind.roseWeights}
          directionDeg={d.wind.directionDeg}
          speedMph={d.wind.speedMph}
          size={SIZE}
        />

        <div style={{ display: 'flex', flexDirection: 'column', gap: s(5), minWidth: 0 }}>
          <div style={{ ...type('title'), color: v.text }}>Wind</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: s(6) }}>
            <span style={{ ...type('mono', fs(34)), ...tnum, color: v.text, lineHeight: 1 }}>
              {fmt(d.wind.speedMph, 0)}
            </span>
            <SectionLabel>mph {d.wind.directionLabel ?? ''}</SectionLabel>
          </div>
          <div style={{ ...type('body', fs(12.5)), color: v.textSecondary, lineHeight: 1.4, textWrap: 'pretty' }}>
            {d.wind.directionLabel && (COMPASS_NAME[d.wind.directionLabel] ?? d.wind.directionLabel)}
            {d.wind.gustMph != null && `, gusting ${fmt(d.wind.gustMph, 0)}`}
            {(d.wind.directionLabel || d.wind.gustMph != null) && '. '}
            {d.wind.peakMph != null && `Peak ${fmt(d.wind.peakMph, 0)} mph${d.wind.peakAt ? ` at ${fmtTime(d.wind.peakAt)}` : ''}.`}
          </div>
          <div style={{ display: 'flex', gap: s(16), marginTop: 'auto', paddingTop: s(8), borderTop: `${v.ruleHairWidth} ${v.ruleStyle} ${v.ruleHair}` }}>
            {d.wind.directionDeg != null && (
              <span style={{ ...type('mono', fs(11)), ...tnum, color: v.textSecondary }}>
                {Math.round(d.wind.directionDeg)}°
              </span>
            )}
            <span style={{ ...type('mono', fs(11)), ...tnum, color: v.textSecondary }}>
              Humidity {fmt(d.outside.humidityPct, 0, '%')}
              {d.outside.insideHumidityPct != null && ` · inside ${fmt(d.outside.insideHumidityPct, 0, '%')}`}
            </span>
          </div>
        </div>
      </div>
    </Tile>
  );
};

/** Full compass names for the log's prose line. */
const COMPASS_NAME: Record<string, string> = {
  N: 'North', NNE: 'North-northeast', NE: 'Northeast', ENE: 'East-northeast',
  E: 'East', ESE: 'East-southeast', SE: 'Southeast', SSE: 'South-southeast',
  S: 'South', SSW: 'South-southwest', SW: 'Southwest', WSW: 'West-southwest',
  W: 'West', WNW: 'West-northwest', NW: 'Northwest', NNW: 'North-northwest',
};

/* ────────────────────────────────────────────────────────────────── 6. rain */

export const RainTile: React.FC<{ d: DashboardData; title?: string; style?: React.CSSProperties }> = ({ d, title = 'Rain', style }) => (
  <Tile id="rain" style={style}>
    <TileHeading>{title}</TileHeading>
    <div style={{ display: 'flex', alignItems: 'baseline', gap: s(8) }}>
      <span style={{ ...type('mono', fs(30)), ...tnum, color: v.sky, lineHeight: 1 }}>
        {fmt(d.rain.rateInPerHr, 2)}
      </span>
      <SectionLabel>in/hr</SectionLabel>
      <SectionLabel style={{ marginLeft: 'auto' }}>
        {(d.rain.rateInPerHr ?? 0) > 0 ? 'Raining' : 'Not raining'}
      </SectionLabel>
    </div>
    <div style={{ marginTop: 'auto' }}>
      <Row label="Today" value={fmt(d.rain.todayIn, 2, ' in')} />
      <Row label="Yesterday" value={fmt(d.rain.yesterdayIn, 2, ' in')} />
      {/* Year figure carries provenance when it's an archive-derived
          recomputation — Design v41.  The banner in Settings explains
          the situation once; the inline label explains the number
          every time someone reads it, which is where ``0.21 in`` was
          suspicious for three rounds. */}
      <Row
        label="Year"
        value={
          fmt(d.rain.yearIn, 2, ' in') +
          (d.rain.yearSource === 'archive' ? ' (archive)' : '')
        }
        last
      />
    </div>
  </Tile>
);

/* ──────────────────────────────────────────────────────────── 7. solar & uv */

export const SolarUvTile: React.FC<{ d: DashboardData; style?: React.CSSProperties }> = ({ d, style }) => (
  <Tile id="solar-uv" style={style}>
    <TileHeading>Sun &amp; water</TileHeading>
    <div style={{ display: 'flex', alignItems: 'baseline', gap: s(8) }}>
      <span style={{ ...type('mono', fs(30)), ...tnum, color: v.warning, lineHeight: 1 }}>
        {fmtInt(d.solar.wm2)}
      </span>
      <SectionLabel>W/m²</SectionLabel>
      <span style={{ ...type('mono'), ...tnum, color: v.textSecondary, marginLeft: 'auto' }}>
        UV {fmt(d.solar.uvIndex)}
      </span>
    </div>
    <div style={{ marginTop: 'auto' }}>
      <Row label="Energy today" value={fmt(d.solar.energyMJ, 2, ' MJ/m²')} />
      <Row label="Evapotranspiration" value={fmt(d.solar.etIn, 3, ' in')} last />
    </div>
  </Tile>
);

/* ─────────────────────────────────────────────────────────────── 8. almanac */

export const AlmanacTile: React.FC<{ d: DashboardData; style?: React.CSSProperties }> = ({ d, style }) => (
  <Tile id="almanac" style={style}>
    <TileHeading>Almanac for today</TileHeading>
    {/* Three rows. Station diagnostics are their own tile — don't merge them here. */}
    <div>
      <Row label="Sunrise / sunset" value={`${d.almanac.sunrise ?? '—'} · ${d.almanac.sunset ?? '—'}`} />
      <Row
        label="Day length"
        value={
          <>
            {d.almanac.dayLength ?? '—'}
            {d.almanac.dayLengthDelta && <span style={{ color: v.danger }}> {d.almanac.dayLengthDelta}</span>}
          </>
        }
      />
      <Row
        label="Moon"
        value={`${d.almanac.moonPhase ?? '—'}${d.almanac.moonIlluminationPct != null ? ` ${Math.round(d.almanac.moonIlluminationPct)}%` : ''}`}
        last
      />
    </div>
  </Tile>
);

/* ────────────────────────────────────────────────────── 9. rainfall by hour */

/**
 * 1d labels this axis '24h ago · <peak> in peak, <time> · now' — three marks, not
 * six hour ticks. Set `relativeAxis` false for the 12a/4a/8a… form.
 */
export const RainfallByHourTile: React.FC<{ d: DashboardData; relativeAxis?: boolean; style?: React.CSSProperties }> = ({ d, relativeAxis = true, style }) => {
  const bars = d.rain.hourlyIn ?? [];
  const max = Math.max(0.05, ...bars.map((n) => n ?? 0));
  const peakIdx = bars.findIndex((n) => (n ?? 0) === max);
  const peakLabel =
    peakIdx < 0 ? null : peakIdx === 0 ? '12 AM' : peakIdx < 12 ? `${peakIdx} AM` : peakIdx === 12 ? '12 PM' : `${peakIdx - 12} PM`;
  const W = 700, H = 74;

  return (
    <Tile id="rainfall-hourly" style={style}>
      <TileHeading style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <span>Rainfall by hour</span>
        <span style={{ ...type('mono'), ...tnum, color: v.textSecondary }}>
          {fmt(d.rain.todayIn, 2)} in today · peak {fmt(max, 2)} in/hr
        </span>
      </TileHeading>
      {/* Always render the 24 slots. An empty axis reads as "no rain today";
          an empty tile reads as broken.

          ⚠ preserveAspectRatio="none" stretches EVERYTHING in the viewBox,
          including <text> — with the tile stretched, 10px hour labels rendered
          ~3x oversized and detached from the plot. The axis is therefore HTML
          below the svg, and the svg has a fixed height rather than flex:1. */}
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        style={{ display: 'block', width: '100%', height: H, flexShrink: 0 }}
      >
        {Array.from({ length: 24 }, (_, i) => {
          const val = bars[i] ?? 0;
          const h = val > 0 ? Math.max(2, (val / max) * (H - 8)) : 0;
          const w = W / 24;
          return <rect key={i} x={i * w + 2} y={H - h} width={w - 4} height={h} fill={v.chart.rain} />;
        })}
        <line x1={0} y1={H - 0.4} x2={W} y2={H - 0.4} stroke={v.rule} strokeWidth={0.8} />
      </svg>
      <div style={{ display: 'flex', ...type('sectionLabel'), color: v.chart.axis }}>
        {relativeAxis ? (
          <>
            <span style={{ flex: 1, textAlign: 'left' }}>24h ago</span>
            <span style={{ flex: 2, textAlign: 'center' }}>
              {max > 0.001 ? `${fmt(max, 2)} in peak${peakLabel ? `, ${peakLabel}` : ''}` : 'no rain recorded'}
            </span>
            <span style={{ flex: 1, textAlign: 'right' }}>now</span>
          </>
        ) : (
          Array.from({ length: 6 }, (_, k) => (
            <span key={k} style={{ flex: 1, textAlign: k === 0 ? 'left' : 'center' }}>
              {k * 4 === 0 ? '12a' : k * 4 < 12 ? `${k * 4}a` : k * 4 === 12 ? '12p' : `${k * 4 - 12}p`}
            </span>
          ))
        )}
      </div>
    </Tile>
  );
};

/* ──────────────────────────────────────────────────────── 10. station status */

export const StationStatusTile: React.FC<{ d: DashboardData; style?: React.CSSProperties }> = ({ d, style }) => {
  // Named ``stn`` so it doesn't shadow the ``s(n)`` scale helper.
  const stn = d.station;
  const items: [string, React.ReactNode][] = [
    ['Console', `${stn.console} ${stn.model}`],
    ['Firmware', stn.firmware],
    ['Transmitters', <span style={{ color: stn.transmittersOk ? v.success : v.danger }}>{stn.transmittersOk ? 'ok' : 'fault'}</span>],
    ['Battery', fmt(stn.batteryVolts, 2, ' V')],
    ['CRC / timeouts', `${stn.crcErrors} / ${stn.timeouts}`],
    ['Archive', fmtInt(stn.archiveRecords, ' records')],
  ];

  return (
    <Tile id="station-status" style={style}>
      <SectionLabel>Station status</SectionLabel>
      <Rule strong />
      {/* A diagnostics STRIP: label + value pairs flowing on two lines, separated
          by rules. Not a 16-field form, and no Sync button — that lives in
          Settings › Station, which is sign-in gated. */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: `${s(6)} ${s(18)}`, alignItems: 'baseline' }}>
        {items.map(([label, value]) => (
          <span key={label} style={{ display: 'inline-flex', alignItems: 'baseline', gap: s(6), whiteSpace: 'nowrap' }}>
            <span style={{ ...type('sectionLabel'), color: v.textMuted }}>{label}</span>
            <span style={{ ...type('mono'), ...tnum, color: v.text }}>{value}</span>
          </span>
        ))}
      </div>
      {/* No clock line here — it's in the footer strip, and having both was the
          duplicated 'Clock … last poll …' pair at the foot of the page. */}
    </Tile>
  );
};

const Empty: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ ...type('body'), color: v.textMuted, display: 'flex', alignItems: 'center', flex: 1 }}>{children}</div>
);
