"""WebSocket endpoint for live sensor data.

Relays sensor_update messages from the logger daemon (via IPC subscription)
to all connected browser WebSocket clients.
"""

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from ..config import settings
from ..ipc.client import IPCClient

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages browser WebSocket connections and the IPC relay to the logger."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._relay_task: asyncio.Task | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket client connected. Total: %d", len(self.active_connections))

        # Start the IPC relay if this is the first browser client
        if len(self.active_connections) == 1:
            self._start_relay()

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("WebSocket client disconnected. Total: %d", len(self.active_connections))

        # Stop relay when no more browser clients
        if not self.active_connections and self._relay_task:
            self._relay_task.cancel()
            self._relay_task = None

    def _start_relay(self) -> None:
        if self._relay_task and not self._relay_task.done():
            return
        self._relay_task = asyncio.create_task(self._relay_loop())

    async def _relay_loop(self) -> None:
        """Subscribe to the logger daemon IPC and relay messages to browsers."""
        while self.active_connections:
            try:
                client = IPCClient(settings.ipc_port)
                async for msg in client.subscribe():
                    if not self.active_connections:
                        break
                    await self.broadcast(msg)
            except asyncio.CancelledError:
                break
            except (ConnectionRefusedError, OSError):
                # Logger not running — wait and retry
                await asyncio.sleep(2.0)
            except Exception as exc:
                logger.error("IPC relay error: %s", exc)
                await asyncio.sleep(2.0)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a message to all connected WebSocket clients."""
        disconnected: list[WebSocket] = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                disconnected.append(conn)
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)


# Global connection manager
ws_manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket) -> None:
    """Handle WebSocket connections for live data streaming."""
    await ws_manager.connect(websocket)
    try:
        # Send initial connection status from logger
        try:
            client = IPCClient(settings.ipc_port)
            result = await client.send_command({"cmd": "status"}, timeout=3.0)
            connected = (
                result.get("ok", False)
                and result.get("data", {}).get("connected", False)
            )
            await client.close()
        except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
            connected = False

        await websocket.send_json({
            "type": "connection_status",
            "connected": connected,
        })

        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass
    except (WebSocketDisconnect, ConnectionResetError, OSError):
        # OSError covers Windows semaphore timeout on client disconnect
        ws_manager.disconnect(websocket)
    except Exception:
        logger.debug("WebSocket closed unexpectedly", exc_info=True)
        ws_manager.disconnect(websocket)
