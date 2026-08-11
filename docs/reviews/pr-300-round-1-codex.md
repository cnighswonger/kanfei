# Review: PR #300 on-connect clock sync capability gate

Date: 2026-08-11
Reviewed: `backend/logger_main.py`, `tests/backend/test_onconnect_clock_sync.py` at `e03a1718aef188ce248013a441d7f42c3fc6b752`
Round: 1
Label applied: changes-requested

## What Is Correct

Hoisting the clock sync out of the `link is not None` block is the right direction. The code in that block is still LinkDriver-specific: archive period/sample period reads, WeatherLink settings reconciliation, and archive sync startup all depend on `LinkDriver` semantics and should remain there. The clock sync itself is not LinkDriver-specific, so gating it on the method that actually performs the operation is the cleaner boundary.

The `hasattr(self.driver, "async_write_station_time")` gate is also consistent with nearby command handling in `_h_sync_station_time`, and avoids turning an already-method-shaped capability into another driver-declaration chore. I do not see a reason to require a new `CAP_CLOCK_SYNC` check for this narrow path.

The structural test is acceptable for this regression class. It is not elegant, but the failure mode is textual and has recurred more than once; pinning `_connect()` against `link.async_write_station_time` is a proportionate guard as long as it stays focused.

## Blockers

1. `backend/logger_main.py:309` still dereferences `link` inside the newly capability-gated clock-sync block. For a Vantage driver, `self._link` is `None` while `async_write_station_time` exists, so `_connect()` now reaches the hoisted sync and then evaluates `link.station_model`, raising `AttributeError: 'NoneType' object has no attribute 'station_model'`. That turns the intended Vantage on-connect improvement into a failed connection after the clock write path succeeds. The assignment belonged to the old LinkDriver-only block; after hoisting, it should either stay inside `if link is not None:` or be removed in favor of the existing `_driver_model_code(self.driver)` default set before the block.

## What Needs Attention

The new tests do not exercise the real `_connect()` control flow far enough to catch the leftover `link` dereference. The helper duplicates the intended clock-sync slice, so the capability tests pass even though the production Vantage path would fail immediately after the sync. Add a small fake-driver `_connect()` test or extend the structural pin to assert the clock-sync block does not reference `link`.

## Bloat / Non-Functional

None.

## Recommendations

Move `station_type_code = link.station_model.value if link.station_model else 0` back under the `link is not None` branch, near the other LinkDriver-specific station model handling, or delete it if `_driver_model_code(self.driver)` is now the intended single source. Then add a regression test that drives `_connect()` with a non-LinkDriver fake implementing `async_write_station_time` and verifies the poller is constructed rather than crashing.

## Bottom Line

Request changes. The architectural direction is sound, but the current diff leaves a LinkDriver-only dereference in the newly non-LinkDriver path, which breaks the Vantage scenario the PR is meant to fix.

— Codex, cross-LLM review, round 1
