// ============================================================
// Hook that surfaces current weather conditions from the
// WeatherDataContext with loading / error semantics.
// ============================================================

import { useState, useEffect } from "react";
import type { CurrentConditions } from "../api/types.ts";
import { useWeatherData } from "../context/WeatherDataContext.tsx";

interface UseCurrentConditionsReturn {
  data: CurrentConditions | null;
  loading: boolean;
  error: string | null;
}

export function useCurrentConditions(): UseCurrentConditionsReturn {
  const { currentConditions } = useWeatherData();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (currentConditions !== null) {
      setLoading(false);
      setError(null);
    }
  }, [currentConditions]);

  // If data never arrives after a generous timeout, surface an error.
  useEffect(() => {
    const timer = setTimeout(() => {
      if (currentConditions === null) {
        setLoading(false);
        setError("Timed out waiting for weather data");
      }
    }, 15_000);
    return () => clearTimeout(timer);
  }, [currentConditions]);

  return { data: currentConditions, loading, error };
}
