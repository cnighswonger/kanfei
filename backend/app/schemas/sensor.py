"""Pydantic schemas for sensor data API responses."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ValueWithUnit(BaseModel):
    value: Optional[float] = None
    unit: str


class TemperatureData(BaseModel):
    inside: Optional[ValueWithUnit] = None
    outside: Optional[ValueWithUnit] = None


class HumidityData(BaseModel):
    inside: Optional[ValueWithUnit] = None
    outside: Optional[ValueWithUnit] = None


class WindData(BaseModel):
    speed: Optional[ValueWithUnit] = None
    direction: Optional[ValueWithUnit] = None
    cardinal: Optional[str] = None
    gust: Optional[ValueWithUnit] = None


class BarometerData(BaseModel):
    value: Optional[float] = None
    unit: str = "inHg"
    trend: Optional[str] = None
    trend_rate: Optional[float] = None


class RainData(BaseModel):
    daily: Optional[ValueWithUnit] = None
    yearly: Optional[ValueWithUnit] = None
    rate: Optional[ValueWithUnit] = None


class DerivedData(BaseModel):
    heat_index: Optional[ValueWithUnit] = None
    dew_point: Optional[ValueWithUnit] = None
    wind_chill: Optional[ValueWithUnit] = None
    feels_like: Optional[ValueWithUnit] = None
    theta_e: Optional[ValueWithUnit] = None


class CurrentConditionsResponse(BaseModel):
    timestamp: datetime
    station_type: str
    temperature: TemperatureData
    humidity: HumidityData
    wind: WindData
    barometer: BarometerData
    rain: RainData
    derived: DerivedData
    solar_radiation: Optional[ValueWithUnit] = None
    uv_index: Optional[ValueWithUnit] = None


class HistoryPoint(BaseModel):
    timestamp: datetime
    value: Optional[float] = None


class HistoryResponse(BaseModel):
    sensor: str
    unit: str
    start: datetime
    end: datetime
    resolution: str
    data: list[HistoryPoint]
