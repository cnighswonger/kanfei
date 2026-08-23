# Review: PR #481 frontend stalled Last Poll badge

Date: 2026-08-23
Reviewed: `frontend/src/components/panels/StationStatus.tsx` at `0f40c0ddb60ae149d4b42765d62c3da0242d9899`
Round: 1
Label applied: `approved-by-codex-agent`, `reviewed-by-codex-agent`

## What Is Correct

The stalled-link badge is scoped to the existing StationStatus Last Poll row and does not depend on fresh station status messages to advance. The separate 10 s interval is keyed by `stationStatus?.last_poll`, so a frozen non-null timestamp continues to re-render and age into warning/danger, while a transition to `null`/`undefined` cleans up the interval through the effect dependency change.

The threshold shape is operator-reasonable for this UI surface: `3 * poll_interval` handles the normal configured cadence, the 180 s fallback avoids a human-facing false alarm when no interval is available, and the 900 s danger threshold gives a distinct "probably wedged" state. I would not make the fallback 30 s in this frontend component unless the backend contract guarantees that `poll_interval` is unavailable only in a state where a 30 s warning is actionable. In the current `/api/station` shape, normal connected status carries `poll_interval`, and degraded status carries no `last_poll`, so the fallback is mostly an edge guard.

Computing `Date.now()` inline in render is acceptable here. The component already re-renders from the station-clock tick, and this added tick is low-frequency. There is no meaningful performance or lint concern from reading the clock during render for display-only derived state.

The suffix-on-value approach should not break the existing layout in the usual desktop/mobile modal widths. The row value is already a text span inside a wrapping-capable flex/grid layout, and the suffix contains spaces where the browser can wrap if needed.

I searched for other frontend references to `Last Poll` and `last_poll`; this StationStatus row is the only rendered timestamp carrying that field on main, so there is no second frontend display that needs the badge in this PR.

Verification run:

```text
cd frontend && npx tsc --noEmit
```

## Blockers

None.

## What Needs Attention

Non-blocking: the comments in this PR say the warning threshold matches `/api/health`, but this checkout does not contain an `/api/health` route on `main` or in this PR diff. If #473 lands separately with a different fallback, update the comment or constants then so the frontend does not document a contract that is not present in this branch.

## Bloat / Non-Functional

None blocking. The new comments are more expansive than this component normally needs, but they do capture the operator-facing threshold reasoning and are not enough to hold the PR.

## Recommendations

Keep the 180 s fallback for the frontend unless the backend health route becomes a shared API contract that requires identical fallback semantics. The frontend is read by a human and already has `poll_interval` for the normal path.

## Bottom Line

Approve. The implementation answers the stalled-poller UX gap without introducing a render-loop or cleanup problem. The only caveat is to keep the `/api/health` wording aligned when that backend route is actually present in the target branch.

— Codex, cross-LLM review, round 1
