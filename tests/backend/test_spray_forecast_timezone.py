"""fetch_hourly_forecast must request ``timezone=auto`` from Open-Meteo.

Regression pin for the 2026-08-23 spray-strip axis diagnosis:
without ``timezone=auto`` the API defaults to GMT and emits naked
ISO strings like ``"2026-08-24T01:00"`` with no zone marker.
ECMAScript's ``new Date(...)`` then parses those as browser-local,
so the axis renders UTC hours as if they were local hours — 4 hours
off in EDT, and off by the local UTC offset everywhere else.

The fix is a one-line addition to the request params.  This test
proves the param is present so a future edit to the URL builder
can't silently reopen the hole.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import spray_engine


@pytest.mark.asyncio
async def test_open_meteo_call_requests_local_timezone():
    """The ``timezone=auto`` param is what makes Open-Meteo return
    times in the location's local zone.  Anything else falls back
    to GMT, which is the shape that caused the axis to be 4 h off."""
    # Bust the module-level cache so this test drives a fresh call.
    spray_engine._forecast_cache["data"] = None
    spray_engine._forecast_cache["expires"] = 0

    captured_params: dict = {}

    class _StubResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"hourly": {"time": [], "temperature_2m": []}}

    class _StubClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, params):
            captured_params.update(params)
            return _StubResponse()

    with patch.object(spray_engine.httpx, "AsyncClient", return_value=_StubClient()):
        await spray_engine.fetch_hourly_forecast(35.38, -78.60, hours=24)

    assert captured_params.get("timezone") == "auto", (
        "Open-Meteo defaults to GMT without this param; the axis "
        "renders UTC as if it were local (v51 diagnosis)."
    )
