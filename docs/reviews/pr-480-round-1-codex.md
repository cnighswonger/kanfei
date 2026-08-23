# Review: PR #480 DMPAFT catchup on Vantage reconnect

Date: 2026-08-23
Reviewed: `backend/app/services/dmpaft_catchup.py`, `backend/logger_main.py`, `tests/backend/test_dmpaft_catchup.py`, and DMPAFT driver context at commit `264e93aa62ef58a1a59665d92c8dd4ab72c63b36`
Round: 1
Label applied: changes-requested

## What Is Correct

The catchup is wired at the right lifecycle point for the issue shape: `_connect()` schedules the Vantage-specific background task, so both initial startup and watchdog-forced reconnects use the same path.

The local/UTC storage convention is directionally correct for the current daemon model. `Poller` writes `datetime.now(timezone.utc)` into a naive SQLAlchemy `DateTime`, and `_floor_timestamp()` converts the newest naive-UTC DB timestamp into naive local time before calling DMPAFT. The reverse conversion in `_to_utc_naive()` then stores backfilled rows as naive UTC, matching live rows.

DMPAFT ordering supports the current cap direction. The driver reads pages from the console-reported first new record forward and appends parsed records in that order (`backend/app/protocol/vantage/driver.py:1257`, `backend/app/protocol/vantage/driver.py:1275`, `backend/app/protocol/vantage/driver.py:1366`). The vendor reference says DMPAFT returns the location of the first new data record and then streams pages from there, so `records[:max_records]` preserves the oldest returned records and drops the newest tail if an impossible over-cap response occurs. That is the less harmful failure mode for a gap fill.

The exact timestamp dedupe is acceptable for this specific flow. Archive records are minute-granular console archive timestamps; live poll rows are subsecond wall-clock samples. A poll row near the same minute is not the same observation, and DMPAFT is requested after the newest DB timestamp, so normal overlap should be minimal. If a future change wants archive-bucket dedupe, it should be explicit about replacing or suppressing live samples within an archive interval, not hidden behind fuzzy equality.

The `_io_lock` contention is real but bounded by the same driver serialization already used elsewhere. `async_dmpaft()` and `poll()` both run blocking work in the executor and take the driver's `_io_lock` (`backend/app/protocol/vantage/driver.py:255`, `backend/app/protocol/vantage/driver.py:1319`, `backend/app/protocol/vantage/driver.py:2106`). That can delay the first poll while a DMPAFT transfer is active, but it should not deadlock by itself: only one serial operation holds the lock at a time. The watchdog may observe a startup stall if the archive transfer is long; that is a tradeoff to watch, not a blocker in this diff.

## Blockers

1. `backend/app/services/dmpaft_catchup.py:230` computes derived values with raw SI units instead of the tenths units required by the shared calculation helpers.

   `Poller` first scales outside temperature, barometer, and wind to tenths, then passes those tenths into `heat_index`, `dew_point`, `wind_chill`, `feels_like`, and `equivalent_potential_temperature` (`backend/app/services/poller.py:240`, `backend/app/services/poller.py:267`, `backend/app/services/poller.py:274`, `backend/app/services/poller.py:277`). The helpers document the same contract: temperature, pressure, and wind inputs are tenths (`backend/app/services/calculations.py:94`).

   The DMPAFT projection passes raw `outside_temp_avg`, `wind_speed_avg`, and `barometer` into those helpers, then wraps the returned value in `_tenths()` (`backend/app/services/dmpaft_catchup.py:231`, `backend/app/services/dmpaft_catchup.py:232`, `backend/app/services/dmpaft_catchup.py:234`, `backend/app/services/dmpaft_catchup.py:238`, `backend/app/services/dmpaft_catchup.py:242`). That corrupts the derived columns for every backfilled row. With the new test fixture values, live-style `dew_point(225, 60)` is `144`, while the catchup path computes `dew_point(22.5, 60)` as `-47` and stores `-470`; `wind_chill` similarly becomes `-60` instead of `216`, and theta-e becomes `70430` instead of `3240`.

   Fix by scaling the archive values to the same tenths variables used for DB storage before calling the calculation helpers, and store the helper returns directly without a second `_tenths()` pass. Add assertions that compare the derived values against the live helper calls, not just `is not None`.

## What Needs Attention

The timezone assumption is serviceable but should be named as an operational assumption. `_local_tzinfo()` assumes the console clock and daemon process timezone are the same (`backend/app/services/dmpaft_catchup.py:72`). `_connect()` does sync the console from `datetime.now()`, which makes that true for normal deployments. If someone runs the daemon under a different `TZ` than the intended station locale, the backfill will shift records. I do not think this blocks the PR because the app already treats local station time as the daemon's local time in several places, but the release note or issue closure should call it out if this is expected to run in containers.

DST transition behavior is not fully safe, but the risk is narrow. `replace(tzinfo=_local_tzinfo())` does not detect nonexistent local times and chooses the default fold for ambiguous fall-back times (`backend/app/services/dmpaft_catchup.py:93`). A reconnect catchup spanning the repeated hour can map one of the repeated local archive rows to the wrong UTC hour, and spring-forward nonexistent archive times will be normalized by the timezone implementation rather than rejected. Given this is a personal station daemon and archive rows carry only local wall-clock minute fields, there may not be enough information to make this perfect. I would not block on it, but it deserves a targeted test or documented limitation if DST-gap correctness is part of the acceptance criteria.

The cap behavior is not directly tested for ordering. Existing evidence says `records[:max_records]` preserves the oldest returned records, but the test only checks count. A small unit test with ordered fake timestamps would make the intended cap direction explicit.

## Bloat / Non-Functional

None. The new service is narrow and uses the existing driver, model, and calculation surfaces.

## Recommendations

Add a projection test that checks exact derived values for the fixture row:

- `dew_point == dew_point(225, 60)`
- `heat_index == heat_index(225, 60)`
- `wind_chill == wind_chill(225, 25)`
- `feels_like == feels_like(225, 60, 25)`
- `theta_e == equivalent_potential_temperature(225, 60, 10132)`

For the DST concern, prefer documenting the limitation unless there is a reliable station timezone setting to use. A fake timezone test around an ambiguous local time can at least pin today's behavior.

## Verification

Ran focused backend tests:

```text
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q ../tests/backend/test_dmpaft_catchup.py ../tests/backend/test_vantage_dmp.py
26 passed in 2.66s
```

The first root-level `uv run pytest -q tests/backend/test_dmpaft_catchup.py tests/backend/test_vantage_dmp.py` attempt failed because `uv` could not write its default cache under the managed filesystem. Retrying with `UV_CACHE_DIR=/tmp/uv-cache` from the repo root then failed because this repo's backend imports require running from `backend/`. The verification above used the repo's backend test layout.

## Bottom Line

Request changes. The reconnect backfill shape is sound enough, and the commissioned timezone, ordering, dedupe, and lock concerns do not expose a merge-blocking defect in this diff. The derived-value unit mismatch is merge-blocking because it writes visibly wrong `dew_point`, `wind_chill`, `feels_like`, `theta_e`, and sometimes `heat_index` values into every DMPAFT-backfilled row.

— Codex, cross-LLM review, round 1