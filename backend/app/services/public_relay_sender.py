"""Private-side public-droplet relay.

Runs inside ``kanfei-logger`` on the private station host.  On every
poller broadcast it re-reads its config from ``station_config``,
short-circuits if disabled or if the local driver IS the droplet's own
``public_relay`` driver, and POSTs the current ``SensorSnapshot`` to
the droplet's ``/api/ingest/reading`` endpoint with a bearer credential.

Shape mirrors ``services/wunderground.py`` and ``services/cwop.py`` on
purpose:

- ``maybe_upload`` is idempotent, called on every broadcast, and
  self-limits via a monotonic timer.
- Config re-reads happen inside ``maybe_upload`` so a change through
  the Settings UI takes effect immediately, no restart needed.
- Consecutive-error counter drives exponential backoff up to 5 min,
  same shape as WU/CWOP ``_apply_backoff``.
- One persistent ``httpx.AsyncClient`` for connection reuse.

Two things this sender does that WU/CWOP don't:

- **Identity push.** On start and whenever ``station_name`` / firmware
  / capabilities change, it POSTs ``/api/ingest/config`` so the
  droplet's Station Status tile can render the real upstream station
  rather than the bare "Public Relay" label.
- **Last-error surface.** Failures write ``public_relay_last_error``
  into ``station_config`` so the Settings UI can show the operator
  what's wrong — WU/CWOP just log.  The row clears on the next
  successful push.

Issue #336 Phase 3.
"""

import hashlib
import json
import logging
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from ..models.database import SessionLocal
from ..models.station_config import StationConfigModel
from ..protocol.base import SensorSnapshot
from .public_mode import PUBLIC_RELAY_DRIVER_TYPE

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10.0
MAX_CONSECUTIVE_ERRORS = 5
MAX_BACKOFF_INTERVAL = 300  # 5 min, matches WU
BASE_UPLOAD_INTERVAL = 0    # 0 = push on every broadcast (no rate-limit)

_LAST_ERROR_KEY = "public_relay_last_error"


class PublicRelaySender:
    """POSTs the current SensorSnapshot to a public droplet."""

    def __init__(self) -> None:
        self._enabled = False
        self._target_url = ""
        self._secret = ""
        self._driver_type = ""
        self._last_upload: float = 0.0
        self._consecutive_errors = 0
        self._effective_interval = BASE_UPLOAD_INTERVAL
        # Hash of the last identity payload we pushed successfully.
        # Non-None means we've done the initial config push at least
        # once; a mismatch triggers a re-push on the next cycle.
        self._last_identity_hash: Optional[str] = None
        # One long-lived client per process for connection reuse.
        # Created lazily so an unconfigured install carries no cost.
        self._client: Optional[httpx.AsyncClient] = None

    # ---- Public entry point ----

    async def maybe_upload(self, snapshot: SensorSnapshot, driver: Any) -> None:
        """Push ``snapshot`` to the droplet if the gate is open.

        Called from ``LoggerDaemon._broadcast_and_upload`` on every
        poll cycle.  Both arguments are always supplied — ``driver`` is
        the currently-connected station driver (needed for the identity
        push).  A None ``snapshot`` (upstream returned nothing) skips
        the reading upload but still keeps the identity fresh.
        """
        self._reload_config()

        # Config-gate.
        if not self._enabled or not self._target_url or not self._secret:
            return
        # Driver-gate.  A droplet running ``public_relay`` has nothing
        # to relay (its own buffered snapshots came FROM a private
        # station); relaying them back would create a broadcast loop.
        if self._driver_type == PUBLIC_RELAY_DRIVER_TYPE:
            return

        # Reading upload (skip if no snapshot yet — driver still
        # warming up, first cycle after connect).
        if snapshot is not None:
            await self._push_reading(snapshot)

        # Identity push, only when it changed (or first time).
        await self._maybe_push_identity(driver)

    async def close(self) -> None:
        """Release the httpx client.  Called on daemon shutdown."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

    # ---- Config reload ----

    def _reload_config(self) -> None:
        """Read the four relay keys from ``station_config``."""
        db = SessionLocal()
        try:
            rows = (
                db.query(StationConfigModel)
                .filter(StationConfigModel.key.in_([
                    "public_relay_enabled",
                    "public_relay_target_url",
                    "public_relay_secret",
                    "station_driver_type",
                ]))
                .all()
            )
            cfg = {r.key: (r.value or "") for r in rows}
            self._enabled = cfg.get("public_relay_enabled", "").lower() == "true"
            self._target_url = cfg.get("public_relay_target_url", "").strip().rstrip("/")
            self._secret = cfg.get("public_relay_secret", "")
            self._driver_type = cfg.get("station_driver_type", "")
        except Exception as exc:
            # A DB read failure here is NOT the relay's error to persist —
            # it's a Kanfei infrastructure fault.  Log and treat as
            # "disabled" so we don't push a maybe-stale value.
            logger.warning("PublicRelaySender: config reload failed: %s", exc)
            self._enabled = False
        finally:
            db.close()

    # ---- Reading push ----

    async def _push_reading(self, snapshot: SensorSnapshot) -> None:
        """POST ``/api/ingest/reading`` with the SensorSnapshot."""
        now = time.monotonic()
        if now - self._last_upload < self._effective_interval:
            return

        # Ingest endpoint expects a FLAT SensorSnapshot mirror; do not
        # wrap in {"snapshot": ...}.  Wrapping causes the endpoint's
        # pydantic model (extra=allow) to model_dump() back into
        # {"snapshot": {...}}, then wrap AGAIN for IPC — the daemon's
        # field filter then drops every key and buffers an empty
        # SensorSnapshot.  Caught on the vsits-02 → droplet smoke test
        # 2026-08-14.
        payload = asdict(snapshot)
        url = f"{self._target_url}/api/ingest/reading"
        ok, detail = await self._post(url, payload)
        if ok:
            self._last_upload = now
            self._on_success()
        else:
            self._on_failure(f"reading push: {detail}")

    # ---- Identity push ----

    def _identity_payload(self, driver: Any) -> dict:
        """Build the identity dict from the driver's cached attrs.

        Every attribute is best-effort — a driver may not have a
        firmware version or product SKU, and that's fine.
        """
        hw = getattr(driver, "hw_config", None)
        model_code_obj = getattr(hw, "station_type", None) if hw is not None else None
        model_code = getattr(model_code_obj, "value", None) if model_code_obj is not None else None
        return {
            "station_name": getattr(driver, "station_name", "") or "",
            "station_type_code": model_code,
            "firmware_version": getattr(hw, "firmware_version", None) if hw is not None else None,
            "firmware_date": getattr(hw, "firmware_date", None) if hw is not None else None,
            "product_sku": getattr(hw, "product_sku", None) if hw is not None else None,
            "capabilities": sorted(getattr(driver, "capabilities", set()) or []),
        }

    async def _maybe_push_identity(self, driver: Any) -> None:
        """Push identity iff it has changed since the last successful
        push (or if this is the first push after startup).

        Failures do NOT set ``last_error`` — the identity push is
        cosmetic and a stale label on the droplet is not a data-flow
        failure.  Reading pushes stay the authoritative "is the relay
        working" signal.

        Backoff: we honour the reading path's ``_effective_interval``
        gate here so a down droplet doesn't get spammed with identity
        pushes every broadcast just because ``_last_identity_hash``
        never advances.  Codex round 1 on PR #340 flagged this — the
        reading path backs off, but identity was ignoring it.
        """
        payload = self._identity_payload(driver)
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()
        if digest == self._last_identity_hash:
            return

        # Share the reading backoff timer.  ``_last_upload`` is
        # updated by both successful reading pushes and by the backoff
        # anchor in ``_apply_backoff``, so this gate widens naturally
        # as failures accumulate.
        now = time.monotonic()
        if self._effective_interval and now - self._last_upload < self._effective_interval:
            return

        # Ingest endpoint expects a flat config dict, same shape reason
        # as the reading push above.
        url = f"{self._target_url}/api/ingest/config"
        ok, _ = await self._post(url, payload)
        if ok:
            self._last_identity_hash = digest
            logger.info(
                "PublicRelaySender: identity pushed (%s)",
                payload.get("station_name") or "<no name>",
            )
        # A failed identity push retries on the next broadcast because
        # the hash never advances — subject to the backoff gate above.

    # ---- HTTP core ----

    async def _post(self, url: str, body: dict) -> tuple[bool, str]:
        """POST JSON with bearer auth.  Returns (ok, detail_or_error)."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
        headers = {
            "Authorization": f"Bearer {self._secret}",
            "Content-Type": "application/json",
        }
        try:
            resp = await self._client.post(url, json=body, headers=headers)
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            # NEVER include the secret or the full URL with credentials
            # in an error message — the URL is safe (no auth in URL)
            # but the header wouldn't be if we ever put it there.
            return False, f"transport: {type(exc).__name__}: {exc}"
        except Exception as exc:
            return False, f"unexpected: {type(exc).__name__}: {exc}"

        if resp.status_code == 200:
            return True, "ok"
        # Distinguish "wrong credential" from "misconfigured droplet"
        # from "unreachable" in the persisted detail so operators know
        # what to fix.
        detail = f"HTTP {resp.status_code}"
        try:
            body_json = resp.json()
            if isinstance(body_json, dict) and body_json.get("detail"):
                detail = f"HTTP {resp.status_code}: {body_json['detail']}"
        except Exception:
            pass
        return False, detail

    # ---- Success / failure handlers ----

    def _on_success(self) -> None:
        self._consecutive_errors = 0
        self._effective_interval = BASE_UPLOAD_INTERVAL
        # Clear a stale error row so the Settings UI reflects the
        # current-good state.
        self._persist_last_error("")

    def _on_failure(self, detail: str) -> None:
        self._consecutive_errors += 1
        logger.warning("PublicRelaySender: %s (err #%d)", detail, self._consecutive_errors)
        self._persist_last_error(detail)
        self._apply_backoff()

    def _apply_backoff(self) -> None:
        if self._consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            # First hit: 30 s.  Doubles on each subsequent failure.
            base = self._effective_interval or 30
            self._effective_interval = min(base * 2, MAX_BACKOFF_INTERVAL)
            # Anchor the timer to now so the backoff actually delays
            # the next attempt (otherwise a broadcast that arrives
            # inside the same second would fire again immediately).
            self._last_upload = time.monotonic()
            logger.error(
                "PublicRelaySender: %d consecutive errors; backing off to %ds",
                self._consecutive_errors, self._effective_interval,
            )

    # ---- Last-error persistence ----

    def _persist_last_error(self, message: str) -> None:
        """Upsert ``public_relay_last_error`` in ``station_config``.

        Truncated to 500 chars so a giant exception repr can't blow up
        the row.  The Settings UI reads this key to surface a stale
        error to the operator.
        """
        value = (message or "")[:500]
        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key=_LAST_ERROR_KEY).first()
            now = datetime.now(timezone.utc)
            if row is None:
                if value == "":
                    # Nothing to record and no row to clear.
                    return
                db.add(StationConfigModel(key=_LAST_ERROR_KEY, value=value, updated_at=now))
            else:
                # Skip the write if the value hasn't changed — this
                # runs every poll cycle and there's no point rewriting
                # the same string.
                if row.value == value:
                    return
                row.value = value
                row.updated_at = now
            db.commit()
        except Exception as exc:
            logger.warning(
                "PublicRelaySender: failed to persist last_error: %s", exc,
            )
        finally:
            db.close()
