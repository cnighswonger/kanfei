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
