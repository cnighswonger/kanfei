"""Parametrized driver tests — one test framework for all hardware drivers.

Test fixtures are defined in driver_fixtures.json. Each fixture specifies:
- driver type
- raw input data (bytes, JSON, HTTP params)
- expected SI SensorSnapshot fields

Adding a new driver test is just adding a JSON entry. No new test code needed.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from app.protocol.base import SensorSnapshot

FIXTURES_PATH = Path(__file__).parent / "driver_fixtures.json"
FIXTURES = json.loads(FIXTURES_PATH.read_text())

# Remove the _comment key
FIXTURES.pop("_comment", None)


# ---------------------------------------------------------------------------
# Driver-specific parsers: raw fixture data → SensorSnapshot
# ---------------------------------------------------------------------------

def _run_ecowitt(fixture: dict) -> SensorSnapshot:
    """Feed raw marker dict through Ecowitt parser."""
    from app.protocol.ecowitt.sensors import raw_to_snapshot

    # Convert string hex keys back to int (JSON can't have int keys)
    raw = {int(k, 16): v for k, v in fixture["raw_markers"].items()}
    return raw_to_snapshot(raw)


def _run_tempest(fixture: dict) -> SensorSnapshot:
    """Feed raw obs_st array through Tempest parser."""
    from app.protocol.tempest.sensors import parse_obs_st, build_snapshot

    obs_data = parse_obs_st(fixture["raw_obs"])
    rain = fixture.get("rain_state", {})
    return build_snapshot(
        obs_data,
        rapid_wind=None,
        rain_daily_mm=rain.get("rain_daily_mm", 0.0),
        rain_yearly_mm=rain.get("rain_yearly_mm", 0.0),
        rain_rate_mm_hr=rain.get("rain_rate_mm_hr", 0.0),
        elevation_m=0.0,
    )


def _run_ambient(fixture: dict) -> SensorSnapshot:
    """Feed HTTP params through Ambient parser."""
    from app.protocol.ambient.sensors import parse_params

    return parse_params(fixture["params"])


def _run_weatherlink_live(fixture: dict) -> SensorSnapshot:
    """Feed JSON response through WeatherLink Live parser."""
    from app.protocol.weatherlink_live.sensors import parse_wll_response

    snapshot = parse_wll_response(fixture["raw_json"])
    assert snapshot is not None, "WLL parser returned None"
    return snapshot


_DRIVER_RUNNERS = {
    "ecowitt": _run_ecowitt,
    "tempest": _run_tempest,
    "ambient": _run_ambient,
    "weatherlink_live": _run_weatherlink_live,
}


# ---------------------------------------------------------------------------
# Parametrized test
# ---------------------------------------------------------------------------

def _fixture_ids():
    return list(FIXTURES.keys())


def _fixture_params():
    return list(FIXTURES.values())


@pytest.mark.parametrize(
    "fixture",
    _fixture_params(),
    ids=_fixture_ids(),
)
def test_driver_output_si(fixture: dict):
    """Run raw input through driver parser and verify SI output.

    Each expected field is checked with a tolerance of ±0.15 for floats
    (accounts for rounding in multi-step conversions) and exact match
    for integers.
    """
    driver = fixture["driver"]
    runner = _DRIVER_RUNNERS.get(driver)
    if runner is None:
        pytest.skip(f"No test runner for driver: {driver}")

    snapshot = runner(fixture)
    expected = fixture["expected"]

    for field, expected_val in expected.items():
        actual = getattr(snapshot, field, None)
        assert actual is not None, (
            f"{fixture['description']}: {field} is None, expected {expected_val}"
        )

        if isinstance(expected_val, float):
            assert abs(actual - expected_val) <= 0.15, (
                f"{fixture['description']}: {field} = {actual}, "
                f"expected {expected_val} (±0.15)"
            )
        elif isinstance(expected_val, int):
            # For int fields, allow float that rounds to the expected int
            if isinstance(actual, float):
                assert round(actual) == expected_val, (
                    f"{fixture['description']}: {field} = {actual}, "
                    f"expected {expected_val}"
                )
            else:
                assert actual == expected_val, (
                    f"{fixture['description']}: {field} = {actual}, "
                    f"expected {expected_val}"
                )


def test_all_fixtures_have_runners():
    """Every fixture must have a matching driver runner."""
    for name, fixture in FIXTURES.items():
        driver = fixture["driver"]
        assert driver in _DRIVER_RUNNERS, (
            f"Fixture '{name}' uses driver '{driver}' but no runner exists"
        )


def test_snapshot_fields_are_valid():
    """Every expected field must be a real SensorSnapshot attribute."""
    valid_fields = {f.name for f in SensorSnapshot.__dataclass_fields__.values()}
    for name, fixture in FIXTURES.items():
        for field in fixture["expected"]:
            assert field in valid_fields, (
                f"Fixture '{name}' expects '{field}' which is not a SensorSnapshot field"
            )
