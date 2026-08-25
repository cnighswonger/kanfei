"""Cache for the two expensive period-extremes queries on /api/current.

Pins the invariants of ``_cached_period_extremes`` in
``app/api/current.py``: same key returns the cached value, a new key
recomputes and updates, and ``None`` key never touches the cache. The
performance win depends on all three.
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


def test_second_call_with_same_key_skips_recomputation():
    key = datetime(2026, 8, 25, 20, 0, 0, tzinfo=timezone.utc)
    monthly = {"outside_temp_hi": 90}
    yearly = {"outside_temp_hi": 100}
    with patch.object(current_module, "get_month_extremes", return_value=monthly) as m, \
         patch.object(current_module, "get_year_extremes", return_value=yearly) as y:
        m1, y1 = _cached_period_extremes(_Db(), key)
        m2, y2 = _cached_period_extremes(_Db(), key)
    assert (m1, y1) == (monthly, yearly)
    assert (m2, y2) == (monthly, yearly)
    assert m.call_count == 1
    assert y.call_count == 1


def test_new_key_recomputes_and_updates_cache():
    k1 = datetime(2026, 8, 25, 20, 0, 0, tzinfo=timezone.utc)
    k2 = k1 + timedelta(seconds=10)
    with patch.object(current_module, "get_month_extremes", side_effect=[{"a": 1}, {"a": 2}]) as m, \
         patch.object(current_module, "get_year_extremes", side_effect=[{"b": 1}, {"b": 2}]) as y:
        _cached_period_extremes(_Db(), k1)
        m2, y2 = _cached_period_extremes(_Db(), k2)
    assert (m2, y2) == ({"a": 2}, {"b": 2})
    assert m.call_count == 2
    assert y.call_count == 2
    assert current_module._extremes_cache["key"] == k2


def test_none_key_never_hits_or_writes_cache():
    """A None key means there is no latest-reading anchor, so the cache
    must neither be read from nor written to (writing a None key would
    poison the next real request that also happens to see no reading)."""
    with patch.object(current_module, "get_month_extremes", return_value={"x": 1}) as m, \
         patch.object(current_module, "get_year_extremes", return_value={"y": 1}) as y:
        _cached_period_extremes(_Db(), None)
        _cached_period_extremes(_Db(), None)
    assert m.call_count == 2
    assert y.call_count == 2
    assert current_module._extremes_cache["key"] is None
