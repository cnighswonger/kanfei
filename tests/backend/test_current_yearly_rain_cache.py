"""Cache for the yearly-rain query on /api/current.

Pins the invariants of ``_cached_yearly_rain`` in ``app/api/current.py``:
same (reading, day, source_mode, season_month) returns the cached
value; a new reading, day boundary, source_mode, or season_month
recomputes; ``None`` reading never touches the cache. The
performance win depends on all four invalidation axes.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.api import current as current_module
from app.api.current import _cached_yearly_rain


@pytest.fixture(autouse=True)
def reset_cache():
    current_module._yearly_rain_cache.update({"key": None, "result": None})
    yield


class _Db:
    """Stand-in for a Session — the cache never actually touches it."""


def _mk_result(value: int) -> dict:
    return {"value": value, "source": "console"}


def test_second_call_with_same_reading_skips_recomputation():
    reading_ts = datetime(2026, 8, 25, 20, 0, 0, tzinfo=timezone.utc)
    result = _mk_result(1234)
    with patch.object(current_module, "compute_yearly_rain", return_value=result) as fn:
        r1 = _cached_yearly_rain(_Db(), reading_ts, 1234, "auto", None)
        r2 = _cached_yearly_rain(_Db(), reading_ts, 1234, "auto", None)
    assert r1 == result
    assert r2 == result
    assert fn.call_count == 1


def test_new_reading_recomputes():
    r1_ts = datetime(2026, 8, 25, 20, 0, 0, tzinfo=timezone.utc)
    r2_ts = r1_ts + timedelta(seconds=10)
    with patch.object(current_module, "compute_yearly_rain",
                      side_effect=[_mk_result(1000), _mk_result(1010)]) as fn:
        _cached_yearly_rain(_Db(), r1_ts, 1000, "auto", None)
        second = _cached_yearly_rain(_Db(), r2_ts, 1010, "auto", None)
    assert second["value"] == 1010
    assert fn.call_count == 2


def test_source_mode_change_recomputes():
    """A change in rain_yearly_source (auto → console → archive) MUST
    invalidate: the result shape depends on which branch runs."""
    reading_ts = datetime(2026, 8, 25, 20, 0, 0, tzinfo=timezone.utc)
    with patch.object(current_module, "compute_yearly_rain",
                      side_effect=[_mk_result(1000), {"value": 999, "source": "archive"}]) as fn:
        first = _cached_yearly_rain(_Db(), reading_ts, 1000, "auto", None)
        second = _cached_yearly_rain(_Db(), reading_ts, 1000, "archive", None)
    assert first["source"] == "console"
    assert second["source"] == "archive"
    assert fn.call_count == 2


def test_season_month_change_recomputes():
    reading_ts = datetime(2026, 8, 25, 20, 0, 0, tzinfo=timezone.utc)
    with patch.object(current_module, "compute_yearly_rain",
                      side_effect=[_mk_result(100), _mk_result(200)]) as fn:
        _cached_yearly_rain(_Db(), reading_ts, 100, "auto", None)
        _cached_yearly_rain(_Db(), reading_ts, 100, "auto", 7)
    assert fn.call_count == 2


def test_day_boundary_invalidates_cache_even_when_reading_unchanged():
    """A stalled logger across local midnight must not freeze the cache
    on yesterday's 30-day reset-detection window."""
    reading_ts = datetime(2026, 8, 25, 20, 0, 0, tzinfo=timezone.utc)
    day_a = datetime(2026, 8, 25, 4, 0, 0, tzinfo=timezone.utc)
    day_b = datetime(2026, 8, 26, 4, 0, 0, tzinfo=timezone.utc)
    with patch.object(current_module, "compute_yearly_rain",
                      side_effect=[_mk_result(1), _mk_result(2)]) as fn, \
         patch.object(current_module, "_reset_lookback_day_start",
                      side_effect=[day_a, day_b]):
        first = _cached_yearly_rain(_Db(), reading_ts, 100, "auto", None)
        second = _cached_yearly_rain(_Db(), reading_ts, 100, "auto", None)
    assert first["value"] == 1
    assert second["value"] == 2
    assert fn.call_count == 2


def test_none_reading_never_hits_or_writes_cache():
    """A None reading timestamp means no anchor — recompute and skip
    the cache both ways (matches the extremes helper's shape)."""
    with patch.object(current_module, "compute_yearly_rain",
                      return_value=_mk_result(1)) as fn:
        _cached_yearly_rain(_Db(), None, None, "auto", None)
        _cached_yearly_rain(_Db(), None, None, "auto", None)
    assert fn.call_count == 2
    assert current_module._yearly_rain_cache["key"] is None
