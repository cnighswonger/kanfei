# Review: PR #310 weather-quiescence gates + unit-pref render

Date: 2026-08-12
Reviewed: PR #310 at 3179e904dc5aeca38b29942d6d66db9c891e1ef8
Round: 1
Label applied: changes-requested

## What Is Correct

The requested high-level gate ordering is mostly present. `unsettled_console` fires after the console sample-count gate and before the no-METAR branch, and `unsettled_regional` fires after MAD marking and before the min-stations gate.

The rapid-trend regex is narrowly scoped: `\bPRES(?:RR|FR)\b` matches standard uppercase `PRESRR` and `PRESFR` remark tokens, does not match `PRESIDENTIAL`, and is case-sensitive, which is acceptable for METAR raw text.

The unit-preference render from PR #309 is plumbed through `Settings.tsx` -> `BarometerCalibration` -> `BaroCalibrationAggregate`, and the changed aggregate pressure displays use the operator's selected pressure unit. I did not see a reason to split that already-approved change back out for this beta27 rebuild; the branch shape is acceptable as long as PR #309 is closed without merge after #310 lands.

The new MAD-order test is a real regression test: the fixture's `KDRIFT` station is marked outlier before the regional gate runs, leaving 0 of 4 survivors with `has_rapid_trend=True`.

## Blockers

1. `backend/app/services/barometer_aggregation.py:901` runs the regional quiescence fraction gate for `n_used >= 1`, before the existing min-stations gate at `backend/app/services/barometer_aggregation.py:924`. That means one surviving METAR with `has_rapid_trend=True` returns `unsettled_regional` (`1 / 1 == 100%`) instead of `insufficient_stations`. This contradicts the surrounding policy text that "a single station firing is noise" and bypasses the cross-check floor that already exists to reject single-reference decisions. I verified the current code returns `unsettled_regional 1 False` for a one-station rapid-trend fixture. Gate Wq2 should require at least the same corroboration floor as the reference gates, e.g. `n_used >= MIN_STATIONS`, before applying the fraction.

2. `_aggregate_per_station()` sets `has_rapid_trend=True` if any valid observation in the full aviationweather fetch window carries `PRESRR` or `PRESFR` (`backend/app/services/barometer_aggregation.py:651`, `backend/app/services/barometer_aggregation.py:663`). The regional gate comments, threshold comments, and intended "weather is dynamic right now" behavior describe the latest report carrying the trend group, not any report up to two hours old. With the current set-once semantics, an old rapid-trend remark can keep a station counted as rapidly trending after the newest METAR has cleared, causing stale `unsettled_regional` holds. Either change the implementation to evaluate the newest valid raw report per station or explicitly update the design/tests to defend the broader "any obs in window" semantics.

## What Needs Attention

`frontend/src/components/settings/BaroCalibrationAggregate.tsx:171` still defines the Console badge pass state only as "enough samples". When the backend returns `unsettled_console`, the text correctly says the console pressure is moving too fast, but the Console badge can still render as green because `stdev_hpa` is ignored. The new quiescence gate should be represented in that summary badge, or the summary should avoid pass/fail coloring that conflicts with the actual skip reason.

The module docstring in `backend/app/services/barometer_aggregation.py:19` still describes only the pre-quiescence min-stations and weighted-spread gates. Since this file's docstring is the algorithm narrative, add Wq1 and Wq2 to the "Current algorithm" section and clarify their ordering relative to MAD and min-stations.

The new tests do not cover the single-survivor Wq2 edge or the stale older-observation `PRESRR` case. Add focused tests for whichever policy the implementation adopts.

## Bloat / Non-Functional

None. The added constants, API type fields, and frontend unit helpers are proportional to the requested behavior.

## Recommendations

Move the Wq2 condition behind an explicit corroboration floor, preferably `n_used >= MIN_STATIONS`, unless the product decision is that one METAR can represent regional unsettled weather. If the latter is intended, update the comments and tests because they currently say the opposite.

For rapid-trend parsing, keep the median calculation over the observation window but derive `has_rapid_trend` from the newest valid observation for the station if the gate is intended to mean current regional pressure motion.

## Bottom Line

Revise before merge. The general design is sound, the regex is fine, and the unit-pref render is acceptable in this bundled rebuild, but Wq2 currently fires on a single station and can be driven by stale trend remarks from older observations. Those are correctness issues in the new gate, not presentation polish.
