"""POST /api/discord/test — Send a test message via the Discord bot."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class DiscordTestRequest(BaseModel):
    token: str
    channel_id: str


@router.post("/discord/test")
async def send_test_message(req: DiscordTestRequest):
    """Send a test message to verify Discord bot token and channel ID."""
    if not req.token or not req.channel_id:
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
                if req.token in detail:
                    detail = detail.replace(req.token, "***")
                result["message"] = detail
            finally:
                await client.close()

        await client.start(req.token)

        if result["ok"]:
            return result
        raise HTTPException(status_code=400, detail=result["message"])

    except HTTPException:
        raise
    except Exception as exc:
        detail = str(exc)
        if req.token in detail:
            detail = detail.replace(req.token, "***")
        logger.warning("Discord test failed: %s", detail)
        raise HTTPException(status_code=400, detail=detail)
