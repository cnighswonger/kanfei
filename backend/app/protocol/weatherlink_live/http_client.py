"""Async HTTP client for the WeatherLink Live local API.

Uses stdlib urllib to avoid adding httpx/aiohttp as a dependency.
All blocking I/O is dispatched via asyncio.to_thread().
"""

import asyncio
import json
import logging
import urllib.request
import urllib.error
from typing import Any, Optional

from .constants import API_PATH, DEFAULT_HTTP_PORT, HTTP_TIMEOUT_SECS

logger = logging.getLogger(__name__)


def _fetch_sync(
    ip: str,
    port: int = DEFAULT_HTTP_PORT,
    timeout: float = HTTP_TIMEOUT_SECS,
) -> dict[str, Any]:
    """Synchronous HTTP GET to WLL, returns parsed JSON dict."""
    url = f"http://{ip}:{port}{API_PATH}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


async def fetch_current_conditions(
    ip: str,
    port: int = DEFAULT_HTTP_PORT,
    timeout: float = HTTP_TIMEOUT_SECS,
) -> Optional[dict[str, Any]]:
    """Async wrapper: GET /v1/current_conditions from WLL.

    Returns the parsed JSON response dict, or None on failure.
    """
    try:
        return await asyncio.to_thread(_fetch_sync, ip, port, timeout)
    except urllib.error.URLError as exc:
        logger.warning("WLL HTTP error (%s:%d): %s", ip, port, exc)
        return None
    except Exception as exc:
        logger.warning("WLL fetch failed (%s:%d): %s", ip, port, exc)
        return None
