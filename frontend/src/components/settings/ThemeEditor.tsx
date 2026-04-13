/**
 * Custom theme editor — full color picker, font, and gauge style controls.
 * Manages its own draft state and calls applyThemeToDOM for live preview.
 * On save, persists via ThemeContext.setCustomTheme.
 * On cancel, ThemeContext re-applies the committed theme.
 */

import { useState, useCallback, useEffect, useRef } from "react";
import { HexColorPicker } from "react-colorful";
import { useTheme, applyThemeToDOM } from "../../context/ThemeContext.tsx";
import { themes, type Theme } from "../../themes/index.ts";

// --- Color field groups ---

interface ColorDef {
  key: keyof Theme["colors"];
  label: string;
  /** One-line description of where this color appears in the UI. */
  hint: string;
}

const COLOR_GROUPS: { title: string; fields: ColorDef[] }[] = [
  {
    title: "General",
    fields: [
      { key: "bg",             label: "Background",     hint: "Page background" },
      { key: "bgSecondary",    label: "Secondary BG",   hint: "Panels, dropdowns, inputs" },
      { key: "bgCard",         label: "Card BG",        hint: "Gauge and dashboard tiles" },
      { key: "bgCardHover",    label: "Card Hover",     hint: "Tile hover state" },
      { key: "text",           label: "Text",           hint: "Main text and gauge values" },
      { key: "textSecondary",  label: "Secondary Text", hint: "Labels, axes, chart gridlines" },
      { key: "textMuted",      label: "Muted Text",     hint: "Timestamps, hints, disabled" },
    ],
  },
  {
    title: "Accent & Status",
    fields: [
      { key: "accent",      label: "Accent",       hint: "Buttons, links, active tabs" },
      { key: "accentHover", label: "Accent Hover", hint: "Accent elements on hover" },
      { key: "success",     label: "Success",      hint: "OK indicators, rising trends" },
      { key: "warning",     label: "Warning",      hint: "Caution states, stale data" },
      { key: "danger",      label: "Danger",       hint: "Errors, falling trends" },
    ],
  },
  {
    title: "Borders",
    fields: [
      { key: "border",      label: "Border",       hint: "Tile outlines, dividers" },
      { key: "borderLight", label: "Border Light", hint: "Subtle separators" },
    ],
  },
  {
    title: "Gauges",
    fields: [
      { key: "gaugeTrack",      label: "Track",            hint: "Empty portion of dial gauges" },
      { key: "gaugeFill",       label: "Fill",             hint: "Filled portion of dial gauges" },
      { key: "barometerNeedle", label: "Barometer Needle", hint: "Barometer pointer" },
      { key: "windArrow",       label: "Wind Arrow",       hint: "Wind direction arrow on compass" },
      { key: "rainBlue",        label: "Rain",             hint: "Rain gauge fill" },
      { key: "humidityGreen",   label: "Humidity",         hint: "Humidity gauge fill" },
      { key: "solarYellow",     label: "Solar",            hint: "Solar/UV gauge fill" },
    ],
  },
  {
    title: "Temperature",
    fields: [
      { key: "tempHot",  label: "Hot",  hint: "Daily high marker on temperature gauge" },
      { key: "tempCold", label: "Cold", hint: "Daily low marker on temperature gauge" },
      { key: "tempMid",  label: "Mid",  hint: "Middle of temperature gradient" },
    ],
  },
  {
    title: "Layout",
    fields: [
      { key: "headerBg",  label: "Header BG",  hint: "Top navigation bar" },
      { key: "sidebarBg", label: "Sidebar BG", hint: "Left navigation sidebar" },
    ],
  },
];

// --- Helpers ---

/** Convert hex (#rrggbb) to rgba string with given alpha. */
function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** Derive accentMuted from accent hex. */
function deriveAccentMuted(accent: string): string {
  return hexToRgba(accent, 0.12);
}

// --- Styles ---

const sectionStyle: React.CSSProperties = {
  marginBottom: "16px",
};

const sectionHeaderStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  cursor: "pointer",
  userSelect: "none",
  fontSize: "13px",
  fontWeight: 600,
  fontFamily: "var(--font-body)",
  color: "var(--color-text-secondary)",
  marginBottom: "8px",
};

const colorRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  marginBottom: "6px",
  fontSize: "12px",
  fontFamily: "var(--font-body)",
  color: "var(--color-text)",
};

const swatchStyle: React.CSSProperties = {
  width: "24px",
  height: "24px",
  borderRadius: "4px",
  border: "1px solid var(--color-border)",
  cursor: "pointer",
  flexShrink: 0,
};

const inputStyle: React.CSSProperties = {
  flex: 1,
  padding: "4px 8px",
  fontSize: "12px",
  fontFamily: "var(--font-mono)",
  background: "var(--color-bg-secondary)",
  color: "var(--color-text)",
  border: "1px solid var(--color-border)",
  borderRadius: "4px",
  boxSizing: "border-box",
};

const btnStyle: React.CSSProperties = {
  padding: "8px 16px",
  fontSize: "13px",
  fontWeight: 600,
  fontFamily: "var(--font-body)",
  border: "none",
  borderRadius: "6px",
  cursor: "pointer",
};

// --- Color field with popover picker ---

function ColorField({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const popRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (popRef.current && !popRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Normalize rgba/named to hex for the picker (best effort)
  const hexValue = value.startsWith("#") ? value.slice(0, 7) : value;

  return (
    <div style={colorRowStyle}>
      <div style={{ width: "130px", flexShrink: 0, fontWeight: 500 }}>{label}</div>
      <div style={{ position: "relative" }} ref={popRef}>
        <div
          style={{ ...swatchStyle, background: value }}
          onClick={() => setOpen(!open)}
        />
        {open && (
          <div
            style={{
              position: "absolute",
              top: "30px",
              left: 0,
              zIndex: 100,
              background: "var(--color-bg-card-solid, var(--color-bg-card))",
              border: "1px solid var(--color-border)",
              borderRadius: "8px",
              padding: "8px",
              boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
            }}
          >
            <HexColorPicker color={hexValue} onChange={onChange} />
          </div>
        )}
      </div>
      <input
        style={{ ...inputStyle, maxWidth: "100px", flex: "0 0 100px" }}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {hint && (
        <div style={{
          flex: 1,
          fontSize: "11px",
          color: "var(--color-text-secondary)",
          fontStyle: "italic",
          marginLeft: "8px",
        }}>
          {hint}
        </div>
      )}
    </div>
  );
}

// --- Main editor ---

interface ThemeEditorProps {
  onClose: () => void;
}

export default function ThemeEditor({ onClose }: ThemeEditorProps) {
  const { theme, setCustomTheme } = useTheme();
  const [baseName, setBaseName] = useState<string>("dark");
  const [draft, setDraft] = useState<Theme>(() => ({
    ...structuredClone(theme),
    name: "custom",
    label: "Custom",
  }));
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [saved, setSaved] = useState(false);
  const committedRef = useRef(theme);
  const savedRef = useRef(false);

  // Live preview: apply draft to DOM on every change
  useEffect(() => {
    applyThemeToDOM(draft);
  }, [draft]);

  // On unmount, restore committed theme ONLY if we didn't save
  useEffect(() => {
    return () => {
      if (!savedRef.current) {
        applyThemeToDOM(committedRef.current);
      }
    };
  }, []);

  const updateColor = useCallback((key: keyof Theme["colors"], value: string) => {
    setDraft((d) => ({
      ...d,
      colors: { ...d.colors, [key]: value },
    }));
  }, []);

  const updateFont = useCallback((key: keyof Theme["fonts"], value: string) => {
    setDraft((d) => ({
      ...d,
      fonts: { ...d.fonts, [key]: value },
    }));
  }, []);

  const updateGauge = useCallback((key: keyof Theme["gauge"], value: string | number) => {
    setDraft((d) => ({
      ...d,
      gauge: { ...d.gauge, [key]: value },
    }));
  }, []);

  const resetToBase = useCallback(() => {
    const base = themes[baseName] ?? themes.dark;
    setDraft({ ...structuredClone(base), name: "custom", label: "Custom" });
  }, [baseName]);

  const handleBaseChange = useCallback((name: string) => {
    setBaseName(name);
    const base = themes[name] ?? themes.dark;
    setDraft({ ...structuredClone(base), name: "custom", label: "Custom" });
  }, []);

  const handleSave = useCallback(() => {
    // Auto-derive accentMuted from accent
    const final: Theme = {
      ...draft,
      colors: {
        ...draft.colors,
        accentMuted: deriveAccentMuted(draft.colors.accent),
      },
    };
    setCustomTheme(final);
    committedRef.current = final;
    savedRef.current = true;
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }, [draft, setCustomTheme]);

  const handleCancel = useCallback(() => {
    // Restore original theme (cleanup effect handles DOM)
    onClose();
  }, [onClose]);

  const toggleSection = useCallback((title: string) => {
    setCollapsed((c) => ({ ...c, [title]: !c[title] }));
  }, []);

  return (
    <div style={{
      marginTop: "16px",
      padding: "16px",
      background: "var(--color-bg-secondary)",
      borderRadius: "var(--gauge-border-radius, 8px)",
      border: "1px solid var(--color-border)",
    }}>
      {/* Base theme selector */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px" }}>
        <label style={{
          fontSize: "12px",
          fontFamily: "var(--font-body)",
          color: "var(--color-text-secondary)",
        }}>
          Base Theme
        </label>
        <select
          value={baseName}
          onChange={(e) => handleBaseChange(e.target.value)}
          style={{
            ...inputStyle,
            maxWidth: "150px",
          }}
        >
          {Object.entries(themes).map(([key, t]) => (
            <option key={key} value={key}>{t.label}</option>
          ))}
        </select>
        <button
          onClick={resetToBase}
          style={{
            ...btnStyle,
            background: "var(--color-bg-card)",
            color: "var(--color-text)",
            border: "1px solid var(--color-border)",
            padding: "4px 12px",
            fontSize: "12px",
          }}
        >
          Reset to Base
        </button>
      </div>

      {/* Color sections */}
      {COLOR_GROUPS.map((group) => (
        <div key={group.title} style={sectionStyle}>
          <div
            style={sectionHeaderStyle}
            onClick={() => toggleSection(group.title)}
          >
            <span>{collapsed[group.title] ? "\u25B8" : "\u25BE"}</span>
            <span>{group.title}</span>
          </div>
          {!collapsed[group.title] && (
            <div style={{ paddingLeft: "16px" }}>
              {group.fields.map((f) => (
                <ColorField
                  key={f.key}
                  label={f.label}
                  hint={f.hint}
                  value={draft.colors[f.key]}
                  onChange={(v) => updateColor(f.key, v)}
                />
              ))}
            </div>
          )}
        </div>
      ))}

      {/* Fonts section */}
      <div style={sectionStyle}>
        <div
          style={sectionHeaderStyle}
          onClick={() => toggleSection("Fonts")}
        >
          <span>{collapsed["Fonts"] ? "\u25B8" : "\u25BE"}</span>
          <span>Fonts</span>
        </div>
        {!collapsed["Fonts"] && (
          <div style={{ paddingLeft: "16px" }}>
            {(["body", "heading", "mono", "gauge"] as const).map((key) => (
              <div key={key} style={colorRowStyle}>
                <div style={{ width: "110px", flexShrink: 0, textTransform: "capitalize" }}>
                  {key}
                </div>
                <input
                  style={inputStyle}
                  type="text"
                  value={draft.fonts[key]}
                  onChange={(e) => updateFont(key, e.target.value)}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Gauge style section */}
      <div style={sectionStyle}>
        <div
          style={sectionHeaderStyle}
          onClick={() => toggleSection("Gauge Style")}
        >
          <span>{collapsed["Gauge Style"] ? "\u25B8" : "\u25BE"}</span>
          <span>Gauge Style</span>
        </div>
        {!collapsed["Gauge Style"] && (
          <div style={{ paddingLeft: "16px" }}>
            <div style={colorRowStyle}>
              <div style={{ width: "110px", flexShrink: 0 }}>Stroke Width</div>
              <input
                type="range"
                min={2}
                max={16}
                step={1}
                value={draft.gauge.strokeWidth}
                onChange={(e) => updateGauge("strokeWidth", parseInt(e.target.value))}
                style={{ flex: 1 }}
              />
              <span style={{ width: "30px", textAlign: "right" }}>{draft.gauge.strokeWidth}</span>
            </div>
            <div style={colorRowStyle}>
              <div style={{ width: "110px", flexShrink: 0 }}>BG Opacity</div>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={draft.gauge.bgOpacity}
                onChange={(e) => updateGauge("bgOpacity", parseFloat(e.target.value))}
                style={{ flex: 1 }}
              />
              <span style={{ width: "30px", textAlign: "right" }}>{draft.gauge.bgOpacity}</span>
            </div>
            <div style={colorRowStyle}>
              <div style={{ width: "110px", flexShrink: 0 }}>Shadow</div>
              <input
                style={inputStyle}
                type="text"
                value={draft.gauge.shadow}
                onChange={(e) => updateGauge("shadow", e.target.value)}
              />
            </div>
            <div style={colorRowStyle}>
              <div style={{ width: "110px", flexShrink: 0 }}>Border Radius</div>
              <input
                style={inputStyle}
                type="text"
                value={draft.gauge.borderRadius}
                onChange={(e) => updateGauge("borderRadius", e.target.value)}
              />
            </div>
          </div>
        )}
      </div>

      {/* Save / Cancel */}
      <div style={{ display: "flex", gap: "12px", marginTop: "16px" }}>
        <button
          onClick={handleSave}
          style={{
            ...btnStyle,
            background: saved ? "var(--color-success, #22c55e)" : "var(--color-accent)",
            color: "#fff",
          }}
        >
          {saved ? "Saved!" : "Save Custom Theme"}
        </button>
        <button
          onClick={handleCancel}
          style={{
            ...btnStyle,
            background: "var(--color-bg-card)",
            color: "var(--color-text)",
            border: "1px solid var(--color-border)",
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
