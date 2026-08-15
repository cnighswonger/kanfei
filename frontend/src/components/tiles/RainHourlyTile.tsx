/**
 * Rainfall-by-hour histogram tile per Design REVIEW-02.
 *
 * 24 bars of hourly rain totals, derived from the outside rain_rate
 * / rain_total history bucketed by hour.  A bar is empty when no rain
 * fell that hour so the eye reads dry bands as gaps rather than a
 * flat baseline.
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

/**
 * Bucket rain-rate samples (in/hr) into hourly totals (in).  Each
 * sample represents an instantaneous rate; multiply by its share of
 * the hour and sum.  Server-side we already resample; here we just
 * bin whatever comes back to the top-of-hour of the reading's local
 * time.
 */
function bucketHourly(points: HistoryPoint[]): { x: number; y: number }[] {
  const buckets = new Map<number, number>();
  for (let i = 0; i < points.length; i++) {
    const p = points[i];
    if (p.value == null) continue;
    const t = Date.parse(p.timestamp);
    const hour = new Date(t);
    hour.setMinutes(0, 0, 0);
    const key = hour.getTime();
    // Sample width in hours = time to previous sample, clamped to a
    // sensible upper bound so a long gap doesn't inflate one bar.
    const prev = i > 0 ? Date.parse(points[i - 1].timestamp) : t - 5 * 60_000;
    const dtHours = Math.min(Math.max((t - prev) / 3_600_000, 0), 1);
    buckets.set(key, (buckets.get(key) ?? 0) + p.value * dtHours);
  }
  return Array.from(buckets.entries())
    .sort(([a], [b]) => a - b)
    .map(([x, y]) => ({ x, y: Math.round(y * 1000) / 1000 }));
}

export default function RainHourlyTile() {
  const [pts, setPts] = useState<HistoryPoint[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const end = new Date();
      const start = new Date(end.getTime() - 24 * 60 * 60_000);
      try {
        const r = await fetchHistory('rain_rate', start.toISOString(), end.toISOString(), '5m');
        if (!cancelled) setPts(r.points ?? []);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    const id = setInterval(load, 5 * 60_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  const hourly = useMemo(() => bucketHourly(pts), [pts]);
  const peak = hourly.reduce((m, p) => (p.y > m.y ? p : m), { x: 0, y: 0 });

  const options: Highcharts.Options = useMemo(() => {
    const trace = getCSSVar('--chart-series-rain') || getCSSVar('--color-rain-blue') || '#5c7f9a';
    const grid = getCSSVar('--chart-grid') || 'rgba(0,0,0,0.12)';
    const axis = getCSSVar('--chart-axis') || getCSSVar('--color-text-secondary') || '#5c6478';
    const bodyFont = getCSSVar('--font-body') || "'Inter', sans-serif";
    return {
      time: getHighchartsTimeConfig(),
      chart: {
        type: 'column',
        backgroundColor: 'transparent',
        spacing: [8, 8, 8, 8],
        style: { fontFamily: bodyFont },
      },
      title: { text: undefined },
      credits: { enabled: false },
      legend: { enabled: false },
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
        labels: { style: { color: axis, fontSize: 'calc(9px * var(--font-scale))' }, format: '{value} in' },
        min: 0,
      },
      tooltip: { xDateFormat: '%a %H:%M', valueSuffix: ' in', valueDecimals: 2 },
      plotOptions: { column: { pointPadding: 0.05, borderWidth: 0, animation: false } },
      series: [{
        type: 'column',
        name: 'Rain',
        color: trace,
        data: hourly.map((p) => [p.x, p.y] as [number, number]),
      }],
    };
  }, [hourly]);

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
      <TileLabel>Rainfall by hour</TileLabel>
      <div style={{ flex: 1, minHeight: 0 }}>
        {loading && hourly.length === 0 ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--color-text-muted)' }}>Loading…</div>
        ) : (
          <HighchartsReact
            highcharts={Highcharts}
            options={options}
            containerProps={{ style: { height: '100%', width: '100%' } }}
          />
        )}
      </div>
      {peak.y > 0 && (
        <div style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 'calc(10px * var(--font-scale))',
          color: 'var(--color-text-muted)',
          marginTop: '4px',
        }}>
          {`${peak.y.toFixed(2)} in peak, ${new Date(peak.x).toLocaleTimeString('en-US', { hour: 'numeric' })}`}
        </div>
      )}
    </div>
  );
}
