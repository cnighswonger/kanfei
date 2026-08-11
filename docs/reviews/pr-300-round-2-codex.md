# Review: PR #300 on-connect clock sync capability gate

Date: 2026-08-11
Reviewed: `backend/logger_main.py`, `tests/backend/test_onconnect_clock_sync.py` at `58e00f5878a6c34fe8db83328f2cf38dbd981953`
Round: 2
Label applied: approved-by-codex-agent

## What Is Correct

The R1 blocker is fixed. In `backend/logger_main.py`, `station_type_code = link.station_model.value if link.station_model else 0` is back inside the `if link is not None:` block, so the hoisted capability-gated clock sync no longer dereferences `link` on the Vantage path.

The Vantage station-type path remains intact: `_connect()` initializes `station_type_code = _driver_model_code(self.driver)` before the LinkDriver-only block, and that default is what reaches `Poller(...)` when `self._link` is `None`.

The new structural pin in `tests/backend/test_onconnect_clock_sync.py` directly isolates the `if hasattr(self.driver, "async_write_station_time"):` branch and fails on `link.` references in that branch. That covers the R1 regression class, where a LinkDriver-only dereference was accidentally left in the newly driver-capability-gated path.

Verification run:

- `python3 -m py_compile backend/logger_main.py tests/backend/test_onconnect_clock_sync.py`
- `cd backend && PYTHONPATH=. UV_CACHE_DIR=/tmp/uv-cache uv run pytest ../tests/backend/test_onconnect_clock_sync.py -q` -> `5 passed`

## Blockers

None.

## What Needs Attention

None. The remaining tests are structural rather than a full `_connect()` integration exercise, but for the specific R1 bug they now pin the important invariant: the capability branch must not touch `link`.

## Bloat / Non-Functional

None.

## Recommendations

No changes required for this round. Hardware verification remains outside this review; the API fallback path is unchanged.

## Bottom Line

Approve. R2 addresses the R1 crash path without disturbing the existing Vantage station model fallback or the LinkDriver-specific station type override.

— Codex, cross-LLM review, round 2
