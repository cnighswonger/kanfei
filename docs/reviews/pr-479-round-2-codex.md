# Review: PR #479 poll-stall watchdog

Date: 2026-08-23
Reviewed: `backend/logger_main.py`, `tests/backend/test_logger_watchdog.py` at `1122c1da28b6d4d1fc32ba849ca68f562fa64dfd`
Round: 2
Label applied: approved-by-codex-agent

## What Is Correct

The R1 blocker is fixed. Both operator IPC lifecycle handlers now acquire the same `_reconnect_lock` used by `_forced_reconnect`: `_h_connect()` wraps teardown plus connect in the lock, and `_h_reconnect()` wraps config lookup, teardown, and connect in the lock. The watchdog still uses the right asymmetric behavior: it skips if the lock is already held, while an explicit operator reconnect waits its turn.

The corrected watchdog config comment now matches the actual behavior. `_forced_reconnect()` records the current serial config before reconnect, but `_connect()` re-reads the effective config before creating the driver. The comment now correctly states that recovery honors the latest committed intent rather than stale intent from the wedged poll.

The new regression test covers the important race. `test_ipc_reconnect_serialised_with_watchdog` parks the watchdog inside teardown while it holds `_reconnect_lock`, starts `_h_reconnect()`, verifies the operator path has not entered teardown, then releases the watchdog and confirms the operator teardown/connect happens afterward. That would have failed under the R1 implementation where `_h_reconnect()` bypassed the lock.

I also checked the other daemon lifecycle transitions. Startup auto-connect runs before the watchdog task is created, and shutdown cancels the watchdog before calling `_teardown_driver()`. I do not see another teardown/connect transition in this daemon that should share `_reconnect_lock` for the R1 race class.

## Blockers

None.

## What Needs Attention

The new race test proves `_h_reconnect()` specifically. `_h_connect()` uses the same lock pattern and is covered by code inspection rather than a second mirrored test. That is acceptable for this narrow fix; adding a nearly identical `_h_connect()` race test would mostly duplicate the existing concurrency proof.

## Bloat / Non-Functional

None.

## Recommendations

None for this round.

## Verification

Ran:

```bash
UV_CACHE_DIR=/tmp/uv-cache PYTHONPATH="$PWD" uv run pytest -q ../tests/backend/test_logger_watchdog.py
```

Result: 10 passed in 0.81s.

## Bottom Line

Approve. The R1 serialization blocker is closed, the comment now matches the intended reconnect semantics, and I do not see another daemon lifecycle transition that needs the same lock for this PR's race boundary.

— Codex, cross-LLM review, round 2
