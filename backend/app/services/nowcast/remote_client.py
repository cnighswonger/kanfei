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
        self._latest: Optional[dict] = None
        self._last_push_ts: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    def reload_config(self) -> None:
        """Read remote nowcast config."""
        self._enabled = self._config.get_bool("nowcast_enabled", False)
        self._remote_url = self._config.get("nowcast_remote_url", "").rstrip("/")

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
        self._client = httpx.AsyncClient(timeout=30.0)

        # Seed from remote on startup
        if self.is_enabled():
            await self._poll_nowcast()

        while True:
            try:
                await self._tick()
            except Exception:
                logger.exception("Remote client tick failed")
            await asyncio.sleep(PUSH_INTERVAL)

    async def _tick(self) -> None:
        """Single iteration: push readings, poll for results."""
        self.reload_config()
        if not self.is_enabled():
            return

        await self._push_readings()
        await self._poll_nowcast()

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
            if resp.status_code != 200:
                logger.warning(
                    "Failed to fetch nowcast: %d %s",
                    resp.status_code, resp.text[:200],
                )
                return

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
