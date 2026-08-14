"""Ingest endpoints — POST /api/ingest/{reading,config}.

Phase 2 of the public-droplet mode (issue #336).  These endpoints are
the ONLY writes a public droplet legitimately accepts; they sit
outside `require_admin` (the guest bypass would let anyone in
otherwise) and are gated by a bearer secret stored in station_config.

The tests here pin:

- Bearer-secret verification (missing/wrong/right).
- 503 when the secret is unconfigured (distinguishable from 401).
- The two ingest paths bypass the public-mode write-block middleware
  because they're in `app.state.public_mode_write_allowlist`.
- The secret is masked in GET /api/config.
- The daemon-side wrong-driver refusal returns 400 to the caller.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.database import Base, SessionLocal, engine
from app.models.station_config import StationConfigModel
from app.services import public_mode
from app.ipc import dependencies as ipc_deps

INGEST_SECRET = "s" * 32  # not a real secret; length is arbitrary


class _FakeIPCClient:
    """Stand-in for IPCClient that records the last command and returns
    a canned response.  Keeps daemon out of the test loop entirely."""

    def __init__(self, response: dict | None = None) -> None:
        self.response = response or {"ok": True, "data": {"success": True}}
        self.calls: list[dict] = []

    async def send_command(self, msg: dict, timeout: float = 5.0) -> dict:
        self.calls.append(msg)
        return self.response

    async def is_available(self) -> bool:
        return True

    async def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _reset_public_mode_cache():
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


def _set_config(key: str, value: str) -> None:
    db = SessionLocal()
    try:
        row = db.query(StationConfigModel).filter_by(key=key).first()
        if row is None:
            db.add(StationConfigModel(
                key=key, value=value,
                updated_at=datetime.now(timezone.utc),
            ))
        else:
            row.value = value
        db.commit()
    finally:
        db.close()


@pytest.fixture
def public_droplet(clean_station_config):
    """A TestClient with public mode active, a configured ingest secret,
    and a fake IPC client so tests never touch the real daemon."""
    _set_config("station_driver_type", "public_relay")
    _set_config("public_mode_ingest_secret", INGEST_SECRET)
    public_mode.invalidate_cache()

    fake = _FakeIPCClient()
    prior = ipc_deps._ipc_client
    ipc_deps.set_ipc_client(fake)
    try:
        with TestClient(app) as c:
            # TestClient's `with` block runs the lifespan, which resets
            # the ipc client to a real IPCClient.  Overwrite AGAIN after
            # the lifespan so the fake wins.
            ipc_deps.set_ipc_client(fake)
            yield c, fake
    finally:
        ipc_deps.set_ipc_client(prior)


class TestBearerAuth:
    """The bearer check runs before the IPC round-trip — every failure
    mode must NOT reach the daemon."""

    def test_401_without_authorization_header(self, public_droplet):
        client, fake = public_droplet
        resp = client.post("/api/ingest/reading", json={"outside_temp": 22.0})
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Bearer credentials required"}
        assert fake.calls == [], "IPC must not fire on failed auth"

    def test_401_with_wrong_bearer(self, public_droplet):
        client, fake = public_droplet
        resp = client.post(
            "/api/ingest/reading",
            json={"outside_temp": 22.0},
            headers={"Authorization": f"Bearer wrong-{INGEST_SECRET}"},
        )
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Invalid ingest credentials"}
        assert fake.calls == []

    def test_401_with_non_bearer_scheme(self, public_droplet):
        client, fake = public_droplet
        resp = client.post(
            "/api/ingest/reading",
            json={"outside_temp": 22.0},
            headers={"Authorization": f"Basic {INGEST_SECRET}"},
        )
        assert resp.status_code == 401
        assert fake.calls == []

    def test_503_when_secret_not_configured(self, clean_station_config):
        """A droplet that hasn't been fully set up returns 503 — an
        operator debugging a bad push should see 'not configured' rather
        than chase the wrong secret."""
        _set_config("station_driver_type", "public_relay")
        public_mode.invalidate_cache()

        fake = _FakeIPCClient()
        prior = ipc_deps._ipc_client
        ipc_deps.set_ipc_client(fake)
        try:
            with TestClient(app) as c:
                ipc_deps.set_ipc_client(fake)
                resp = c.post(
                    "/api/ingest/reading",
                    json={"outside_temp": 22.0},
                    headers={"Authorization": f"Bearer {INGEST_SECRET}"},
                )
        finally:
            ipc_deps.set_ipc_client(prior)
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"].lower()

    def test_200_with_correct_bearer_forwards_to_ipc(self, public_droplet):
        client, fake = public_droplet
        resp = client.post(
            "/api/ingest/reading",
            json={"outside_temp": 22.5, "outside_humidity": 60},
            headers={"Authorization": f"Bearer {INGEST_SECRET}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["accepted"] is True
        assert "buffered_at" in body

        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["cmd"] == "ingest_reading"
        assert call["snapshot"]["outside_temp"] == 22.5
        assert call["snapshot"]["outside_humidity"] == 60


class TestConfigIngest:
    def test_config_push_forwards_verbatim(self, public_droplet):
        client, fake = public_droplet
        payload = {
            "station_name": "Vantage Vue (fw 2.12)",
            "firmware_version": "2.12",
            "capabilities": ["archive_sync"],
        }
        resp = client.post(
            "/api/ingest/config",
            json=payload,
            headers={"Authorization": f"Bearer {INGEST_SECRET}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"accepted": True}
        assert fake.calls[-1]["cmd"] == "ingest_config"
        assert fake.calls[-1]["config"]["station_name"] == "Vantage Vue (fw 2.12)"


class TestWrongDriverFromDaemon:
    """If the daemon rejects the ingest because the driver isn't
    ``public_relay`` (defensive check on the daemon side), surface that
    as a 400 — it's an operator misconfiguration, not a transient fault."""

    def test_reading_returns_400_when_daemon_rejects(self, public_droplet):
        client, fake = public_droplet
        fake.response = {
            "ok": False,
            "error": "ingest endpoints are only available when station_driver_type == 'public_relay'",
        }
        resp = client.post(
            "/api/ingest/reading",
            json={"outside_temp": 22.0},
            headers={"Authorization": f"Bearer {INGEST_SECRET}"},
        )
        assert resp.status_code == 400
        assert "public_relay" in resp.json()["detail"]

    def test_reading_returns_503_on_generic_daemon_error(self, public_droplet):
        client, fake = public_droplet
        fake.response = {"ok": False, "error": "daemon busy"}
        resp = client.post(
            "/api/ingest/reading",
            json={"outside_temp": 22.0},
            headers={"Authorization": f"Bearer {INGEST_SECRET}"},
        )
        assert resp.status_code == 503


class TestMiddlewareAllowlist:
    """The public-mode write-block middleware must let the ingest paths
    reach their handler.  A regression here would return 403 before the
    bearer check ever runs."""

    def test_reading_bypasses_write_block(self, public_droplet):
        client, _ = public_droplet
        # Without an auth header we get 401 (from the handler), NOT 403
        # (from the middleware).  Distinguishing these is the whole
        # point: the allowlist worked iff we reached the handler at all.
        resp = client.post("/api/ingest/reading", json={})
        assert resp.status_code == 401, (
            "Ingest path returned {resp.status_code}; if 403, the "
            "middleware is not honouring the allowlist"
        )

    def test_config_bypasses_write_block(self, public_droplet):
        client, _ = public_droplet
        resp = client.post("/api/ingest/config", json={})
        assert resp.status_code == 401

    def test_allowlist_matches_route_paths_exactly(self):
        """A trailing-slash mismatch between the middleware allowlist and
        the FastAPI route path would silently 403 all ingests.  Assert
        every allowlist entry corresponds to a real route."""
        from fastapi.routing import APIRoute
        route_paths = {r.path for r in app.routes if isinstance(r, APIRoute)}
        for path in app.state.public_mode_write_allowlist:
            assert path in route_paths, (
                f"Allowlist entry {path!r} does not match any registered "
                f"route.  Trailing slash or typo? Registered write paths: "
                f"{sorted(p for p in route_paths if p.startswith('/api/ingest'))}"
            )


class TestSecretMasking:
    """A viewer of GET /api/config must never see the raw ingest secret —
    otherwise anyone with settings-read access could impersonate the
    upstream relay."""

    def test_secret_masked_in_get_config(self, clean_station_config):
        _set_config("public_mode_ingest_secret", "abcd" + "e" * 28)
        # Use production (non-public) mode so require_admin bootstrap
        # bypass applies (no users seeded).
        with TestClient(app) as c:
            resp = c.get("/api/config")
        assert resp.status_code == 200
        items = {item["key"]: item["value"] for item in resp.json()}
        assert "public_mode_ingest_secret" in items
        assert items["public_mode_ingest_secret"] != "abcd" + "e" * 28, (
            "GET /api/config returned the raw ingest secret; must be "
            "masked (see _SECRET_KEYS in app/api/config.py)"
        )
        assert "*" in items["public_mode_ingest_secret"]
