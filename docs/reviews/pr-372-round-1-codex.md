# Review: PR 372 ui dashboard minHeight pivot

Date: 2026-08-15
Reviewed: PR #372 against `ui/refactor` at `f73afb0cbd5ddf3c759ed31b8524792913d56efb`
Round: 1
Label applied: `approved-by-codex-agent`

## What Is Correct

- `DashboardGrid` now uses `gridAutoRows: "min-content"`, `alignItems: "start"`, and a normal grid gap. With the remaining explicit `gridColStart` values, CSS Grid auto-placement places each item into the first row where its requested column range fits. Row height is still shared by cells that occupy the same row, and each row is sized by the tallest item/min-height contribution in that row; rows are no longer coupled by the previous fixed 8-px row-span lattice.
- Legacy layouts with `rowSpan` / `gridRowStart` continue to parse. `parseLayout` preserves known tile placement objects other than filtering unknown tile IDs, and rendering ignores the legacy fields.
- `stripPins` correctly strips `gridColStart` and `gridRowStart` while preserving `minHeight`. `minHeight` is a tile floor, not a placement pin, so keeping it after reorder/resize/add/remove is the right behavior.
- `HeroTemperatureTile` reads `theme.type.display`, `title`, and `sectionLabel` directly and applies `fontStyle: display.italic ? "italic" : "normal"` to the hero value. Calling `useTheme()` here is consistent with the existing context model and only re-renders this tile on the same theme updates that already re-render theme consumers.
- `HistoryChartTile` computes `softMin` / `softMax` from both temperature and dew-point points inside the existing `useMemo`. The recomputation cadence is tied to the point arrays and is reasonable for 5-minute history refreshes. The predicate `(v): v is number => v != null && Number.isFinite(v)` correctly narrows nullable values to finite numbers.
- `data-dashboard-grid`, normal-mode `data-tile-id`, edit-mode `data-tile-id`, and `data-role="hero-value"` are present on the paths queried by `verify-dashboard.js`.
- `frontend/public/verify-dashboard.js` is copied into `frontend/dist/verify-dashboard.js` by the Vite production build.

## Blockers

None.

## What Needs Attention

None material.

## Bloat / Non-Functional

Nit: `frontend/src/dashboard/tileRegistry.ts` still exports `GRID_ROW_UNIT_PX` / `DEFAULT_ROW_SPAN` with row-span-era comments, and `frontend/src/dashboard/SortableTile.tsx` still has a stale comment saying the wrapper passes through `style.gridRow`. These are harmless in this PR because no rendering path imports or uses the constants, but they should be cleaned up in a follow-up to avoid confusing the next layout change.

## Recommendations

- Optional cleanup: remove the unused row-span constants or explicitly mark them legacy-only, and update the stale `SortableTile` comment.

## Bottom Line

Approved. The structural min-height pivot, legacy layout behavior, data attributes, hero type-role path, chart y-domain change, and public verify script all check out. The remaining issues are documentation/dead-code nits, not merge blockers.
