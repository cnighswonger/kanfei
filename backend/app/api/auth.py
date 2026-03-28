"""Authentication API — login, logout, session management, API keys."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.auth import UserModel
from ..services.auth import (
    any_user_exists,
    change_password,
    create_api_key,
    create_session,
    create_user,
    get_user_by_username,
    list_api_keys,
    revoke_api_key,
    revoke_session,
    verify_password,
)
from .dependencies import _get_db, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Session cookie settings.
_COOKIE_NAME = "knf_session"
_COOKIE_MAX_AGE = 72 * 3600  # 72 hours


def _is_https(request: Request) -> bool:
    """Detect if the request arrived over HTTPS (direct or via reverse proxy)."""
    if request.url.scheme == "https":
        return True
    # Trust X-Forwarded-Proto from reverse proxy.
    return request.headers.get("x-forwarded-proto", "").lower() == "https"


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class CreateApiKeyRequest(BaseModel):
    label: str = ""


class CreateAdminRequest(BaseModel):
    username: str
    password: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/login")
async def login(req: LoginRequest, request: Request, response: Response, db: Session = Depends(_get_db)):
    """Authenticate and create a session."""
    user = get_user_by_username(db, req.username)
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_session(db, user.id)
    secure = _is_https(request)
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    logger.info("User %s logged in (secure=%s)", user.username, secure)
    return {"username": user.username, "is_admin": user.is_admin}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: Session = Depends(_get_db),
    _admin: UserModel = Depends(require_admin),
):
    """Invalidate the current session (server-side and cookie)."""
    token = request.cookies.get(_COOKIE_NAME)
    if token:
        revoke_session(db, token)
    response.delete_cookie(_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
async def get_current_user_info(
    _admin: UserModel = Depends(require_admin),
):
    """Return current authenticated user info."""
    if _admin is None:
        # Bootstrap mode — no users exist.
        return {"authenticated": False, "setup_required": True}
    return {
        "authenticated": True,
        "username": _admin.username,
        "is_admin": _admin.is_admin,
    }


@router.post("/change-password")
async def change_password_endpoint(
    req: ChangePasswordRequest,
    db: Session = Depends(_get_db),
    _admin: UserModel = Depends(require_admin),
):
    """Change the current user's password."""
    if _admin is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not verify_password(req.current_password, _admin.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    change_password(db, _admin.id, req.new_password)
    logger.info("User %s changed password", _admin.username)
    return {"ok": True}


@router.post("/api-keys")
async def create_api_key_endpoint(
    req: CreateApiKeyRequest,
    db: Session = Depends(_get_db),
    _admin: UserModel = Depends(require_admin),
):
    """Create a new API key. The full key is returned once and never stored."""
    if _admin is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    full_key, key_model = create_api_key(db, _admin.id, req.label)
    logger.info("API key created: %s (%s)", key_model.prefix, req.label or "no label")
    return {
        "key": full_key,
        "prefix": key_model.prefix,
        "label": key_model.label,
        "id": key_model.id,
        "created_at": key_model.created_at.isoformat() if key_model.created_at else None,
    }


@router.get("/api-keys")
async def list_api_keys_endpoint(
    db: Session = Depends(_get_db),
    _admin: UserModel = Depends(require_admin),
):
    """List API keys (prefix + label only, never the full key)."""
    if _admin is None:
        return []
    keys = list_api_keys(db, _admin.id)
    return [
        {
            "id": k.id,
            "prefix": k.prefix,
            "label": k.label,
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        }
        for k in keys
    ]


@router.delete("/api-keys/{key_id}")
async def revoke_api_key_endpoint(
    key_id: int,
    db: Session = Depends(_get_db),
    _admin: UserModel = Depends(require_admin),
):
    """Revoke an API key."""
    if _admin is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not revoke_api_key(db, key_id, _admin.id):
        raise HTTPException(status_code=404, detail="API key not found")
    logger.info("API key %d revoked", key_id)
    return {"ok": True}


@router.post("/setup-admin")
async def setup_admin(
    req: CreateAdminRequest,
    db: Session = Depends(_get_db),
):
    """Create the first admin account. Only works when no users exist."""
    if any_user_exists(db):
        raise HTTPException(status_code=400, detail="Admin account already exists")
    if len(req.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    user = create_user(db, req.username, req.password)
    logger.info("First admin account created: %s", user.username)
    return {"ok": True, "username": user.username}
