"""Pydantic schemas for configuration API."""

from pydantic import BaseModel


class ConfigItem(BaseModel):
    key: str
    value: str


class ConfigResponse(BaseModel):
    items: list[ConfigItem]


class StationStatusResponse(BaseModel):
    type_code: int
    type_name: str
    connected: bool
    link_revision: str
    poll_interval: int
    last_poll: str | None = None
    archive_records: int = 0
    uptime_seconds: int = 0
    crc_errors: int = 0
    timeouts: int = 0
