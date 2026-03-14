"""Pydantic schemas for WebSocket messages."""

from pydantic import BaseModel
from typing import Any


class WSMessage(BaseModel):
    type: str
    data: Any = None
