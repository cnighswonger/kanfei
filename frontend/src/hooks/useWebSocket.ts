// ============================================================
// Custom hook wrapping the WebSocketManager.
// Manages connect-on-mount / disconnect-on-unmount lifecycle.
// ============================================================

import { useEffect, useRef, useState } from "react";
import type { WSMessage } from "../api/types.ts";
import { WebSocketManager } from "../api/websocket.ts";

interface UseWebSocketReturn {
  connected: boolean;
  lastMessage: WSMessage | null;
}

export function useWebSocket(): UseWebSocketReturn {
  const [connected, setConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const wsRef = useRef<WebSocketManager | null>(null);

  useEffect(() => {
    const ws = new WebSocketManager();
    wsRef.current = ws;

    // Generic handler that reconstructs the full WSMessage shape so
    // consumers get a typed discriminated union.
    const onSensorUpdate = (data: unknown) => {
      setLastMessage({ type: "sensor_update", data } as WSMessage);
    };
    const onForecastUpdate = (data: unknown) => {
      setLastMessage({ type: "forecast_update", data } as WSMessage);
    };
    const onConnectionStatus = (data: unknown) => {
      setLastMessage({
        type: "connection_status",
        connected: data,
      } as WSMessage);
    };

    ws.onMessage("sensor_update", onSensorUpdate);
    ws.onMessage("forecast_update", onForecastUpdate);
    ws.onMessage("connection_status", onConnectionStatus);

    // Poll WS connection state
    const timer = setInterval(() => {
      setConnected(ws.isConnected);
    }, 1000);

    ws.connect();

    return () => {
      clearInterval(timer);
      ws.offMessage("sensor_update", onSensorUpdate);
      ws.offMessage("forecast_update", onForecastUpdate);
      ws.offMessage("connection_status", onConnectionStatus);
      ws.disconnect();
      wsRef.current = null;
    };
  }, []);

  return { connected, lastMessage };
}
