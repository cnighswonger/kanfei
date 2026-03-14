/**
 * Full-page area spline chart for the History page.
 * Supports zoom/pan on the x-axis with gradient fill.
 */
import { useMemo } from "react";
import Highcharts from "highcharts";
import HighchartsReact from "highcharts-react-official";
import { getHighchartsTimeConfig, resolveTimezone } from "../../utils/timezone.ts";
import { computeYAxisScale } from "../../utils/chartScaling.ts";

interface HistoricalChartProps {
  title: string;
  sensor: string;
  data: { timestamp: string; value: number }[];
  unit: string;
}

function getCSSVar(name: string): string {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
}

export default function HistoricalChart({
  title,
  sensor,
  data,
  unit,
}: HistoricalChartProps) {
  const tz = resolveTimezone();
  const options: Highcharts.Options = useMemo(() => {
    const textColor = getCSSVar("--color-text") || "#e8e9ed";
    const secondaryColor = getCSSVar("--color-text-secondary") || "#9ca3b4";
    const mutedColor = getCSSVar("--color-text-muted") || "#5c6478";
    const borderColor = getCSSVar("--color-border") || "#2a2d3e";
    const accentColor = getCSSVar("--color-accent") || "#3b82f6";
    const cardBg = getCSSVar("--color-bg-card-solid") || getCSSVar("--color-bg-card") || "#1e2130";

    const seriesData = data.map((pt) => [
      new Date(pt.timestamp).getTime(),
      pt.value,
    ]);

    const yScale = computeYAxisScale(
      sensor,
      data.map((pt) => pt.value).filter(Number.isFinite),
    );

    return {
      time: getHighchartsTimeConfig(),
      chart: {
        type: "areaspline",
        height: 400,
        backgroundColor: "transparent",
        zooming: { type: "x" },
        style: {
          fontFamily:
            getCSSVar("--font-body") ||
            "'Inter', -apple-system, sans-serif",
        },
      },
      title: {
        text: title,
        style: {
          fontSize: "16px",
          fontWeight: "bold",
          color: textColor,
        },
      },
      subtitle: {
        text: "Click and drag to zoom",
        style: {
          fontSize: "11px",
          color: mutedColor,
        },
      },
      credits: { enabled: false },
      legend: { enabled: false },
      xAxis: {
        type: "datetime",
        lineColor: borderColor,
        tickColor: borderColor,
        labels: {
          style: { color: secondaryColor, fontSize: "11px" },
        },
        gridLineWidth: 0,
      },
      yAxis: {
        title: {
          text: unit,
          style: { color: secondaryColor, fontSize: "12px" },
        },
        labels: {
          style: { color: secondaryColor, fontSize: "11px" },
        },
        gridLineColor: borderColor,
        gridLineWidth: 1,
        gridLineDashStyle: "Dot",
        softMin: yScale.softMin,
        softMax: yScale.softMax,
        ...(yScale.tickInterval != null && { tickInterval: yScale.tickInterval }),
      },
      tooltip: {
        xDateFormat: "%A, %b %e %Y %l:%M %p",
        pointFormat: `<b>{point.y:.1f}</b> ${unit}`,
        backgroundColor: cardBg,
        borderColor: borderColor,
        style: { color: textColor, fontSize: "12px" },
      },
      plotOptions: {
        areaspline: {
          lineWidth: 2,
          marker: {
            enabled: false,
            states: {
              hover: { enabled: true, radius: 4 },
            },
          },
          fillColor: {
            linearGradient: { x1: 0, y1: 0, x2: 0, y2: 1 },
            stops: [
              [0, Highcharts.color(accentColor).setOpacity(0.4).get("rgba") as string],
              [1, Highcharts.color(accentColor).setOpacity(0.02).get("rgba") as string],
            ],
          },
          threshold: null,
        },
      },
      series: [
        {
          type: "areaspline" as const,
          name: sensor,
          data: seriesData,
          color: accentColor,
        },
      ],
    };
  }, [title, sensor, data, unit, tz]);

  return (
    <div
      style={{
        background: "var(--color-bg-card)",
        borderRadius: "var(--gauge-border-radius, 16px)",
        boxShadow: "var(--gauge-shadow, 0 4px 24px rgba(0,0,0,0.4))",
        border: "1px solid var(--color-border)",
        padding: "16px",
        overflow: "hidden",
      }}
    >
      <HighchartsReact highcharts={Highcharts} options={options} />
    </div>
  );
}
