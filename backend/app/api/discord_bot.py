"""POST /api/discord/test — Send a test message via the Discord bot."""

import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..config import settings
from .dependencies import require_admin

logger = logging.getLogger(__name__)

router = APIRouter()


class DiscordTestRequest(BaseModel):
    channel_id: str


def _get_discord_token() -> str:
    """Read the real Discord token from the DB (not the masked UI value)."""
    try:
        conn = sqlite3.connect(settings.db_path)
        cur = conn.execute(
            "SELECT value FROM station_config WHERE key = 'bot_discord_token'"
        )
        row = cur.fetchone()
        conn.close()
        return row[0] if row else ""
    except Exception:
        return ""


@router.post("/discord/test")
async def send_test_message(req: DiscordTestRequest, _admin=Depends(require_admin)):
    """Send a test message to verify Discord bot token and channel ID."""
    token = _get_discord_token()
    if not token or not req.channel_id:
        raise HTTPException(status_code=400, detail="Token and channel ID are required")

    try:
        import discord
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="discord.py is not installed",
        )

    try:
        intents = discord.Intents.default()
        client = discord.Client(intents=intents)

        result = {"ok": False, "message": ""}

        @client.event
        async def on_ready():
            try:
                channel = client.get_channel(int(req.channel_id))
                if channel is None:
                    channel = await client.fetch_channel(int(req.channel_id))
                await channel.send("\u2705 Kanfei weather bot connected successfully!")
                result["ok"] = True
                result["message"] = "Test message sent"
            except Exception as exc:
                detail = str(exc)
                if token in detail:
                    detail = detail.replace(token, "***")
                result["message"] = detail
            finally:
                await client.close()

        await client.start(token)

        if result["ok"]:
            return result
        raise HTTPException(status_code=400, detail=result["message"])

    except HTTPException:
        raise
    except Exception as exc:
        detail = str(exc)
        if token in detail:
            detail = detail.replace(token, "***")
        logger.warning("Discord test failed: %s", detail)
        raise HTTPException(status_code=400, detail=detail)
