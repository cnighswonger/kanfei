"""Lightweight async HTTP server for receiving weather data pushes.

Weather stations (Ambient Weather, Ecowitt, Froggit, etc.) push sensor
data to a configured "Custom Server" endpoint via HTTP GET or POST.
This module provides:

  create_http_receiver()  — persistent server for the driver
  wait_for_data()         — temporary server for the setup wizard probe
"""

import asyncio
import logging
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlparse

from .constants import DEFAULT_HTTP_PORT, HTTP_BIND, SCAN_TIMEOUT

logger = logging.getLogger(__name__)


def _parse_http_request(data: bytes) -> dict[str, str]:
    """Parse an HTTP GET or POST into a flat parameter dict.

    Returns a dict of param_name -> value (first value only for each key).
    """
    text = data.decode("utf-8", errors="replace")
    lines = text.split("\r\n")
    if not lines:
        return {}

    first_line = lines[0]
    parts = first_line.split(" ")
    if len(parts) < 2:
        return {}

    method = parts[0].upper()
    path = parts[1]
    params: dict[str, str] = {}

    # GET: parse query string from URL
    if method == "GET":
        parsed = urlparse(path)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        for key, values in qs.items():
            params[key] = values[0] if values else ""

    # POST: parse form-encoded body
    elif method == "POST":
        # Find the body after the blank line
        body = ""
        blank_idx = text.find("\r\n\r\n")
        if blank_idx >= 0:
            body = text[blank_idx + 4:]
        if body:
            qs = parse_qs(body.strip(), keep_blank_values=True)
            for key, values in qs.items():
                params[key] = values[0] if values else ""

    return params


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    on_data: Callable[[dict[str, str]], None],
) -> None:
    """Handle a single HTTP request from a weather station."""
    try:
        data = await asyncio.wait_for(reader.read(8192), timeout=10.0)
        if not data:
            return

        params = _parse_http_request(data)
        if params:
            on_data(params)
            logger.debug("Received HTTP push with %d parameters", len(params))
        else:
            logger.debug("Received HTTP request with no parameters")

        # Send 200 OK — stations expect a success response
        response = b"HTTP/1.1 200 OK\r\nContent-Length: 7\r\nConnection: close\r\n\r\nsuccess"
        writer.write(response)
        await writer.drain()
    except asyncio.TimeoutError:
        logger.debug("HTTP client read timed out")
    except Exception:
        logger.debug("Error handling HTTP push", exc_info=True)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def create_http_receiver(
    port: int = DEFAULT_HTTP_PORT,
    on_data: Callable[[dict[str, str]], None] = lambda _: None,
) -> asyncio.Server:
    """Start an async HTTP server that accepts weather data pushes.

    Returns the asyncio.Server instance — caller is responsible for
    calling server.close() + await server.wait_closed() to shut down.
    """
    async def client_handler(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
    ) -> None:
        await _handle_client(reader, writer, on_data)

    server = await asyncio.start_server(
        client_handler,
        host=HTTP_BIND,
        port=port,
    )
    logger.info("HTTP push receiver listening on %s:%d", HTTP_BIND, port)
    return server


async def wait_for_data(
    port: int = DEFAULT_HTTP_PORT,
    timeout: float = SCAN_TIMEOUT,
) -> Optional[dict[str, str]]:
    """Start a temporary HTTP receiver and wait for the first data push.

    Used by the setup wizard to detect a station. Returns the first
    received parameter dict, or None on timeout.
    """
    result: dict[str, Any] = {"params": None}
    event = asyncio.Event()

    def on_first_data(params: dict[str, str]) -> None:
        if not event.is_set():
            result["params"] = params
            event.set()

    server: Optional[asyncio.Server] = None
    try:
        server = await create_http_receiver(port=port, on_data=on_first_data)
        logger.info("Waiting for weather data push (timeout %.0fs)...", timeout)
        await asyncio.wait_for(event.wait(), timeout=timeout)
        return result["params"]
    except asyncio.TimeoutError:
        logger.info("No weather data received within %.0fs", timeout)
        return None
    finally:
        if server is not None:
            server.close()
            await server.wait_closed()
