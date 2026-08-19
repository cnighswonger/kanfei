/**
 * Section rail — the left column of the Settings page.
 *
 * Design's spec (SETTINGS.md v31): a 250 px column with five group
 * headers.  One group is expanded at a time; expanding a group shows
 * its child sections.  Non-active groups collapse to a single header
 * row — there's no accordion animation, no icon tree, no per-section
 * count summary.  Hierarchy is expressed by the 22 px indent on child
 * rows, nothing else.
 *
 * The Settings page owns the ``activeGroup`` / ``activeSection`` state
 * and the click-to-navigate wiring; this component is presentation
 * only.  Match counts feed the search-hits badge (Phase 2+).
 */

import React from "react";

export interface SectionRailGroup {
  id: string;
  label: string;
  sections: { id: string; label: string; matches?: number }[];
  /**
   * For a leaf group (``sections.length === 0``): match count for the
   * row itself.  Ignored when the group has sub-sections — those sum
   * their own ``matches`` fields into the group badge.
   */
  matches?: number;
}

export const SectionRail: React.FC<{
  groups: SectionRailGroup[];
  activeGroup: string;
  activeSection: string;
  onSelect: (groupId: string, sectionId: string) => void;
  /**
   * Optional auth reminder rendered as a bordered box at the bottom of
   * the rail.  Design v31 SETTINGS.md: "matching the existing auth
   * split" — the rail carries the note whenever an operator might not
   * be signed in yet.  On a private station where the operator is the
   * only user this is a truism, so Settings passes it only in
   * public-mode.
   */
  authNote?: string | null;
}> = ({ groups, activeGroup, activeSection, onSelect, authNote = null }) => (
  <nav
    style={{
      padding: "18px 14px",
      borderRight: "0.8px solid var(--color-border)",
      overflowY: "auto",
      fontFamily: "var(--font-body)",
      display: "flex",
      flexDirection: "column",
    }}
    aria-label="Settings sections"
  >
    <div style={{ flex: 1, minHeight: 0 }}>
    {groups.map((g) => {
      const open = g.id === activeGroup;
      // A group with zero sections is a LEAF: the header IS the row, no
      // children to expand.  Design's v32 review flagged that
      // one-section groups read as "an accordion holding one item" —
      // Appearance now uses a single panel with three cards, and its
      // rail entry should behave like the leaf it is.  Match-badge
      // still surfaces so a search hit on Persona / Theme / Backgrounds
      // still marks the row.
      const isLeaf = g.sections.length === 0;
      const leafSectionId = g.id;
      // Sum of matches across every section in this group, or the
      // leaf's own match count when the group has no sub-sections.
      const groupMatches = isLeaf
        ? (g.matches ?? 0)
        : g.sections.reduce((n, s) => n + (s.matches ?? 0), 0);
      return (
        <div key={g.id}>
          <button
            type="button"
            onClick={() =>
              onSelect(g.id, isLeaf ? leafSectionId : (g.sections[0]?.id ?? ""))
            }
            style={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "8px",
              padding: "8px 10px",
              margin: 0,
              border: "none",
              cursor: "pointer",
              fontFamily: "var(--font-body)",
              fontSize: "calc(13.5px * var(--font-scale))",
              background: open ? "var(--color-text)" : "transparent",
              color: open ? "var(--color-bg)" : "var(--color-text)",
              textAlign: "left",
            }}
          >
            <span>{g.label}</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
              {groupMatches > 0 ? (
                <span
                  style={{
                    fontFamily: "var(--font-mono, var(--font-body))",
                    fontSize: "calc(10px * var(--font-scale))",
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                    padding: "1px 6px",
                    // Accent chip that reads on both the inverted (open)
                    // and default (closed) group backgrounds.  Ink border
                    // when open so the chip has contrast on the ink fill.
                    border: open
                      ? "0.8px solid var(--color-bg)"
                      : "0.8px solid var(--color-accent)",
                    color: open ? "var(--color-bg)" : "var(--color-accent)",
                    borderRadius: 0,
                    background: "transparent",
                  }}
                >
                  {groupMatches}
                </span>
              ) : null}
              {isLeaf ? null : (
                <span style={{ opacity: 0.7 }}>{open ? "▾" : "▸"}</span>
              )}
            </span>
          </button>
          {open &&
            g.sections.map((sec) => {
              const isActive = sec.id === activeSection;
              return (
                <button
                  type="button"
                  key={sec.id}
                  onClick={() => onSelect(g.id, sec.id)}
                  style={{
                    width: "100%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "6px 10px 6px 22px",
                    margin: 0,
                    border: "none",
                    background: "transparent",
                    cursor: "pointer",
                    fontFamily: "var(--font-body)",
                    fontSize: "calc(12.5px * var(--font-scale))",
                    fontWeight: isActive ? 600 : 400,
                    color: isActive ? "var(--color-text)" : "var(--color-text-secondary)",
                    textAlign: "left",
                  }}
                >
                  <span>{sec.label}</span>
                  {sec.matches ? (
                    <span
                      style={{
                        fontFamily: "var(--font-mono, var(--font-body))",
                        fontSize: "calc(10px * var(--font-scale))",
                        letterSpacing: "0.1em",
                        textTransform: "uppercase",
                        color: "var(--color-accent)",
                      }}
                    >
                      {sec.matches}
                    </span>
                  ) : null}
                </button>
              );
            })}
        </div>
      );
    })}
    </div>

    {authNote ? (
      <div
        style={{
          border: "0.8px solid var(--color-border)",
          padding: "12px",
          marginTop: "12px",
          fontSize: "calc(11.5px * var(--font-scale))",
          lineHeight: 1.4,
          color: "var(--color-text-secondary)",
        }}
      >
        {authNote}
      </div>
    ) : null}
  </nav>
);
