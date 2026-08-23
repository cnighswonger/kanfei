# Review: PR #478 /api/health and poll liveness telemetry

Date: 2026-08-23
Reviewed: PR #478 at `a2b626e8b1f6c38175c536eb7a2e0f9bd0d42975`
Round: 1
Label applied: `changes-requested`

## What Is Correct

The core completed-poll timestamp is placed at the right semantic boundary. `backend/app/services/poller.py:140` awaits `_process_reading(snapshot)`, and `backend/app/services/poller.py:147` advances `_last_poll_completed_at` only after that returns. Because `_process_reading` includes the DB write, subscriber broadcast callback, and configured uploaders, this is the right liveness clock for "the poller is making end-to-end progress" rather than just "a serial read returned."

The post-first-completion stall shape is also reasonable: `poll_stall_seconds > 3 * poll_interval` gives normal single-cycle jitter room while still surfacing the multi-hour silent failure from #472 quickly. The response also has the basic fields a Nagios/Uptime Kuma style check needs: stable HTTP status, `ok`, a human-readable `reason`, the interval, current stall age, and relevant timestamps.

I do not see a concurrency bug in the unlocked timestamp reads. The poller task and IPC handler run in the logger daemon's asyncio event loop, `Poller.stats` has no await points, and the fields are single object-reference assignments/readbacks. At worst, one status response can observe the previous timestamp, which is acceptable for health telemetry.

## Blockers

1. `poll_stall_seconds: null` can keep `/api/health` green forever before the first completed poll, so a startup wedge is not actually caught by the documented 30 second fallback.

   `Poller.stats` returns `poll_stall_seconds: None` until `_last_poll_completed_at` exists (`backend/app/services/poller.py:96`-`backend/app/services/poller.py:102`). `/api/health` then only trips the stall branch when `stall is not None` (`backend/app/api/health.py:83`-`backend/app/api/health.py:95`) and unconditionally sets `ok=True` afterward (`backend/app/api/health.py:97`-`backend/app/api/health.py:98`). The fallback threshold in `_stall_threshold()` is therefore only used for non-null stall values with a missing/invalid interval; it is not a startup elapsed-time fallback.

   That leaves a real monitoring hole for exactly this issue's goal: if the daemon connects the driver and creates the poller, but the first `driver.poll()` or downstream first-cycle work wedges before `_last_poll_completed_at` is ever set, `/api/health` reports 200 indefinitely as long as `connected` remains true. The test currently pins that behavior (`tests/backend/test_health.py:90`-`tests/backend/test_health.py:104`) while its docstring says the fallback catches stuck startup, which the implementation cannot do.

   Fix direction: expose enough daemon/poller start time to compute age before first completion, or make `poll_stall_seconds` measure from poller start until first completion. Then add a test where `connected=True`, no completed poll exists, startup age exceeds the fallback/threshold, and `/api/health` returns 503.

## What Needs Attention

`TestResponseShape` uses exact key equality (`tests/backend/test_health.py:158`-`tests/backend/test_health.py:177`) even though the endpoint contract says "extend rather than rename" (`backend/app/api/health.py:8`-`backend/app/api/health.py:10`). For a load-bearing external-monitor response, the guard should probably assert that the required key subset exists on both 200 and 503 responses, not that no additional diagnostic field can ever be added. Exact equality protects against accidental removal but turns additive, backward-compatible telemetry into a test failure.

`last_broadcast_at` is useful, but its name/comment deserve a second look. The timestamp is advanced after the full broadcast callback returns, and in the daemon that callback also runs WU, CWOP, and public relay uploads after the IPC subscriber broadcast. So this field is not purely "handed to broadcast callback" timing; an uploader hang can also prevent it from advancing.

## Bloat / Non-Functional

None. The endpoint and tests are small and appropriately scoped for the sub-issue.

## Recommendations

Keep `_last_poll_completed_at` distinct from the existing `_last_poll`; preserving the frontend consumer is the right compatibility call.

After fixing startup-age handling, keep the current 503 body shape stable and add the startup-wedge test to the same response-shape suite so the contract covers the case this round caught.

## Bottom Line

Request changes. The post-completion liveness design is sound, and the endpoint shape is close, but the startup/null path currently leaves an indefinite green health check before the first completed poll. That is a direct gap in the external paging goal for #473.

— Codex, cross-LLM review, round 1
