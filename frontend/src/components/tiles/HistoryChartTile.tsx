/**
 * 24-hour temperature + dew point spline.  On paper themes a
 * ``ledgerGrid()`` overlay draws pale ruled horizontals (with a
 * stronger midline) behind the plot so the trace reads as ink on
 * ruled paper rather than a line on a chart.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import Highcharts from 'highcharts';
import { HighchartsReact } from 'highcharts-react-official';
import { fetchHistory } from '../../api/client.ts';
import type { HistoryPoint } from '../../api/types.ts';
import { getHighchartsTimeConfig } from '../../utils/timezone.ts';
import TileLabel from '../common/TileLabel.tsx';
import { useTheme } from '../../context/ThemeContext.tsx';
import { ledgerGrid } from '../../utils/gauges.ts';

function getCSSVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export default function HistoryChartTile() {
  const [tempPts, setTempPts] = useState<HistoryPoint[]>([]);
  const [dewPts, setDewPts] = useState<HistoryPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const { theme } = useTheme();
  const paper = theme.surface?.ownsBackground === true;
  const plotRef = useRef<HTMLDivElement>(null);
  const [plotSize, setPlotSize] = useState({ w: 0, h: 0 });

  useEffect(() => {
    if (!paper) return;
    const el = plotRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setPlotSize({ w: entry.contentRect.width, h: entry.contentRect.height });
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [paper]);

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
        // Domain across BOTH series so the dew line (lower than temp
        // by ~10 °F on humid days) never falls below the plot floor.
        // Highcharts auto-computes when min/max are unset; the
        // softMin/softMax pad the extremes without hard-clamping the
        // trace when a series briefly leaves the padded range.
        softMin: (() => {
          const all = [...tempPts, ...dewPts]
            .map((p) => p.value)
            .filter((v): v is number => v != null && Number.isFinite(v));
          return all.length ? Math.floor(Math.min(...all) - 2) : undefined;
        })(),
        softMax: (() => {
          const all = [...tempPts, ...dewPts]
            .map((p) => p.value)
            .filter((v): v is number => v != null && Number.isFinite(v));
          return all.length ? Math.ceil(Math.max(...all) + 2) : undefined;
        })(),
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
      <div ref={plotRef} style={{ flex: 1, minHeight: 0, position: 'relative' }}>
        {paper && plotSize.w > 0 && plotSize.h > 0 && (
          <svg
            width={plotSize.w}
            height={plotSize.h}
            viewBox={`0 0 ${plotSize.w} ${plotSize.h}`}
            style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}
            aria-hidden
          >
            {(() => {
              const g = ledgerGrid(plotSize.w, plotSize.h);
              return (
                <>
                  {g.hRules.map((r, i) => (
                    <line key={`h${i}`} x1={0} y1={r.y} x2={plotSize.w} y2={r.y} stroke="var(--chart-grid)" opacity={r.op} />
                  ))}
                  {g.vRules.map((r, i) => (
                    <line key={`v${i}`} x1={r.x} y1={0} x2={r.x} y2={plotSize.h} stroke="var(--chart-grid)" opacity={r.op} />
                  ))}
                </>
              );
            })()}
          </svg>
        )}
        {loading && !tempPts.length ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--color-text-muted)' }}>Loading…</div>
        ) : (
          <HighchartsReact
            highcharts={Highcharts}
            options={options}
            containerProps={{ style: { height: '100%', width: '100%', position: 'relative', zIndex: 1 } }}
          />
        )}
      </div>
    </div>
  );
}
