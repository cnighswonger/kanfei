/**
 * Daily cumulative solar energy bar chart.
 *
 * Backend integrates instantaneous solar_radiation samples per local
 * calendar day and returns one value per day; this component renders
 * them as a Highcharts column chart with day-boundary bars.
 *
 * The last bar is always today, growing through the day. Days with no
 * data render as gaps (Highcharts treats null values as gaps in the
 * column series by default).
 *
 * Values are already in the operator's preferred unit (MJ/m² / kWh/m² /
 * Wh/m²) — the backend converts before returning.
 */

import { useEffect, useMemo, useState } from "react";
import Highcharts from "highcharts";
import { HighchartsReact } from "highcharts-react-official";
import { API_BASE } from "../../utils/constants.ts";

interface Point {
  date: string;    // YYYY-MM-DD (local date, no timezone info)
  value: number | null;
}

interface Response {
  unit: string;
  days: number;
  points: Point[];
}

interface SolarEnergyDailyChartProps {
  days: number;
  height: number;
}

export default function SolarEnergyDailyChart({ days, height }: SolarEnergyDailyChartProps) {
  const [data, setData] = useState<Response | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`${API_BASE}/api/history/solar-energy?days=${days}`, {
      credentials: "same-origin",
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(`API ${r.status}: ${await r.text()}`);
        return (await r.json()) as Response;
      })
      .then((body) => {
        if (!cancelled) {
          setData(body);
          setLoading(false);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [days]);

  const chartOptions: Highcharts.Options = useMemo(() => {
    const root = document.documentElement;
    const cs = getComputedStyle(root);
    const textMuted = cs.getPropertyValue("--color-text-muted").trim();
    const accent = cs.getPropertyValue("--color-accent").trim();
    const bgCard =
      cs.getPropertyValue("--color-bg-card-solid").trim() ||
      cs.getPropertyValue("--color-bg-card").trim();
    const borderColor = cs.getPropertyValue("--color-border").trim();

    const points = data?.points ?? [];
    const unit = data?.unit ?? "";

    const categories = points.map((p) => p.date);
    const values = points.map((p) => p.value);

    return {
      chart: {
        type: "column",
        height,
        backgroundColor: bgCard,
        style: { fontFamily: "var(--font-body)" },
      },
      title: { text: undefined },
      accessibility: { enabled: false },
      credits: { enabled: false },
      xAxis: {
        categories,
        lineColor: borderColor,
        tickColor: borderColor,
        labels: {
          style: { color: textMuted, fontSize: "calc(11px * var(--font-scale))" },
        },
      },
      yAxis: {
        title: {
          text: `Solar Energy (${unit})`,
          style: { color: textMuted, fontSize: "calc(12px * var(--font-scale))" },
        },
        gridLineColor: borderColor,
        labels: {
          style: { color: textMuted, fontSize: "calc(11px * var(--font-scale))" },
        },
        min: 0,
      },
      tooltip: {
        headerFormat: "<b>{point.key}</b><br/>",
        pointFormat: `{point.y:.2f} ${unit}`,
        backgroundColor: bgCard,
        borderColor,
      },
      plotOptions: {
        column: {
          color: accent,
          borderWidth: 0,
        },
      },
      series: [
        {
          type: "column",
          name: `Daily Solar Energy (${unit})`,
          data: values,
          showInLegend: false,
        },
      ],
    };
  }, [data, height]);

  if (loading) {
    return (
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          height,
        }}
      >
        <div
          style={{
            width: "36px",
            height: "36px",
            border: "3px solid var(--color-border)",
            borderTopColor: "var(--color-accent)",
            borderRadius: "50%",
            animation: "spin 0.8s linear infinite",
          }}
        />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          height,
          flexDirection: "column",
          gap: "8px",
        }}
      >
        <span style={{ color: "var(--color-danger)", fontSize: "calc(16px * var(--font-scale))" }}>
          Failed to load solar-energy history
        </span>
        <span
          style={{
            color: "var(--color-text-muted)",
            fontSize: "calc(13px * var(--font-scale))",
            maxWidth: "400px",
            textAlign: "center",
          }}
        >
          {error}
        </span>
      </div>
    );
  }

  return <HighchartsReact highcharts={Highcharts} options={chartOptions} />;
}
