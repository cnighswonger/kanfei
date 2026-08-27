import { useState, useEffect } from "react";

/**
 * 768–1213 middle tier — Design v54 §8.  The zone between the phone
 * composition (≤768) and the desktop scaled grids (≥1214) where the
 * ``--kt`` width term is below its floor but the desktop tile bands
 * are still nominally in force.  The middle-tier composition pairs
 * the three- and four-up bands into two columns and drops the chart
 * to full width, at natural type sizes rather than ``st()``.
 *
 * ``min-width: 769px`` is deliberately inclusive of the mobile floor
 * plus one — the phone tier owns exactly 0 through 768, this owns
 * the immediate next pixel.  Same shape as ``useIsMobile``: lazy
 * initial matchMedia + a listener that keeps the boolean in sync
 * across viewport resizes.
 */
const TABLET_QUERY = "(min-width: 769px) and (max-width: 1213px)";

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
