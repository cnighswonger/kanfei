"""Forecast blender service.

Merges the always-available Zambretti barometric forecast with the
optionally-available NWS grid forecast to produce a unified forecast
view with source attribution.
"""

from dataclasses import dataclass, field
from typing import Optional

from .forecast_local import ZambrettiResult
from .forecast_nws import NWSForecast, ForecastPeriod


@dataclass
class BlendedPeriod:
    """A single period in the blended forecast."""
    name: str
    text: str
    source: str  # "zambretti", "nws", or "blended"
    temperature: Optional[int] = None
    wind: Optional[str] = None
    precipitation_pct: Optional[int] = None


@dataclass
class BlendedForecast:
    """Combined forecast from all available sources."""
    periods: list[BlendedPeriod]
    zambretti_available: bool
    nws_available: bool
    summary: str


def _zambretti_period(zambretti: ZambrettiResult) -> BlendedPeriod:
    """Convert a Zambretti result into a BlendedPeriod for the current outlook."""
    confidence_pct = round(zambretti.confidence * 100)
    text = (
        f"{zambretti.forecast_text} "
        f"(barometric trend: {zambretti.trend}, "
        f"confidence: {confidence_pct}%)"
    )
    return BlendedPeriod(
        name="Local Barometric Outlook",
        text=text,
        source="zambretti",
    )


def _nws_period_to_blended(nws_period: ForecastPeriod) -> BlendedPeriod:
    """Convert an NWS ForecastPeriod into a BlendedPeriod."""
    return BlendedPeriod(
        name=nws_period.name,
        text=nws_period.text,
        source="nws",
        temperature=nws_period.temperature,
        wind=nws_period.wind if nws_period.wind else None,
        precipitation_pct=nws_period.precipitation_pct,
    )


def blend_forecasts(
    zambretti: ZambrettiResult,
    nws: Optional[NWSForecast] = None,
) -> BlendedForecast:
    """Merge Zambretti and NWS forecasts into a unified result.

    The Zambretti forecast is always included as the first period since
    it is derived from local sensor data and is always available.
    NWS periods, if available, follow and provide extended detail.

    When both sources are available, the summary combines them. When only
    Zambretti is available, the summary notes that the NWS forecast is
    unavailable.

    Args:
        zambretti: Local Zambretti barometric forecast (always available).
        nws: NWS grid forecast, or None if the API was unreachable.

    Returns:
        BlendedForecast with ordered periods and source labels.
    """
    periods: list[BlendedPeriod] = []

    # Always include the Zambretti local outlook first
    zambretti_bp = _zambretti_period(zambretti)
    periods.append(zambretti_bp)

    nws_available = nws is not None and len(nws.periods) > 0

    if nws_available:
        assert nws is not None  # type narrowing for mypy
        for nws_period in nws.periods:
            periods.append(_nws_period_to_blended(nws_period))

    # Build summary
    if nws_available:
        assert nws is not None
        nws_first = nws.periods[0]
        summary = (
            f"Local: {zambretti.forecast_text} | "
            f"NWS ({nws_first.name}): {nws_first.text[:120]}"
        )
        if len(nws_first.text) > 120:
            summary += "..."
    else:
        summary = (
            f"Local: {zambretti.forecast_text} "
            f"(NWS forecast unavailable)"
        )

    return BlendedForecast(
        periods=periods,
        zambretti_available=True,
        nws_available=nws_available,
        summary=summary,
    )
