"""GET /api/health — composite liveness signal for external monitors.

Anonymous, cheap, and safe to hit at high cadence.  Composed from the
logger daemon's `status` IPC (which never touches serial, so it stays
responsive even when the driver is wedged — the exact failure mode this
endpoint exists to surface, see umbrella #472 and sub-issue #473).

Response shape is stable API and load-bearing.  Changing field names or
removing fields silently disarms external checks — extend rather than
rename.
"""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..ipc.dependencies import get_ipc_client

logger = logging.getLogger(__name__)
router = APIRouter()

# Multiplier over the daemon's reported ``poll_interval`` after which we
# call the poller stalled.  One slow poll (e.g. an archive sync taking a
# few seconds) should never trip this.
_STALL_MULTIPLIER = 3

# Fallback threshold when the daemon isn't reachable or hasn't reported
# a poll interval yet.  30 s is well above the typical 10 s poll cadence
# and gives a fresh start a full cycle to complete before flipping to 503.
_FALLBACK_STALL_SECONDS = 30

# Short timeout on the status IPC — the whole point of `/api/health` is
# to answer quickly even when the daemon is degraded.  ``status`` does
# not touch serial, so it returns instantly on a healthy daemon; a 2 s
# ceiling here catches the case where the IPC connection itself hangs.
_STATUS_TIMEOUT = 2.0


@router.get("/health")
async def get_health() -> JSONResponse:
    """Composite health for external monitors (Nagios, Uptime Kuma, Discord).

    Returns 200 when the logger daemon is reachable AND the poller has
    completed a cycle within `_STALL_MULTIPLIER * poll_interval`; returns
    503 with the same body shape otherwise so a monitor gets structured
    detail on the failure it just flagged.
    """
    body: dict = {
        "ok": False,
        "connected": False,
        "poll_stall_seconds": None,
        "poll_interval": None,
        "last_poll_completed_at": None,
        "last_broadcast_at": None,
        "reason": None,
    }

    try:
        client = get_ipc_client()
        result = await client.send_command(
            {"cmd": "status"}, timeout=_STATUS_TIMEOUT,
        )
    except Exception as exc:
        body["reason"] = f"logger unreachable: {type(exc).__name__}"
        return JSONResponse(body, status_code=503)

    if not result.get("ok"):
        body["reason"] = result.get("error", "logger status returned not-ok")
        return JSONResponse(body, status_code=503)

    data = result.get("data", {})
    body["connected"] = bool(data.get("connected", False))
    body["poll_stall_seconds"] = data.get("poll_stall_seconds")
    body["poll_interval"] = data.get("poll_interval")
    body["last_poll_completed_at"] = data.get("last_poll_completed_at")
    body["last_broadcast_at"] = data.get("last_broadcast_at")

    if not body["connected"]:
        body["reason"] = "driver not connected"
        return JSONResponse(body, status_code=503)

    threshold = _stall_threshold(body["poll_interval"])
    stall = body["poll_stall_seconds"]
    # None during startup — the poller has been created but no cycle has
    # completed yet.  Report ok=True so a monitor doesn't page during the
    # first ~10 s after logger restart.  A wedged startup is caught by
    # the second check the /api/health caller runs (or the frontend badge
    # from #474, whose thresholds are separate).
    if stall is not None and stall > threshold:
        body["reason"] = (
            f"poll stalled: {stall:.0f}s since last completion "
            f"(threshold {threshold:.0f}s)"
        )
        return JSONResponse(body, status_code=503)

    body["ok"] = True
    return JSONResponse(body, status_code=200)


def _stall_threshold(poll_interval: int | None) -> float:
    """Threshold in seconds past which the poller counts as stalled."""
    if poll_interval and poll_interval > 0:
        return float(_STALL_MULTIPLIER * poll_interval)
    return float(_FALLBACK_STALL_SECONDS)
