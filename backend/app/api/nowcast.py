"""GET/PUT/POST /api/nowcast — AI nowcast endpoints."""

import base64
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.nowcast import NowcastHistory, NowcastKnowledge, NowcastRadarImage, NowcastVerification
from kanfei_nowcast import service as _nowcast_svc_mod
from ..services.nowcast_collector import get_cached_radar

router = APIRouter()


@router.get("/nowcast")
def get_nowcast(db: Session = Depends(get_db)):
    """Return the latest nowcast, or null if none available."""
    # Try in-memory cache first (fastest).
    cached = _nowcast_svc_mod.nowcast_service.get_latest()
    if cached is not None:
        return cached

    # Fall back to database.
    record = (
        db.query(NowcastHistory)
        .order_by(NowcastHistory.created_at.desc())
        .first()
    )
    if record is None:
        return None

    return _history_to_dict(record)


@router.post("/nowcast/generate")
async def generate_now():
    """Trigger an immediate nowcast generation and return the result."""
    _nowcast_svc_mod.nowcast_service.reload_config()
    if not _nowcast_svc_mod.nowcast_service.is_enabled():
        raise HTTPException(status_code=400, detail="Nowcast is not enabled")
    try:
        await _nowcast_svc_mod.nowcast_service.generate_once()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    result = _nowcast_svc_mod.nowcast_service.get_latest()
    if result is None:
        raise HTTPException(status_code=500, detail="Generation produced no result")
    return result


def _serve_radar(product_id: str, db: Session) -> Response:
    """Serve radar from in-memory cache, falling back to DB."""
    img = get_cached_radar(product_id)
    if img is not None:
        png_bytes = base64.b64decode(img.png_base64)
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=300"},
        )
    # DB fallback — latest standard image for this product.
    db_img = (
        db.query(NowcastRadarImage)
        .filter(
            NowcastRadarImage.product_id == product_id,
            NowcastRadarImage.image_type == "standard",
        )
        .order_by(NowcastRadarImage.created_at.desc())
        .first()
    )
    if db_img is None:
        raise HTTPException(status_code=404, detail=f"No radar image for '{product_id}'")
    png_bytes = base64.b64decode(db_img.png_base64)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/nowcast/radar")
def get_radar_image(db: Session = Depends(get_db)):
    """Return the NEXRAD composite reflectivity radar image as PNG binary."""
    return _serve_radar("nexrad_composite", db)


@router.get("/nowcast/radar/{product_id}")
def get_radar_product(product_id: str, db: Session = Depends(get_db)):
    """Return a radar image by product ID (e.g. nexrad_velocity)."""
    return _serve_radar(product_id, db)


@router.get("/nowcast/alerts")
async def get_nws_alerts(db: Session = Depends(get_db)):
    """Return currently active NWS alerts for the station location."""
    from ..models.station_config import StationConfigModel
    from ..services.alerts_nws import fetch_nws_active_alerts
    from dataclasses import asdict

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


@router.get("/nowcast/history")
def get_nowcast_history(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Return recent nowcasts, newest first."""
    records = (
        db.query(NowcastHistory)
        .order_by(NowcastHistory.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_history_to_dict(r) for r in records]


@router.get("/nowcast/knowledge")
def get_knowledge(
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """Return knowledge base entries, optionally filtered by status."""
    query = db.query(NowcastKnowledge).order_by(NowcastKnowledge.created_at.desc())
    if status:
        query = query.filter(NowcastKnowledge.status == status)
    entries = query.limit(100).all()
    return [_knowledge_to_dict(e) for e in entries]


class KnowledgeUpdate(BaseModel):
    status: str  # "accepted" or "rejected"


@router.put("/nowcast/knowledge/{entry_id}")
def update_knowledge(
    entry_id: int,
    update: KnowledgeUpdate,
    db: Session = Depends(get_db),
):
    """Approve or reject a knowledge base entry."""
    if update.status not in ("accepted", "rejected"):
        raise HTTPException(status_code=400, detail="Status must be 'accepted' or 'rejected'")

    entry = db.query(NowcastKnowledge).filter_by(id=entry_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")

    entry.status = update.status
    entry.reviewed_at = datetime.now(timezone.utc)
    db.commit()

    return _knowledge_to_dict(entry)


@router.get("/nowcast/verifications")
def get_verifications(
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """Return recent verification results, newest first."""
    records = (
        db.query(NowcastVerification)
        .order_by(NowcastVerification.verified_at.desc())
        .limit(limit)
        .all()
    )
    return [_verification_to_dict(r) for r in records]


def _verification_to_dict(record: NowcastVerification) -> dict:
    """Convert a NowcastVerification ORM object to an API response dict."""
    return {
        "id": record.id,
        "nowcast_id": record.nowcast_id,
        "verified_at": record.verified_at.isoformat() if record.verified_at else None,
        "element": record.element,
        "predicted": record.predicted,
        "actual": record.actual,
        "accuracy_score": record.accuracy_score,
        "notes": record.notes,
    }


def _history_to_dict(record: NowcastHistory) -> dict:
    """Convert a NowcastHistory ORM object to an API response dict."""
    try:
        elements = json.loads(record.details)
    except (json.JSONDecodeError, TypeError):
        elements = {}

    try:
        sources = json.loads(record.sources_used)
    except (json.JSONDecodeError, TypeError):
        sources = []

    # Extract top-level fields from raw_response (full Claude JSON output).
    farming_impact = None
    current_vs_model = ""
    data_quality = ""
    radar_analysis = None
    spray_advisory = None
    severe_weather = None
    if record.raw_response:
        try:
            raw_text = record.raw_response.strip()
            brace_start = raw_text.find("{")
            brace_end = raw_text.rfind("}")
            if brace_start != -1 and brace_end > brace_start:
                raw_text = raw_text[brace_start:brace_end + 1]
            raw = json.loads(raw_text)
            if isinstance(raw, dict):
                farming_impact = raw.get("farming_impact")
                current_vs_model = raw.get("current_vs_model", "")
                data_quality = raw.get("data_quality", "")
                radar_analysis = raw.get("radar_analysis")
                spray_advisory = raw.get("spray_advisory")
                severe_weather = raw.get("severe_weather")
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "id": record.id,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "valid_from": record.valid_from.isoformat() if record.valid_from else None,
        "valid_until": record.valid_until.isoformat() if record.valid_until else None,
        "model_used": record.model_used,
        "summary": record.summary,
        "elements": elements,
        "farming_impact": farming_impact,
        "current_vs_model": current_vs_model,
        "radar_analysis": radar_analysis,
        "spray_advisory": spray_advisory,
        "severe_weather": severe_weather,
        "data_quality": data_quality,
        "sources_used": sources,
        "input_tokens": record.input_tokens or 0,
        "output_tokens": record.output_tokens or 0,
    }


def _knowledge_to_dict(entry: NowcastKnowledge) -> dict:
    """Convert a NowcastKnowledge ORM object to an API response dict."""
    return {
        "id": entry.id,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "source": entry.source,
        "category": entry.category,
        "content": entry.content,
        "status": entry.status,
        "auto_accept_at": entry.auto_accept_at.isoformat() if entry.auto_accept_at else None,
        "reviewed_at": entry.reviewed_at.isoformat() if entry.reviewed_at else None,
        "recommendation": _knowledge_recommendation(entry),
    }


_AI_RECOMMENDATIONS: dict[str, str] = {
    "bias": (
        "Accept — the AI detected a systematic measurement bias at this "
        "station. Including this helps compensate in future forecasts."
    ),
    "timing": (
        "Accept — the AI noticed a recurring timing pattern for weather "
        "events at this location. Including this refines precipitation "
        "and temperature change timing."
    ),
    "terrain": (
        "Accept — the AI identified a terrain-influenced weather effect. "
        "Including this helps account for local geography in forecasts."
    ),
    "seasonal": (
        "Accept — the AI detected a seasonal pattern specific to this "
        "location. Including this improves forecasts during similar "
        "conditions."
    ),
}


def _knowledge_recommendation(entry: NowcastKnowledge) -> str:
    """Generate a contextual recommendation for a knowledge entry."""
    if entry.source == "verification":
        return (
            "Accept — this was identified from a verified prediction miss. "
            "Including this helps the AI learn from its errors and "
            "calibrate future forecasts."
        )
    if entry.source == "ai_proposed":
        return _AI_RECOMMENDATIONS.get(
            entry.category,
            "Accept if this matches your understanding of local weather "
            "patterns. The AI will use accepted entries to improve future "
            "forecasts.",
        )
    return (
        "Review and accept if this reflects accurate local knowledge. "
        "Accepted entries are included as context in future nowcasts."
    )
