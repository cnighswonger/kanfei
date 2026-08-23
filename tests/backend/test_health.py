"""GET /api/health — composite liveness for external monitors.

Pins the response shape (external-check callers depend on it) and the
200/503 flip conditions.  Sub-issue #473 of umbrella #472; the failure
mode this endpoint exists to surface is documented on those issues.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ipc import dependencies as ipc_deps


class _StubIPC:
    """IPCClient stand-in.  ``status`` returns a canned status payload
    from `data`; other commands raise NotImplemented so a stray call
    from the endpoint under test surfaces loudly instead of hanging."""

    def __init__(self, data: dict | None = None, raise_exc: Exception | None = None):
        self._data = data
        self._exc = raise_exc

    async def send_command(self, msg: dict, timeout: float = 5.0) -> dict:
        if self._exc is not None:
            raise self._exc
        if msg.get("cmd") == "status":
            return {"ok": True, "data": self._data}
        raise NotImplementedError(msg)

    async def is_available(self) -> bool:
        return True

    async def close(self) -> None:
        return None


@pytest.fixture
def make_client():
    """Yield a factory that installs a stub IPC and returns a TestClient.

    Each caller controls its own stub payload, so 200/503 branches don't
    share state.
    """
    prior = ipc_deps._ipc_client

    def _factory(stub: _StubIPC) -> TestClient:
        ipc_deps.set_ipc_client(stub)
        client = TestClient(app)
        client.__enter__()
        # TestClient's `with` block runs the lifespan which resets the
        # ipc client to a real IPCClient; re-install the stub after.
        ipc_deps.set_ipc_client(stub)
        return client

    made: list[TestClient] = []

    def factory(stub):
        c = _factory(stub)
        made.append(c)
        return c

    yield factory

    for c in made:
        c.__exit__(None, None, None)
    ipc_deps.set_ipc_client(prior)


class TestHealthy:
    def test_200_when_poller_fresh(self, make_client):
        client = make_client(_StubIPC(data={
            "connected": True,
            "poll_interval": 10,
            "poll_stall_seconds": 4.2,
            "last_poll_completed_at": "2026-08-23T18:00:00+00:00",
            "last_broadcast_at": "2026-08-23T18:00:00+00:00",
        }))
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["connected"] is True
        assert body["poll_stall_seconds"] == pytest.approx(4.2)
        assert body["poll_interval"] == 10
        assert body["reason"] is None

    def test_200_during_startup_when_no_poll_completed_yet(self, make_client):
        """`poll_stall_seconds: null` is the startup window between
        driver-connect and first-poll-complete.  A monitor calling
        /api/health here must not page — the fallback threshold catches
        the case where startup itself is stuck."""
        client = make_client(_StubIPC(data={
            "connected": True,
            "poll_interval": 10,
            "poll_stall_seconds": None,
            "last_poll_completed_at": None,
            "last_broadcast_at": None,
        }))
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["ok"] is True


class TestUnhealthy:
    def test_503_when_poll_stalled(self, make_client):
        """3 × poll_interval (10 s) = 30 s.  32 s > 30 s → 503."""
        client = make_client(_StubIPC(data={
            "connected": True,
            "poll_interval": 10,
            "poll_stall_seconds": 32.0,
            "last_poll_completed_at": "2026-08-23T17:59:28+00:00",
            "last_broadcast_at": "2026-08-23T17:59:28+00:00",
        }))
        r = client.get("/api/health")
        assert r.status_code == 503
        body = r.json()
        assert body["ok"] is False
        assert "stalled" in body["reason"]
        # Structured detail comes back on 503 so the monitor knows WHY.
        assert body["poll_stall_seconds"] == 32.0

    def test_503_when_driver_disconnected(self, make_client):
        client = make_client(_StubIPC(data={
            "connected": False,
            "poll_interval": 10,
            "poll_stall_seconds": None,
            "last_poll_completed_at": None,
            "last_broadcast_at": None,
        }))
        r = client.get("/api/health")
        assert r.status_code == 503
        assert r.json()["reason"] == "driver not connected"

    def test_503_when_ipc_times_out(self, make_client):
        """Whole point of the endpoint: give a fast, structured 503
        even when the daemon is degraded.  A hung IPC must not hang
        /api/health."""
        client = make_client(_StubIPC(raise_exc=asyncio.TimeoutError()))
        r = client.get("/api/health")
        assert r.status_code == 503
        assert "TimeoutError" in r.json()["reason"]

    def test_503_when_ipc_refuses_connection(self, make_client):
        """Logger daemon isn't running or crashed."""
        client = make_client(_StubIPC(raise_exc=ConnectionRefusedError()))
        r = client.get("/api/health")
        assert r.status_code == 503
        assert "ConnectionRefusedError" in r.json()["reason"]


class TestResponseShape:
    """External monitors depend on these fields; renaming or removing
    any of them silently disarms callers.  Extend rather than rename."""

    _EXPECTED_KEYS = {
        "ok", "connected", "poll_stall_seconds", "poll_interval",
        "last_poll_completed_at", "last_broadcast_at", "reason",
    }

    def test_200_body_has_documented_keys(self, make_client):
        client = make_client(_StubIPC(data={
            "connected": True, "poll_interval": 10, "poll_stall_seconds": 1,
            "last_poll_completed_at": "2026-08-23T18:00:00+00:00",
            "last_broadcast_at": "2026-08-23T18:00:00+00:00",
        }))
        assert set(client.get("/api/health").json()) == self._EXPECTED_KEYS

    def test_503_body_has_documented_keys(self, make_client):
        client = make_client(_StubIPC(data={
            "connected": True, "poll_interval": 10, "poll_stall_seconds": 999,
            "last_poll_completed_at": "2026-08-23T12:00:00+00:00",
            "last_broadcast_at": "2026-08-23T12:00:00+00:00",
        }))
        assert set(client.get("/api/health").json()) == self._EXPECTED_KEYS
