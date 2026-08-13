# Review: PR 324 station clock live tick

Date: 2026-08-13
Reviewed: PR 324 (`fix/station-clock-live-tick`) at `bd04eebc87ac213c45e8378ad5ca3191b0f64b70`
Round: 1
Label applied: changes-requested

## What Is Correct

- The backend adds `station_time_epoch_ms` to both normal and degraded `/api/station` responses, so disconnected and IPC-failure responses preserve a stable shape.
- The auto-sync path updates both the display string and epoch from the same `datetime.now()` snapshot after a successful sync, so it is internally consistent with the read path as long as the intended timezone is the server's local timezone.
- The frontend fallback behavior is correct: before the first poll, on degraded/disconnected responses, and when clock read support is unavailable, `clockOffsetMs` stays `null` and the UI falls back to `station_time ?? "--"`.
- The interval cleanup is the normal React pattern used for this kind of display-only ticker. The discard state slot is a little noisy, but it is acceptable here and does not justify a heavier abstraction.
- Recomputing the offset on each status poll can cause a visible one-second correction if the console clock has drifted by about one second over the poll interval. That jump is expected and preferable to hiding real console drift. Larger jumps after auto-sync are also expected.
- Verification passed:
  - `python3 -m py_compile backend/app/api/station.py`
  - `cd backend && python3 -m pytest ../tests/backend/ -q`
  - `cd frontend && npx tsc --noEmit`

## Blockers

1. `backend/app/api/station.py:91` / `frontend/src/components/panels/StationStatus.tsx:40` - The epoch is treated as an absolute instant, which changes the displayed console wall time when the browser timezone differs from the server/station timezone.

   Failure scenario: if the station/server are in Los Angeles and the station reports `12:00:00 08/13`, `station_dt.timestamp()` encodes that naive value as noon Pacific. A browser in New York then renders `new Date(epochMs)` with local getters and shows `15:00:00 08/13`. Near midnight this can also roll the displayed date to the previous or next day. That is a regression from the existing `station_time` string, which represented the console's own wall-clock fields rather than the viewer's timezone-adjusted instant.

   DST has the same shape of risk: ambiguous or nonexistent local wall-clock values are resolved by the server's local timezone rules when `.timestamp()` runs, then formatted using the browser's timezone rules. The UI is no longer guaranteed to show the console clock values it read.

   Auto-sync is internally consistent with the current implementation because it also uses server-local `datetime.now().timestamp()`, but that consistency does not fix the cross-timezone display bug. The frontend needs either a timezone-stable wall-clock representation to tick, or the backend needs to provide enough timezone context for the browser to format in the station/server timezone instead of the viewer timezone.

2. `frontend/src/components/panels/StationStatus.tsx:43` - The live formatter drops the year for stations that report one.

   Backend `_format_station_time()` includes `/{year}` when the driver returns a year (`backend/app/api/station.py:38`), and Vantage `GETTIME` does return `year` (`backend/app/protocol/vantage/driver.py:1156`). The first fallback render can therefore show `HH:MM:SS MM/DD/YYYY`, then the live-ticked display switches to `HH:MM:SS MM/DD` as soon as `clockOffsetMs` is set. This violates the intended format match between `station_time` and the live display and removes information the existing UI already showed.

## What Needs Attention

None beyond the blockers above.

## Bloat / Non-Functional

None. The added React state/effect shape is small and scoped to the panel. I would not replace it with `useSyncExternalStore` or a custom force-update hook for this one display.

## Recommendations

- Preserve station wall-clock semantics explicitly. Reasonable options include sending clock fields plus a snapshot wall time and ticking those fields, or sending an epoch that is deliberately encoded/decoded in a fixed display timezone along with the corresponding formatting rule.
- Make the live formatter preserve the same year/no-year shape as `station_time`, either by carrying the original `year` availability through the API or by formatting from the same structured clock data used to compute the tick.
- Add a focused frontend/unit test or simple utility test for cross-timezone formatting if a formatter utility is extracted; at minimum test the Vantage year-present shape.

## Bottom Line

Request changes. The polling, fallback, cleanup, and expected drift-correction behavior are sound, but the current epoch contract changes the station clock into the browser's local clock representation and drops the year for year-reporting stations. Fix those display-contract issues before approval.
