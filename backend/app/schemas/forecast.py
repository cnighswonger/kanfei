"""Pydantic schemas for forecast API."""

from pydantic import BaseModel


class LocalForecast(BaseModel):
    source: str = "zambretti"
    text: str
    confidence: float
    trend: str | None = None
    updated: str


class NWSPeriod(BaseModel):
    name: str
    temperature: int | None = None
    wind: str | None = None
    precipitation_pct: int | None = None
    text: str
    icon_url: str | None = None
    short_forecast: str | None = None
    is_daytime: bool | None = None


class NWSForecast(BaseModel):
    source: str = "nws"
    periods: list[NWSPeriod]
    updated: str


class ForecastResponse(BaseModel):
    local: LocalForecast | None = None
    nws: NWSForecast | None = None
