"""IPC server — runs inside the logger daemon.

Listens on TCP localhost for commands from the web application.
Supports request/response commands and streaming subscriptions
for live sensor data.
"""

import asyncio
import logging
from typing import Any, Callable, Coroutine

from .protocol import (
    IPC_HOST,
    CMD_SUBSCRIBE,
    CMD_UNSUBSCRIBE,
    encode_message,
    decode_message,
)

logger = logging.getLogger(__name__)


class IPCServer:
    """Async TCP server for logger <-> web app IPC."""

    def __init__(self, port: int):
        self.port = port
        self._server: asyncio.Server | None = None
        self._subscribers: set[asyncio.StreamWriter] = set()
        self._handlers: dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}

    def register_handler(
        self,
        cmd: str,
        handler: Callable[[dict[str, Any]], Coroutine[Any, Any, Any]],
    ) -> None:
        """Register an async handler for a command name."""
        self._handlers[cmd] = handler

    async def start(self) -> None:
        """Start listening on the configured port."""
        self._server = await asyncio.start_server(
            self._handle_client, IPC_HOST, self.port,
        )
        addr = self._server.sockets[0].getsockname() if self._server.sockets else "?"
        logger.info("IPC server listening on %s", addr)

    async def stop(self) -> None:
        """Shut down the server and close all subscriber connections."""
        for writer in list(self._subscribers):
            try:
                writer.close()
            except Exception:
                pass
        self._subscribers.clear()

        if self._server:
            self._server.close()
            try:
                await asyncio.wait_for(self._server.wait_closed(), timeout=3.0)
            except asyncio.TimeoutError:
                logger.warning("IPC server wait_closed timed out")
            logger.info("IPC server stopped")

    async def broadcast_to_subscribers(self, message: dict[str, Any]) -> None:
        """Send a message to all subscribed clients."""
        if not self._subscribers:
            return

        data = encode_message(message)
        dead: list[asyncio.StreamWriter] = []

        for writer in self._subscribers:
            try:
                writer.write(data)
                await writer.drain()
            except (ConnectionResetError, BrokenPipeError, OSError):
                dead.append(writer)

        for w in dead:
            self._subscribers.discard(w)

    # --- Internal ---

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a single client connection."""
        peer = writer.get_extra_info("peername")
        logger.debug("IPC client connected: %s", peer)

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break

                try:
                    msg = decode_message(line)
                except Exception:
                    await self._send(writer, {"ok": False, "error": "Invalid JSON"})
                    continue

                cmd = msg.get("cmd")

                if cmd == CMD_SUBSCRIBE:
                    self._subscribers.add(writer)
                    await self._send(writer, {"ok": True, "subscribed": True})
                    continue

                if cmd == CMD_UNSUBSCRIBE:
                    self._subscribers.discard(writer)
                    await self._send(writer, {"ok": True})
                    continue

                handler = self._handlers.get(cmd)
                if handler is None:
                    await self._send(
                        writer, {"ok": False, "error": f"Unknown command: {cmd}"}
                    )
                    continue

                try:
                    result = await handler(msg)
                    await self._send(writer, {"ok": True, "data": result})
                except Exception as exc:
                    logger.error("IPC handler error for %s: %s", cmd, exc, exc_info=True)
                    await self._send(writer, {"ok": False, "error": str(exc)})

        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            pass
        finally:
            self._subscribers.discard(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            logger.debug("IPC client disconnected: %s", peer)

    @staticmethod
    async def _send(writer: asyncio.StreamWriter, msg: dict[str, Any]) -> None:
        writer.write(encode_message(msg))
        await writer.drain()
