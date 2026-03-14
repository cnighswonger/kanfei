"""IPC client — used by the web application to talk to the logger daemon.

Provides request/response commands and a streaming subscription for
live sensor data.  All methods handle connection errors gracefully.
"""

import asyncio
import logging
from typing import Any, AsyncIterator

from .protocol import IPC_HOST, encode_message, decode_message

logger = logging.getLogger(__name__)


class IPCClient:
    """Async TCP client for communicating with the logger daemon."""

    def __init__(self, port: int):
        self.port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()  # serialise request/response pairs

    async def _ensure_connected(self) -> None:
        """Open a connection if one isn't already active."""
        if self._writer is not None and not self._writer.is_closing():
            return
        self._reader, self._writer = await asyncio.open_connection(
            IPC_HOST, self.port,
        )

    async def is_available(self) -> bool:
        """Check whether the logger daemon is reachable."""
        try:
            result = await self.send_command({"cmd": "status"}, timeout=3.0)
            return result.get("ok", False)
        except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
            return False

    async def send_command(
        self,
        msg: dict[str, Any],
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        """Send a command and wait for the single-line response.

        Raises ConnectionRefusedError / OSError if the logger is unreachable.
        Raises asyncio.TimeoutError if the logger doesn't respond in time.
        """
        async with self._lock:
            try:
                await self._ensure_connected()
            except (ConnectionRefusedError, OSError):
                # Reset stale state so next call retries cleanly
                self._reader = None
                self._writer = None
                raise

            assert self._writer is not None and self._reader is not None
            try:
                self._writer.write(encode_message(msg))
                await self._writer.drain()
                line = await asyncio.wait_for(
                    self._reader.readline(), timeout=timeout,
                )
                if not line:
                    raise ConnectionError("Logger closed the connection")
                return decode_message(line)
            except Exception:
                # Connection may be broken — force reconnect on next call
                await self._close_connection()
                raise

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to live sensor data on a **dedicated** connection.

        Yields messages as they arrive. The dedicated connection keeps
        the streaming traffic separate from request/response on the
        shared connection.
        """
        reader, writer = await asyncio.open_connection(IPC_HOST, self.port)
        try:
            writer.write(encode_message({"cmd": "subscribe"}))
            await writer.drain()

            # Read the acknowledgement
            ack_line = await reader.readline()
            if not ack_line:
                return

            # Stream sensor updates until disconnected
            while True:
                line = await reader.readline()
                if not line:
                    break
                yield decode_message(line)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def close(self) -> None:
        """Close the shared command connection."""
        await self._close_connection()

    async def _close_connection(self) -> None:
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None
