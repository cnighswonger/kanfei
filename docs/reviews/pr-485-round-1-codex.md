# Review: PR #485 connect clears driver on failed handshake

Date: 2026-08-24
Reviewed: `backend/logger_main.py`, `tests/backend/test_logger_watchdog.py` at `7f7b4fd40e2f394ee67f4712343ccbe79963cf2a`
Round: 1
Label applied: `changes-requested`

## What Is Correct

The fix is in the right layer for the field failure that motivated this PR. Clearing `self.driver` at the `_connect` assignment/handshake boundary preserves the watchdog invariant at the source instead of teaching every consumer to reason about a stale unconnected driver. Pushing this specific recovery into `_teardown_driver` would not help when `driver.connect()` raises after `_forced_reconnect` has already completed teardown, and changing State B to accept any `driver is not None and not driver.connected` would weaken the mid-init guard that prevents re-entrant reconnects.

The regression tests do prove the intended handshake invariant. `tests/backend/test_logger_watchdog.py:376` would fail before the production change because `daemon.driver` would still point at `_RaisingDriver`, and `tests/backend/test_logger_watchdog.py:413` would also fail because `_watchdog_tick()` returns at `backend/logger_main.py:522` when `self.driver` is still non-`None`. This is not an accidentally passing end-to-end test.

## Blockers

`backend/logger_main.py:359` and `backend/logger_main.py:409` still leave the daemon stranded if `_connect()` fails after `driver.connect()` succeeds but before `poller_task` starts. The new cleanup only covers `await self.driver.connect()` at `backend/logger_main.py:331`, but `_connect()` then awaits several post-handshake operations before the poller is running: legacy archive/sample period reads at `backend/logger_main.py:359`, clock sync at `backend/logger_main.py:409`, and then synchronous setup through poller construction/config reload before `backend/logger_main.py:438` starts the poller task.

That is the same recovery hole in a slightly different state. `_forced_reconnect()` catches and logs any `_connect()` exception at `backend/logger_main.py:599` without calling `_teardown_driver()` again. On the next watchdog tick, State A does not run if no poller is active, and State B returns immediately because `self.driver is not None` at `backend/logger_main.py:522`. For Vantage/legacy drivers, the driver may even be `connected == True`, but there is still no poller liveness clock to trip State A. A transient post-handshake I/O failure can therefore idle the daemon forever just like the original USB-gone failure.

Please extend the cleanup to cover the whole `_connect()` initialization window until the poller has been successfully started, ideally by tearing down the partially initialized driver on any exception after assignment. Add a regression test where `driver.connect()` succeeds, a later awaited setup method raises, `_forced_reconnect()` swallows it, and a subsequent `_watchdog_tick()` attempts another reconnect.

## What Needs Attention

The `_forced_reconnect()` log still says the daemon will retry via "subsequent stall detections" at `backend/logger_main.py:600`, but State B is the retry path after a failed reconnect leaves no poller. Since this PR is already touching the invariant, updating that wording would make future smoke-test logs less misleading.

## Bloat / Non-Functional

None blocking. The new test comments and docstrings are verbose, but they document a real field regression and the load-bearing invariant.

## Recommendations

Keep the source-invariant approach, but make the source boundary match the real lifecycle: `self.driver` should not survive any failed `_connect()` call that has not reached a running poller. If disconnect can block in these failure modes, reuse the same bounded teardown reasoning already present in `_forced_reconnect()` rather than leaving an open file descriptor/server/listener behind.

## Bottom Line

Revise before merge. The PR fixes the exact failed-handshake bug and the new tests are meaningful, but the same watchdog dead zone remains reachable from later `_connect()` failures before the poller starts.

— Codex, cross-LLM review, round 1