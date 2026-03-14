/**
 * Alert context: listens for alert_triggered / alert_cleared WebSocket
 * events and manages a stack of active alert toasts.
 */

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useCallback,
} from "react";
import type { ReactNode } from "react";
import type { AlertEvent } from "../api/types.ts";
import { useWeatherData } from "./WeatherDataContext.tsx";

interface AlertContextValue {
  alerts: AlertEvent[];
  dismissAlert: (id: string) => void;
}

const AlertCtx = createContext<AlertContextValue | null>(null);

interface AlertProviderProps {
  children: ReactNode;
}

const AUTO_DISMISS_MS = 30_000;

export function AlertProvider({ children }: AlertProviderProps) {
  const { ws } = useWeatherData();
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const dismissTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const dismissAlert = useCallback((id: string) => {
    const timer = dismissTimers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      dismissTimers.current.delete(id);
    }
    setAlerts((prev) => prev.filter((a) => a.id !== id));
  }, []);

  useEffect(() => {
    if (!ws) return;

    const onTriggered = (data: unknown) => {
      const alert = data as AlertEvent;
      setAlerts((prev) => {
        const filtered = prev.filter((a) => a.id !== alert.id);
        return [...filtered, alert];
      });

      // Reset auto-dismiss timer (clear old one first)
      const existing = dismissTimers.current.get(alert.id);
      if (existing) clearTimeout(existing);
      dismissTimers.current.set(
        alert.id,
        setTimeout(() => {
          dismissTimers.current.delete(alert.id);
          setAlerts((prev) => prev.filter((a) => a.id !== alert.id));
        }, AUTO_DISMISS_MS),
      );
    };

    const onCleared = (data: unknown) => {
      const { id } = data as { id: string };
      const timer = dismissTimers.current.get(id);
      if (timer) {
        clearTimeout(timer);
        dismissTimers.current.delete(id);
      }
      setAlerts((prev) => prev.filter((a) => a.id !== id));
    };

    ws.onMessage("alert_triggered", onTriggered);
    ws.onMessage("alert_cleared", onCleared);

    return () => {
      ws.offMessage("alert_triggered", onTriggered);
      ws.offMessage("alert_cleared", onCleared);
    };
  }, [ws]);

  return (
    <AlertCtx.Provider value={{ alerts, dismissAlert }}>
      {children}
    </AlertCtx.Provider>
  );
}

export function useAlerts(): AlertContextValue {
  const ctx = useContext(AlertCtx);
  if (ctx === null) {
    throw new Error("useAlerts must be used within an AlertProvider");
  }
  return ctx;
}
