"""PublicRelaySender — the private-side relay task (issue #336 Phase 3).

Called on every poller broadcast, self-gated on config + driver type,
persists last error into ``station_config`` so the Settings UI can
surface it.  Tests here pin:

- Config gates (enabled / target_url / secret all required).
- Driver-type gate — a droplet (``public_relay``) never relays.
- Bearer header on the wire.
- Backoff triggers after N consecutive failures.
- Last-error row updates on failure and clears on success.
- Identity push fires only when the payload changes.
- The secret never appears in error messages.
"""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.models.database import Base, SessionLocal, engine
from app.models.station_config import StationConfigModel
from app.protocol.base import SensorSnapshot
from app.services.public_relay_sender import (
    MAX_BACKOFF_INTERVAL,
    MAX_CONSECUTIVE_ERRORS,
    PublicRelaySender,
)


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


def _set(key: str, value: str) -> None:
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


def _get(key: str) -> str | None:
    db = SessionLocal()
    try:
        row = db.query(StationConfigModel).filter_by(key=key).first()
        return row.value if row is not None else None
    finally:
        db.close()


def _enable_relay() -> None:
    _set("public_relay_enabled", "true")
    _set("public_relay_target_url", "https://droplet.example.com")
    _set("public_relay_secret", "secret-token-abcdefghijklmnop")
    _set("station_driver_type", "vantage")


def _snapshot() -> SensorSnapshot:
    return SensorSnapshot(
        outside_temp=22.5, outside_humidity=55, barometer=1015.0,
    )


class _FakeDriver:
    """Minimal driver stand-in — the sender only reads a few attrs."""

    station_name = "Vantage Vue (fw 2.12)"
    capabilities = {"archive_sync"}
    hw_config = SimpleNamespace(
        station_type=SimpleNamespace(value=16),
        firmware_version="2.12",
        firmware_date="Mar 15 2010",
        product_sku="6555",
    )


def _install_mock_client(sender: PublicRelaySender) -> AsyncMock:
    """Replace the sender's httpx client with an AsyncMock.

    Returns the mock so tests can assert calls and set response
    behaviour.  Sender lazily creates a client on first POST; we
    install ours before that ever happens.
    """
    mock = AsyncMock()
    mock.post = AsyncMock(return_value=httpx.Response(200, json={"accepted": True}))
    mock.aclose = AsyncMock()
    sender._client = mock
    return mock


def _run(coro):
    """asyncio.run() shim so each test spins up its own loop."""
    return asyncio.run(coro)


# ---------------- Config gates ----------------


class TestConfigGates:
    def test_disabled_by_default(self, clean_station_config):
        sender = PublicRelaySender()
        mock = _install_mock_client(sender)
        _run(sender.maybe_upload(_snapshot(), _FakeDriver()))
        assert mock.post.call_count == 0, "must not push when disabled"

    def test_missing_target_url_blocks(self, clean_station_config):
        _set("public_relay_enabled", "true")
        _set("public_relay_secret", "s" * 32)
        _set("station_driver_type", "vantage")
        # target_url intentionally unset
        sender = PublicRelaySender()
        mock = _install_mock_client(sender)
        _run(sender.maybe_upload(_snapshot(), _FakeDriver()))
        assert mock.post.call_count == 0

    def test_missing_secret_blocks(self, clean_station_config):
        _set("public_relay_enabled", "true")
        _set("public_relay_target_url", "https://d.example.com")
        _set("station_driver_type", "vantage")
        sender = PublicRelaySender()
        mock = _install_mock_client(sender)
        _run(sender.maybe_upload(_snapshot(), _FakeDriver()))
        assert mock.post.call_count == 0

    def test_driver_is_public_relay_blocks(self, clean_station_config):
        """A droplet running ``public_relay`` MUST NOT relay — its own
        buffered snapshots came FROM a station, and echoing them back
        would loop."""
        _enable_relay()
        _set("station_driver_type", "public_relay")
        sender = PublicRelaySender()
        mock = _install_mock_client(sender)
        _run(sender.maybe_upload(_snapshot(), _FakeDriver()))
        assert mock.post.call_count == 0


# ---------------- Happy path ----------------


class TestPushShape:
    def test_reading_posts_with_bearer_and_snapshot(self, clean_station_config):
        _enable_relay()
        sender = PublicRelaySender()
        mock = _install_mock_client(sender)
        _run(sender.maybe_upload(_snapshot(), _FakeDriver()))

        # First POST = reading, second = identity (first-time push).
        assert mock.post.call_count == 2
        reading_call = mock.post.call_args_list[0]
        url = reading_call.args[0]
        assert url == "https://droplet.example.com/api/ingest/reading"

        headers = reading_call.kwargs["headers"]
        assert headers["Authorization"] == "Bearer secret-token-abcdefghijklmnop"
        assert headers["Content-Type"] == "application/json"

        body = reading_call.kwargs["json"]
        assert "snapshot" in body
        assert body["snapshot"]["outside_temp"] == 22.5
        assert body["snapshot"]["outside_humidity"] == 55

    def test_success_clears_last_error(self, clean_station_config):
        _enable_relay()
        # Pretend a prior failure was recorded.
        _set("public_relay_last_error", "HTTP 503: earlier")
        sender = PublicRelaySender()
        _install_mock_client(sender)
        _run(sender.maybe_upload(_snapshot(), _FakeDriver()))
        assert _get("public_relay_last_error") == ""


# ---------------- Identity push ----------------


class TestIdentity:
    def test_identity_posts_on_first_cycle(self, clean_station_config):
        _enable_relay()
        sender = PublicRelaySender()
        mock = _install_mock_client(sender)
        _run(sender.maybe_upload(_snapshot(), _FakeDriver()))

        identity_call = mock.post.call_args_list[1]
        assert identity_call.args[0] == "https://droplet.example.com/api/ingest/config"
        assert identity_call.kwargs["json"]["config"]["station_name"] == "Vantage Vue (fw 2.12)"
        assert identity_call.kwargs["json"]["config"]["capabilities"] == ["archive_sync"]
        assert identity_call.kwargs["json"]["config"]["station_type_code"] == 16

    def test_identity_skipped_when_unchanged(self, clean_station_config):
        _enable_relay()
        sender = PublicRelaySender()
        mock = _install_mock_client(sender)
        driver = _FakeDriver()
        _run(sender.maybe_upload(_snapshot(), driver))
        assert mock.post.call_count == 2
        # Second cycle, same driver, same identity → only the reading
        # push fires; identity is not re-sent.
        _run(sender.maybe_upload(_snapshot(), driver))
        assert mock.post.call_count == 3

    def test_identity_re_sent_when_driver_changes(self, clean_station_config):
        _enable_relay()
        sender = PublicRelaySender()
        mock = _install_mock_client(sender)
        _run(sender.maybe_upload(_snapshot(), _FakeDriver()))
        assert mock.post.call_count == 2

        # Simulate a firmware upgrade / driver reconnect with different name.
        class _DifferentDriver(_FakeDriver):
            station_name = "Vantage Vue (fw 3.90)"

        _run(sender.maybe_upload(_snapshot(), _DifferentDriver()))
        # 1 more reading + 1 more identity = 2 more calls.
        assert mock.post.call_count == 4


# ---------------- Failure + backoff ----------------


class TestFailureModes:
    def test_http_500_persists_last_error(self, clean_station_config):
        _enable_relay()
        sender = PublicRelaySender()
        mock = _install_mock_client(sender)
        mock.post.return_value = httpx.Response(
            500, json={"detail": "internal"},
        )
        _run(sender.maybe_upload(_snapshot(), _FakeDriver()))
        assert sender._consecutive_errors >= 1
        last = _get("public_relay_last_error")
        assert last is not None and "500" in last

    def test_transport_error_persists_last_error(self, clean_station_config):
        _enable_relay()
        sender = PublicRelaySender()
        mock = _install_mock_client(sender)
        mock.post.side_effect = httpx.ConnectError("Connection refused")
        _run(sender.maybe_upload(_snapshot(), _FakeDriver()))
        last = _get("public_relay_last_error")
        assert last is not None
        assert "transport" in last
        assert "Connection refused" in last

    def test_secret_never_leaks_into_last_error(self, clean_station_config):
        _enable_relay()
        sender = PublicRelaySender()
        mock = _install_mock_client(sender)
        # Any failure mode — the persisted message must not carry the
        # secret.  This is the "no secret in logs / DB" contract.
        mock.post.return_value = httpx.Response(401, json={"detail": "Invalid ingest credentials"})
        _run(sender.maybe_upload(_snapshot(), _FakeDriver()))
        last = _get("public_relay_last_error") or ""
        assert "secret-token-abcdefghijklmnop" not in last, (
            "The bearer secret must never appear in the persisted "
            "last-error row — anyone with settings-read access "
            "would then be able to lift it."
        )

    def test_backoff_kicks_in_after_N_failures(self, clean_station_config):
        _enable_relay()
        sender = PublicRelaySender()
        mock = _install_mock_client(sender)
        mock.post.return_value = httpx.Response(503, json={"detail": "down"})

        for _ in range(MAX_CONSECUTIVE_ERRORS + 1):
            _run(sender.maybe_upload(_snapshot(), _FakeDriver()))

        assert sender._effective_interval > 0
        assert sender._effective_interval <= MAX_BACKOFF_INTERVAL
        assert sender._consecutive_errors >= MAX_CONSECUTIVE_ERRORS

    def test_identity_push_shares_backoff_gate(self, clean_station_config):
        """Codex round 1 on PR #340: a failed identity push must not
        fire on every broadcast when the reading path has already
        backed off — otherwise a down droplet gets ~2x the traffic
        the operator thinks they've throttled to."""
        _enable_relay()
        sender = PublicRelaySender()
        mock = _install_mock_client(sender)
        mock.post.return_value = httpx.Response(503, json={"detail": "down"})

        # Drive the sender into a backoff state.
        for _ in range(MAX_CONSECUTIVE_ERRORS + 1):
            _run(sender.maybe_upload(_snapshot(), _FakeDriver()))
        assert sender._effective_interval > 0
        calls_after_backoff = mock.post.call_count

        # One more broadcast — reading push should be gated (no new
        # call), and the identity push must also be gated (otherwise
        # it would still fire because the hash never advanced past the
        # first failed attempt).
        _run(sender.maybe_upload(_snapshot(), _FakeDriver()))
        assert mock.post.call_count == calls_after_backoff, (
            "Identity push fired despite reading-path backoff being "
            "active — see Codex round 1 on PR #340."
        )


# ---------------- Edge cases ----------------


class TestNoSnapshot:
    def test_none_snapshot_skips_reading_but_pushes_identity(self, clean_station_config):
        """First cycle after connect — driver may not have polled yet.
        Identity push should still fire so the droplet knows who the
        upstream station is before data starts flowing."""
        _enable_relay()
        sender = PublicRelaySender()
        mock = _install_mock_client(sender)
        _run(sender.maybe_upload(None, _FakeDriver()))
        # Exactly one call, and it must be the identity push.
        assert mock.post.call_count == 1
        assert mock.post.call_args_list[0].args[0].endswith("/api/ingest/config")
