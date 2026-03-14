"""Lightweight nowcast API endpoints.

Serves nowcast data from whatever service is active (local or remote)
via the module-level service reference. Does not import kanfei_nowcast —
works in remote mode without the package installed.

When the full kanfei-nowcast package is installed, the full nowcast.py
module is loaded instead (it has additional endpoints for radar images,
knowledge base, verifications, etc.).
"""

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.station_config import StationConfigModel
from ..services.nowcast import service_ref as _svc_ref
from ..services.alerts_nws import fetch_nws_active_alerts

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/nowcast")
def get_nowcast():
    """Return the latest nowcast, or null if none available."""
    if _svc_ref.nowcast_service is None:
        return None
    return _svc_ref.nowcast_service.get_latest()


@router.post("/nowcast/generate")
async def generate_now():
    """Trigger an immediate nowcast fetch and return the result."""
    if _svc_ref.nowcast_service is None:
        raise HTTPException(status_code=400, detail="Nowcast service not active")
    _svc_ref.nowcast_service.reload_config()
    if not _svc_ref.nowcast_service.is_enabled():
        raise HTTPException(status_code=400, detail="Nowcast is not enabled")
    try:
        await _svc_ref.nowcast_service.generate_once()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    result = _svc_ref.nowcast_service.get_latest()
    if result is None:
        raise HTTPException(status_code=500, detail="Generation produced no result")
    return result


@router.get("/nowcast/status")
def get_nowcast_status():
    """Return nowcast service status including auth errors."""
    svc = _svc_ref.nowcast_service
    if svc is None:
        return {"active": False, "error": None}
    auth_error = getattr(svc, "auth_error", None)
    return {
        "active": True,
        "enabled": svc.is_enabled(),
        "has_data": svc.get_latest() is not None,
        "error": auth_error,
    }


@router.get("/nowcast/presets")
def get_presets():
    """Return available quality presets for this customer's tier."""
    svc = _svc_ref.nowcast_service
    if svc is None:
        # No service — return all presets as available (local mode fallback)
        return {
            "tier": "local",
            "current_preset": "economy",
            "available": [
                {"id": "economy", "name": "Economy", "description": "Lowest cost. Haiku for routine, Sonnet during severe."},
                {"id": "standard", "name": "Standard", "description": "Good balance. Haiku for routine, Opus for warnings."},
                {"id": "premium", "name": "Premium", "description": "Best quality. Sonnet always, Opus during severe."},
            ],
        }
    presets = getattr(svc, "available_presets", None)
    if presets:
        return presets
    # Fallback — no presets fetched yet
    return {
        "tier": "unknown",
        "current_preset": "economy",
        "available": [
            {"id": "economy", "name": "Economy", "description": "Lowest cost. Haiku for routine, Sonnet during severe."},
            {"id": "standard", "name": "Standard", "description": "Good balance. Haiku for routine, Opus for warnings."},
            {"id": "premium", "name": "Premium", "description": "Best quality. Sonnet always, Opus during severe."},
        ],
    }


@router.get("/nowcast/alerts")
async def get_nws_alerts(db: Session = Depends(get_db)):
    """Return currently active NWS alerts for the station location."""
    rows = db.query(StationConfigModel).filter(
        StationConfigModel.key.in_(["latitude", "longitude"])
    ).all()
    cfg = {r.key: r.value for r in rows}

    try:
        lat = float(cfg.get("latitude", "0"))
        lon = float(cfg.get("longitude", "0"))
    except ValueError:
        lat, lon = 0.0, 0.0

    if lat == 0.0 and lon == 0.0:
        return {"alerts": [], "count": 0}

    result = await fetch_nws_active_alerts(lat, lon)
    if result is None:
        return {"alerts": [], "count": 0}
    return {"alerts": [asdict(a) for a in result.alerts], "count": result.count}
