"""Pydantic schemas for astronomy API."""

from pydantic import BaseModel


class TwilightTimes(BaseModel):
    dawn: str
    dusk: str


class SunData(BaseModel):
    sunrise: str
    sunset: str
    solar_noon: str
    day_length: str
    day_change: str
    civil_twilight: TwilightTimes
    nautical_twilight: TwilightTimes
    astronomical_twilight: TwilightTimes


class MoonData(BaseModel):
    phase: str
    illumination: float
    next_full: str
    next_new: str


class AstronomyResponse(BaseModel):
    sun: SunData
    moon: MoonData
