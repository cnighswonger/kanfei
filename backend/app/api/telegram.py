"""POST /api/telegram/test — Send a test message via the Telegram bot."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .dependencies import require_admin

logger = logging.getLogger(__name__)

router = APIRouter()


class TelegramTestRequest(BaseModel):
    token: str
    chat_id: str


@router.post("/telegram/test")
async def send_test_message(req: TelegramTestRequest, _admin=Depends(require_admin)):
    """Send a test message to verify Telegram bot token and chat ID."""
    if not req.token or not req.chat_id:
        raise HTTPException(status_code=400, detail="Token and chat ID are required")

    try:
        from telegram import Bot
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="python-telegram-bot is not installed",
        )

    try:
        bot = Bot(token=req.token)
        await bot.send_message(
            chat_id=int(req.chat_id),
            text="\u2705 Kanfei weather bot connected successfully!",
        )
        return {"ok": True, "message": "Test message sent"}
    except Exception as exc:
        detail = str(exc)
        # Avoid leaking the token in error messages
        if req.token in detail:
            detail = detail.replace(req.token, "***")
        logger.warning("Telegram test failed: %s", detail)
        raise HTTPException(status_code=400, detail=detail)
