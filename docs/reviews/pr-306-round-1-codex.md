# Review: PR #306 barometer aggregate apply wiring

Date: 2026-08-12
Reviewed: PR #306 (`fix/wire-aggregate-apply`) at `6349b8207233fdadd492473111bf5ba6875cf61b`
Round: 1
Label applied: changes-requested

## What Is Correct

The aggregate-to-parent contract shift is implemented correctly. `BaroCalibrationAggregate` now types `onApplyRecommendation` as an absolute target pressure callback and invokes it with `recommendation.median_of_medians_thousandths_inhg`, not `recommendation.offset_thousandths_inhg`.

The parent forwards that value unchanged into the existing `write()` path, and `write()` still calls `setBarometerCalibration(barThousandths, Math.round(elevationNum))`. That matches the backend/client contract: `setBarometerCalibration` posts `bar_thousandths_inhg`, which is the absolute BAR target, while `0` remains the explicit clear-offset sentinel.

The environment gate is composed correctly for the code path under review: the callback is withheld unless the console read and reference fetch are loaded, location is configured, elevation is valid, the console snapshot is fresh, and no write is in progress. The aggregate component separately requires `recommendation.should_apply` and a non-null median-of-medians before rendering the button, so I do not see a route for the button to render when either the aggregate gates or the parent environment gates fail.

The backend contract was not changed in this PR. The diff is limited to `frontend/src/components/settings/BaroCalibrationAggregate.tsx` and `frontend/src/components/settings/BarometerCalibration.tsx`; `/api/station/barometer-reference` still returns both `references` and `aggregate`.

The elevation reconcile flow remains intact. The input still seeds from the console snapshot when untouched, validation still feeds the shared `write()` path, and the "use Kanfei's" button still updates the same `elevationFt` state used by apply and clear.

The clear-offset path remains intact: `handleClear()` still gates on elevation validity and `applying`, confirms with the operator, and calls `write(0, "Offset clear")`.

## Blockers

Active Playwright coverage for this panel was not updated for the removed single-station UI, and the targeted E2E group now fails. `tests/e2e/settings.spec.ts:350`, `tests/e2e/settings.spec.ts:366`, `tests/e2e/settings.spec.ts:385`, `tests/e2e/settings.spec.ts:462`, and `tests/e2e/settings.spec.ts:493` still assert the old radio-picker / stale-reference / `Apply Calibration` flow that this PR removes. This is not just dead text: I ran `KANFEI_E2E_PORT=8876 npx playwright test settings.spec.ts --grep "Barometer calibration panel" --reporter=line` and got 5 failed / 3 passed. The failures are all stale expectations around the removed picker or missing aggregate fixture data, including `getByRole('button', { name: 'Apply Calibration' })` and the old `KHRJ` single-station row.

Update this spec to cover the new aggregate write path instead: fixtures should include an `aggregate` object with a passing recommendation, the apply test should click `Use recommended offset`, and the intercepted POST should assert that `bar_thousandths_inhg` equals `median_of_medians_thousandths_inhg` rather than the signed offset delta. The location, stale/fetch-failure, and rejected-write tests should be rewritten around callback-withheld / aggregate-hidden behavior instead of the removed disabled `Apply Calibration` button.

## What Needs Attention

The implementation intentionally hides the aggregate apply button when parent environment state is not ready. That is consistent with the stated design, and the nearby UI still explains the major missing prerequisites: no location, reference fetch error/loading, stale console snapshot, and invalid non-empty elevation. I do not consider this a blocker.

## Bloat / Non-Functional

None. The production diff is mostly deletion and removes the old single-station state instead of carrying it forward.

## Recommendations

After updating the E2E spec, run the same targeted command on an alternate port if `8765` is occupied:

`KANFEI_E2E_PORT=8876 npx playwright test settings.spec.ts --grep "Barometer calibration panel" --reporter=line`

Also keep `npx tsc --noEmit` in the verification set; it passed in this review.

## Bottom Line

Request changes. The runtime wiring matches the intended absolute-pressure BAR contract, and I found no backend churn or clear/ elevation regression in the changed components. The PR should not merge until the active barometer-calibration E2E tests are updated to the new aggregate-only flow and pass.
