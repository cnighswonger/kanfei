"""Cache for the two expensive period-extremes queries on /api/current.

Pins the invariants of ``_cached_period_extremes`` in
``app/api/current.py``: same key returns the cached value, a new
reading recomputes and updates, ``None`` key never touches the cache,
and a wall-clock crossing of the local month/year boundary forces a
recompute even when the latest reading has not advanced. The
performance win depends on all three, and the boundary case is what a
stalled logger looks like.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.api import current as current_module
from app.api.current import _cached_period_extremes


@pytest.fixture(autouse=True)
def reset_cache():
    """The cache is module-global; wipe it between tests."""
    current_module._extremes_cache.update({"key": None, "monthly": None, "yearly": None})
    yield


class _Db:
    """Stand-in for a Session — the cache never actually touches it."""


def test_second_call_with_same_reading_skips_recomputation():
    reading_ts = datetime(2026, 8, 25, 20, 0, 0, tzinfo=timezone.utc)
    monthly = {"outside_temp_hi": 90}
    yearly = {"outside_temp_hi": 100}
    with patch.object(current_module, "get_month_extremes", return_value=monthly) as m, \
         patch.object(current_module, "get_year_extremes", return_value=yearly) as y:
        m1, y1 = _cached_period_extremes(_Db(), reading_ts)
        m2, y2 = _cached_period_extremes(_Db(), reading_ts)
    assert (m1, y1) == (monthly, yearly)
    assert (m2, y2) == (monthly, yearly)
    assert m.call_count == 1
    assert y.call_count == 1


def test_new_reading_recomputes_and_updates_cache():
    r1 = datetime(2026, 8, 25, 20, 0, 0, tzinfo=timezone.utc)
    r2 = r1 + timedelta(seconds=10)
    with patch.object(current_module, "get_month_extremes", side_effect=[{"a": 1}, {"a": 2}]) as m, \
         patch.object(current_module, "get_year_extremes", side_effect=[{"b": 1}, {"b": 2}]) as y:
        _cached_period_extremes(_Db(), r1)
        m2, y2 = _cached_period_extremes(_Db(), r2)
    assert (m2, y2) == ({"a": 2}, {"b": 2})
    assert m.call_count == 2
    assert y.call_count == 2


def test_none_reading_never_hits_or_writes_cache():
    """A None reading timestamp means no latest-reading anchor, so the
    cache must neither be read from nor written to (writing a None key
    would poison the next real request that also happens to see no
    reading)."""
    with patch.object(current_module, "get_month_extremes", return_value={"x": 1}) as m, \
         patch.object(current_module, "get_year_extremes", return_value={"y": 1}) as y:
        _cached_period_extremes(_Db(), None)
        _cached_period_extremes(_Db(), None)
    assert m.call_count == 2
    assert y.call_count == 2
    assert current_module._extremes_cache["key"] is None


def test_month_boundary_invalidates_cache_even_when_reading_unchanged():
    """A stalled logger across local midnight on the 1st must not
    freeze the cache on the previous month's window. Simulates the
    boundary by moving the window-starts helper forward while keeping
    the reading timestamp constant."""
    reading_ts = datetime(2026, 8, 25, 20, 0, 0, tzinfo=timezone.utc)
    before_month = (
        datetime(2026, 8, 1, 4, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 5, 0, 0, tzinfo=timezone.utc),
    )
    after_month = (
        datetime(2026, 9, 1, 4, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 5, 0, 0, tzinfo=timezone.utc),
    )
    with patch.object(current_module, "get_month_extremes", side_effect=[{"m": "aug"}, {"m": "sep"}]) as m, \
         patch.object(current_module, "get_year_extremes", side_effect=[{"y": 1}, {"y": 1}]) as y, \
         patch.object(current_module, "_period_window_starts", side_effect=[before_month, after_month]):
        first_m, _ = _cached_period_extremes(_Db(), reading_ts)
        second_m, _ = _cached_period_extremes(_Db(), reading_ts)
    assert first_m == {"m": "aug"}
    assert second_m == {"m": "sep"}
    assert m.call_count == 2
    assert y.call_count == 2


def test_year_boundary_invalidates_cache_even_when_reading_unchanged():
    """Same as the month test, for the year window."""
    reading_ts = datetime(2026, 12, 31, 23, 59, 0, tzinfo=timezone.utc)
    before_year = (
        datetime(2026, 12, 1, 5, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 5, 0, 0, tzinfo=timezone.utc),
    )
    after_year = (
        datetime(2027, 1, 1, 5, 0, 0, tzinfo=timezone.utc),
        datetime(2027, 1, 1, 5, 0, 0, tzinfo=timezone.utc),
    )
    with patch.object(current_module, "get_month_extremes", side_effect=[{"m": 1}, {"m": 2}]) as _m, \
         patch.object(current_module, "get_year_extremes", side_effect=[{"y": 2026}, {"y": 2027}]) as y, \
         patch.object(current_module, "_period_window_starts", side_effect=[before_year, after_year]):
        _, first_y = _cached_period_extremes(_Db(), reading_ts)
        _, second_y = _cached_period_extremes(_Db(), reading_ts)
    assert first_y == {"y": 2026}
    assert second_y == {"y": 2027}
    assert y.call_count == 2
