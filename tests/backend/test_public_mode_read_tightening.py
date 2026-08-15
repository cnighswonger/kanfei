"""Public-droplet read-side gates — the tightening that landed after
the sys_admin red-team review on 2026-08-15.

## What this pins

**Critical finding.**  ``GET /api/db-admin/export/backup`` was reachable
by unauthenticated guests on a public droplet (via the
``require_admin`` public-mode bypass) and returned a full SQLite dump
of ``kanfei.db``, including the plaintext
``public_mode_ingest_secret`` — enough to impersonate the private
station's relay indefinitely.  This test asserts the guest is now
refused.

**Medium finding.**  ``GET /api/config`` returned the entire config
map to guests, including third-party account IDs (Discord guild,
Telegram chat, WU station ID, CWOP callsign, METAR station) and ops
metadata (``backup_*``, ``*_last_error``, ``nowcast_disclaimer_accepted``).
The read-only Settings UI doesn't render those; they're now filtered
out of the public-mode response by ``_PUBLIC_MODE_HIDDEN_KEYS``.
Authenticated admins still see everything.

## Endpoints covered

The following now use ``require_admin_read`` (no public-mode bypass):

- ``GET /api/db-admin/export/backup``  — critical
- ``GET /api/db-admin/export/json/{table}``
- ``GET /api/db-admin/stats``
- ``GET /api/backup/list``
- ``GET /api/backup/download/{name}``
- ``GET /api/logs``
- ``GET /api/auth/api-keys``

Each is tested here for guest-403/401 in public mode.

Issue #336 red-team follow-up.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.config import _PUBLIC_MODE_HIDDEN_KEYS
from app.main import app
from app.models.database import Base, SessionLocal, engine
from app.models.station_config import StationConfigModel
from app.services import public_mode


# ---- fixtures -----------------------------------------------------------


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


@pytest.fixture
def public_droplet(clean_station_config):
    """TestClient with public mode active (guest-side of the boundary)."""
    _set("station_driver_type", "public_relay")
    public_mode.invalidate_cache()
    with TestClient(app) as c:
        yield c


# ---- The critical finding ----------------------------------------------


class TestCriticalBackupDump:
    """The two-curl exploit chain in the red-team memo must not work
    anymore.  ``GET /api/db-admin/export/backup`` to an unauthenticated
    caller on a public droplet used to stream the whole DB — including
    the plaintext ingest bearer secret — because the masking in
    ``get_config`` doesn't extend to SQLite dumps."""

    def test_export_backup_refuses_guest_in_public_mode(self, public_droplet):
        resp = public_droplet.get("/api/db-admin/export/backup")
        # Before the fix: 200 + application/x-sqlite3 body.
        # After the fix: 401 (bootstrap bypass doesn't fire — no users
        # are seeded — but the require_admin_read dep has no public-
        # mode bypass either, so a guest is refused).
        assert resp.status_code in (401, 403), (
            f"CRITICAL: /api/db-admin/export/backup returned "
            f"{resp.status_code} to an unauthenticated guest on a "
            f"public droplet — the full SQLite dump including the "
            f"plaintext public_mode_ingest_secret is guest-readable. "
            f"Red-team finding #2, 2026-08-15."
        )


# ---- The full require_admin_read endpoint set --------------------------


ADMIN_READ_ENDPOINTS = [
    ("/api/db-admin/export/backup", None),
    ("/api/db-admin/stats", None),
    ("/api/db-admin/export/json/sensor_readings", None),
    ("/api/backup/list", None),
    ("/api/backup/download/some-backup.tar.gz", None),
    ("/api/logs", None),
    ("/api/auth/api-keys", None),
]


class TestAdminReadEndpointsRefuseGuests:
    """Every endpoint we moved to ``require_admin_read`` must refuse
    unauthenticated guests on a public droplet.

    Parametrised so a future endpoint added to the ``require_admin_read``
    set has a natural place to land its assertion.  The 401 vs 403
    difference is not the point — both indicate the guest didn't get
    through.  What matters is *not* 200.
    """

    @pytest.mark.parametrize("path,_", ADMIN_READ_ENDPOINTS)
    def test_guest_refused_in_public_mode(self, public_droplet, path, _):
        resp = public_droplet.get(path)
        assert resp.status_code in (401, 403), (
            f"{path} returned {resp.status_code} to an unauthenticated "
            f"guest on a public droplet — this endpoint should use "
            f"require_admin_read (no public-mode bypass) because its "
            f"response streams admin-only data.  Body: {resp.text[:200]!r}"
        )


# ---- /api/config hidden keys -------------------------------------------


class TestPublicModeConfigFilter:
    """``GET /api/config`` in public mode must drop the ops-metadata /
    third-party-ID keys enumerated in ``_PUBLIC_MODE_HIDDEN_KEYS``.
    A real admin (same endpoint, private station) still sees them.
    """

    def test_hidden_keys_absent_from_public_mode_response(self, public_droplet):
        # Seed a couple of hidden keys with observable values so a
        # regression (dropping the filter) would leak them into the
        # response.
        _set("bot_discord_guild_id", "123456789012345678")
        _set("wu_station_id", "KDCA1234")
        _set("backup_last_error", "disk full 2026-08-15")

        resp = public_droplet.get("/api/config")
        assert resp.status_code == 200, resp.text

        returned_keys = {item["key"] for item in resp.json()}
        leaked = returned_keys & _PUBLIC_MODE_HIDDEN_KEYS
        assert not leaked, (
            f"Public-mode GET /api/config leaked hidden keys: "
            f"{sorted(leaked)}.  These should be filtered by "
            f"_PUBLIC_MODE_HIDDEN_KEYS in app/api/config.py.  "
            f"Red-team finding #1, 2026-08-15."
        )

    def test_hidden_keys_present_for_admin_on_private_station(self, clean_station_config):
        """The filter is public-mode-only.  A real admin on a private
        station keeps the full view."""
        # NOT setting station_driver_type = public_relay.
        # No users seeded either → bootstrap bypass on require_admin.
        _set("bot_discord_guild_id", "123456789012345678")
        _set("wu_station_id", "KDCA1234")

        with TestClient(app) as c:
            resp = c.get("/api/config")
        assert resp.status_code == 200
        returned_keys = {item["key"] for item in resp.json()}
        # Bot IDs / WU ID present (admin sees them).
        assert "bot_discord_guild_id" in returned_keys
        assert "wu_station_id" in returned_keys

    def test_non_hidden_keys_still_present_in_public_mode(self, public_droplet):
        """Sanity: the filter only drops hidden keys.  The rest of the
        config (lat/lon, unit prefs, driver type, etc.) still renders
        so the read-only Settings UI has something to show."""
        resp = public_droplet.get("/api/config")
        assert resp.status_code == 200
        returned_keys = {item["key"] for item in resp.json()}
        # A representative sample the Settings UI actually renders.
        for key in ("latitude", "longitude", "elevation",
                    "station_driver_type", "temp_unit", "pressure_unit",
                    "wind_unit", "rain_unit", "ui_theme"):
            assert key in returned_keys, (
                f"Filter dropped {key!r} which the read-only Settings "
                f"UI needs.  Trim _PUBLIC_MODE_HIDDEN_KEYS."
            )


# ---- Public feature flags: still guest-readable -------------------------


class TestPublicFlagsUnchanged:
    """``/api/config/flags`` was and remains guest-readable in public
    mode.  Regression guard: don't accidentally tighten this one; the
    frontend consumes it to route based on ``public_mode_active``."""

    def test_flags_reachable_by_guest(self, public_droplet):
        resp = public_droplet.get("/api/config/flags")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("public_mode_active") is True
