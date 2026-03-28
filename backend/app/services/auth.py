"""Authentication service — password hashing, sessions, API keys."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from sqlalchemy.orm import Session

from ..models.auth import ApiKeyModel, SessionModel, UserModel

# Session lifetime: 72 hours of inactivity.
SESSION_MAX_AGE_HOURS = 72

# API key prefix for easy identification.
API_KEY_PREFIX = "knf_"


# ---------------------------------------------------------------------------
# Password operations
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# User operations
# ---------------------------------------------------------------------------

def create_user(db: Session, username: str, password: str) -> UserModel:
    user = UserModel(username=username, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_username(db: Session, username: str) -> Optional[UserModel]:
    return db.query(UserModel).filter_by(username=username).first()


def any_user_exists(db: Session) -> bool:
    return db.query(UserModel).first() is not None


def change_password(db: Session, user_id: int, new_password: str) -> None:
    user = db.query(UserModel).filter_by(id=user_id).first()
    if user:
        user.password_hash = hash_password(new_password)
        db.commit()


# ---------------------------------------------------------------------------
# Session operations
# ---------------------------------------------------------------------------

def create_session(db: Session, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    session = SessionModel(
        user_id=user_id,
        token=token,
        expires_at=now + timedelta(hours=SESSION_MAX_AGE_HOURS),
        last_active_at=now,
    )
    db.add(session)
    db.commit()
    return token


def _ensure_utc(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (UTC). SQLite returns naive datetimes."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def validate_session(db: Session, token: str) -> Optional[UserModel]:
    session = db.query(SessionModel).filter_by(token=token).first()
    if session is None:
        return None
    now = datetime.now(timezone.utc)
    if now > _ensure_utc(session.expires_at):
        db.delete(session)
        db.commit()
        return None
    # Slide expiry on activity.
    session.last_active_at = now
    session.expires_at = now + timedelta(hours=SESSION_MAX_AGE_HOURS)
    db.commit()
    user = db.query(UserModel).filter_by(id=session.user_id).first()
    return user


def revoke_session(db: Session, token: str) -> bool:
    session = db.query(SessionModel).filter_by(token=token).first()
    if session:
        db.delete(session)
        db.commit()
        return True
    return False


def cleanup_expired_sessions(db: Session) -> int:
    now = datetime.now(timezone.utc)
    count = db.query(SessionModel).filter(SessionModel.expires_at < now).delete()
    db.commit()
    return count


# ---------------------------------------------------------------------------
# API key operations
# ---------------------------------------------------------------------------

def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns (full_key, prefix, sha256_hash).
    The full key is shown once at creation time, never stored.
    """
    raw = secrets.token_urlsafe(32)
    full_key = f"{API_KEY_PREFIX}{raw}"
    prefix = full_key[:8]
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, prefix, key_hash


def create_api_key(db: Session, user_id: int, label: str = "") -> tuple[str, ApiKeyModel]:
    """Create and store a new API key. Returns (full_key, model)."""
    full_key, prefix, key_hash = generate_api_key()
    key = ApiKeyModel(
        user_id=user_id,
        prefix=prefix,
        key_hash=key_hash,
        label=label,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return full_key, key


def validate_api_key(db: Session, key_str: str) -> Optional[UserModel]:
    key_hash = hashlib.sha256(key_str.encode()).hexdigest()
    api_key = (
        db.query(ApiKeyModel)
        .filter_by(key_hash=key_hash, revoked=False)
        .first()
    )
    if api_key is None:
        return None
    api_key.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return db.query(UserModel).filter_by(id=api_key.user_id).first()


def list_api_keys(db: Session, user_id: int) -> list[ApiKeyModel]:
    return (
        db.query(ApiKeyModel)
        .filter_by(user_id=user_id, revoked=False)
        .order_by(ApiKeyModel.created_at.desc())
        .all()
    )


def revoke_api_key(db: Session, key_id: int, user_id: int) -> bool:
    key = db.query(ApiKeyModel).filter_by(id=key_id, user_id=user_id).first()
    if key:
        key.revoked = True
        db.commit()
        return True
    return False
