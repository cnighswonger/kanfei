# Review: PR 370 row-gap inflation and REVIEW-03 dial fixes

Date: 2026-08-15
Reviewed: PR #370 (`ui(dashboard): fix row-gap inflation + REVIEW-03 dial fixes (PR 26)`) at `1d6314a2b95d5bd91ada4bb05e3039e6d5f441ee`
Round: 1
Label applied: changes-requested

## What Is Correct

The desktop grid change fixes the core row-gap arithmetic. `DashboardGrid` now uses `columnGap: 16px` and `rowGap: 0` (`frontend/src/dashboard/DashboardGrid.tsx:187`), so explicit row starts resolve against the intended 8 px auto-row unit. A tile at `gridRow: 27 / span 30` starts at `(27 - 1) * 8 = 208px` and ends at `208 + 30 * 8 = 448px`; the right-column barometer at `gridRow: 1 / span 56` occupies `56 * 8 = 448px`. Because the tile wrappers use `paddingBottom: GAP` with `boxSizing: "border-box"` (`frontend/src/dashboard/DashboardGrid.tsx:308`, `frontend/src/dashboard/SortableTile.tsx:138`), the visible card content is reduced by 16 px and the gutter stays inside the cell rather than overlapping the following row.

The horizontal gap math is preserved. `tilePixelWidth()` still models 12 columns with 11 column gaps (`frontend/src/dashboard/DashboardGrid.tsx:136`), and the grid now keeps `columnGap: GAP`, so a 3-column tile still occupies 3 tracks plus 2 internal gaps.

`SortableTile` matches normal-mode wrapper sizing, and the edit overlay remains absolutely positioned with `inset: 0` (`frontend/src/dashboard/SortableTile.tsx:145`), so it fills the whole grid cell rather than being inset by the new padding.

The barometer change is consistent with the design handoff. When pressure data is null, `inHgValue` still defaults to `29.92` (`frontend/src/components/gauges/BarometerDial.tsx:78`), `wheelDial()` clamps and returns finite tip/trend points (`frontend/src/utils/gauges.ts:56`), and the always-rendered trend hand has valid coordinates (`frontend/src/components/gauges/BarometerDial.tsx:154`).

The wind compass sizing is internally consistent: `RING_SIZE = 220`, center is `110`, and `compass(cx, cy, 80, 98)` matches the requested geometry (`frontend/src/components/gauges/WindCompass.tsx:28`, `frontend/src/components/gauges/WindCompass.tsx:53`).

Verification run locally:

- `cd frontend && npx tsc --noEmit` — passed
- `cd frontend && npm run build` — passed, with only the repo-documented non-blocking Vite chunk-size warning

## Blockers

1. Mobile still gets per-row grid-gap inflation because the mobile stylesheet overrides the new inline `rowGap: 0`.

   `frontend/src/index.css:206` sets `.dashboard-grid { gap: 10px !important; }` inside the mobile media query. That author-level `!important` declaration overrides the normal inline `rowGap: 0` / `columnGap: 16px` style from `DashboardGrid`. On mobile, each 8 px auto-row line therefore still has a 10 px row gap between it, so a `rowSpan: 26` tile computes as `26 * 8 + 25 * 10 = 458px` before the newly added 16 px bottom padding is applied. This leaves the same class of inflated row-height bug in the mobile branch and makes the padding addition non-harmless there.

   Fix by splitting the mobile rule the same way as desktop, for example `column-gap: 10px !important; row-gap: 0 !important;`, and keep the per-tile bottom padding as the visual vertical gutter. If mobile wants a 10 px gutter rather than 16 px, the wrapper padding also needs a mobile-specific value; the important part is that CSS Grid row gaps must stay at zero with an 8 px auto-row unit.

## What Needs Attention

None beyond the blocker.

## Bloat / Non-Functional

None. The implementation is narrow and mechanical.

## Recommendations

After fixing the mobile cascade, add a quick browser/computed-style smoke check at a mobile viewport: `.dashboard-grid` should report `row-gap: 0px`, and a tile with `rowSpan: 26` should have a grid cell height of 208 px with the visible card content ending 16 px above the cell bottom.

Nit: the new inline comments reference `REVIEW-03` in production source (`frontend/src/dashboard/DashboardGrid.tsx:181`, `frontend/src/components/gauges/BarometerDial.tsx:149`, `frontend/src/components/gauges/WindCompass.tsx:26`). This codebase already has some design-document comments, so I am not blocking on it, but current-task references in source tend to age poorly. Prefer keeping the arithmetic explanation without naming the review round.

## Bottom Line

Request changes. The desktop fix, dial changes, and build verification are good, but the mobile media rule still overrides `rowGap: 0`, preserving the original row-gap inflation on the mobile path the review explicitly asked us to verify.
