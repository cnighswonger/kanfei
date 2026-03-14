// ============================================================
// WebSocket manager for live weather data streaming.
// Auto-reconnects with exponential back-off and dispatches
// typed callbacks for each server message type.
// ============================================================

import type { WSMessage } from "./types.ts";
import {
  WS_RECONNECT_INTERVAL,
  WS_MAX_RECONNECT_INTERVAL,
  WS_PING_INTERVAL,
} from "../utils/constants.ts";

export type WSMessageType = WSMessage["type"];
export type WSCallback = (data: unknown) => void;

export class WebSocketManager {
  private ws: WebSocket | null = null;
  private listeners = new Map<string, Set<WSCallback>>();
  private reconnectDelay = WS_RECONNECT_INTERVAL;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private intentionalClose = false;
  private _isConnected = false;

  /** Whether the WebSocket is currently open. */
  get isConnected(): boolean {
    return this._isConnected;
  }

  /** Open (or re-open) the WebSocket connection. */
  connect(): void {
    this.intentionalClose = false;
    this.openSocket();
  }

  /** Permanently close the WebSocket (no auto-reconnect). */
  disconnect(): void {
    this.intentionalClose = true;
    this.clearTimers();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this._isConnected = false;
  }

  /** Subscribe to a specific message type. */
  onMessage(type: string, callback: WSCallback): void {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set());
    }
    this.listeners.get(type)!.add(callback);
  }

  /** Unsubscribe a previously registered callback. */
  offMessage(type: string, callback: WSCallback): void {
    this.listeners.get(type)?.delete(callback);
  }

  // --- Internal ---

  private buildUrl(): string {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/ws/live`;
  }

  private openSocket(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    const url = this.buildUrl();
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this._isConnected = true;
      this.reconnectDelay = WS_RECONNECT_INTERVAL;
      this.startPing();
    };

    this.ws.onmessage = (event: MessageEvent) => {
      this.handleMessage(event);
    };

    this.ws.onclose = () => {
      this._isConnected = false;
      this.stopPing();
      if (!this.intentionalClose) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      // onclose will fire after onerror; reconnect is handled there.
    };
  }

  private handleMessage(event: MessageEvent): void {
    let msg: WSMessage;
    try {
      msg = JSON.parse(String(event.data)) as WSMessage;
    } catch {
      return; // ignore malformed messages
    }

    const callbacks = this.listeners.get(msg.type);
    if (!callbacks) return;

    const payload =
      msg.type === "connection_status"
        ? (msg as { connected: boolean }).connected
        : (msg as { data: unknown }).data;

    for (const cb of callbacks) {
      try {
        cb(payload);
      } catch {
        // prevent one bad callback from breaking others
      }
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.openSocket();
    }, this.reconnectDelay);
    // exponential back-off
    this.reconnectDelay = Math.min(
      this.reconnectDelay * 2,
      WS_MAX_RECONNECT_INTERVAL,
    );
  }

  private startPing(): void {
    this.stopPing();
    this.pingTimer = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "ping" }));
      }
    }, WS_PING_INTERVAL);
  }

  private stopPing(): void {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  private clearTimers(): void {
    this.stopPing();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}
