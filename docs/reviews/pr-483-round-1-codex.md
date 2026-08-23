# Review: PR #483 watchdog driverless recovery

Date: 2026-08-23
Reviewed: `backend/logger_main.py`, `tests/backend/test_logger_watchdog.py` at `3bcc7e27c6f2df58d3bc70abc4057264b40722ac`
Round: 1
Label applied: approved-by-codex-agent, reviewed-by-codex-agent

## What Is Correct

The State A / State B ordering is correct. `backend/logger_main.py:486` still evaluates the live connected-driver + poller path first, and the below-threshold test in `tests/backend/test_logger_watchdog.py:166` pins that a healthy poller is not torn down by the new driverless branch.

The three State B guards are the right shape for this fix: `self.driver is None`, setup complete, and reconnect lock idle. In particular, `_connect` assigns `self.driver` before `driver.connect()` completes, so treating "driver present but not connected" as recoverable in State B would risk a re-entrant reconnect during startup. The new `tests/backend/test_logger_watchdog.py:137` case covers that mid-init window.

The retry cadence is acceptable for this PR. The watchdog already ticks every 10 seconds, the issue documents backoff as deferred, and the reconnect path is serialized by `_reconnect_lock`, so this change closes the driverless-recovery hole without adding retry policy complexity here.

The functional claim that the daemon self-heals once hardware is back is supported: after a failed `_forced_reconnect`, `_teardown_driver()` leaves `self.driver` and `self.poller` as `None`, and later watchdog ticks now enter State B and call `_forced_reconnect()` again.

## Blockers

None.

## What Needs Attention

Non-blocking: `backend/logger_main.py:586` still logs that a failed watchdog reconnect will keep retrying "via subsequent stall detections." After this PR, the important retry path is the new driverless State B branch, not a subsequent stall detection. That stale operational message should be corrected in a follow-up or before merge, but it does not undermine the functional fix.

## Bloat / Non-Functional

None.

## Recommendations

Update the reconnect-failure log string to describe the new retry mechanism, for example "via subsequent watchdog ticks while driverless." No bounded backoff is required in this PR given the explicit deferral in issue #482.

## Bottom Line

Approve. The code closes the driverless-recovery gap from the vsits-02 smoke test, preserves the existing stall detector behavior, and has focused tests for the newly relevant states. The only issue I found is a stale log message describing the old retry theory.

— Codex, cross-LLM review, round 1
