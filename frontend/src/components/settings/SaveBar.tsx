/**
 * Save bar — bottom-of-page footer showing the pending changes and
 * offering revert / save.
 *
 * Design's SETTINGS.md v31 spec: "the single most useful addition."
 * A bare "2 unsaved changes" doesn't tell you whether you're about to
 * save something you forgot you touched; naming the fields is what
 * makes it trustworthy.  ``dirtyLabels`` is the readable list of
 * changed field names; when empty, this renders nothing (the panel
 * takes the whole vertical budget).
 *
 * Presentation only — Settings owns the dirty-state computation and
 * both callbacks.  ``status`` surfaces the save-flow result inline
 * with the change list so it doesn't pop up somewhere separate.
 */

import React from "react";

export type SaveBarStatus =
  | { kind: "idle" }
  | { kind: "saved" }
  | { kind: "reconnected"; msg: string }
  | { kind: "error"; msg: string };

export const SaveBar: React.FC<{
  dirtyLabels: string[];
  onRevert: () => void;
  onSave: () => void;
  onSaveAndReconnect?: () => void;
  saving?: boolean;
  reconnecting?: boolean;
  hideActions?: boolean;
  status?: SaveBarStatus;
}> = ({
  dirtyLabels,
  onRevert,
  onSave,
  onSaveAndReconnect,
  saving,
  reconnecting,
  hideActions,
  status = { kind: "idle" },
}) => {
  const n = dirtyLabels.length;
  const hasDirty = n > 0;
  const hasStatusMsg =
    status.kind === "saved" || status.kind === "reconnected" || status.kind === "error";
  // Nothing to say and nothing to show: keep row 3 out of the way.
  if (!hasDirty && !hasStatusMsg) return null;

  const statusColor =
    status.kind === "error" ? "var(--color-danger)" : "var(--color-success)";
  const statusText =
    status.kind === "saved"
      ? "Saved."
      : status.kind === "reconnected"
      ? status.msg
      : status.kind === "error"
      ? `Error: ${status.msg}`
      : "";

  return (
    <div
      style={{
        gridColumn: "1 / -1",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "12px",
        padding: "12px 26px",
        borderTop: "0.8px solid var(--color-border)",
        background: "var(--color-bg-secondary)",
        minHeight: "59px",
        boxSizing: "border-box",
        flexWrap: "wrap",
      }}
    >
      <span
        style={{
          fontFamily: "var(--font-body)",
          fontSize: "calc(12.5px * var(--font-scale))",
          color: "var(--color-text)",
          minWidth: 0,
          flex: 1,
        }}
      >
        {hasDirty ? (
          <>
            {n} unsaved change{n === 1 ? "" : "s"} · {dirtyLabels.join(", ")}
          </>
        ) : hasStatusMsg ? (
          <span style={{ color: statusColor }}>{statusText}</span>
        ) : null}
      </span>

      {hasDirty && hasStatusMsg && (
        <span
          style={{
            fontFamily: "var(--font-body)",
            fontSize: "calc(12.5px * var(--font-scale))",
            color: statusColor,
            marginRight: "10px",
          }}
        >
          {statusText}
        </span>
      )}

      {hasDirty && !hideActions && (
        <div style={{ display: "flex", gap: "10px", flexShrink: 0 }}>
          <button
            type="button"
            onClick={onRevert}
            disabled={saving || reconnecting}
            style={{
              fontFamily: "var(--font-body)",
              fontSize: "calc(13px * var(--font-scale))",
              padding: "0 16px",
              height: "34px",
              background: "transparent",
              color: "var(--color-text)",
              border: "0.8px solid var(--color-border)",
              cursor: saving || reconnecting ? "wait" : "pointer",
            }}
          >
            Revert
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={saving || reconnecting}
            style={{
              fontFamily: "var(--font-body)",
              fontSize: "calc(13px * var(--font-scale))",
              padding: "0 16px",
              height: "34px",
              background: "var(--color-text)",
              color: "var(--color-bg)",
              border: "0.8px solid var(--color-text)",
              cursor: saving || reconnecting ? "wait" : "pointer",
              opacity: saving || reconnecting ? 0.6 : 1,
            }}
          >
            {saving && !reconnecting ? "Saving…" : "Save changes"}
          </button>
          {onSaveAndReconnect && (
            <button
              type="button"
              onClick={onSaveAndReconnect}
              disabled={saving || reconnecting}
              style={{
                fontFamily: "var(--font-body)",
                fontSize: "calc(13px * var(--font-scale))",
                padding: "0 16px",
                height: "34px",
                background: "transparent",
                color: "var(--color-text)",
                border: "0.8px solid var(--color-border)",
                cursor: saving || reconnecting ? "wait" : "pointer",
                opacity: reconnecting ? 0.6 : 1,
              }}
            >
              {reconnecting ? "Reconnecting…" : "Save & reconnect"}
            </button>
          )}
        </div>
      )}
    </div>
  );
};

/**
 * Human-readable label for a config key.  ``rain_collector_clicks`` →
 * "rain collector clicks".  Deliberately dumb: a curated map would be
 * better but the config schema has ~80 keys and half of them are
 * self-documenting; the dumb fallback covers everything and a curated
 * map can layer on top when a specific key needs polish.
 */
export const configKeyToLabel = (key: string): string =>
  key.replace(/^ui_/, "").replace(/_/g, " ");
