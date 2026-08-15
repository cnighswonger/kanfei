# Review: PR #371 AlmanacTile data unpacking + tile overflow clip

Date: 2026-08-15
Reviewed: PR #371 head commit a7a609169c9e4ea674dbb13d539025e4399f503d
Round: 1
Label applied: changes-requested

## What Is Correct

The AlmanacTile data fix matches the backend contract. `backend/app/api/astronomy.py` formats computed sun times through `_fmt_time`, formats console override times through `_fmt_hhmm_console`, and returns `sun.sunrise` / `sun.sunset` as display strings. The same response returns `moon.illumination` from `moon.illumination_pct`, which the existing Astronomy page already treats as a 0-100 percentage. Removing the local `new Date(...)` parsing and the extra `* 100` in `frontend/src/components/tiles/AlmanacTile.tsx` is correct.

No stale `fmtTime` references remain under `frontend/src`, `backend/app/api`, or `tests`.

Normal-mode `overflow: hidden` on the grid child is consistent with the stated SolarUVGauge containment goal: the normal-mode wrapper owns only tile content and has no edit controls or external affordances.

## Blockers

1. `frontend/src/dashboard/SortableTile.tsx:139` adds `overflow: "hidden"` to the edit-mode sortable wrapper, but that same wrapper contains `ResizeHandle`. `frontend/src/dashboard/ResizeHandle.tsx:69`-`73` positions the handle at `right: -4` with an 8px hit area, and its 4px visual grip is centered in that area. With parent overflow hidden, the right half of the handle and grip is clipped. This is a user-visible edit-mode regression in the resize affordance and directly contradicts the intended verification point for resize handles. Please clip the oversized tile content without clipping edit-mode controls, for example by moving the clipping to a content-only inner wrapper or by making the resize handle fully internal to the sortable wrapper.

## What Needs Attention

None beyond the blocker.

## Bloat / Non-Functional

None.

## Recommendations

Keep the AlmanacTile changes. For the overflow fix, separate the tile-content clipping boundary from the edit chrome boundary so drag/remove/span controls and the resize handle remain fully visible while over-tall tile internals cannot spill into neighboring grid cells.

## Bottom Line

Request changes. The backend astronomy shape and removed helper are clean, and the normal-mode clipping fix is directionally right, but edit mode currently clips the resize affordance.
