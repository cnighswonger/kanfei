# Review: PR 332 ET Column Migration

Date: 2026-08-13
Reviewed: PR 332 at `133ca14c4ffe745d3886a0157d2bc424f0b1b2f2`
Round: 1
Label applied: changes-requested

## What Is Correct

The `ALTER TABLE ADD COLUMN` path follows the established local
SELECT-then-catch migration pattern used for `rain_yearly`, `wind_gust`, and
`thsw_index`, and the `WHERE {column} IS NULL` backfill guard makes repeated
startup runs idempotent.

The poller now writes `et_daily`, `et_monthly`, and `et_yearly` as top-level
`SensorReadingModel` fields, and `_build_extra_json()` no longer emits the old
`et_*_mm` keys. I found no remaining production caller that depends on those ET
keys being present in `extra_json`.

The `/api/current` response preserves the existing `{value, unit}` shape and
uses the same rain-unit setting branch as the old JSON parser did. For new rows
written by the poller, the values are equivalent to the old response path apart
from the expected tenths-mm storage quantization.

`sensor_meta` registers the three ET columns for history queries, units, bounds,
and conversion. Reusing `si_rain_to_display_in` is correct because the storage
shape is the same tenths-mm shape used by rain totals.

The frontend picker additions are wired correctly: `History.tsx` builds the
dropdown from `SENSOR_DISPLAY_NAMES`, so the three ET entries become selectable
automatically. The history API accepts these keys directly because they match
the backend sensor names.

The E2E fixture schema now includes the three model columns. Column order is not
material for SQLite or the existing fixture parity test, which checks column
presence.

## Blockers

1. `backend/app/models/database.py:129` can abort startup on a single malformed
   historical `extra_json` value.

   The migration evaluates `json_extract(extra_json, '$.<key>')` for every row
   where `extra_json IS NOT NULL`. SQLite raises `OperationalError: malformed
   JSON` when the blob is invalid JSON, so one corrupt or manually restored old
   row prevents `init_database()` from completing and blocks the daemon/web app
   from starting after upgrade.

   This is not just theoretical defensive handling: existing production code
   treats malformed `sensor_readings.extra_json` as survivable. For example,
   the old ET current API parsed `extra_json` inside a `try` and ignored
   `ValueError`, and the station/astronomy extra-json readers still do the same.
   The migration should preserve that tolerance.

   Add a JSON-validity guard to the backfill, for example
   `AND json_valid(extra_json)`, before calling `json_extract`, and add a
   migration test with an invalid `extra_json` row to prove startup/backfill
   skips it instead of raising.

## What Needs Attention

The migration truncates with `CAST(... * 10 AS INTEGER)`, while the live poller
stores with Python `round(snapshot.et_* * 10)`. That can differ by one raw unit
for fractional tenths, e.g. `630.68 mm` becomes `6306` in the migration but
`6307` on the poller path. The display impact is only `0.1 mm`, but the
semantic mismatch is real. Consider using SQLite `round(json_extract(...) * 10)`
before casting if the backfilled rows should match the live write path exactly.

`backend/app/models/sensor_meta.py:91` adds `_ET_FIELDS` but never uses it.
Existing `_RAIN_FIELDS` already has that shape, so this is not a new functional
problem, but the added unused constant is dead code and can be dropped unless it
is intentionally part of a near-term cleanup.

The new migration tests focus on the SQL statement and metadata, but they do
not exercise the full `init_database()` path against an old-schema table where
the ET columns are absent. The ADD COLUMN path is simple and matches existing
patterns, so this is not a blocker, but an old-schema init test would guard the
most important upgrade behavior directly.

## Bloat / Non-Functional

No material over-abstraction. The only minor bloat is the unused `_ET_FIELDS`
constant noted above.

## Recommendations

Guard the backfill with `json_valid(extra_json)` and add tests for invalid JSON
and full old-schema `init_database()` migration. If touching the SQL anyway,
align the backfill conversion with the poller by rounding rather than
truncating.

## Bottom Line

Request changes. The feature wiring is otherwise coherent, but startup
migrations need to tolerate malformed historical `extra_json` the same way the
runtime readers already do.
