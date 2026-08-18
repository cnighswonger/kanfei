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
}

export const SectionRail: React.FC<{
  groups: SectionRailGroup[];
  activeGroup: string;
  activeSection: string;
  onSelect: (groupId: string, sectionId: string) => void;
}> = ({ groups, activeGroup, activeSection, onSelect }) => (
  <nav
    style={{
      padding: "18px 14px",
      borderRight: "0.8px solid var(--color-border)",
      overflowY: "auto",
      fontFamily: "var(--font-body)",
    }}
    aria-label="Settings sections"
  >
    {groups.map((g) => {
      const open = g.id === activeGroup;
      return (
        <div key={g.id}>
          <button
            type="button"
            onClick={() => onSelect(g.id, g.sections[0]?.id ?? "")}
            style={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
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
            <span style={{ opacity: 0.7 }}>{open ? "▾" : "▸"}</span>
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
  </nav>
);
