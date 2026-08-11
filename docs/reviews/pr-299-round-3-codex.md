# Review: PR #299 Vantage rain season and firmware status

Date: 2026-08-11
Reviewed: PR #299 at e61e58741cc072e0117946f4e7756296404fe502
Round: 3
Label applied: approved-by-codex-agent, reviewed-by-codex-agent

## What Is Correct

The R1 blocker is fixed. `backend/logger_main.py::_h_set_rain_season` no longer treats an EEPROM ACK as success by itself; it now reads `RAIN_YEAR_START` after the write and raises unless the register equals the requested month. That covers the important failure modes from the earlier review: ACK with unchanged value, ACK with wrong value, and ACK with failed/garbage read-back.

The driver layer keeps the boundary clean. `backend/app/protocol/vantage/driver.py` declares the new Vantage-only `CAP_RAIN_SEASON_RW`, reads EEPROM address `0x2C` as a single byte, rejects illegal stored values outside `1..12`, and refuses to write out-of-range months before sending anything to the console.

The firmware status addition is appropriately cheap and cached. `_h_status` surfaces `hw_config.firmware_version` and `hw_config.firmware_date` without issuing status-time serial commands, and normalizes the empty dataclass default date to `None` so the frontend can hide unsupported or not-yet-known firmware cleanly.

The tests exercise the contract that matters for this follow-up. `tests/backend/test_vantage_rain_season.py::TestHandlerReadBackContract` covers ACK/read-back mismatch, ACK/read-back `None`, NAK, and the happy path. `tests/backend/test_firmware_status.py` covers Vantage version/date, VP1 date-only behavior, empty date normalization, legacy driver absence, and no-driver status.

## Blockers

None.

## What Needs Attention

None blocking. The new settings component is fairly prose-heavy, but the behavior is narrow and isolated to a Vantage-only capability panel, so I do not see a merge-blocking complexity issue in this bundle.

## Bloat / Non-Functional

None.

## Recommendations

No required changes. If this area is touched again, a small API-level test for `/api/station/rain-season` request validation would be a useful complement, but the daemon and driver contracts are covered for this PR's failure mode.

## Verification

Passed:

- `PYTHONPATH=/home/manager/git_repos/kanfei-working/backend UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/backend/test_vantage_rain_season.py tests/backend/test_firmware_status.py`
- `cd frontend && npx tsc --noEmit`
- `PYTHONPATH=/home/manager/git_repos/kanfei-working/backend UV_CACHE_DIR=/tmp/uv-cache uv run python -m py_compile backend/app/api/station.py backend/app/ipc/protocol.py backend/app/protocol/base.py backend/app/protocol/vantage/driver.py backend/logger_main.py tests/backend/test_vantage_rain_season.py tests/backend/test_firmware_status.py`

Note: the first unmodified `uv run pytest` attempt could not acquire a cache lock because this sandbox cannot write `/home/manager/.cache/uv`; rerunning with `UV_CACHE_DIR=/tmp/uv-cache` executed the tests successfully.

## Bottom Line

Approve. The R1 correctness hole is closed empirically, the capability boundary is Vantage-only, cached firmware status is surfaced without extra serial I/O, and the focused regression tests pass.

— Codex, cross-LLM review, round 3
