# Review: PR #479 poll-stall watchdog

Date: 2026-08-23
Reviewed: `backend/logger_main.py`, `tests/backend/test_logger_watchdog.py` at `a2edaf16ed846121f9f2a48ac9db9c568d740d08`
Round: 1
Label applied: changes-requested

## What Is Correct

The watchdog is wired into the daemon lifetime, uses the `poll_stall_seconds` telemetry from #478, and leaves the normal no-poller and pre-first-poll windows as no-ops. The threshold calculation is consistent with `/api/health`: `POLL_STALL_MULTIPLIER * max(1, poller.poll_interval)`, and the tests pin both the below-threshold and above-threshold behavior.

The exit-for-systemd branch is the right backstop for the failure class in umbrella #472. If `_teardown_driver()` times out, the daemon has already proved that the normal disconnect path is wedged; retrying a longer timeout or creating a fresh driver inside the same process risks stacking another serial owner onto the same stuck close path. Handing control to systemd is the cleanest recovery boundary here, and the new test verifies that `_connect()` is not attempted after the forced exit trigger.

The DMPAFT catchup hook for #477 is in the right location: after bounded teardown and successful reconnect, before declaring recovery complete. The preceding stall-detection warning includes the observed stall duration and threshold, which is enough operational context for the future catchup implementation to compute and log the recovery gap from the poller/archive state it will introduce.

## Blockers

1. `backend/logger_main.py:470` documents `_reconnect_lock` as serializing watchdog reconnects against operator-initiated reconnects, but the IPC handlers at `backend/logger_main.py:1385` and `backend/logger_main.py:1393` still bypass that lock and call `_teardown_driver()` / `_connect()` directly. That leaves the highest-risk race in place: a watchdog stall tick can enter `_forced_reconnect()` and hold the lock while an operator `connect` or `reconnect` IPC command concurrently tears down the same `self.driver`, replaces it, or connects a second driver instance. The loser does not reliably "silently do nothing" because only watchdog callers check the lock. Please route IPC connect/reconnect through the same serialized path, or make their teardown/connect critical sections acquire the same lock, and add a regression test that starts a slow watchdog reconnect and proves an IPC reconnect cannot overlap it.

## What Needs Attention

The watchdog's config snapshot comments overstate what the code preserves. `_forced_reconnect()` calls `_get_serial_config()` at `backend/logger_main.py:491`, but `_connect(port, baud)` immediately re-reads the full effective config at `backend/logger_main.py:325`, and `_create_driver()` uses that config rather than the `port` / `baud` parameters. That means the watchdog reconnect actually follows the latest committed DB config, not necessarily the port/baud active when the stalled driver was created. I do not see that as blocking for this PR because the setup flow commits DB config before asking the daemon to connect, but the comments should be corrected or the reconnect should snapshot the full effective config if "same config as the stalled driver" is intended.

The 3x poll interval recovery boundary is aggressive but defensible for this sub-issue because the target failure is a silent poller stall, not a noisy transient. If false recoveries become an operational problem, the next knob should be a recovery-specific multiplier or floor rather than diverging the liveness signal itself from `/api/health`.

## Bloat / Non-Functional

None.

## Recommendations

Keep the systemd-exit path for teardown timeout. The missing piece is not a longer in-process recovery attempt; it is making every driver lifecycle transition use one serialization boundary.

After the lock fix, add one focused test for the operator race. It can mirror `test_serialised_by_reconnect_lock`, but call `_h_reconnect()` or `_h_connect()` as the second actor so the test covers the actual IPC entry point.

## Verification

Ran:

```bash
UV_CACHE_DIR=/tmp/uv-cache PYTHONPATH="$PWD" uv run pytest -q ../tests/backend/test_logger_watchdog.py
```

Result: 9 passed in 0.62s.

Ran:

```bash
UV_CACHE_DIR=/tmp/uv-cache PYTHONPATH="$PWD" uv run pytest -q ../tests/backend/test_poller_liveness.py ../tests/backend/test_health.py
```

Result: 18 passed, 1 existing Pydantic deprecation warning.

Initial attempts without `UV_CACHE_DIR` failed because `uv` tried to create cache files under a read-only home directory; attempts without `PYTHONPATH` failed collection because `logger_main` was not importable from the test runner's selected root.

## Bottom Line

Revise before merge. The watchdog recovery path itself is directionally right, including the exit-for-systemd backstop and the 3x threshold, but the claimed reconnect serialization is incomplete until the IPC connect/reconnect handlers use the same lock.

— Codex, cross-LLM review, round 1
