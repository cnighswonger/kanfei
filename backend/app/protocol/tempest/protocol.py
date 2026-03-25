"""UDP listener for WeatherFlow Tempest broadcasts.

The Tempest hub broadcasts JSON datagrams on UDP port 50222 to the local
network.  No authentication, no request/response — just continuous broadcast.

This module provides:
  - TempestUDPProtocol  — asyncio.DatagramProtocol that parses and dispatches
  - create_listener()   — bind a UDP socket and start listening
  - scan_for_hub()      — temporary listener for setup wizard probe
"""

import asyncio
import json
import logging
from typing import Any, Callable, Optional

from .constants import (
    UDP_PORT, UDP_BIND, SCAN_TIMEOUT,
    MSG_HUB_STATUS, MSG_DEVICE_STATUS, MSG_OBS_ST, MSG_OBS_AIR, MSG_OBS_SKY,
)

logger = logging.getLogger(__name__)


class TempestUDPProtocol(asyncio.DatagramProtocol):
    """Receives and dispatches Tempest UDP broadcast datagrams."""

    def __init__(
        self,
        on_message: Callable[[dict[str, Any]], None],
        hub_sn_filter: str = "",
    ) -> None:
        self._on_message = on_message
        self._hub_sn_filter = hub_sn_filter
        self._transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self._transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            msg = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.debug("Ignoring non-JSON datagram from %s", addr)
            return

        if not isinstance(msg, dict) or "type" not in msg:
            return

        # Filter by hub serial number if configured
        if self._hub_sn_filter:
            hub_sn = msg.get("hub_sn", msg.get("serial_number", ""))
            if hub_sn != self._hub_sn_filter:
                return

        self._on_message(msg)

    def error_received(self, exc: Exception) -> None:
        logger.warning("UDP error: %s", exc)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if exc:
            logger.warning("UDP connection lost: %s", exc)

    def close(self) -> None:
        if self._transport:
            self._transport.close()


async def create_listener(
    hub_sn: str = "",
    on_message: Callable[[dict[str, Any]], None] = lambda _: None,
    port: int = UDP_PORT,
) -> tuple[asyncio.DatagramTransport, TempestUDPProtocol]:
    """Bind a UDP socket and start listening for Tempest broadcasts.

    Returns (transport, protocol) — caller owns the transport and must
    close it when done.
    """
    loop = asyncio.get_event_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: TempestUDPProtocol(on_message, hub_sn_filter=hub_sn),
        local_addr=(UDP_BIND, port),
        reuse_port=True,
    )
    logger.info("Tempest UDP listener bound to %s:%d", UDP_BIND, port)
    return transport, protocol


async def scan_for_hub(timeout: float = SCAN_TIMEOUT) -> Optional[dict[str, Any]]:
    """Listen briefly for a Tempest hub and return its info.

    Used by the setup wizard probe.  Creates a temporary listener, waits
    for a hub_status, obs_st, obs_air, or obs_sky message, and returns
    hub info.  Returns None on timeout.
    """
    result: dict[str, Any] = {}
    found = asyncio.Event()

    def _on_msg(msg: dict[str, Any]) -> None:
        msg_type = msg.get("type", "")

        if msg_type == MSG_HUB_STATUS:
            result["hub_sn"] = msg.get("serial_number", "")
            result["firmware_version"] = msg.get("firmware_revision", "")
            result["uptime"] = msg.get("uptime", 0)
            result["rssi"] = msg.get("rssi", 0)
            found.set()

        elif msg_type in (MSG_OBS_ST, MSG_OBS_AIR, MSG_OBS_SKY):
            result["hub_sn"] = msg.get("hub_sn", "")
            result["device_sn"] = msg.get("serial_number", "")
            result["firmware_version"] = str(msg.get("firmware_revision", ""))
            found.set()

    transport: Optional[asyncio.DatagramTransport] = None
    try:
        transport, _protocol = await create_listener(on_message=_on_msg)
        try:
            await asyncio.wait_for(found.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        return result if result else None
    except OSError as exc:
        logger.error("Failed to bind UDP port %d: %s", UDP_PORT, exc)
        return None
    finally:
        if transport:
            transport.close()
