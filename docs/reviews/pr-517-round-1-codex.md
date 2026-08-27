# Review: PR 517 Weather Nerd Tablet Tier

Date: 2026-08-27
Reviewed: `frontend/src/dashboard/WeatherNerdDashboard.tsx` at `a1233a238e40073c43d266aedb88c62d714ab17e`
Round: 1
Label applied: `changes-requested`

## What Is Correct

The tablet fork is ordered after the mobile fork, so the 989-1433 viewport tablet window does not steal the <=768 phone composition. The `useIsTablet` hook keeps the same viewport math established by phases 4a/4b: 989-1433 viewport with the fixed 220 px sidebar corresponds to 769-1213 dashboard content.

The Nerd chart does not have the same collapse mode as Everyday's `HistoryChartTile`: `NerdChartTile` already gives the outer tile `minHeight: s(341)` and the plot area has `height`/`minHeight: s(250)`. Passing `style={{ minHeight: 341 }}` from the tablet shell is redundant but harmless because React treats the numeric value as px and it preserves the same minimum height.

The 2x2 stat grid uses the existing `StatCell` behavior. Pressure suppresses its left border and ForecastAgreement does not, so the bottom-left cell gets an extra separator compared with the top-left cell. That is a cosmetic mismatch in the current stat-card API, not a functional blocker for this PR.

Passing `compact` from the phone shell is the right direction. The phone shell reuses the same desktop `ConsoleExtremesTile` below the divider, and the prior two-column internal grid is exactly the narrow-width clipping mode that §9 is meant to remove.

## Blockers

1. `compact` does not actually render the advertised eight hairline-separated rows. `ConsoleExtremesTile` changes the grid at `frontend/src/dashboard/WeatherNerdDashboard.tsx:864` to `1fr`, but both calibration rows still pass `last` at `frontend/src/dashboard/WeatherNerdDashboard.tsx:880` and `frontend/src/dashboard/WeatherNerdDashboard.tsx:896`. In the original two-column grid that made sense because those two rows formed the visual bottom row. In compact one-column flow, `Baro offset` becomes the seventh row, so its `last` prop drops the separator between row 7 and row 8. The clipping fix is mostly there, but the §9 requirement described in the PR as "8 hairline-separated rows" is not met on tablet or phone. Make `last` conditional on non-compact for `Baro offset`, or otherwise ensure only the final compact row suppresses the bottom rule.

## What Needs Attention

None beyond the blocker.

## Bloat / Non-Functional

None. The change is a one-file composition fork and a narrowly scoped tile prop. The extra `style` prop on `NerdChartTile` is not strictly necessary for this PR, but it is small and mirrors the phase-4b fix pattern without adding a new abstraction.

## Recommendations

After fixing the compact-row separator, rerun `cd frontend && npx tsc --noEmit` and `cd frontend && npm run build`. The build's Vite chunk-size warning is the known non-blocking warning for this repo.

## Bottom Line

Revise. The tablet composition, chart height, threshold math, and mobile use of compact mode are sound, but compact mode needs one small correction before this can satisfy §9's single-column console-extremes collapse.
