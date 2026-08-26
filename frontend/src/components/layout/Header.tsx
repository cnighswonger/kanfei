import { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTheme } from '../../context/ThemeContext';
import { useWeatherData } from '../../context/WeatherDataContext';
import { useAuth } from '../../context/AuthContext';
import { usePersona, PERSONAS, type Persona } from '../../context/PersonaContext';
import { useIsMobile } from '../../hooks/useIsMobile';
import { themes } from '../../themes';

const PERSONA_LABEL: Record<Persona, string> = {
  everyday: 'Everyday',
  agriculture: 'Agriculture',
  weather_nerd: 'Weather nerd',
};

// Theme picker: two shipping defaults surfaced from the wordmark tag
// (mocks 13a / 13b).  Descriptors are ``ground · accent · face`` and
// live here because the theme tokens don't carry a display descriptor.
const PICKER_SHORTCUTS: Array<{ name: string; descriptor: string }> = [
  { name: 'glaisher', descriptor: 'Paper · Brass · IM Fell' },
  { name: 'mammoth', descriptor: 'Paper · Copper · Source Serif' },
];

// --- Header component ---

interface HeaderProps {
  connected: boolean;
  onMenuToggle: () => void;
  sidebarOpen: boolean;
  hidden?: boolean;
}

export default function Header({ connected, onMenuToggle, sidebarOpen, hidden = false }: HeaderProps) {
  const { themeName, setThemeName, theme } = useTheme();
  const { currentConditions } = useWeatherData();
  const { user, logout } = useAuth();
  const { persona, setPersona } = usePersona();
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const location = useLocation();

  // Paper themes render the header per the Design Agent's Glaisher
  // mock (`1c-dashboard-glaisher-notebook.png`): CREAM bar with
  // italic-serif "Kanfei" wordmark, tracked mono "· NOTEBOOK · STATION"
  // subtitle, three persona pills (active segment DARK-FILLED cream-text),
  // date/time on the right, and a "VUE · RUNNING" status pill.  Hi/lo,
  // forecast pill, and connected label are absent from the mock and
  // hidden for paper themes.
  const paper = theme.surface.ownsBackground;
  const paperInk = 'var(--color-text)';                  // dark on cream
  const paperInkDim = 'var(--color-text-secondary)';     // dimmer dark
  // Wordmark tag: the active theme's full ``label`` field, uppercased
  // via CSS (``text-transform``) so the raw label stays presentable
  // wherever else it's used (theme picker, dashboard title, footer).
  const themeTag = theme.label;

  // Theme picker (mocks 13a/13b): wordmark tag is the trigger.  Menu
  // shows two shipping defaults plus a jump to Settings › Appearance.
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerHover, setPickerHover] = useState(false);
  const pickerRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!pickerOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setPickerOpen(false);
      }
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPickerOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onEsc);
    };
  }, [pickerOpen]);

  // Wall-clock ticker.  useState + setInterval so the header time
  // updates every 30 s without a full page reload; without this, the
  // date/time on paper themes would freeze at initial-render time.
  const [clockNow, setClockNow] = useState(() => new Date());
  useEffect(() => {
    if (!paper) return;
    const id = setInterval(() => setClockNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, [paper]);
  // Per Design REVIEW-17: drop the weekday; the mock reads
  // "14 AUG 2026 · 14:41" not "SUN, AUG 16, 2026".
  const dateStr = clockNow
    .toLocaleDateString('en-US', { day: '2-digit', month: 'short', year: 'numeric' })
    .toUpperCase();
  const timeStr = clockNow.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });

  // Status pill: one word for the model, then one word for state.
  // Design REVIEW-17: drop the parenthetical firmware ("VUE · RUNNING",
  // not "VUE (FW 4.33) · RUNNING") — firmware already appears in the
  // Console & link tile.
  const stationTypeShort = (currentConditions?.station_type ?? 'STATION')
    .replace(/^Davis /i, '')
    .replace(/^Vantage /i, '')
    .replace(/\s*\(.*\)\s*/g, '')
    .toUpperCase();

  const authLabel = user?.authenticated ? 'Logout' : 'Sign in';
  const onAuth = () => {
    if (user?.authenticated) logout();
    else navigate('/login', { state: { from: location.pathname } });
  };

  return (
    <header
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        height: paper ? '60px' : '56px',
        background: 'var(--color-header-bg)',
        borderBottom: paper
          ? `${theme.rules.hairline}px solid ${theme.rules.strong}`
          : '1px solid var(--color-border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: paper ? '0 26px' : '0 20px',
        zIndex: 100,
        fontFamily: 'var(--font-body)',
        color: paper ? paperInk : undefined,
        transform: hidden ? 'translateY(-100%)' : 'translateY(0)',
        transition: 'transform 0.3s ease',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button
          onClick={onMenuToggle}
          aria-label={sidebarOpen ? 'Close menu' : 'Open menu'}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--color-text)',
            fontSize: 'calc(20px * var(--font-scale))',
            cursor: 'pointer',
            padding: '4px 8px',
            borderRadius: '4px',
            display: 'none',
            lineHeight: 1,
          }}
          className="header-menu-btn"
        >
          {sidebarOpen ? '✕' : '☰'}
        </button>

        {/* Wordmark cluster — Kanfei title + theme-tag trigger.  The
            tag is the theme picker (mocks 13a/13b); a caret glyph sits
            at 0.5 opacity until hover.  The wordmark itself is not
            interactive — clicking "Kanfei" doesn't open the picker. */}
        <h1
          className="header-title"
          style={{
            margin: 0,
            fontSize: paper ? 'calc(26px * var(--font-scale))' : 'calc(18px * var(--font-scale))',
            fontWeight: paper ? 400 : 600,
            fontStyle: paper ? 'italic' : 'normal',
            color: paper ? paperInk : 'var(--color-text)',
            fontFamily: 'var(--font-heading)',
            letterSpacing: paper ? '0' : '-0.01em',
          }}
        >
          Kanfei
        </h1>

        <div ref={pickerRef} style={{ position: 'relative' }}>
          <button
            type="button"
            aria-haspopup="menu"
            aria-expanded={pickerOpen}
            aria-label={`Theme: ${themeTag}. Open theme picker.`}
            onClick={() => setPickerOpen((v) => !v)}
            onMouseEnter={() => setPickerHover(true)}
            onMouseLeave={() => setPickerHover(false)}
            style={{
              background: 'transparent',
              border: 'none',
              padding: '4px 4px',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontFamily: 'var(--font-mono)',
              fontSize: paper ? 'calc(10px * var(--font-scale))' : 'calc(11px * var(--font-scale))',
              fontWeight: 500,
              letterSpacing: '0.20em',
              color: paper ? paperInkDim : 'var(--color-text-secondary)',
              textTransform: 'uppercase',
              whiteSpace: 'nowrap',
            }}
          >
            <span>{themeTag}</span>
            <span
              aria-hidden="true"
              style={{
                fontSize: 'calc(9px * var(--font-scale))',
                opacity: pickerHover || pickerOpen ? 1 : 0.5,
                transition: 'opacity 0.15s ease',
                lineHeight: 1,
              }}
            >
              {'▾'}
            </span>
          </button>

          {pickerOpen && (
            <ThemePickerMenu
              paper={paper}
              activeTheme={themeName}
              signedIn={!!user?.authenticated}
              onPick={(name) => {
                setThemeName(name);
                setPickerOpen(false);
              }}
              onJumpToSettings={() => {
                setPickerOpen(false);
                navigate('/settings?tab=appearance');
              }}
            />
          )}
        </div>

        {/* Forecast pill and H/L chip dropped everywhere: the hero
            tile below already shows the same Zambretti sentence,
            confidence, and hi/lo values, and the header just
            duplicated them.  Kept the Connected indicator — it names
            a state (daemon reachable / not) that no tile currently
            surfaces.  Design's DIFF-dark-background.md. */}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {!paper && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              fontSize: 'calc(13px * var(--font-scale))',
              color: 'var(--color-text-secondary)',
            }}
          >
            <span
              style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: connected ? 'var(--color-success)' : 'var(--color-danger)',
                display: 'inline-block',
                boxShadow: connected
                  ? '0 0 6px var(--color-success)'
                  : '0 0 6px var(--color-danger)',
              }}
            />
            <span className="header-connected-label">{connected ? 'Connected' : 'Disconnected'}</span>
          </div>
        )}

        {/* Persona switch — 3 segments.  Paper themes render the pills
            as an outlined group with cream-on-brown active state; other
            themes keep the pre-refactor accent-tinted background.

            Hidden at phone widths (≤768 px): v54 §7 folds the strip
            into the drawer alongside page nav, so Weather Nerd is
            reachable on the S10 (previously the strip overflowed and
            the third tab was unclickable). Desktop is unchanged. */}
        {!isMobile && (
          <div
            role="group"
            aria-label="Persona"
            className="header-persona-switch"
            style={{
              display: 'flex',
              border: paper
                ? '1px solid var(--color-border)'
                : '1px solid var(--color-border)',
              borderRadius: paper ? '2px' : '6px',
              overflow: 'hidden',
              fontFamily: paper ? 'var(--font-heading)' : 'var(--font-body)',
            }}
          >
            {PERSONAS.map((p, i) => {
              const active = p === persona;
              return (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPersona(p)}
                  aria-pressed={active}
                  title={PERSONA_LABEL[p]}
                  style={paper ? {
                    background: active ? 'var(--color-text)' : 'transparent',
                    color: active ? 'var(--color-bg)' : paperInk,
                    border: 'none',
                    borderLeft: i > 0 ? '1px solid var(--color-border)' : 'none',
                    padding: '7px 16px',
                    fontFamily: 'var(--font-heading)',
                    fontSize: 'calc(13px * var(--font-scale))',
                    fontStyle: 'italic',
                    fontWeight: active ? 600 : 400,
                    cursor: 'pointer',
                    transition: 'background 0.15s ease, color 0.15s ease',
                  } : {
                    background: active ? 'var(--color-accent-muted)' : 'transparent',
                    color: active ? 'var(--color-accent)' : 'var(--color-text-secondary)',
                    border: 'none',
                    borderLeft: i > 0 ? '1px solid var(--color-border)' : 'none',
                    padding: '6px 10px',
                    fontSize: 'calc(12px * var(--font-scale))',
                    fontWeight: active ? 600 : 400,
                    cursor: 'pointer',
                    transition: 'background 0.15s ease, color 0.15s ease',
                  }}
                >
                  {PERSONA_LABEL[p]}
                </button>
              );
            })}
          </div>
        )}

        {paper && (
          <>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 'calc(11px * var(--font-scale))',
                letterSpacing: '0.14em',
                color: paperInk,
                whiteSpace: 'nowrap',
              }}
            >
              {`${dateStr} · ${timeStr}`}
            </span>
            <span
              aria-label={connected ? 'connected' : 'disconnected'}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                fontFamily: 'var(--font-mono)',
                fontSize: 'calc(11px * var(--font-scale))',
                letterSpacing: '0.14em',
                color: paperInk,
                whiteSpace: 'nowrap',
              }}
            >
              <span
                style={{
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  backgroundColor: connected ? 'var(--color-success)' : 'var(--color-danger)',
                  boxShadow: connected
                    ? '0 0 6px var(--color-success)'
                    : '0 0 6px var(--color-danger)',
                  flexShrink: 0,
                }}
              />
              {`${stationTypeShort} · ${connected ? 'RUNNING' : 'OFFLINE'}`}
            </span>
          </>
        )}

        {/* Sign in / Logout.  Present on every theme now (mocks 13a/13b)
            so an anonymous visitor has a route into Settings from any
            page.  Paper themes use the quiet mono-caps button; dark and
            classic keep the accent-outlined pill. */}
        <button
          onClick={onAuth}
          style={paper ? {
            background: 'transparent',
            border: '1px solid var(--color-border)',
            borderRadius: '2px',
            padding: '7px 14px',
            fontFamily: 'var(--font-mono)',
            fontSize: 'calc(10px * var(--font-scale))',
            letterSpacing: '0.20em',
            textTransform: 'uppercase',
            color: paperInk,
            cursor: 'pointer',
          } : {
            background: 'none',
            border: '1px solid var(--color-border)',
            borderRadius: '6px',
            padding: '6px 10px',
            fontSize: 'calc(12px * var(--font-scale))',
            fontFamily: 'var(--font-body)',
            color: 'var(--color-text-secondary)',
            cursor: 'pointer',
          }}
        >
          {authLabel}
        </button>
      </div>
    </header>
  );
}

/* ────────────────────────────────────────────────── Theme picker menu */

interface ThemePickerMenuProps {
  paper: boolean;
  activeTheme: string;
  signedIn: boolean;
  onPick: (name: string) => void;
  onJumpToSettings: () => void;
}

/**
 * Anchored under the header rule (mocks 13a/13b).  Two shipping
 * defaults are named directly; everything else — the other three
 * themes, backgrounds, fonts — sits behind the jump.  That keeps the
 * menu a shortcut rather than a duplicate picker, and adding a sixth
 * theme later doesn't lengthen it.
 */
function ThemePickerMenu({ paper, activeTheme, signedIn, onPick, onJumpToSettings }: ThemePickerMenuProps) {
  const headerLine = signedIn ? 'Theme' : 'Theme · for this browser';
  return (
    <div
      role="menu"
      style={{
        position: 'absolute',
        top: 'calc(100% + 12px)',
        left: '-30px',
        width: '288px',
        background: 'var(--color-bg)',
        border: paper
          ? '1px solid var(--color-border)'
          : '1px solid var(--color-border)',
        borderRadius: paper ? '0' : '8px',
        boxShadow: paper ? 'none' : '0 8px 24px rgba(0,0,0,0.35)',
        zIndex: 200,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          padding: '10px 16px',
          borderBottom: paper
            ? '1px solid var(--color-border)'
            : '1px solid var(--color-border-light)',
          fontFamily: 'var(--font-mono)',
          fontSize: 'calc(10px * var(--font-scale))',
          letterSpacing: '0.20em',
          textTransform: 'uppercase',
          color: 'var(--color-text-secondary)',
        }}
      >
        {headerLine}
      </div>
      {PICKER_SHORTCUTS.map((row) => {
        const t = themes[row.name];
        if (!t) return null;
        const active = row.name === activeTheme;
        return (
          <button
            key={row.name}
            role="menuitemradio"
            aria-checked={active}
            type="button"
            onClick={() => onPick(row.name)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              width: '100%',
              minHeight: '56px',
              padding: '10px 16px',
              background: active
                ? (paper ? 'var(--color-bg-secondary)' : 'var(--color-accent-muted)')
                : 'transparent',
              border: 'none',
              borderBottom: paper
                ? '1px solid var(--color-border)'
                : '1px solid var(--color-border-light)',
              color: 'var(--color-text)',
              cursor: 'pointer',
              textAlign: 'left',
            }}
          >
            <span
              aria-hidden="true"
              style={{
                display: 'inline-block',
                width: '14px',
                fontFamily: 'var(--font-mono)',
                fontSize: 'calc(12px * var(--font-scale))',
                color: 'var(--color-accent)',
                flexShrink: 0,
              }}
            >
              {active ? '✓' : ''}
            </span>
            <span style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0 }}>
              <span
                style={{
                  fontFamily: 'var(--font-heading)',
                  fontSize: 'calc(15px * var(--font-scale))',
                  fontStyle: 'italic',
                  fontWeight: 600,
                  color: 'var(--color-text)',
                  lineHeight: 1.2,
                }}
              >
                {t.label}
              </span>
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 'calc(10px * var(--font-scale))',
                  letterSpacing: '0.16em',
                  textTransform: 'uppercase',
                  color: 'var(--color-text-secondary)',
                }}
              >
                {row.descriptor}
              </span>
            </span>
          </button>
        );
      })}
      <button
        type="button"
        role="menuitem"
        onClick={onJumpToSettings}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          width: '100%',
          padding: '14px 16px',
          background: 'transparent',
          border: 'none',
          fontFamily: 'var(--font-mono)',
          fontSize: 'calc(10px * var(--font-scale))',
          letterSpacing: '0.20em',
          textTransform: 'uppercase',
          color: 'var(--color-text-secondary)',
          cursor: 'pointer',
          textAlign: 'left',
        }}
      >
        <span>All themes &amp; appearance</span>
        <span aria-hidden="true">{'→'}</span>
      </button>
    </div>
  );
}
