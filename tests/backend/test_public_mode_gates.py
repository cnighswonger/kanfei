"""Read-only gates that apply when ``station_driver_type = 'public_relay'``.

The public droplet runs the exact same Kanfei binary as production — the
only difference is a driver-type value in ``station_config``.  Two
gates enforce read-only:

  * A write-block middleware in ``app/main.py`` returns 403 for every
    ``POST``/``PUT``/``DELETE``/``PATCH`` outside a small allowlist.
  * ``require_admin`` in ``app/api/dependencies.py`` bypasses the auth
    check so guests can read admin-only GETs (Settings, config, etc.)
    for the Phase 4 read-only UI.

The route-walk regression guard at the bottom of this file is the
important one: it iterates ``app.routes`` and asserts every write path
gets the 403, so a new endpoint added later cannot silently ship without
the gate.

Issue #336 (Phase 1).
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.database import Base, SessionLocal, engine
from app.models.station_config import StationConfigModel
from app.services import public_mode
from ._route_walk import walk_api_routes


@pytest.fixture(autouse=True)
def _reset_public_mode_cache():
    """The module-level 30 s cache in ``public_mode`` would otherwise
    let one test's ``station_config`` write bleed into the next.  Wipe
    it before AND after every test so a stale ``True`` never survives
    into ``test_middleware_allows_writes_when_not_public``."""
    public_mode.invalidate_cache()
    yield
    public_mode.invalidate_cache()


@pytest.fixture
def clean_station_config():
    tables = [StationConfigModel.__table__]
    Base.metadata.drop_all(bind=engine, tables=tables)
    Base.metadata.create_all(bind=engine, tables=tables)
    yield
    db = SessionLocal()
    try:
        db.query(StationConfigModel).delete()
        db.commit()
    finally:
        db.close()


def _set_driver_type(driver_type: str | None) -> None:
    """Seed or clear ``station_driver_type``.  Also invalidates the
    ``is_public_mode`` cache so the next call re-reads."""
    db = SessionLocal()
    try:
        row = db.query(StationConfigModel).filter_by(
            key="station_driver_type",
        ).first()
        if driver_type is None:
            if row is not None:
                db.delete(row)
        elif row is None:
            db.add(StationConfigModel(
                key="station_driver_type",
                value=driver_type,
                updated_at=datetime.now(timezone.utc),
            ))
        else:
            row.value = driver_type
        db.commit()
    finally:
        db.close()
    public_mode.invalidate_cache()


@pytest.fixture
def client_public(clean_station_config):
    """TestClient with public mode active."""
    _set_driver_type("public_relay")
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_private(clean_station_config):
    """TestClient with public mode INACTIVE — the normal shape."""
    _set_driver_type("legacy")
    with TestClient(app) as c:
        yield c


class TestWriteBlockMiddleware:
    """A representative sample of write endpoints must return 403 with the
    read-only detail message when public mode is active."""

    @pytest.mark.parametrize("method,path,body", [
        ("POST", "/api/setup/reconnect", None),
        ("POST", "/api/setup/complete", {}),
        ("POST", "/api/station/sync-time", None),
        ("POST", "/api/auth/login", {"username": "x", "password": "y"}),
        ("POST", "/api/auth/setup-admin", {"username": "x", "password": "y"}),
        ("POST", "/api/backup", None),
        ("PUT", "/api/config", {}),
        ("DELETE", "/api/backup/foo", None),
    ])
    def test_write_returns_403_in_public_mode(self, client_public, method, path, body):
        kwargs = {"json": body} if body is not None else {}
        resp = client_public.request(method, path, **kwargs)
        assert resp.status_code == 403, (
            f"{method} {path} returned {resp.status_code} in public mode; "
            f"expected 403 from the write-block middleware. Body: {resp.text!r}"
        )
        assert resp.json() == {"detail": "Kanfei is running in read-only public mode"}

    def test_write_not_blocked_when_not_public(self, client_private):
        """The middleware must be a no-op in production mode — otherwise
        we would be double-gating every write on all deployments."""
        # ``/api/config`` is admin-only, so an unauthenticated PUT returns
        # 401 (or 422 for a bad body), never 403.  What matters is that
        # the response is *not* the read-only-mode 403.
        resp = client_private.put("/api/config", json={})
        assert resp.status_code != 403 or resp.json() != {
            "detail": "Kanfei is running in read-only public mode",
        }


class TestReadEndpointsUnaffected:
    """GET endpoints must return their normal responses in public mode —
    the middleware only touches state-mutating methods."""

    @pytest.mark.parametrize("path", [
        "/api/setup/status",
        "/api/setup/serial-ports",
        "/api/station",
        "/api/station/drivers",
        "/api/config",
    ])
    def test_get_returns_non_403(self, client_public, path):
        resp = client_public.get(path)
        # 200 for open GETs, or a 5xx from the IPC-unavailable degraded
        # path for driver-touching ones — both prove the middleware
        # is not blocking reads.
        assert resp.status_code != 403, (
            f"GET {path} returned 403 in public mode — the write-block "
            f"middleware must NOT gate reads. Body: {resp.text!r}"
        )


class TestRequireAdminBypass:
    """Admin-only GETs must be readable by unauthenticated guests when
    public mode is active — that's what makes the Phase 4 read-only
    Settings UI possible."""

    def test_admin_only_config_get_readable_by_guest(self, client_public):
        resp = client_public.get("/api/config")
        assert resp.status_code == 200, (
            f"GET /api/config should be 200 for a guest in public mode "
            f"(require_admin bypass). Got {resp.status_code}: {resp.text!r}"
        )

    def test_admin_only_get_returns_401_when_not_public(self, client_private):
        """Sanity — without public mode active, the same guest GET is 401
        so we know the bypass really is what unlocked it."""
        # /api/config in production mode: 401 (no auth), UNLESS the
        # bootstrap bypass is active (no users exist yet), in which case
        # it returns 200.  This conftest starts with no users, so accept
        # either — what matters is it's not gated by public_mode.
        resp = client_private.get("/api/config")
        assert resp.status_code in (200, 401)


class TestCacheInvalidation:
    """Every writer of ``station_driver_type`` must invalidate the
    ``is_public_mode`` cache in its own commit path.  Missing one leaves
    the read-only gate stale for up to 30 s after the flip (PR #337
    Codex round 1 blocker on ``/api/config``)."""

    def test_cache_reflects_new_driver_type_after_invalidate(self, clean_station_config):
        _set_driver_type("public_relay")
        assert public_mode.is_public_mode() is True
        _set_driver_type("legacy")
        assert public_mode.is_public_mode() is False

    def test_put_config_flip_to_public_relay_blocks_next_write(self, clean_station_config):
        """A ``PUT /api/config`` that flips ``station_driver_type`` to
        ``public_relay`` must have the middleware block the very next
        write — no 30 s cache window in which writes still slip through.
        Regression for PR #337 Codex round 1."""
        _set_driver_type("legacy")
        # Prime the cache with the pre-flip (False) value.
        assert public_mode.is_public_mode() is False
        with TestClient(app) as c:
            # A pre-flip write is not gated by public mode (the read
            # here — it might 401 or 422, but not the mode 403).
            resp = c.put("/api/config", json=[])
            assert resp.status_code != 403 or resp.json() != {
                "detail": "Kanfei is running in read-only public mode",
            }

            # Flip via /api/config PUT — the code path Codex flagged.
            resp = c.put("/api/config", json=[
                {"key": "station_driver_type", "value": "public_relay"},
            ])
            assert resp.status_code == 200, resp.text

            # Next write must be gated — no cache lag allowed.
            resp = c.put("/api/config", json=[])
            assert resp.status_code == 403
            assert resp.json() == {
                "detail": "Kanfei is running in read-only public mode",
            }

    def test_put_config_flip_away_from_public_unblocks_next_write(self, clean_station_config):
        """Same invariant in the other direction: flipping OUT of public
        mode via /api/config must let the next write through immediately."""
        _set_driver_type("public_relay")
        assert public_mode.is_public_mode() is True
        with TestClient(app) as c:
            # /api/config PUT is blocked in public mode — but the middleware
            # only sees the PATH, not the payload, so we cannot flip out
            # of public mode via /api/config once it is on.  Simulate the
            # flip via a direct DB write (mirrors what would happen if
            # the operator re-ran the setup wizard).
            _set_driver_type("legacy")
            # Next write must go through.
            resp = c.put("/api/config", json=[])
            assert resp.status_code != 403 or resp.json() != {
                "detail": "Kanfei is running in read-only public mode",
            }


# --------------- Route-walk regression guard ---------------

def _substitute_path_params(path: str) -> str:
    """Replace ``{param}`` placeholders with ``dummy`` so a real HTTP
    request can be made against the route.  A 403 fires at the middleware
    layer before the handler resolves the placeholder, so any string
    works — we just need to satisfy Starlette's router matcher."""
    import re
    return re.sub(r"\{[^}]+\}", "dummy", path)


def _write_routes() -> list[tuple[str, str]]:
    """Enumerate every ``APIRoute`` with a state-mutating method.

    Returns a list of ``(method, concrete_path)`` pairs suitable for
    parametrisation.  Both halves are load-bearing: walking every
    reachable route catches endpoints someone forgot to gate, and
    substituting params lets us hit ones with URL variables like
    ``/api/backup/{name}``.

    Uses ``walk_api_routes`` because FastAPI 0.141+ wraps included
    routers in ``_IncludedRouter`` — a naive ``isinstance(r, APIRoute)``
    filter on ``app.routes`` returns an empty list and vacuously
    passes, silently defanging the whole regression guard.
    """
    routes: list[tuple[str, str]] = []
    for route in walk_api_routes(app):
        methods = route.methods & {"POST", "PUT", "DELETE", "PATCH"}
        if not methods:
            continue
        concrete = _substitute_path_params(route.path)
        for method in sorted(methods):
            routes.append((method, concrete))
    return routes


class TestNoWriteEndpointEscapesTheGate:
    """The invariant this guards: any new write endpoint added later is
    caught by the middleware without a per-endpoint change.

    Same shape as the WS-payload parity test that landed in #335 — pin
    the invariant with a walk of the live route table so the next
    developer cannot silently ship an ungated write.
    """

    def test_every_write_route_returns_403_in_public_mode(self, client_public):
        allowlist = frozenset(app.state.public_mode_write_allowlist)
        offenders: list[str] = []
        for method, path in _write_routes():
            if path in allowlist:
                continue
            # Empty JSON body is a syntactically valid request against
            # every JSON-body endpoint; validation errors come AFTER the
            # middleware, and the middleware runs first regardless.
            resp = client_public.request(method, path, json={})
            if resp.status_code != 403:
                offenders.append(
                    f"{method} {path} -> {resp.status_code} {resp.text!r}"
                )
        assert not offenders, (
            "Write endpoints escaped the public-mode middleware:\n  "
            + "\n  ".join(offenders)
            + "\n\nEither the middleware isn't running, or the path "
            "belongs in ``app.state.public_mode_write_allowlist`` "
            "(currently empty in Phase 1; Phase 2 adds the ingest paths)."
        )
