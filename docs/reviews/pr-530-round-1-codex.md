# Review: PR #530 Weather Nerd phone below-divider compact

Date: 2026-08-27
Reviewed: PR #530 (`frontend/src/dashboard/WeatherNerdDashboard.tsx`) at `0f39da42bb1cc937584ed841c9935941c0fb84ef`
Round: 1
Label applied: approved-by-codex-agent, reviewed-by-codex-agent

## What Is Correct

The PR is scoped to the commissioned items 1, 3, and 5. The only changed file is `frontend/src/dashboard/WeatherNerdDashboard.tsx`, and the compact props are only passed from the phone shell for `NerdChartTile` and `WindRoseTile`.

`NerdChartTile` keeps the `compact=false` path as the existing row layout: `flexDirection: 'row'`, `alignItems: 'baseline'`, and the desktop/tablet call sites do not pass `compact`. A browser render probe at 1100 px and 1600 px confirmed the heading and controls remain on the same baseline row, with the resolution group and CSV button aligned horizontally. At 390 px, the heading stacks above the controls, and the controls wrap inside the tile instead of causing document overflow.

`WindRoseTile` correctly removes only the radial dial in compact mode. A phone render showed no Highcharts wind-rose container and the caption immediately below the heading (`S dominant · 8 mph mean · 13 peak` in the fixture data). Tablet and desktop renders still included the Highcharts dial, so the non-phone paths are unchanged in behavior.

The `overflowX: 'hidden'` change is applied to `WeatherNerdMobileShell`. Tablet shell styles were unchanged and computed as non-hidden horizontal overflow in the render probe; desktop already had its own existing `overflow: 'hidden'` on the outer main, so this PR does not newly route the mobile shell rule into tablet or desktop.

The explicit non-applied items check holds. `SolarEnergyTile` remains unchanged and its footer uses `mono` 20 figures, not hero-scale type. `ConsoleExtremesTile` already has the `compact` single-column grid for phone/tablet use, and the phone shell continues passing `compact`. I did not find an additional below-divider hero-scale figure, phone chip-pair overlap, or missed Console two-column pattern in the touched Weather Nerd body.

## Blockers

None.

## What Needs Attention

None.

## Bloat / Non-Functional

None.

## Recommendations

No follow-up required for this PR. The comments are verbose, but they document existing design constraints in the same style as the surrounding file and are not introducing extra runtime abstraction.

## Verification

- `cd frontend && npm run build` passed. Vite emitted only the repo-documented non-blocking chunk-size warning.
- `cd frontend && npx tsc --noEmit` passed.
- Local Playwright/Chromium render probe against the e2e fixture DB checked 390 px phone, 1100 px tablet, and 1600 px desktop for responsive shell selection, document horizontal overflow, chart heading/control layout, and compact/non-compact wind-rose dial presence.

## Bottom Line

Approve. The implementation matches the commissioned Weather Nerd phone compact items without leaking the compact behavior into tablet or desktop, and the explicitly skipped items are not present in the inspected tile bodies.

— Codex, cross-LLM review, round 1
