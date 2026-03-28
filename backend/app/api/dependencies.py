"""FastAPI authentication dependencies."""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..models.auth import UserModel
from ..models.database import SessionLocal
from ..services.auth import any_user_exists, validate_api_key, validate_session


def _get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    request: Request,
    db: Session = Depends(_get_db),
) -> UserModel | None:
    """Extract user from session cookie or API key header.

    Returns None if unauthenticated.
    """
    # 1. Check session cookie.
    token = request.cookies.get("knf_session")
    if token:
        user = validate_session(db, token)
        if user:
            return user

    # 2. Check Authorization: Bearer header (API keys).
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        key = auth_header[7:]
        if key.startswith("knf_"):
            user = validate_api_key(db, key)
            if user:
                return user

    return None


def require_admin(
    request: Request,
    user: UserModel | None = Depends(get_current_user),
    db: Session = Depends(_get_db),
) -> UserModel:
    """Dependency for admin-only endpoints.

    Raises 401 if not authenticated, 403 if not admin.
    During initial setup (no users exist), all requests pass through
    so the setup wizard can create the first admin account.
    """
    # Bootstrap: if no users exist yet, allow unauthenticated access
    # so the setup wizard can run.
    if not any_user_exists(db):
        return None  # type: ignore[return-value]

    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def optional_auth(
    user: UserModel | None = Depends(get_current_user),
) -> UserModel | None:
    """For endpoints that behave differently for authed vs unauthed users."""
    return user
