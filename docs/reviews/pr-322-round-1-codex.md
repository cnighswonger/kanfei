# Review: PR 322 RX Diagnostics tile

Date: 2026-08-13
Reviewed: PR 322 diff at `ef0479f0b659bdf516bb5935304724abb580cb83`
Round: 1
Label applied: changes-requested

## What Is Correct

The checkout was verified at the PR head SHA before review. The PR touches only the four expected files: `frontend/src/components/panels/RxDiagnostics.tsx`, `frontend/src/pages/About.tsx`, `frontend/src/api/client.ts`, and `frontend/src/api/types.ts`.

The reception-rate denominator matches the existing Settings tile in `frontend/src/components/settings/SignalQuality.tsx`: `packets_received / (packets_received + missed)`. The existing component explicitly documents that `resync` and `crc_errors` describe handling of received packets and would double-count if included in the denominator.

The partial-result path for `signal-quality` success plus `radio-state` 501 is structurally correct: the radio status becomes `unsupported`, the reception status becomes `loaded`, and the render shows the reception section without a radio section.

The `RadioState` interface matches the observed backend wire shape documented by `tests/backend/test_vantage_opmode.py` and `backend/app/protocol/vantage/driver.py`: `TST`, `TX`, `RX`, `HOP`, `BAND`, `CHAN`, `DOM`, `XTLCAL`, `TEMP`, and normalized `TEMP_CAL`. The fields are optional, which matches the driver behavior of dropping malformed individual fields.

The parallel fetch handling avoids the specific stuck-loading case where one endpoint rejects and the other resolves: both promises are converted to result objects before `Promise.all`, and both statuses are assigned after the await.

`cd frontend && npx tsc --noEmit` passes at the reviewed SHA.

## Blockers

1. `frontend/src/components/panels/RxDiagnostics.tsx:104` - `load()` can set state after the component has unmounted.

   Failure scenario: About mounts and starts both station reads; the user navigates away while either request is still in flight. When both promises settle, `load()` continues through `setHidden`, `setRx`, `setRxStatus`, `setRadio`, `setRadioStatus`, and `setReadAt` even though the component instance is gone. These station endpoints can wait up to 20 seconds behind the serial lock, so this is not just a narrow timing window. Add a cleanup/cancellation guard around the initial effect path, or otherwise prevent post-await state writes after unmount.

## What Needs Attention

None beyond the blocker.

## Bloat / Non-Functional

No blocking bloat found. The modified existing files are small additive wire-ins; the large addition is the new panel component. No dead exports or unused state were found in the reviewed diff.

## Recommendations

Keep the radio-state partial-result behavior as implemented. Do not include `resync` or `crc_errors` in the reception-rate denominator; the Settings tile already documents why that would double-count.

## Bottom Line

Revise before merge. The data shape and partial-result behavior are sound, but the new long-running mount fetch needs unmount-safe state handling before this tile should ship.
