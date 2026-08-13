# Review: PR 324 station clock live tick

Date: 2026-08-13
Reviewed: PR 324 at d438ae91509b49be48dec77f83f1a699e7f82610
Round: 2
Label applied: changes-requested

## What Is Correct

The previous timezone blocker is resolved for the normal clock-read path. The backend no longer serializes an epoch derived from the station's naive wall-clock value; instead it returns raw `station_time_components` and an independent `server_epoch_ms_at_read` anchor. The frontend advances those components with `Date.UTC(...)` and formats with `getUTC*()` accessors, so browser local timezone settings do not affect the rendered station clock.

The frontend formatter preserves the year suffix when `components.year != null` and omits it cleanly when `year` is null. Manual simulation across `UTC`, `America/New_York`, `Pacific/Honolulu`, and `Asia/Tokyo` produced the same output for the requested fixed-time and midnight-rollover cases.

`station_time_epoch_ms` is fully removed from the backend/frontend surfaces reviewed here. `_DEGRADED_RESPONSE`, the final `get_station()` response, and `frontend/src/api/types.ts` all carry the new paired fields.

## Blockers

1. `backend/app/api/station.py:124` still drops the year from `station_time` after auto-sync, even when the station read included one.

   In the successful auto-sync branch, `station_time_components["year"]` is set from `t.get("year")`, but the legacy `station_time` string is always built with `now.strftime("%H:%M:%S %m/%d")`. For Vantage-style reads where `t.get("year")` is present, that response now contains components that format as `HH:MM:SS MM/DD/YYYY` while `station_time` remains `HH:MM:SS MM/DD`.

   That reintroduces the round-1 shape mismatch on the auto-sync response and contradicts the round-2 requirement that year availability be inherited so the sync path does not gain or lose the suffix. Build the synced `station_time` with the same year-presence rule as `_format_station_time`, using the same `now` snapshot as the components.

## What Needs Attention

The `useEffect` interval depends on `[components, readAnchor]`, so a poll that returns a fresh object with the same values will tear down and recreate the interval. That is harmless for this panel and does not need memoization unless this path becomes noisier later.

## Bloat / Non-Functional

None.

## Recommendations

Add a focused backend test for the auto-sync response shape with `t.get("year")` present and absent. The missing year suffix is easy to regress because the visible frontend generally uses `station_time_components` when the pair is present.

## Verification

- `cd frontend && npx tsc --noEmit` passed.
- `cd backend && python3 -m pytest ../tests/backend/ -q` passed: 1301 passed, 7 warnings.
- Manual formatter simulation passed for fixed time, +1 hour, midnight rollover, and null-year formatting across multiple `TZ` settings.

## Bottom Line

Revise before merge. The main timezone fix is sound, but the auto-sync response still loses the year suffix in `station_time` for year-reporting stations, so the round-1 shape mismatch is not fully closed.
