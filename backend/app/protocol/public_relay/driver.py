"""Public-relay station driver.

The driver that runs on the public-facing droplet.  It never opens a
serial port or a network socket of its own — data arrives via an HTTP
push from the operator's private Kanfei instance and is buffered in
memory.  ``poll()`` hands the buffered snapshot back to the poller so
the rest of the app is unchanged.

Selecting this driver is what puts the app into read-only public mode
(``app/services/public_mode.py``): the write-block middleware and the
``require_admin`` guest bypass both key off
``station_driver_type == 'public_relay'``.  There is no separate mode
flag — the driver *is* the mode.

Phase 1 (issue #336) ships the skeleton: buffered ``poll()`` and stub
``push_snapshot`` / ``push_config``.  Phase 2 wires the real ingest
endpoints that call them.
"""

import logging
import time
from types import SimpleNamespace
from typing import Any, Optional

from ..base import HardwareInfo, SensorSnapshot, StationDriver

logger = logging.getLogger(__name__)


STATION_NAME = "Public Relay"


class PublicRelayDriver(StationDriver):
    """No-I/O driver whose poll returns the last snapshot pushed in.

    Every ``StationDriver`` method is implemented so the poller and
    logger-daemon paths that program against the ABC keep working; the
    difference is that ``connect()`` opens nothing and ``poll()`` reads
    from an in-memory buffer instead of the wire.
    """

    def __init__(self) -> None:
        self._connected = False
        self._last_snapshot: Optional[SensorSnapshot] = None
        self._last_push_at: Optional[float] = None
        # Populated by push_config() in Phase 2 — the upstream station's
        # advertised model/firmware so ``station_name`` can render it.
        # Empty in Phase 1.
        self._upstream_info: dict = {}

    # ---- StationDriver interface ----

    async def connect(self) -> None:
        """No-op — the driver has no wire to open.

        Marks itself connected so the poller loop treats it as live.
        Actual data arrives asynchronously via ``push_snapshot`` (Phase 2
        ingest endpoint), not by any action this method takes.
        """
        self._connected = True
        logger.info("PublicRelayDriver ready (waiting for pushed data)")

    async def disconnect(self) -> None:
        self._connected = False

    async def poll(self) -> Optional[SensorSnapshot]:
        """Return the last snapshot pushed in, or None if nothing yet."""
        return self._last_snapshot

    async def detect_hardware(self) -> HardwareInfo:
        return HardwareInfo(
            name=self.station_name,
            model_code=0,
            capabilities=self.capabilities,
        )

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def station_name(self) -> str:
        upstream = self._upstream_info.get("station_name")
        if upstream:
            return f"{STATION_NAME} — {upstream}"
        return STATION_NAME

    @property
    def capabilities(self) -> set[str]:
        # A public droplet holds no hardware — no capability set can
        # meaningfully apply.  Every capability-gated write endpoint is
        # also blocked by the read-only middleware; capability=empty is
        # the belt to the middleware's braces.
        return set()

    # ---- Ingest surface (called by Phase 2 HTTP endpoints) ----

    def push_snapshot(self, snapshot: SensorSnapshot) -> None:
        """Replace the buffered snapshot with a freshly-pushed one."""
        self._last_snapshot = snapshot
        self._last_push_at = time.time()

    def push_config(self, info: dict) -> None:
        """Update advertised upstream identity (station_name, firmware).

        Phase 1 stub — Phase 2's ingest endpoint calls this on the first
        push and whenever the upstream re-registers.
        """
        if isinstance(info, dict):
            self._upstream_info = info

    # ---- Read surface that the daemon's ``_h_status`` / ``_h_read_station_time``
    # exercise via ``getattr`` on the active driver.  The daemon "asks the
    # driver, not its type," so surfacing the pushed identity via the same
    # attribute names every real driver uses lets ``/api/station`` render
    # firmware, product SKU, and station clock without a public-relay
    # branch in the endpoint.

    @property
    def hw_config(self) -> Any:
        """Namespace exposing pushed identity fields the ``_h_status``
        handler reads via ``getattr`` (``firmware_version``,
        ``firmware_date``, ``product_sku``).  Empty upstream_info
        surfaces as None attributes, same shape as a driver whose
        detection hasn't completed."""
        u = self._upstream_info
        return SimpleNamespace(
            firmware_version=u.get("firmware_version"),
            firmware_date=u.get("firmware_date"),
            product_sku=u.get("product_sku"),
        )

    # ``async_read_station_time`` intentionally NOT implemented.  The
    # daemon gates on ``hasattr(drv, "async_read_station_time")``, and
    # a public-relay droplet has no way to construct the upstream's
    # console clock: ``_last_push_at`` is a ``time.time()`` on the
    # droplet's own machine (typically UTC), and returning components
    # from it prints the droplet's timezone as if it were the
    # operator's (240 min drift on a US-East → UTC droplet).  Better
    # to render "—" than to publish a four-hour lie.  A proper fix
    # requires the upstream to push its console-clock components in
    # each snapshot; tracked separately.
