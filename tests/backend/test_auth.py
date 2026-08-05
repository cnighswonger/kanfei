"""Tests for authentication service, dependencies, and API endpoints."""

import hashlib
import secrets
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from app.services.auth import (
    API_KEY_PREFIX,
    any_user_exists,
    change_password,
    cleanup_expired_sessions,
    create_api_key,
    create_session,
    create_user,
    generate_api_key,
    get_user_by_username,
    hash_password,
    list_api_keys,
    revoke_api_key,
    revoke_session,
    validate_api_key,
    validate_session,
    verify_password,
)
from app.models.auth import ApiKeyModel, SessionModel, UserModel
from app.models.database import Base, SessionLocal, engine


@pytest.fixture(autouse=True)
def _setup_db():
    """Create auth tables for each test, drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    db = SessionLocal()
    db.query(ApiKeyModel).delete()
    db.query(SessionModel).delete()
    db.query(UserModel).delete()
    db.commit()
    db.close()


@pytest.fixture
def db():
    db = SessionLocal()
    yield db
    db.close()


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:

    def test_hash_and_verify(self):
        hashed = hash_password("testpass123")
        assert hashed != "testpass123"
        assert verify_password("testpass123", hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("testpass123")
        assert not verify_password("wrongpass", hashed)

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # bcrypt uses random salt


# ---------------------------------------------------------------------------
# User operations
# ---------------------------------------------------------------------------

class TestUserOperations:

    def test_create_user(self, db):
        user = create_user(db, "admin", "password123")
        assert user.id is not None
        assert user.username == "admin"
        assert user.is_admin is True

    def test_get_user_by_username(self, db):
        create_user(db, "admin", "password123")
        user = get_user_by_username(db, "admin")
        assert user is not None
        assert user.username == "admin"

    def test_get_nonexistent_user(self, db):
        assert get_user_by_username(db, "nobody") is None

    def test_any_user_exists_false(self, db):
        assert any_user_exists(db) is False

    def test_any_user_exists_true(self, db):
        create_user(db, "admin", "password123")
        assert any_user_exists(db) is True

    def test_change_password(self, db):
        user = create_user(db, "admin", "oldpass123")
        change_password(db, user.id, "newpass456")
        updated = get_user_by_username(db, "admin")
        assert verify_password("newpass456", updated.password_hash)
        assert not verify_password("oldpass123", updated.password_hash)

    def test_duplicate_username_raises(self, db):
        create_user(db, "admin", "password123")
        with pytest.raises(Exception):
            create_user(db, "admin", "password456")


# ---------------------------------------------------------------------------
# Session operations
# ---------------------------------------------------------------------------

class TestSessionOperations:

    def test_create_and_validate_session(self, db):
        user = create_user(db, "admin", "password123")
        token = create_session(db, user.id)
        assert token is not None
        assert len(token) > 20

        validated = validate_session(db, token)
        assert validated is not None
        assert validated.id == user.id

    def test_invalid_token_returns_none(self, db):
        assert validate_session(db, "bogus_token") is None

    def test_expired_session_returns_none(self, db):
        user = create_user(db, "admin", "password123")
        token = create_session(db, user.id)
        # Manually expire the session
        session = db.query(SessionModel).filter_by(token=token).first()
        session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
        assert validate_session(db, token) is None

    def test_session_slides_expiry(self, db):
        user = create_user(db, "admin", "password123")
        token = create_session(db, user.id)
        session = db.query(SessionModel).filter_by(token=token).first()
        original_expiry = session.expires_at

        # Validate (should slide expiry)
        validate_session(db, token)
        db.refresh(session)
        assert session.expires_at >= original_expiry

    def test_revoke_session(self, db):
        user = create_user(db, "admin", "password123")
        token = create_session(db, user.id)
        assert revoke_session(db, token) is True
        assert validate_session(db, token) is None

    def test_revoke_nonexistent_session(self, db):
        assert revoke_session(db, "bogus") is False

    def test_cleanup_expired(self, db):
        user = create_user(db, "admin", "password123")
        token = create_session(db, user.id)
        # Expire it
        session = db.query(SessionModel).filter_by(token=token).first()
        session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
        count = cleanup_expired_sessions(db)
        assert count == 1


# ---------------------------------------------------------------------------
# API key operations
# ---------------------------------------------------------------------------

class TestApiKeyOperations:

    def test_generate_api_key_format(self):
        full, prefix, key_hash = generate_api_key()
        assert full.startswith(API_KEY_PREFIX)
        assert prefix == full[:8]
        assert key_hash == hashlib.sha256(full.encode()).hexdigest()

    def test_create_and_validate_api_key(self, db):
        user = create_user(db, "admin", "password123")
        full_key, model = create_api_key(db, user.id, "test key")
        assert model.label == "test key"
        assert model.prefix == full_key[:8]

        validated = validate_api_key(db, full_key)
        assert validated is not None
        assert validated.id == user.id

    def test_invalid_key_returns_none(self, db):
        assert validate_api_key(db, "knf_bogus_key_value") is None

    def test_revoked_key_returns_none(self, db):
        user = create_user(db, "admin", "password123")
        full_key, model = create_api_key(db, user.id)
        revoke_api_key(db, model.id, user.id)
        assert validate_api_key(db, full_key) is None

    def test_list_api_keys(self, db):
        user = create_user(db, "admin", "password123")
        create_api_key(db, user.id, "key1")
        create_api_key(db, user.id, "key2")
        keys = list_api_keys(db, user.id)
        assert len(keys) == 2

    def test_list_excludes_revoked(self, db):
        user = create_user(db, "admin", "password123")
        _, k1 = create_api_key(db, user.id, "keep")
        _, k2 = create_api_key(db, user.id, "revoke")
        revoke_api_key(db, k2.id, user.id)
        keys = list_api_keys(db, user.id)
        assert len(keys) == 1
        assert keys[0].label == "keep"

    def test_revoke_wrong_user(self, db):
        user1 = create_user(db, "admin1", "password123")
        user2 = create_user(db, "admin2", "password456")
        _, model = create_api_key(db, user1.id)
        assert revoke_api_key(db, model.id, user2.id) is False

    def test_validate_updates_last_used(self, db):
        user = create_user(db, "admin", "password123")
        full_key, model = create_api_key(db, user.id)
        assert model.last_used_at is None
        validate_api_key(db, full_key)
        db.refresh(model)
        assert model.last_used_at is not None


# ---------------------------------------------------------------------------
# Secret masking (config.py)
# ---------------------------------------------------------------------------

class TestSecretMasking:

    def test_mask_short_value(self):
        from app.api.config import _mask_value
        assert _mask_value("abc") == "***"

    def test_mask_empty_value(self):
        from app.api.config import _mask_value
        assert _mask_value("") == ""

    def test_mask_long_value(self):
        from app.api.config import _mask_value
        masked = _mask_value("sk-ant-api03-abcdefghijk")
        assert masked.startswith("sk-a")
        assert "***" in masked
        assert masked != "sk-ant-api03-abcdefghijk"

    def test_mask_preserves_prefix(self):
        from app.api.config import _mask_value
        masked = _mask_value("knf_xxxxxxxxxxxx")
        assert masked.startswith("knf_")


class TestConcurrentSessionValidation:
    """Two requests can hold the same session row at once.

    A page load fires several authenticated requests together.  Each gets
    its own SQLAlchemy Session but they resolve to the same row, so one can
    remove the row while another is mid-flight.

    The window is narrow and specific: `validate_session` re-queries, so a
    row deleted *before* its SELECT is handled correctly (returns None).
    The failure is a row deleted *between* that SELECT and the commit of
    the slide-expiry write — the UPDATE then matches zero rows and
    SQLAlchemy raises StaleDataError out of commit(), which leaves the
    request handler as an unhandled exception and 500s an ordinary page
    load (#275).

    Found while investigating intermittent failures in
    tests/e2e/login.spec.ts, but it is NOT their cause — fixing this did
    not change that spec's pass rate, and its failures show no server-side
    exception.  Recorded so the two are not conflated again.
    """

    def test_row_deleted_mid_validation_does_not_raise(self, db, monkeypatch):
        """The actual race, forced deterministically.

        The row is deleted after validate_session has loaded it and before
        it commits the slide-expiry write.  Patching _ensure_utc gives a
        hook at exactly that point without touching production code.
        """
        import app.services.auth as auth_mod

        user = create_user(db, f"race{secrets.token_hex(4)}", "testpass123")
        token = create_session(db, user.id)

        fired = {"done": False}
        real_ensure = auth_mod._ensure_utc

        def delete_then_ensure(dt):
            if not fired["done"]:
                fired["done"] = True
                other = SessionLocal()
                row = other.query(SessionModel).filter_by(token=token).first()
                if row is not None:
                    other.delete(row)
                    other.commit()
                other.close()
            return real_ensure(dt)

        monkeypatch.setattr(auth_mod, "_ensure_utc", delete_then_ensure)

        victim = SessionLocal()
        try:
            # Must report "no valid session", not raise.  Either answer is
            # correct for the caller; an exception is not.
            assert auth_mod.validate_session(victim, token) is None
        finally:
            victim.close()

        assert fired["done"], "the race was never triggered — test is inert"

    def test_a_row_deleted_before_the_query_is_still_handled(self, db):
        """The already-safe path, pinned so a fix does not regress it."""
        user = create_user(db, f"gone{secrets.token_hex(4)}", "testpass123")
        token = create_session(db, user.id)

        killer = SessionLocal()
        killer.delete(killer.query(SessionModel).filter_by(token=token).first())
        killer.commit()
        killer.close()

        victim = SessionLocal()
        try:
            assert validate_session(victim, token) is None
        finally:
            victim.close()

    def test_an_expired_session_is_still_deleted(self, db):
        """Expiry must keep working — the fix must not turn a real
        deletion into a silent no-op."""
        user = create_user(db, f"exp{secrets.token_hex(4)}", "testpass123")
        token = create_session(db, user.id)
        row = db.query(SessionModel).filter_by(token=token).first()
        row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()

        assert validate_session(db, token) is None
        db.expire_all()
        assert db.query(SessionModel).filter_by(token=token).first() is None

    def test_a_live_session_still_slides_its_expiry(self, db):
        """The happy path must keep updating last_active_at."""
        user = create_user(db, f"live{secrets.token_hex(4)}", "testpass123")
        token = create_session(db, user.id)
        row = db.query(SessionModel).filter_by(token=token).first()
        row.last_active_at = datetime.now(timezone.utc) - timedelta(hours=5)
        db.commit()
        before = row.last_active_at

        assert validate_session(db, token) is not None
        db.refresh(row)
        assert row.last_active_at > before
