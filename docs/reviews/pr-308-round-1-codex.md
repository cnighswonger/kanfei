# Review: PR #308 weighted barometer aggregation

Date: 2026-08-12
Reviewed: PR #308 (`fix/weighted-baro-algo`) at `5c765433f2da9fe40d6bc15e39a7bd4fe431ffb1`
Round: 1
Label applied: changes-requested

## What Is Correct

The weighted median helper handles the important boundary cases correctly. Empty input raises, a single survivor returns that value via the `running > half` branch, crossover returns the current value, and exact half weight returns the midpoint with the next sorted value.

The weighted spread implementation is self-consistent with the new statistic: `_weighted_spread_hpa()` computes `2 * sqrt(weighted_variance)` around the weighted median, not an unweighted mean. The backend returns the same `cross_station_spread_hpa` value that the panel displays against the 0.7 hPa threshold.

Gate ordering in `compute_aggregate_recommendation()` is correct: station limit first, then console gates, no-METAR, MAD outlier marking, survivor count, then weighted spread. The min-stations gate counts `survivors` after MAD, so a rejected drifted station cannot inflate the raw station count and unlock an override.

The override contract is correctly constrained in executable code. `hold_override_allowed=True` is only set in the `SKIP_CROSS_STATION_DISAGREEMENT` branch, and the no-console, insufficient-console, no-METAR, insufficient-stations, and auto-apply paths all leave it false.

The frontend button gating is mutually exclusive. `BaroCalibrationAggregate.tsx` branches first on `recommendation.should_apply`; the override button is only evaluated in the HOLD branch and additionally requires `onApplyRecommendation`, `hold_override_allowed`, and a non-null `median_of_medians_thousandths_inhg`. I do not see a path that renders both the autonomous apply and override buttons at once.

`STATION_LIMIT_FOR_CALIBRATION` slices the head of the distance-sorted list before other gates. The sort-stability assumption is backed by `_aggregate_per_station()` sorting by `distance_miles` before `fetch_station_medians()` returns.

The new backend tests are meaningful for the core behavior. In particular, `test_nearest_station_dominates_the_median` would fail if the recommendation used an unweighted median, because the raw median of `[30000, 30010, 30010]` is `30010` while the expected weighted result is `30000`.

## Blockers

1. `backend/app/services/barometer_aggregation.py:11` still documents the old threshold and spread contract. The module docstring says the thresholds match phone-sensor with `CROSS_STATION_SPREAD_THRESHOLD_HPA=0.4`, says the cross-station aggregation is the ordinary median, and says the spread gate is literal `max - min`, "not stddev, not IQR" at `backend/app/services/barometer_aggregation.py:25` and `backend/app/services/barometer_aggregation.py:31`. This PR changes the load-bearing API contract to a distance-weighted median, weighted 2σ spread, and 0.7 hPa threshold. The executable code is updated, but the primary algorithm description at the top of the service now contradicts it. Fix that docstring before merge so future maintainers and reviewers do not read the wrong wire semantics from the source file.

## What Needs Attention

The E2E HOLD fixture is internally inconsistent: `tests/e2e/settings.spec.ts:427` sets `cross_station_spread_hpa: 0.34` while the threshold fixture is 0.7, but `recommendation.skip_reason` is `cross_station_disagreement`. Real backend output should not produce that combination. It does not break production because the UI trusts the backend decision, but it weakens the E2E as a realistic fixture; consider setting the fixture spread above 0.7 so the rendered gate badges and diagnostic agree.

Several backend test comments still mention the old 0.4 hPa max-min threshold even where the assertions now exercise the weighted 0.7 hPa statistic. These are not executable failures, but they are the same class of review hazard as the service docstring and should be cleaned up with the doc fix.

## Bloat / Non-Functional

None.

## Recommendations

Update the service module docstring to describe the new algorithm in the same terms as the code: per-station medians, iterated MAD, distance-weighted median for the write value, weighted 2σ spread for the HOLD gate, 0.7 hPa threshold, and the cross-station-disagreement-only override.

After updating the comments/fixture, rerun the same focused checks: `python3 -m py_compile backend/app/services/barometer_aggregation.py backend/app/api/station.py`, `cd backend && python3 -m pytest ../tests/backend/test_barometer_aggregation.py -q`, and `cd frontend && npx tsc --noEmit`.

## Bottom Line

Revise before merge. The implementation logic satisfies the requested weighted-median, weighted-spread, survivor-count, override, API, frontend, and station-limit contracts, but the load-bearing source documentation still states the old algorithm and threshold.

