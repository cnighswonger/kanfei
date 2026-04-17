"""POST /api/telegram/test — Send a test message via the Telegram bot."""

import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from ..config import settings
from .dependencies import require_admin

logger = logging.getLogger(__name__)

router = APIRouter()


class TelegramTestRequest(BaseModel):
    chat_id: str

    @field_validator("chat_id")
    @classmethod
    def chat_id_must_be_numeric(cls, v: str) -> str:
        v = v.strip()
        if not v.lstrip("-").isdigit():
            raise ValueError("chat_id must be a numeric string")
        return v


def _get_telegram_token() -> str:
    """Read the real Telegram token from the DB (not the masked UI value)."""
    try:
        conn = sqlite3.connect(settings.db_path)
        cur = conn.execute(
            "SELECT value FROM station_config WHERE key = 'bot_telegram_token'"
        )
        row = cur.fetchone()
        conn.close()
        return row[0] if row else ""
    except Exception:
        return ""


@router.post("/telegram/test")
async def send_test_message(req: TelegramTestRequest, _admin=Depends(require_admin)):
    """Send a test message to verify Telegram bot token and chat ID."""
    token = _get_telegram_token()
    if not token or not req.chat_id:
        raise HTTPException(status_code=400, detail="Token and chat ID are required")

    try:
        from telegram import Bot
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="python-telegram-bot is not installed",
        )

    try:
        bot = Bot(token=token)
        await bot.send_message(
            chat_id=int(req.chat_id),
            text="\u2705 Kanfei weather bot connected successfully!",
        )
        return {"ok": True, "message": "Test message sent"}
    except Exception as exc:
        detail = str(exc)
        if token in detail:
            detail = detail.replace(token, "***")
        logger.warning("Telegram test failed: %s", detail)
        raise HTTPException(status_code=400, detail=detail)
