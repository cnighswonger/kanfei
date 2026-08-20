/**
 * Fetch history for N sensors in parallel — Design v34 HISTORY.md
 * tranche 2b support.  The single-sensor hook still exists for the
 * dashboard tiles that plot one series; the History page's rail can
 * activate any subset of eight and needs them all at once.
 *
 * Returns a Map keyed by sensor id so callers can look up whichever
 * series they need without caring about array ordering.  Loading is
 * true until every request resolves; error is the first failure
 * observed (subsequent successes still populate the map so the chart
 * partially recovers).
 */

import { useEffect, useRef, useState } from "react";
import type { HistoryPoint, HistorySummary } from "../api/types.ts";
import { fetchHistory } from "../api/client.ts";

export interface SeriesFetch {
  data: HistoryPoint[];
  summary: HistorySummary | null;
}

interface UseMultiHistoricalDataReturn {
  series: Map<string, SeriesFetch>;
  loading: boolean;
  error: string | null;
}

export function useMultiHistoricalData(
  sensors: string[],
  start: string,
  end: string,
  resolution: string,
): UseMultiHistoricalDataReturn {
  const [series, setSeries] = useState<Map<string, SeriesFetch>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Stable-string comparison so a caller passing a freshly-built
  // array on every render doesn't re-fetch.  Sorted so ordering
  // doesn't matter — the caller assigns axes and colours from its
  // own definitions, not from array order.
  const sensorsKey = [...sensors].sort().join(",");
  // A ref-held cancel flag so the effect ignores stale responses
  // when the caller flips sensors mid-flight (React StrictMode double
  // invocation, tab switches, rapid clicks).
  const cancelRef = useRef(0);

  useEffect(() => {
    if (sensors.length === 0) {
      setSeries(new Map());
      setLoading(false);
      setError(null);
      return;
    }
    cancelRef.current += 1;
    const myGen = cancelRef.current;
    setLoading(true);
    setError(null);

    Promise.allSettled(
      sensors.map((sensor) => fetchHistory(sensor, start, end, resolution)),
    ).then((results) => {
      if (cancelRef.current !== myGen) return;
      const nextSeries = new Map<string, SeriesFetch>();
      let firstErr: string | null = null;
      results.forEach((r, i) => {
        const sensor = sensors[i];
        if (r.status === "fulfilled") {
          nextSeries.set(sensor, {
            data: r.value.points,
            summary: r.value.summary,
          });
        } else if (!firstErr) {
          firstErr = r.reason instanceof Error ? r.reason.message : String(r.reason);
        }
      });
      setSeries(nextSeries);
      setError(firstErr);
      setLoading(false);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sensorsKey, start, end, resolution]);

  return { series, loading, error };
}
