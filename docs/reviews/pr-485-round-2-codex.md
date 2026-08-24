# Review: PR #485 connect cleanup after post-handshake failure

Date: 2026-08-24
Reviewed: `backend/logger_main.py`, `tests/backend/test_logger_watchdog.py` at `662b9b06d4ae9c230a5e8f5a7dab7ff5d50aaaea`
Round: 2
Label applied: `approved-by-codex-agent`

## What Is Correct

The round-2 change closes the blocker from round 1. `backend/logger_main.py:330` still assigns `self.driver` before the hardware handshake, but the cleanup boundary now covers the whole initialization window from `driver.connect()` through `poller_task` and `_midnight_task` creation at `backend/logger_main.py:337` through `backend/logger_main.py:437`. Any exception before `_connect()` completes now calls `_teardown_driver()` at `backend/logger_main.py:450`, which restores the watchdog's driverless State-B recovery invariant.

The boundary is in the right place. Stopping earlier, for example after clock sync or poller construction, would still leave a partial-init path where a synchronous setup failure or task creation failure could leave `self.driver` non-`None` without a valid running lifecycle. Extending through `_midnight_task` creation is conservative and consistent with `_connect()` being all-or-nothing: once `_connect()` returns, the daemon has a driver, poller, poller task, and rain reset task; if it raises, those fields are torn back down.

Reusing `_teardown_driver()` is appropriate for this partial-init state. The method is null-safe for `_midnight_task`, `poller`, `poller_task`, and `driver` at `backend/logger_main.py:617` through `backend/logger_main.py:637`. It also handles the cases an inline half-teardown would be likely to miss, especially a poller object created before a later failure and a driver that connected successfully before a post-handshake await failed. I did not find a partial-init case where `_teardown_driver()` does inappropriate work; `_save_rain_state()` is gated by `self.poller`, and driver disconnect exceptions are swallowed.

The new regression test exercises the widened path, not just the original handshake path. `tests/backend/test_logger_watchdog.py:434` makes `connect()` succeed, `tests/backend/test_logger_watchdog.py:440` raises from `async_write_station_time()`, and `tests/backend/test_logger_watchdog.py:464` asserts `_connect()` raises while leaving `driver`, `poller`, and `poller_task` cleared. That test would have passed only after the try/except moved beyond `driver.connect()`.

The `_forced_reconnect()` log wording at `backend/logger_main.py:610` now matches the actual recovery path: after `_connect()` fails and re-raises, the daemon retries through the watchdog's driverless State-B branch, not through subsequent stall detections.

## Blockers

None.

## What Needs Attention

The fire-and-forget archive/catchup tasks created inside `_connect()` are not tracked by `_teardown_driver()`. That is pre-existing lifecycle behavior, and both wrappers swallow their own failures, so I do not see it as a blocker for this PR's watchdog dead-zone fix. It is worth keeping in mind if a future change needs strict cancellation semantics for background archive work.

## Bloat / Non-Functional

None blocking. The production comments are longer than I would normally add, but they document a load-bearing watchdog invariant that was already subtle enough to miss in round 1.

## Verification

Passed:

```bash
UV_CACHE_DIR=/tmp/uv-cache PYTHONPATH=. uv run pytest ../tests/backend/test_logger_watchdog.py -q
UV_CACHE_DIR=/tmp/uv-cache uv run python -m py_compile logger_main.py ../tests/backend/test_logger_watchdog.py
```

Note: running pytest without `PYTHONPATH=.` from this sandbox failed collection with `ModuleNotFoundError: No module named 'logger_main'`; the explicit backend path matches the module layout and the test suite then passed (`17 passed`).

## Recommendations

Ship this round. The all-or-nothing `_connect()` lifecycle invariant is now pinned for both `connect()` failures and post-handshake await failures.

## Bottom Line

Approved. Round 2 addresses the round-1 blocker, the try/except boundary is correctly scoped through completed task setup, and the added test fails for the old boundary while passing for the widened cleanup.

— Codex, cross-LLM review, round 2
