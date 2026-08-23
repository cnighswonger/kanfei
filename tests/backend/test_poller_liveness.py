"""Poller liveness telemetry — sub-issue #473 of umbrella #472.

Pins the shape and semantics of the new fields on `Poller.stats`.
The daemon's `_h_status` IPC handler spreads `poller.stats` into its
response, so anything named here becomes part of the /api/status API
contract.  Extend rather than rename.
"""

from datetime import datetime, timedelta, timezone

from app.services.poller import Poller


class _FakeDriver:
    connected = True

    async def poll(self):
        return None

    def request_stop(self):
        pass


def _poller() -> Poller:
    return Poller(_FakeDriver(), poll_interval=10)


class TestStatsShape:
    _NEW_KEYS = {
        "last_poll_completed_at",
        "last_broadcast_at",
        "poll_stall_seconds",
    }

    def test_stats_reports_new_liveness_fields(self):
        assert self._NEW_KEYS <= set(_poller().stats)

    def test_liveness_fields_start_null(self):
        s = _poller().stats
        for k in self._NEW_KEYS:
            assert s[k] is None, f"{k} should start None"


class TestPollStallSeconds:
    def test_null_before_first_completion(self):
        assert _poller().stats["poll_stall_seconds"] is None

    def test_climbs_with_wall_clock_after_completion(self):
        p = _poller()
        # Simulate a completed poll five seconds ago.  Real code sets
        # this at the tail of run()'s try block; the test injects it
        # so we don't have to run the loop.
        p._last_poll_completed_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        stall = p.stats["poll_stall_seconds"]
        assert stall is not None
        assert 4.0 <= stall <= 7.0, f"expected ~5s, got {stall}"

    def test_isoformat_strings_for_timestamps(self):
        p = _poller()
        p._last_poll_completed_at = datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc)
        p._last_broadcast_at = datetime(2026, 8, 23, 18, 0, 1, tzinfo=timezone.utc)
        s = p.stats
        assert s["last_poll_completed_at"] == "2026-08-23T18:00:00+00:00"
        assert s["last_broadcast_at"] == "2026-08-23T18:00:01+00:00"
