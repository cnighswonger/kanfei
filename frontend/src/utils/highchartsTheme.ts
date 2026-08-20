/**
 * Highcharts token bridge — Design v34 HIGHCHARTS.md, tranche 1.
 *
 * Resolves the CSS custom properties applyThemeToDOM publishes into
 * concrete rgb/rgba strings and returns a Highcharts.Options object
 * that skins axes, grid, tooltip, plot options and the series colour
 * cycle to the active theme.  Callers install it via
 * ``Highcharts.setOptions(highchartsTheme())`` on every theme change;
 * per-chart options (series data, gauge geometry, etc.) still ride on
 * top and inherit these defaults.
 *
 * WHY resolve tokens once, not per-chart: Highcharts manipulates colour
 * strings in JS — ``Highcharts.color(x).setOpacity(0.4).get('rgba')``.
 * Hand that ``var(--color-accent)`` and it returns undefined, silently
 * producing an invisible gradient stop.  Resolving to a concrete hex
 * or rgba string here means every consumer down the chain gets a real
 * colour, and the theme function has one place to enforce it.
 *
 * WHY memoise on the theme name, not on []: consumers ``useMemo`` their
 * Highcharts options on ``[data, theme.name]`` so a theme switch
 * rebuilds them.  A stale ``[]`` would freeze the chart at whichever
 * theme was loaded first and defeat the whole bridge.
 */

import type Highcharts from "highcharts";

/**
 * Read a CSS custom property from ``:root``, trim it, and fall back to
 * the given default.  The fallback is mandatory — the top-level rule
 * is "never hand a ``var()`` to a Highcharts colour manipulator" and
 * the belt-and-braces for that is a real value when the token is
 * missing (unpublished, mistyped, or read before applyThemeToDOM has
 * run).  Every caller supplies one.
 */
export function readToken(name: string, fallback: string): string {
  if (typeof document === "undefined") return fallback;
  const val = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return val || fallback;
}

/**
 * Build a Highcharts.Options object skinned to the currently-applied
 * theme.  Call after applyThemeToDOM has run (the CSS vars must
 * already be on ``:root``) and pass the result to
 * ``Highcharts.setOptions``.  Per-chart options merge on top of these
 * defaults; anything a chart doesn't override falls back here.
 *
 * The Mammoth-flavoured hex fallbacks are last-resort values that
 * only fire when the token is missing entirely — the real palette
 * for every theme comes from the ``--color-*`` and ``--chart-*``
 * variables applyThemeToDOM publishes.
 */
export function highchartsTheme(): Highcharts.Options {
  const t = {
    ink: readToken("--color-text", "#3a2d1d"),
    inkSoft: readToken("--color-text-secondary", "rgba(58,45,29,0.84)"),
    inkFaint: readToken("--color-text-muted", "rgba(58,45,29,0.62)"),
    accent: readToken("--color-accent", "#a85f24"),
    bg: readToken("--color-bg", "#ebdfc1"),
    surface: readToken("--chart-surface", "#dccfa9"),
    gridMinor: readToken("--chart-grid-minor", "rgba(58,45,29,0.10)"),
    gridMajor: readToken("--chart-grid-major", "rgba(58,45,29,0.20)"),
    trace: readToken("--chart-trace", "#a85f24"),
    traceShade: readToken("--chart-trace-shadow", "rgba(58,45,29,0.35)"),
    traceAlt: readToken("--chart-trace-secondary", "#3f5d7a"),
    mono: readToken("--type-mono-family", "'JetBrains Mono', monospace"),
    body: readToken("--type-body-family", "'Inter', sans-serif"),
  };

  return {
    chart: {
      // Card owns the ground, not the chart.  Charts always sit
      // inside a bordered card whose theme-aware background gives
      // the ruled-paper affordance we want.
      backgroundColor: "transparent",
      // The sunken plot panel gets the chart-surface token — a
      // slightly warmer or cooler shade than the card ground so the
      // plot area reads as recessed.
      plotBackgroundColor: t.surface,
      spacing: [8, 4, 4, 4],
      style: { fontFamily: t.body },
      // Instrument, not infographic — a needle that eases into
      // position implies a measurement that didn't happen.
      animation: false,
    },
    title: { text: undefined },
    // Series are named in the header line above the chart; the
    // Highcharts legend duplicates the label and adds a coloured
    // swatch that fights the trace for attention.
    legend: { enabled: false },
    credits: { enabled: false },
    // Kill the export burger by default — Design v35 flagged it as
    // the highest-contrast element in the barometer tile.  History
    // explicitly opts back in (``exporting: { enabled: true, ... }``
    // in its per-chart options).
    exporting: { enabled: false },
    xAxis: {
      lineColor: t.gridMajor,
      tickColor: t.gridMajor,
      gridLineWidth: 0.4,
      gridLineColor: t.gridMinor,
      labels: { style: { color: t.inkSoft, fontFamily: t.mono, fontSize: "10px" } },
      crosshair: { color: t.accent, width: 0.8, dashStyle: "Dash" },
    },
    yAxis: {
      title: { text: undefined },
      gridLineWidth: 0.6,
      gridLineColor: t.gridMinor,
      labels: { style: { color: t.inkSoft, fontFamily: t.mono, fontSize: "10px" } },
    },
    tooltip: {
      backgroundColor: t.bg,
      borderColor: t.gridMajor,
      borderRadius: 0,
      shadow: false,
      style: { color: t.ink, fontFamily: t.mono, fontSize: "11px" },
    },
    plotOptions: {
      series: { animation: false, marker: { enabled: false } },
      column: { borderWidth: 0, groupPadding: 0.08 },
    },
    // Navigator (the strip beneath a Stock-module chart) ships its
    // own defaults — a sans-serif fallback that clashes with the
    // paper themes.  Push the theme's mono family into the label
    // style and colour it with the muted-ink token so it reads as
    // scale, not chrome.
    navigator: {
      maskFill: "rgba(154,110,43,0.14)",
      outlineColor: t.gridMajor,
      handles: {
        backgroundColor: t.surface,
        borderColor: t.inkSoft,
      },
      xAxis: {
        labels: {
          style: {
            color: t.inkFaint,
            fontFamily: t.mono,
            fontSize: "10px",
          },
        },
        gridLineColor: t.gridMinor,
      },
      series: {
        color: t.trace,
        lineColor: t.trace,
        fillOpacity: 0.15,
      },
    },
    // Scrollbar sits beside the navigator; hidden by default in
    // History.tsx but the theme still styles it so a Stock consumer
    // that enables it doesn't inherit greyscale defaults.
    scrollbar: {
      barBackgroundColor: t.surface,
      barBorderColor: t.gridMajor,
      buttonBackgroundColor: t.surface,
      buttonBorderColor: t.gridMajor,
      rifleColor: t.inkSoft,
      trackBackgroundColor: "transparent",
      trackBorderColor: t.gridMinor,
    },
    // Range selector is a Stock feature; not used in History today
    // but the theme covers it so future Stock consumers inherit
    // typography that matches everything else.
    rangeSelector: {
      inputStyle: {
        color: t.ink,
        fontFamily: t.mono,
        fontSize: "11px",
      },
      labelStyle: {
        color: t.inkSoft,
        fontFamily: t.body,
        fontSize: "11px",
      },
    },
    colors: [t.trace, t.traceAlt, t.accent, t.inkSoft],
  };
}
