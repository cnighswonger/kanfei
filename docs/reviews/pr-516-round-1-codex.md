# Review: PR 516 Everyday Tablet Composition

Date: 2026-08-27
Reviewed: `frontend/src/dashboard/EverydayDashboard.tsx` at `45fbc06dd4994c37d86ea342548da10b09b1ee3b`
Round: 1
Label applied: `changes-requested`

## What Is Correct

The branch selection order is correct: the existing phone shell still wins first, then the new tablet shell handles `useIsTablet()`, and the desktop path remains the fallback. The shared hook keeps the same 989-1433 viewport bounds established in phase 4a, so the intended content-width tier maps to 769-1213 px after the fixed 220 px sidebar.

The new shell follows the same primitive shape as phase 4a: `data-tablet`, `--k` / `--kt` hoisted to `1px`, natural tile bodies, scrollable shell, no corner plate, and two-column rows with 20 px gaps. In the 989 px viewport probe, the tablet branch activated and the reused tile bodies did not report horizontal overflow; the hero / derived / barometer split produced 351 px columns with no scroll-width overrun.

## Blockers

1. `frontend/src/dashboard/EverydayDashboard.tsx:486` renders the full-width history chart without restoring the height contract that the desktop layout gives it via `style={{ minHeight: s(357) }}`. `HistoryChartTile` depends on a parent height because its plot area is a `flex: 1` child with `minHeight: 0`; with no explicit height/min-height in the new tablet shell, the tile collapses to about 61 px tall in a 989 px viewport. The requested §8 composition says "chart - full width", but the rendered tablet tier shows only the heading/empty-state strip rather than a usable full-width chart panel. Pass an explicit minHeight/height for the tablet chart so it retains a real plotting area at natural scale.

## What Needs Attention

The 989 px lower-bound probe did not find clipping or horizontal overflow in the hero, derived, barometer, wind, almanac, rain, solar, rainfall, or console tiles. Boundary checks also matched the stated policy: 988 px remained non-tablet, 989-1433 px used `data-tablet`, and 1434 px returned to desktop. The known 769-988 desktop fit gap remains pre-existing and is not expanded by this PR.

## Bloat / Non-Functional

None. The implementation is additive but narrowly scoped to one shell and reuses the existing tile bodies and tablet hook.

## Recommendations

After fixing the chart height, re-run the same 989 px viewport probe with live fixture data and inspect the screenshot. The dials and hero tile fit the columns in the current render, so the likely fix is localized to the chart tile call rather than a broader shell rewrite.

## Bottom Line

Revise before merge. The breakpoint and two-column composition are otherwise consistent with phase 4a, but the tablet chart currently loses its visual body because the new shell dropped the desktop height/min-height contract.
