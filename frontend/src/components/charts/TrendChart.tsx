/**
 * Reusable sparkline-style 24-hour trend chart using Highcharts.
 * Designed to sit beneath gauges for at-a-glance trending.
 */
import { useMemo } from "react";
import Highcharts from "highcharts";
import HighchartsReact from "highcharts-react-official";
import { getHighchartsTimeConfig, resolveTimezone } from "../../utils/timezone.ts";
import { computeYAxisScale } from "../../utils/chartScaling.ts";

interface TrendChartProps {
  title: string;
  data: { x: number; y: number }[];
  unit: string;
  color?: string;
  height?: number;
  sensor?: string;
}

function getCSSVar(name: string): string {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
}

export default function TrendChart({
  title,
  data,
  unit,
  color,
  height = 120,
  sensor,
}: TrendChartProps) {
  const tz = resolveTimezone();
  const options: Highcharts.Options = useMemo(() => {
    const textColor = getCSSVar("--color-text-secondary") || "#9ca3b4";
    const mutedColor = getCSSVar("--color-text-muted") || "#5c6478";
    const borderColor = getCSSVar("--color-border") || "#2a2d3e";
    const lineColor = color || getCSSVar("--color-accent") || "#3b82f6";

    const yScale = sensor
      ? computeYAxisScale(sensor, data.map((pt) => pt.y).filter(Number.isFinite))
      : undefined;

    return {
      time: getHighchartsTimeConfig(),
      chart: {
        type: "spline",
        height,
        backgroundColor: "transparent",
        spacing: [8, 4, 8, 4],
        style: {
          fontFamily:
            getCSSVar("--font-body") ||
            "'Inter', -apple-system, sans-serif",
        },
      },
      title: {
        text: title,
        style: {
          fontSize: "11px",
          color: mutedColor,
          fontWeight: "normal",
        },
      },
      credits: { enabled: false },
      legend: { enabled: false },
      xAxis: {
        type: "datetime",
        lineColor: borderColor,
        tickColor: borderColor,
        labels: {
          style: { color: mutedColor, fontSize: "9px" },
        },
        gridLineWidth: 0,
      },
      yAxis: {
        title: { text: undefined },
        labels: {
          style: { color: mutedColor, fontSize: "9px" },
        },
        gridLineColor: borderColor,
        gridLineWidth: 1,
        gridLineDashStyle: "Dot",
        ...(yScale && {
          softMin: yScale.softMin,
          softMax: yScale.softMax,
          ...(yScale.tickInterval != null && { tickInterval: yScale.tickInterval }),
        }),
      },
      tooltip: {
        xDateFormat: "%b %e, %l:%M %p",
        valueSuffix: ` ${unit}`,
        backgroundColor: getCSSVar("--color-bg-card-solid") || getCSSVar("--color-bg-card") || "#1e2130",
        borderColor: borderColor,
        style: { color: textColor, fontSize: "11px" },
      },
      plotOptions: {
        spline: {
          lineWidth: 2,
          marker: { enabled: false },
          states: {
            hover: { lineWidthPlus: 1 },
          },
        },
      },
      series: [
        {
          type: "spline" as const,
          name: title,
          data: data.map((pt) => [pt.x, pt.y]),
          color: lineColor,
        },
      ],
    };
  }, [title, data, unit, color, height, sensor, tz]);

  return (
    <div
      style={{
        background: "var(--color-bg-card)",
        borderRadius: "var(--gauge-border-radius, 16px)",
        border: "1px solid var(--color-border)",
        overflow: "hidden",
      }}
    >
      <HighchartsReact highcharts={Highcharts} options={options} />
    </div>
  );
}
