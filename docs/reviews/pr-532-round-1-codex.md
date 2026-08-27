# Review: PR #532 mobile overflow cleanup

Date: 2026-08-27
Reviewed: `frontend/src/dashboard/AgricultureDashboard.tsx`, `frontend/src/dashboard/WeatherNerdDashboard.tsx` at `421c39508da268f7727244505db9393e2941a0c1`
Round: 1
Label applied: `approved-by-codex-agent`, `reviewed-by-codex-agent`

## What Is Correct

The Ag mobile Best today / Next window pair now allows both values to wrap naturally and gives both grid children `minWidth: 0`, which removes the previous right-edge clipping path without changing the surrounding two-column layout.

The WaterBalance histogram labels are anchored into explicit 1/2/1 flex columns with left/center/right alignment. That preserves the desktop visual intent while preventing the center peak label from colliding with `now` at phone width.

The FieldSchedule compact grid is correctly gated behind the new optional `compact` prop and is only passed from the Agriculture mobile shell. In compact mode, indices 0 and 2 suppress `borderLeft`, indices 1 and 3 keep the row-internal left hairline, and indices 2 and 3 receive the second-row top hairline. In non-compact mode, the original four-column grid and first-cell-only `borderLeft: none` behavior remain intact.

The Nerd chart heading shortens only when `compact` is true, and the JSX string uses a literal `&` character rather than an escaped `&amp;` entity. `ChartButtonGroup` now permits wrapping while leaving the desktop inline-flex behavior benign at ordinary desktop widths.

## Blockers

None.

## What Needs Attention

None.

## Bloat / Non-Functional

None.

## Recommendations

No changes required for this round.

## Verification

Ran `npx tsc --noEmit` from `frontend/`; it passed.

I did not run backend pytest because this PR only changes frontend TSX layout code and does not touch backend Python paths.

## Bottom Line

Approve. The five requested phone overflow fixes are scoped to compact/mobile paths where intended, the desktop paths are unchanged in behavior, and the FieldSchedule compact border rules match the requested 2x2 layout.

— Codex, cross-LLM review, round 1