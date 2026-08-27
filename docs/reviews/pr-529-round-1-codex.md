# Review: PR #529 mobile Agriculture compact tiles and Everyday color restore

Date: 2026-08-27
Reviewed: `frontend/src/dashboard/AgricultureDashboard.tsx`, `frontend/src/dashboard/EverydayDashboard.tsx` at `ed83a3c1d87c4e51dae5e2443f62dc84bba394c4`
Round: 1
Label applied: approved-by-codex-agent, reviewed-by-codex-agent

## What Is Correct

The Everyday mobile color restore is scoped to the intended phone shell. The hero `°F` suffix is back on `v.accent`, and `MChip` now accepts an optional `tone` while preserving the old `v.text` fallback. The only new call sites pass `v.danger` for High and `v.sky` for Low.

The Agriculture desktop and tablet paths remain unchanged by call site: desktop band B still renders `<DriftRiskTile d={d} />` and `<WaterBalanceTile d={d} />`, and the tablet shell does the same. Only `AgricultureMobileShell` passes `compact` to the below-divider `WaterBalanceTile` and `DriftRiskTile`.

At `compact={false}` or omitted, both modified tile bodies preserve the pre-PR rendered structure. `DriftRiskTile` still renders the dial column, top wind numeric readout, min-height, and peak/gust border-top. `WaterBalanceTile` still renders the top balance hero figure and label. The compact conditionals are gated so the existing non-compact behavior remains intact.

The Drift compact behavior matches the focus item: compact mode removes both the dial column and the top numeric wind readout, while retaining direction detail, peak/gust rows, and the gust histogram. The peak/gust block's border-top and padding are removed only in compact mode, so the compact tile does not leave a lone divider rule.

The Agriculture mobile shell now clips horizontal overflow at the shell level, and the below-divider stack passes compact only to the two tiles called out in the PR scope.

The item 5 non-change is confirmed by inspection: Agriculture `TileHeading` usages are single-column/plain headings in this file. The stacked-heading issue from shared compact tile headings does not apply here.

## Blockers

None.

## What Needs Attention

None blocking. The new explanatory JSX comments are longer than this code usually needs, but they document the mobile layout constraint and do not change behavior.

## Bloat / Non-Functional

None.

## Recommendations

No code changes requested.

Verification run: `cd frontend && npx tsc --noEmit` passed.

## Bottom Line

Ship it. The PR is narrowly scoped, preserves desktop/tablet behavior, and implements the requested Agriculture phone compact behavior without breaking the existing tile bodies.

— Codex, cross-LLM review, round 1
