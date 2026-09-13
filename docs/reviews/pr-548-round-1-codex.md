# Review: PR #548 rain peak labels

Date: 2026-09-13
Reviewed: `frontend/src/dashboard/tiles.tsx`, `frontend/src/dashboard/AgricultureDashboard.tsx` at `618d743cb06aede338a85e66e7ae405f7b8ed83b`
Round: 1
Label applied: approved-by-codex-agent, reviewed-by-codex-agent

## What Is Correct

The `rawMax` / `scaleMax` split is correct in both changed tiles. `rawMax` is still computed from the same hourly bar shape as before, `bars.map((b) => b?.in ?? 0)`, so populated bar arithmetic is unchanged except that labels now read the real data maximum instead of the chart floor.

The dry-day path now behaves correctly in `RainfallByHourTile`: when all bars are empty or zero, `rawMax` is `0`, the header renders `peak 0.00 in/hr`, the relative-axis label renders `no rain recorded`, and `peakIdx` is explicitly `-1`, so the first zero bar cannot be mistaken for a peak time.

The SVG scaling remains protected from zero division. Both tiles keep `scaleMax = Math.max(0.05, rawMax)`, and each render loop only divides when `val > 0`, so an all-zero bar array renders zero-height bars without dividing by zero or inventing a visible peak.

## Blockers

None.

## What Needs Attention

None.

## Bloat / Non-Functional

None.

## Recommendations

None.

## Verification

Ran `cd frontend && npx tsc --noEmit` successfully. I did not find focused frontend component tests for these tiles; the type check is the applicable verifier for this TSX-only change.

## Bottom Line

Approve. The fix keeps chart scaling and data labels separate without changing the populated-bar max calculation, and it correctly suppresses the dry-day peak time that the previous floor-coupled logic could imply.

— Codex, cross-LLM review, round 1