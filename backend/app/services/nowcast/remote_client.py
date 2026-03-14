"""Built-in remote nowcast client.

Forwards station data to a kanfei-nowcast endpoint and retrieves nowcast
results via HTTP. This client is included in OSS Kanfei so remote mode
works without installing the kanfei-nowcast package locally.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from .protocols import ConfigProvider, StorageBackend, EventEmitter

logger = logging.getLogger(__name__)

# How often to push readings and poll for nowcasts (seconds).
PUSH_INTERVAL = 60
POLL_INTERVAL = 60


class NowcastRemoteClient:
    """Connects to a remote kanfei-nowcast endpoint.

    Periodically pushes sensor readings from the local storage backend
    and polls for nowcast results. Broadcasts updates to connected
    frontend clients via the event emitter.
    """

    def __init__(
        self,
        config: ConfigProvider,
        storage: StorageBackend,
        events: EventEmitter,
    ) -> None:
        self._config = config
        self._storage = storage
        self._events = events
        self._enabled: bool = False
        self._remote_url: str = ""
        self._api_key: str = ""
        self._latest: Optional[dict] = None
        self._last_push_ts: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._auth_error: Optional[str] = None  # Set on 401/403/429
        self._available_presets: Optional[dict] = None  # Cached from remote

    @property
    def auth_error(self) -> Optional[str]:
        """Last auth error message, or None if authenticated successfully."""
        return self._auth_error

    @property
    def available_presets(self) -> Optional[dict]:
        """Cached preset availability from the remote server."""
        return self._available_presets

    def reload_config(self) -> None:
        """Read remote nowcast config."""
        self._enabled = self._config.get_bool("nowcast_enabled", False)
        self._remote_url = self._config.get("nowcast_remote_url", "").rstrip("/")
        self._api_key = self._config.get("nowcast_remote_api_key", "")
        self._quality_preset = self._config.get("nowcast_quality_preset", "economy")

    def is_enabled(self) -> bool:
        return self._enabled and bool(self._remote_url)

    def get_latest(self) -> Optional[dict]:
        return self._latest

    async def generate_once(self) -> None:
        """Trigger an immediate fetch from the remote endpoint."""
        await self._poll_nowcast()

    async def start(self) -> None:
        """Main loop — push readings and poll for nowcasts."""
        logger.info("Nowcast remote client started")
        self.reload_config()
        headers = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        self._client = httpx.AsyncClient(timeout=30.0, headers=headers)

        # Seed from remote on startup
        if self.is_enabled():
            await self._fetch_presets()
            await self._poll_nowcast()

        while True:
            try:
                await self._tick()
            except Exception:
                logger.exception("Remote client tick failed")
            await asyncio.sleep(PUSH_INTERVAL)

    async def _tick(self) -> None:
        """Single iteration: push readings, sync config, poll for results."""
        old_key = self._api_key
        old_preset = getattr(self, "_quality_preset", "")
        self.reload_config()
        if not self.is_enabled():
            return
        # Update auth header if key changed
        if self._api_key != old_key and self._client:
            self._client.headers["X-API-Key"] = self._api_key if self._api_key else ""
        # Sync preset to remote server if changed
        if self._quality_preset != old_preset:
            await self._sync_config({"nowcast_quality_preset": self._quality_preset})
            await self._fetch_presets()  # Refresh in case tier changed

        await self._push_readings()
        await self._poll_nowcast()

    async def _fetch_presets(self) -> None:
        """Fetch available presets from the remote server."""
        try:
            resp = await self._client.get(f"{self._remote_url}/api/presets")
            if resp.status_code == 200:
                self._available_presets = resp.json()
            else:
                logger.debug("Presets fetch returned %d", resp.status_code)
        except httpx.HTTPError as exc:
            logger.debug("Presets fetch failed: %s", exc)

    async def _sync_config(self, updates: dict) -> None:
        """Push config updates to the remote server."""
        try:
            resp = await self._client.post(
                f"{self._remote_url}/api/config",
                json=updates,
            )
            if resp.status_code == 200:
                logger.info("Synced config to remote: %s", updates)
            else:
                logger.warning("Config sync failed: %d", resp.status_code)
        except httpx.HTTPError as exc:
            logger.warning("Config sync failed: %s", exc)

    async def _push_readings(self) -> None:
        """Push new sensor readings to the remote endpoint."""
        if self._last_push_ts:
            since = datetime.fromisoformat(self._last_push_ts)
        else:
            since = datetime.now(timezone.utc) - timedelta(hours=3)

        readings = self._storage.get_readings_since(since)
        if not readings:
            return

        batch = []
        for r in readings:
            row = dict(r)
            ts = row.get("timestamp")
            if hasattr(ts, "isoformat"):
                row["timestamp"] = ts.isoformat()
            batch.append(row)

        try:
            resp = await self._client.post(
                f"{self._remote_url}/api/readings/batch",
                json=batch,
            )
            if resp.status_code == 200:
                self._last_push_ts = batch[-1]["timestamp"]
                logger.info(
                    "Pushed %d readings to %s",
                    len(batch), self._remote_url,
                )
            elif resp.status_code == 401:
                logger.warning("Push rejected: invalid or missing API key")
            elif resp.status_code == 403:
                logger.warning("Push rejected: API key disabled or expired")
            elif resp.status_code == 429:
                logger.warning("Push rejected: rate limit exceeded")
            else:
                logger.warning(
                    "Failed to push readings: %d %s",
                    resp.status_code, resp.text[:200],
                )
        except httpx.HTTPError as exc:
            logger.warning("Failed to push readings to %s: %s", self._remote_url, exc)

    async def _poll_nowcast(self) -> None:
        """Fetch the latest nowcast from the remote endpoint."""
        try:
            resp = await self._client.get(f"{self._remote_url}/api/nowcast")
            if resp.status_code == 401:
                self._auth_error = "Invalid or missing API key"
                logger.warning("Nowcast fetch rejected: %s", self._auth_error)
                return
            if resp.status_code == 403:
                self._auth_error = "API key disabled or expired"
                logger.warning("Nowcast fetch rejected: %s", self._auth_error)
                return
            if resp.status_code == 429:
                self._auth_error = "Rate limit exceeded — try again shortly"
                logger.warning("Nowcast fetch rejected: %s", self._auth_error)
                return
            if resp.status_code != 200:
                logger.warning(
                    "Failed to fetch nowcast: %d %s",
                    resp.status_code, resp.text[:200],
                )
                return

            # Successful fetch — clear any previous auth error
            self._auth_error = None

            data = resp.json()
            if data is None:
                return

            prev_id = self._latest.get("id") if self._latest else None
            new_id = data.get("id")
            self._latest = data

            if new_id and new_id != prev_id:
                logger.info(
                    "New nowcast received from remote (id=%s, model=%s)",
                    new_id, data.get("model_used", "?"),
                )
                await self._events.emit("nowcast_update", data)

        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch nowcast from %s: %s", self._remote_url, exc)
