"""FastAPI authentication dependencies."""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..models.auth import UserModel
from ..models.database import SessionLocal
from ..services.auth import any_user_exists, validate_api_key, validate_session
from ..services.public_mode import is_public_mode


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
    # Public droplet: guest reads admin-only GETs so the read-only
    # Settings UI has data to render.  Writes are still blocked at the
    # middleware layer (see ``public_mode_write_block`` in
    # ``app/main.py``); a bypass here only widens the read surface.
    # Issue #336.
    if is_public_mode():
        return None  # type: ignore[return-value]

    # Bootstrap: if no users exist yet, allow unauthenticated access
    # so the setup wizard can run.
    if not any_user_exists(db):
        return None  # type: ignore[return-value]

    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_admin_read(
    request: Request,
    user: UserModel | None = Depends(get_current_user),
    db: Session = Depends(_get_db),
) -> UserModel:
    """Strict admin-only for endpoints that return secret-bearing or
    bulk-DB data.

    Same shape as ``require_admin`` **without** the public-mode bypass:
    an unauthenticated guest on a public droplet is refused (401)
    rather than allowed through.  Use this on any admin GET whose
    response contains information the operator was trusted with
    privately — SQLite dumps, backup archives, secret prefixes, log
    streams.

    The bootstrap bypass (no users exist yet) is preserved so the
    setup wizard's initial flow still works.

    Issue #336 red-team follow-up (2026-08-15): the public-mode
    ``require_admin`` bypass was fine for state-mutation gating
    (writes still 403 at the middleware layer) but wrong for the
    class of GETs that stream data the admin was trusted with.
    Specifically, ``GET /api/db-admin/export/backup`` returned the
    full SQLite dump — including the plaintext
    ``public_mode_ingest_secret`` — to any unauthenticated caller.
    """
    # Bootstrap: if no users exist yet, allow the setup wizard
    # through — BUT ONLY on a private station.  A public droplet
    # never has an admin (its wizard skips the account step by
    # design), so ``any_user_exists`` returns False forever.  Without
    # the ``and not is_public_mode()`` guard, this bypass would
    # exactly re-open the read surface we're trying to close.
    if not any_user_exists(db) and not is_public_mode():
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
