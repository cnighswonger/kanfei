"""API endpoints for usage and cost tracking.

Two tiers:
  - Local: aggregates token counts from nowcast_history (always available)
  - Anthropic Admin API: real USD costs (requires admin API key)
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.database import get_db
from .dependencies import require_admin
from ..models.station_config import StationConfigModel
from ..models.nowcast import NowcastHistory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/usage", tags=["usage"])

# --- Model pricing (per 1M tokens, USD) ---

MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
    "claude-opus-4-6": {"input": 5.00, "output": 25.00},
    # Grok (xAI)
    "grok-4-1-fast-reasoning": {"input": 3.00, "output": 15.00},
    "grok-3": {"input": 3.00, "output": 15.00},
    "grok-3-mini": {"input": 0.30, "output": 0.50},
    "grok-2": {"input": 2.00, "output": 10.00},
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "o3-mini": {"input": 1.10, "output": 4.40},
}

# Fallback for unknown models — use Haiku pricing as conservative default
_DEFAULT_PRICING = {"input": 1.00, "output": 5.00}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a given model and token counts."""
    pricing = MODEL_PRICING.get(model, _DEFAULT_PRICING)
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


def _get_config_value(db: Session, key: str, default: str = "") -> str:
    row = db.query(StationConfigModel).filter_by(key=key).first()
    return row.value if row else default


def _resolve_tz(db: Session):
    """Return the station timezone (ZoneInfo) or UTC as fallback."""
    tz_name = _get_config_value(db, "station_timezone", "")
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass
    return timezone.utc


def _local_boundaries(db: Session) -> tuple[datetime, datetime]:
    """Return (today_start, month_start) in UTC, aligned to station timezone."""
    tz = _resolve_tz(db)
    now_local = datetime.now(tz)
    today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    month_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    return today_start, month_start


def _resolve_admin_key(db: Session) -> str | None:
    """Check env var first, then DB config."""
    env_key = os.environ.get("ANTHROPIC_ADMIN_API_KEY")
    if env_key:
        return env_key
    db_key = _get_config_value(db, "anthropic_admin_api_key")
    return db_key if db_key else None


# --- Local usage ---

def _aggregate_period(db: Session, start: datetime | None = None, end: datetime | None = None) -> dict:
    """Aggregate token usage from nowcast_history for a time period."""
    query = db.query(
        func.count(NowcastHistory.id).label("calls"),
        func.coalesce(func.sum(NowcastHistory.input_tokens), 0).label("input_tokens"),
        func.coalesce(func.sum(NowcastHistory.output_tokens), 0).label("output_tokens"),
    )
    if start:
        query = query.filter(NowcastHistory.created_at >= start)
    if end:
        query = query.filter(NowcastHistory.created_at < end)

    row = query.one()
    calls = int(row.calls)
    input_tok = int(row.input_tokens)
    output_tok = int(row.output_tokens)

    # Estimate cost using per-model breakdown
    cost = 0.0
    if calls > 0:
        model_rows = db.query(
            NowcastHistory.model_used,
            func.coalesce(func.sum(NowcastHistory.input_tokens), 0),
            func.coalesce(func.sum(NowcastHistory.output_tokens), 0),
        )
        if start:
            model_rows = model_rows.filter(NowcastHistory.created_at >= start)
        if end:
            model_rows = model_rows.filter(NowcastHistory.created_at < end)
        model_rows = model_rows.group_by(NowcastHistory.model_used).all()

        for model, m_in, m_out in model_rows:
            cost += _estimate_cost(model, int(m_in), int(m_out))

    return {
        "calls": calls,
        "input_tokens": input_tok,
        "output_tokens": output_tok,
        "estimated_cost_usd": round(cost, 4),
    }


def _model_breakdown(db: Session, start: datetime | None = None, end: datetime | None = None) -> list[dict]:
    """Per-model token breakdown for a period."""
    query = db.query(
        NowcastHistory.model_used,
        func.count(NowcastHistory.id).label("calls"),
        func.coalesce(func.sum(NowcastHistory.input_tokens), 0).label("input_tokens"),
        func.coalesce(func.sum(NowcastHistory.output_tokens), 0).label("output_tokens"),
    )
    if start:
        query = query.filter(NowcastHistory.created_at >= start)
    if end:
        query = query.filter(NowcastHistory.created_at < end)

    rows = query.group_by(NowcastHistory.model_used).all()
    result = []
    for model, calls, input_tok, output_tok in rows:
        c, i, o = int(calls), int(input_tok), int(output_tok)
        result.append({
            "model": model,
            "calls": c,
            "input_tokens": i,
            "output_tokens": o,
            "estimated_cost_usd": round(_estimate_cost(model, i, o), 4),
        })
    return result


@router.get("/local")
def get_local_usage(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """Aggregate token usage from local nowcast_history."""
    today_start, month_start = _local_boundaries(db)

    return {
        "today": _aggregate_period(db, start=today_start),
        "this_month": _aggregate_period(db, start=month_start),
        "all_time": _aggregate_period(db),
        "model_breakdown": _model_breakdown(db, start=month_start),
    }


# --- Usage status ---

@router.get("/status")
def get_usage_status(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """Return which usage tiers are available and budget status."""
    admin_key = _resolve_admin_key(db)

    budget_str = _get_config_value(db, "usage_budget_monthly_usd", "0")
    try:
        budget_limit = float(budget_str)
    except ValueError:
        budget_limit = 0.0

    auto_pause = _get_config_value(db, "usage_budget_auto_pause", "false").lower() == "true"
    paused = _get_config_value(db, "usage_budget_paused", "false").lower() == "true"

    # Get current month cost estimate
    _, month_start = _local_boundaries(db)
    month_stats = _aggregate_period(db, start=month_start)

    return {
        "local": True,
        "anthropic": admin_key is not None,
        "budget": {
            "limit_usd": budget_limit,
            "current_usd": month_stats["estimated_cost_usd"],
            "paused": paused,
            "auto_pause": auto_pause,
        },
    }


# --- Anthropic Admin API proxy ---

ANTHROPIC_API_BASE = "https://api.anthropic.com/v1/organizations"


def _period_to_range(period: str, db: Session) -> tuple[str, str]:
    """Convert a period string to ISO datetime range."""
    now = datetime.now(timezone.utc)
    if period == "today":
        today_start, _ = _local_boundaries(db)
        start = today_start
    elif period == "7d":
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "30d":
        start = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        _, month_start = _local_boundaries(db)
        start = month_start

    return start.strftime("%Y-%m-%dT%H:%M:%SZ"), now.strftime("%Y-%m-%dT%H:%M:%SZ")


@router.get("/anthropic")
async def get_anthropic_usage(period: str = "7d", db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """Proxy to Anthropic Usage API for token-level data."""
    admin_key = _resolve_admin_key(db)
    if not admin_key:
        return {"error": "No Admin API key configured", "data": []}

    starting_at, ending_at = _period_to_range(period, db)
    bucket_width = "1d" if period != "today" else "1h"

    params = {
        "starting_at": starting_at,
        "ending_at": ending_at,
        "bucket_width": bucket_width,
        "group_by[]": "model",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{ANTHROPIC_API_BASE}/usage_report/messages",
                params=params,
                headers={
                    "x-api-key": admin_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("Anthropic Usage API error: %s %s", e.response.status_code, e.response.text[:200])
        return {"error": f"Anthropic API returned {e.response.status_code}", "data": []}
    except Exception as e:
        logger.error("Anthropic Usage API request failed: %s", e)
        return {"error": str(e), "data": []}


@router.get("/anthropic/cost")
async def get_anthropic_cost(period: str = "30d", db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """Proxy to Anthropic Cost API for USD cost data."""
    admin_key = _resolve_admin_key(db)
    if not admin_key:
        return {"error": "No Admin API key configured", "data": []}

    starting_at, ending_at = _period_to_range(period, db)

    params = {
        "starting_at": starting_at,
        "ending_at": ending_at,
        "bucket_width": "1d",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{ANTHROPIC_API_BASE}/cost_report",
                params=params,
                headers={
                    "x-api-key": admin_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("Anthropic Cost API error: %s %s", e.response.status_code, e.response.text[:200])
        return {"error": f"Anthropic API returned {e.response.status_code}", "data": []}
    except Exception as e:
        logger.error("Anthropic Cost API request failed: %s", e)
        return {"error": str(e), "data": []}


# --- Budget check (called from nowcast service) ---

def check_budget(db: Session) -> bool:
    """Check if monthly budget is exceeded. Returns True if over budget.

    If auto_pause is enabled, sets nowcast_enabled=false and usage_budget_paused=true.
    """
    budget_str = _get_config_value(db, "usage_budget_monthly_usd", "0")
    try:
        budget_limit = float(budget_str)
    except ValueError:
        return False

    if budget_limit <= 0:
        return False

    auto_pause = _get_config_value(db, "usage_budget_auto_pause", "false").lower() == "true"

    _, month_start = _local_boundaries(db)
    month_stats = _aggregate_period(db, start=month_start)
    current_cost = month_stats["estimated_cost_usd"]

    if current_cost >= budget_limit:
        logger.warning(
            "Monthly usage budget exceeded: $%.2f used of $%.2f limit",
            current_cost, budget_limit,
        )
        if auto_pause:
            # Set nowcast_enabled to false
            for key, val in [("nowcast_enabled", "false"), ("usage_budget_paused", "true")]:
                row = db.query(StationConfigModel).filter_by(key=key).first()
                if row:
                    row.value = val
                else:
                    db.add(StationConfigModel(key=key, value=val))
            db.commit()
            logger.warning("Nowcast auto-paused due to budget limit")
        return True

    return False
