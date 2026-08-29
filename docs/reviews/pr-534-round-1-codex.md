# Review: PR #534 Nerd Chart Right-Axis Padding

Date: 2026-08-29
Reviewed: `frontend/src/dashboard/WeatherNerdDashboard.tsx` at `9004d8f8c69be24262071f9ad465a79f8a0f27f4`
Round: 1
Label applied: `approved-by-codex-agent`, `reviewed-by-codex-agent`

## What Is Correct

The module-level `PR` constant is removed, and the only remaining `PR` definition is the local `const PR = compact ? 96 : 52;` inside `NerdChartTile`. A repository search found no dangling chart references to the old module-level value.

Desktop behavior remains geometrically identical for this change: when `compact` is false or undefined, `PR` resolves to `52`, matching the prior module constant. The existing `pathFor(...)` calls, gridline endpoint, axis baseline, right-axis label width, and x-axis right offset all consume that local value.

Compact behavior moves the pressure label band and plot boundary together. At phone width, `PR = 96` widens the right label band from `52 / 660` to `96 / 660` of the chart wrapper while changing the plot right edge from `CW - 52` to `CW - 96`. That pulls the pressure trace, gridline endpoint, baseline endpoint, and x-axis labels inward with the right label band instead of only widening text space.

## Blockers

None.

## What Needs Attention

None.

## Bloat / Non-Functional

None. The change is narrowly scoped to the local chart geometry constant and has no new abstraction or alternate render path.

## Recommendations

None.

## Verification

Ran `npx tsc --noEmit` from `frontend/`; it passed.

## Bottom Line

Approve. The local compact-aware right padding fixes the mobile pressure-label overrun without changing desktop geometry, and all relevant chart coordinate consumers pick up the same local value.

— Codex, cross-LLM review, round 1
