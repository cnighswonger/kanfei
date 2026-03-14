// ============================================================
// React context that provides live weather data to the entire
// application. Combines WebSocket streaming with REST fallback
// for data that updates less frequently.
// ============================================================

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
} from "react";
import type { ReactNode } from "react";
import type {
  CurrentConditions,
  ForecastResponse,
  AstronomyResponse,
  StationStatus,
  NowcastData,
} from "../api/types.ts";
import { WebSocketManager } from "../api/websocket.ts";
import {
  fetchCurrentConditions,
  fetchForecast,
  fetchAstronomy,
  fetchStationStatus,
  fetchNowcast,
  generateNowcast,
} from "../api/client.ts";
import { ASTRONOMY_REFRESH_INTERVAL, FORECAST_REFRESH_INTERVAL } from "../utils/constants.ts";

// --- Context value shape ---

interface WeatherDataContextValue {
  currentConditions: CurrentConditions | null;
  forecast: ForecastResponse | null;
  astronomy: AstronomyResponse | null;
  stationStatus: StationStatus | null;
  nowcast: NowcastData | null;
  /** Whether the backend reports the serial connection to the station is up. */
  connected: boolean;
  /** Whether our browser WebSocket to the backend is open. */
  wsConnected: boolean;
  /** Warning message from nowcast service (truncation retry failure, etc). */
  nowcastWarning: string | null;
  /** Dismiss the current nowcast warning. */
  dismissNowcastWarning: () => void;
  /** True when NWS alerts are active and nowcast is running faster cycles. */
  alertMode: boolean;
  /** Manually refresh forecast data. */
  refreshForecast: () => void;
  /** Manually refresh nowcast data (fetches cached). */
  refreshNowcast: () => void;
  /** Trigger a new nowcast generation via Claude API. */
  triggerNowcast: () => void;
  /** WebSocket manager for alert subscriptions (null until connected). */
  ws: WebSocketManager | null;
}

const WeatherDataContext = createContext<WeatherDataContextValue | null>(null);

// --- Provider component ---

interface WeatherDataProviderProps {
  children: ReactNode;
}

export function WeatherDataProvider({ children }: WeatherDataProviderProps) {
  const [currentConditions, setCurrentConditions] =
    useState<CurrentConditions | null>(null);
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [astronomy, setAstronomy] = useState<AstronomyResponse | null>(null);
  const [stationStatus, setStationStatus] = useState<StationStatus | null>(
    null,
  );
  const [nowcast, setNowcast] = useState<NowcastData | null>(null);
  const [connected, setConnected] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [nowcastWarning, setNowcastWarning] = useState<string | null>(null);
  const [alertMode, setAlertMode] = useState(false);

  const [ws, setWs] = useState<WebSocketManager | null>(null);

  const dismissNowcastWarning = useCallback(() => setNowcastWarning(null), []);

  // Refresh forecast data from REST endpoint.
  const refreshForecast = useCallback(() => {
    fetchForecast()
      .then(setForecast)
      .catch(() => {
        /* ignore -- will retry on next interval */
      });
  }, []);

  // Fetch cached nowcast (fast — used on page load and periodic refresh).
  const refreshNowcast = useCallback(() => {
    fetchNowcast()
      .then(setNowcast)
      .catch(() => {});
  }, []);

  // Trigger a brand-new nowcast generation via Claude API (slow — Refresh button only).
  const triggerNowcast = useCallback(() => {
    generateNowcast()
      .then(setNowcast)
      .catch(() => {
        fetchNowcast().then(setNowcast).catch(() => {});
      });
  }, []);

  // Fetch slow-changing data (astronomy + nowcast — NOT station status,
  // which has its own backoff-based polling below).
  const refreshSlowData = useCallback(() => {
    fetchAstronomy()
      .then(setAstronomy)
      .catch(() => {
        /* ignore -- will retry on next interval */
      });
    refreshNowcast();
  }, [refreshNowcast]);

  useEffect(() => {
    // --- Initial REST fetches ---
    fetchCurrentConditions()
      .then(setCurrentConditions)
      .catch(() => {
        /* ignore */
      });
    fetchForecast()
      .then(setForecast)
      .catch(() => {
        /* ignore */
      });
    refreshSlowData();

    // Periodically refresh astronomy and nowcast.
    const slowTimer = setInterval(refreshSlowData, ASTRONOMY_REFRESH_INTERVAL);

    // Periodically refresh forecast data.
    const forecastTimer = setInterval(refreshForecast, FORECAST_REFRESH_INTERVAL);

    // --- Station status with backoff polling ---
    // Start fast (5s) so the UI recovers quickly if the logger starts
    // after the web app, then back off to the normal 5-minute cadence.
    const INITIAL_INTERVAL = 5_000;
    const MAX_INTERVAL = ASTRONOMY_REFRESH_INTERVAL; // 5 minutes
    let statusInterval = INITIAL_INTERVAL;
    let statusTimer: ReturnType<typeof setTimeout> | null = null;
    let wasConnected = false;

    const pollStationStatus = () => {
      fetchStationStatus()
        .then((status) => {
          setStationStatus(status);
          if (status.connected) {
            // Logger is up — settle into the normal cadence.
            wasConnected = true;
            statusInterval = MAX_INTERVAL;
          } else if (wasConnected) {
            // Was connected but lost — reset to fast polling for recovery.
            wasConnected = false;
            statusInterval = INITIAL_INTERVAL;
          } else {
            // Still disconnected — back off: 5s, 10s, 20s, 40s, 80s, then cap at 5min.
            statusInterval = Math.min(statusInterval * 2, MAX_INTERVAL);
          }
        })
        .catch(() => {
          if (wasConnected) {
            wasConnected = false;
            statusInterval = INITIAL_INTERVAL;
          } else {
            statusInterval = Math.min(statusInterval * 2, MAX_INTERVAL);
          }
        })
        .finally(() => {
          statusTimer = setTimeout(pollStationStatus, statusInterval);
        });
    };
    pollStationStatus();

    // --- WebSocket setup ---
    const manager = new WebSocketManager();
    setWs(manager);

    // Track WS connection state by polling the manager (the manager
    // itself does not emit events for its own connection state, so we use
    // a short poll that is cheap and avoids adding an event to the manager
    // just for this).
    const wsStateTimer = setInterval(() => {
      setWsConnected(manager.isConnected);
    }, 1000);

    manager.onMessage("sensor_update", (data) => {
      setCurrentConditions(data as CurrentConditions);
    });

    manager.onMessage("forecast_update", (data) => {
      setForecast(data as ForecastResponse);
    });

    manager.onMessage("nowcast_update", (data) => {
      setNowcast(data as NowcastData);
    });

    manager.onMessage("nowcast_warning", (data) => {
      const msg = (data as { message: string }).message;
      setNowcastWarning(msg);
    });

    manager.onMessage("connection_status", (data) => {
      setConnected(data as boolean);
    });

    manager.onMessage("severe_weather_status", (data) => {
      const status = data as { alert_mode: boolean; is_new_alert?: boolean };
      setAlertMode(status.alert_mode);
      if (status.is_new_alert) {
        setNowcastWarning("Updating nowcast — new NWS alert detected");
      }
    });

    manager.connect();

    return () => {
      clearInterval(slowTimer);
      clearInterval(forecastTimer);
      clearInterval(wsStateTimer);
      if (statusTimer !== null) clearTimeout(statusTimer);
      manager.disconnect();
      setWs(null);
    };
  }, [refreshSlowData, refreshForecast]);

  const value: WeatherDataContextValue = {
    currentConditions,
    forecast,
    astronomy,
    stationStatus,
    nowcast,
    connected,
    wsConnected,
    nowcastWarning,
    dismissNowcastWarning,
    alertMode,
    refreshForecast,
    refreshNowcast,
    triggerNowcast,
    ws,
  };

  return (
    <WeatherDataContext.Provider value={value}>
      {children}
    </WeatherDataContext.Provider>
  );
}

// --- Convenience hook ---

export function useWeatherData(): WeatherDataContextValue {
  const ctx = useContext(WeatherDataContext);
  if (ctx === null) {
    throw new Error("useWeatherData must be used within a WeatherDataProvider");
  }
  return ctx;
}
