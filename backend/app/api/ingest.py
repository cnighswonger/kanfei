"""Public-relay ingest endpoints.

Two HTTP POST endpoints that accept pushed data from a private Kanfei
instance's relay (Phase 3, still to come).  Both live outside the
regular admin-auth surface: the write-block middleware allowlists them
by exact path, and their own auth dependency requires a shared bearer
secret stored at ``station_config.public_mode_ingest_secret``.

Wire schema for ``POST /api/ingest/reading`` mirrors the
``SensorSnapshot`` dataclass 1:1 — the two Kanfei processes speak the
same shape, so no lossy conversion is needed.  Unknown keys are
ignored to keep the ingest tolerant of a relay running ahead of the
droplet's Kanfei version.

Wire schema for ``POST /api/ingest/config`` is an open-ended dict
describing the upstream identity (``station_name``, firmware, etc.).
The driver caches it verbatim so the Station Status tile can render
the real upstream station rather than the bare "Public Relay" label.

Security model
--------------

- **Bearer secret** — stored server-side in ``station_config``, masked
  in ``GET /api/config``.  Compared constant-time.  A missing secret
  returns 503 (ingest not configured) rather than 401 so an
  unconfigured droplet is distinguishable from a bad-credential push.
- **Reverse-proxy IP allowlist** — expected at the nginx layer on the
  droplet (recommended in the Phase 5 operator docs).  Not enforced in
  the app to keep the security decisions in one place.
- **Read-only elsewhere** — the middleware still blocks every other
  write path; these two are the ONLY holes in the public-mode gate,
  and they are pin-holed with the bearer check.

Issue #336 Phase 2.
"""

import hmac
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..ipc.dependencies import get_ipc_client
from ..ipc import protocol as ipc
from ..models.database import get_db
from ..models.station_config import StationConfigModel

logger = logging.getLogger(__name__)
router = APIRouter()

INGEST_SECRET_KEY = "public_mode_ingest_secret"


def _read_ingest_secret(db: Session) -> Optional[str]:
    """Return the configured bearer secret, or None if unset."""
    row = db.query(StationConfigModel).filter_by(key=INGEST_SECRET_KEY).first()
    if row is None:
        return None
    value = (row.value or "").strip()
    return value or None


def require_ingest_secret(
    request: Request,
    db: Session = Depends(get_db),
) -> None:
    """Dependency: verify the ``Authorization: Bearer <secret>`` header
    against the stored ``public_mode_ingest_secret``.

    - No secret configured → 503 so the operator sees "not configured"
      instead of a generic 401 they might chase as a bad credential.
    - Missing / non-Bearer header → 401.
    - Wrong secret → 401 (constant-time compare — a timing side-channel
      would let an attacker recover the secret one byte at a time).
    """
    stored = _read_ingest_secret(db)
    if stored is None:
        raise HTTPException(
            status_code=503,
            detail="Ingest not configured (set public_mode_ingest_secret)",
        )

    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer credentials required")
    presented = header[7:].strip()

    if not hmac.compare_digest(presented, stored):
        raise HTTPException(status_code=401, detail="Invalid ingest credentials")


class IngestReadingPayload(BaseModel):
    """Wire schema for POST /api/ingest/reading.

    A superset of ``SensorSnapshot`` — unknown keys are ignored on the
    daemon side so a relay running a newer version does not fail to
    push.  All fields optional; the buffer keeps whatever arrived last.
    """

    # We accept an arbitrary object rather than enumerating fields:
    # the SensorSnapshot dataclass is the source of truth for shape,
    # and pinning each field here would just duplicate its definition
    # and drift out of sync when a new sensor lands.
    model_config = {"extra": "allow"}


class IngestConfigPayload(BaseModel):
    """Wire schema for POST /api/ingest/config.

    Open-ended dict cached verbatim by the driver.  ``station_name``
    is the one key the driver acts on today; the rest are for Phase 4
    Station Status tile rendering."""

    model_config = {"extra": "allow"}


@router.post("/ingest/reading")
async def ingest_reading(
    payload: IngestReadingPayload,
    _auth=Depends(require_ingest_secret),
) -> dict[str, Any]:
    """Buffer a pushed SensorSnapshot into the PublicRelayDriver."""
    snapshot = payload.model_dump(exclude_none=False)
    try:
        client = get_ipc_client()
        result = await client.send_command({
            "cmd": ipc.CMD_INGEST_READING,
            "snapshot": snapshot,
        }, timeout=5.0)
    except (ConnectionRefusedError, OSError):
        raise HTTPException(status_code=503, detail="Logger daemon not running")

    if not result.get("ok"):
        detail = result.get("error", "Ingest failed")
        # A "wrong driver type" from the daemon is a client mistake, not
        # a transient fault — the operator selected the wrong driver on
        # the droplet.  Everything else is 503.
        status = 400 if "public_relay" in detail else 503
        raise HTTPException(status_code=status, detail=detail)

    return {
        "accepted": True,
        "buffered_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/ingest/config")
async def ingest_config(
    payload: IngestConfigPayload,
    _auth=Depends(require_ingest_secret),
) -> dict[str, Any]:
    """Push upstream identity/capability metadata into the driver."""
    config = payload.model_dump(exclude_none=False)
    try:
        client = get_ipc_client()
        result = await client.send_command({
            "cmd": ipc.CMD_INGEST_CONFIG,
            "config": config,
        }, timeout=5.0)
    except (ConnectionRefusedError, OSError):
        raise HTTPException(status_code=503, detail="Logger daemon not running")

    if not result.get("ok"):
        detail = result.get("error", "Ingest failed")
        status = 400 if "public_relay" in detail else 503
        raise HTTPException(status_code=status, detail=detail)

    return {"accepted": True}
