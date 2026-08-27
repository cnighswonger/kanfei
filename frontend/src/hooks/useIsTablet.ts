import { useState, useEffect } from "react";

/**
 * 768–1213 CONTENT-width middle tier — Design v54 §8.  The zone
 * between the phone composition (content ≤768) and the desktop
 * scaled grids (content ≥1214) where the ``--kt`` width term is
 * below its floor but the desktop tile bands are still nominally
 * in force.  The middle-tier composition pairs the three- and
 * four-up bands into two columns and drops the chart to full
 * width, at natural type sizes rather than ``st()``.
 *
 * The viewport bounds compensate for the fixed 220 px desktop
 * sidebar that AppShell renders at viewport > 768.  The design
 * spec's 768–1213 numbers describe DASHBOARD CONTENT width, not
 * viewport — the mock is content-only, with no chrome — so:
 *
 *   viewport - 220 (sidebar) = content
 *   content 769 → viewport 989
 *   content 1213 → viewport 1433
 *
 * The lower bound (min-width: 989px) is the load-bearing edit
 * from PR #512 R1: firing at 769px viewport put the reused
 * desktop tiles into a 549 px content strip they can't fit.
 *
 * Same shape as ``useIsMobile``: lazy initial matchMedia + a
 * listener that keeps the boolean in sync across viewport
 * resizes.
 */
const TABLET_QUERY = "(min-width: 989px) and (max-width: 1433px)";

export function useIsTablet(): boolean {
  const [isTablet, setIsTablet] = useState(
    () => window.matchMedia(TABLET_QUERY).matches,
  );

  useEffect(() => {
    const mql = window.matchMedia(TABLET_QUERY);
    const handler = (e: MediaQueryListEvent) => setIsTablet(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);

  return isTablet;
}
