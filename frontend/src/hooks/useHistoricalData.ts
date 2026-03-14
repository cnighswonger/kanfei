// ============================================================
// Hook for fetching historical sensor data from the REST API.
// Automatically refetches when any parameter changes.
// ============================================================

import { useEffect, useState } from "react";
import type { HistoryPoint, HistorySummary } from "../api/types.ts";
import { fetchHistory } from "../api/client.ts";

interface UseHistoricalDataReturn {
  data: HistoryPoint[];
  summary: HistorySummary | null;
  loading: boolean;
  error: string | null;
}

export function useHistoricalData(
  sensor: string,
  start: string,
  end: string,
  resolution: string = "5m",
): UseHistoricalDataReturn {
  const [data, setData] = useState<HistoryPoint[]>([]);
  const [summary, setSummary] = useState<HistorySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Skip fetch if required params are missing.
    if (!sensor || !start || !end) {
      setData([]);
      setSummary(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchHistory(sensor, start, end, resolution)
      .then((res) => {
        if (!cancelled) {
          setData(res.points);
          setSummary(res.summary ?? null);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setData([]);
          setSummary(null);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [sensor, start, end, resolution]);

  return { data, summary, loading, error };
}
