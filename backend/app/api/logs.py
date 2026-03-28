"""GET /api/logs — recent WARNING+ log entries from the in-memory ring buffer."""

from fastapi import APIRouter, Depends, Query

from ..services.log_buffer import log_buffer
from .dependencies import require_admin

router = APIRouter(tags=["logs"])


@router.get("/logs")
async def get_logs(
    level: str = Query("WARNING", description="Minimum log level"),
    limit: int = Query(100, ge=1, le=1000, description="Max entries to return"),
    _admin=Depends(require_admin),
):
    return log_buffer.get_entries(level=level, limit=limit)
