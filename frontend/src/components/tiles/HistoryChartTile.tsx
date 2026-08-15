/**
 * Full-width 24-hour temperature + dew point chart per Design REVIEW-02.
 *
 * Highcharts spline with two series — temperature as the primary trace
 * (chart.trace accent), dew point as chart.traceSecondary.  Per the
 * mock this is the second thing the eye lands on after the hero
 * temperature, and it's the biggest single absence from the shipped
 * dashboard.
 *
 * The paper-theme "ledger grid" (pale horizontals, stronger midline,
 * faint hour verticals) is a later composition PR — this tile lands
 * the chart with the current shared chart tokens; the ruled ledger
 * treatment folds in with PR 25 (`geometry/gauges.ts` wiring).
 */
import { useEffect, useMemo, useState } from 'react';
import Highcharts from 'highcharts';
import { HighchartsReact } from 'highcharts-react-official';
import { fetchHistory } from '../../api/client.ts';
import type { HistoryPoint } from '../../api/types.ts';
import { getHighchartsTimeConfig } from '../../utils/timezone.ts';
import TileLabel from '../common/TileLabel.tsx';

function getCSSVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export default function HistoryChartTile() {
  const [tempPts, setTempPts] = useState<HistoryPoint[]>([]);
  const [dewPts, setDewPts] = useState<HistoryPoint[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const end = new Date();
      const start = new Date(end.getTime() - 24 * 60 * 60_000);
      const [t, d] = await Promise.all([
        fetchHistory('outside_temp', start.toISOString(), end.toISOString(), '5m'),
        fetchHistory('dew_point', start.toISOString(), end.toISOString(), '5m'),
      ]);
      if (cancelled) return;
      setTempPts(t.points ?? []);
      setDewPts(d.points ?? []);
      setLoading(false);
    };
    load().catch(() => setLoading(false));
    const id = setInterval(load, 5 * 60_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  const options: Highcharts.Options = useMemo(() => {
    const trace = getCSSVar('--chart-trace') || getCSSVar('--color-accent') || '#3b82f6';
    const traceSecondary = getCSSVar('--chart-trace-secondary') || '#3f5d7a';
    const grid = getCSSVar('--chart-grid') || 'rgba(0,0,0,0.12)';
    const axis = getCSSVar('--chart-axis') || getCSSVar('--color-text-secondary') || '#5c6478';
    const bodyFont = getCSSVar('--font-body') || "'Inter', sans-serif";

    return {
      time: getHighchartsTimeConfig(),
      chart: {
        type: 'spline',
        backgroundColor: 'transparent',
        spacing: [8, 8, 8, 8],
        style: { fontFamily: bodyFont },
      },
      title: { text: undefined },
      credits: { enabled: false },
      legend: {
        enabled: true,
        align: 'right',
        verticalAlign: 'top',
        itemStyle: { color: axis, fontSize: 'calc(10px * var(--font-scale))', fontWeight: 'normal' },
      },
      xAxis: {
        type: 'datetime',
        lineColor: grid,
        tickColor: grid,
        gridLineWidth: 0,
        labels: { style: { color: axis, fontSize: 'calc(9px * var(--font-scale))' } },
      },
      yAxis: {
        title: { text: undefined },
        gridLineColor: grid,
        gridLineWidth: 1,
        labels: { style: { color: axis, fontSize: 'calc(9px * var(--font-scale))' } },
      },
      tooltip: { xDateFormat: '%a %H:%M', valueSuffix: ' °F', valueDecimals: 1 },
      plotOptions: {
        spline: { marker: { enabled: false }, lineWidth: 2, animation: false },
      },
      series: [
        {
          type: 'spline',
          name: 'Temperature',
          color: trace,
          data: tempPts.map((p) => [Date.parse(p.timestamp), p.value] as [number, number]),
        },
        {
          type: 'spline',
          name: 'Dew point',
          color: traceSecondary,
          dashStyle: 'ShortDash',
          data: dewPts.map((p) => [Date.parse(p.timestamp), p.value] as [number, number]),
        },
      ],
    };
  }, [tempPts, dewPts]);

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      padding: '16px',
      background: 'var(--color-bg-card)',
      borderRadius: 'var(--gauge-border-radius, 16px)',
      border: '1px solid var(--color-border)',
      height: '100%',
      boxSizing: 'border-box',
    }}>
      <TileLabel>Temperature &amp; dew point, 24 hours</TileLabel>
      <div style={{ flex: 1, minHeight: 0 }}>
        {loading && !tempPts.length ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--color-text-muted)' }}>Loading…</div>
        ) : (
          <HighchartsReact
            highcharts={Highcharts}
            options={options}
            containerProps={{ style: { height: '100%', width: '100%' } }}
          />
        )}
      </div>
    </div>
  );
}
