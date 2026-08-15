import { useNavigate, useLocation } from 'react-router-dom';
import { useTheme } from '../../context/ThemeContext';
import { useWeatherData } from '../../context/WeatherDataContext';
import { useAuth } from '../../context/AuthContext';
import { usePersona, PERSONAS, type Persona } from '../../context/PersonaContext';
import { themes } from '../../themes';

const PERSONA_LABEL: Record<Persona, string> = {
  everyday: 'Everyday',
  agriculture: 'Agriculture',
  weather_nerd: 'Weather nerd',
};

// --- Inline SVG weather icons (20x20, currentColor) ---

const iconProps = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

function IconSun() {
  return (
    <svg {...iconProps}>
      <circle cx="12" cy="12" r="5" />
      <line x1="12" y1="1" x2="12" y2="3" />
      <line x1="12" y1="21" x2="12" y2="23" />
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
      <line x1="1" y1="12" x2="3" y2="12" />
      <line x1="21" y1="12" x2="23" y2="12" />
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </svg>
  );
}

function IconSunCloud() {
  return (
    <svg {...iconProps}>
      <path d="M12 2v2" />
      <path d="M4.93 4.93l1.41 1.41" />
      <path d="M20 12h2" />
      <path d="M19.07 4.93l-1.41 1.41" />
      <circle cx="12" cy="10" r="4" />
      <path d="M8 16h8a4 4 0 0 0 0-8H7a5 5 0 0 0 0 10z" fill="currentColor" opacity="0.15" stroke="currentColor" />
    </svg>
  );
}

function IconCloud() {
  return (
    <svg {...iconProps}>
      <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z" />
    </svg>
  );
}

function IconCloudDrizzle() {
  return (
    <svg {...iconProps}>
      <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z" />
      <line x1="8" y1="19" x2="8" y2="21" />
      <line x1="12" y1="19" x2="12" y2="21" />
      <line x1="16" y1="19" x2="16" y2="21" />
    </svg>
  );
}

function IconRain() {
  return (
    <svg {...iconProps}>
      <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z" />
      <line x1="8" y1="19" x2="7" y2="22" />
      <line x1="12" y1="19" x2="11" y2="22" />
      <line x1="16" y1="19" x2="15" y2="22" />
    </svg>
  );
}

function IconStorm() {
  return (
    <svg {...iconProps}>
      <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z" />
      <polyline points="13 16 11 20 15 20 13 24" />
    </svg>
  );
}

function mapForecastIcon(text: string): { icon: React.ReactNode; color: string } {
  const t = text.toLowerCase();
  if (t.includes("stormy")) return { icon: <IconStorm />, color: "var(--color-forecast-stormy, #a855f7)" };
  if (t.includes("rain") || t.includes("very unsettled")) return { icon: <IconRain />, color: "var(--color-forecast-rain, var(--color-accent, #3b82f6))" };
  if (t.includes("shower")) return { icon: <IconCloudDrizzle />, color: "var(--color-forecast-shower, #60a5fa)" };
  if (t.includes("changeable") || t.includes("unsettled") || t.includes("less settled")) return { icon: <IconCloud />, color: "var(--color-forecast-changeable, var(--color-text-secondary, #94a3b8))" };
  if (t.includes("fairly fine") || t.includes("becoming fine") || t.includes("improving")) return { icon: <IconSunCloud />, color: "var(--color-forecast-fair, #fbbf24)" };
  return { icon: <IconSun />, color: "var(--color-forecast-sunny, var(--color-solar-yellow, #f59e0b))" };
}

function trendArrow(trend: string | null): { symbol: string; color: string } {
  if (trend === "rising") return { symbol: "\u25B2", color: "var(--color-success)" };
  if (trend === "falling") return { symbol: "\u25BC", color: "var(--color-warning)" };
  return { symbol: "\u25B6", color: "var(--color-text-muted)" };
}

// --- Header component ---

interface HeaderProps {
  connected: boolean;
  onMenuToggle: () => void;
  sidebarOpen: boolean;
  hidden?: boolean;
}

export default function Header({ connected, onMenuToggle, sidebarOpen, hidden = false }: HeaderProps) {
  const { themeName, setThemeName, theme } = useTheme();
  const { currentConditions, forecast } = useWeatherData();
  const { user, logout } = useAuth();
  const { persona, setPersona } = usePersona();
  const navigate = useNavigate();
  const location = useLocation();
  const extremes = currentConditions?.daily_extremes;
  const hi = extremes?.outside_temp_hi?.value;
  const lo = extremes?.outside_temp_lo?.value;
  const local = forecast?.local ?? null;

  // Paper themes render the header per the Design Agent's Glaisher
  // mock (`1c-dashboard-glaisher-notebook.png`): dark-brown bar with
  // italic-serif "Kanfei" wordmark, tracked mono "· NOTEBOOK · STATION"
  // subtitle, three persona pills, date/time on the right, and a
  // "VUE · RUNNING" status pill.  Hi/lo, forecast pill, and connected
  // label are absent from the mock and hidden for paper themes.
  const paper = theme.surface.ownsBackground;
  const paperInk = 'var(--color-bg)';                    // cream on brown
  const paperInkDim = 'rgba(237, 226, 196, 0.60)';       // dim cream
  const themeTag = theme.label
    .replace(/^The /, '')
    .replace(/'s (Log|Notebook)$/, '')
    .toUpperCase();

  // Current wall-clock time for the paper header display.
  const now = new Date();
  const dateStr = now
    .toLocaleDateString('en-US', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' })
    .toUpperCase();
  const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });

  const stationTypeShort = (currentConditions?.station_type ?? 'STATION')
    .replace(/^Davis /i, '')
    .replace(/^Vantage /i, '')
    .toUpperCase();

  return (
    <header
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        height: '56px',
        background: 'var(--color-header-bg)',
        borderBottom: paper ? 'none' : '1px solid var(--color-border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 20px',
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
          {sidebarOpen ? '\u2715' : '\u2630'}
        </button>
        <h1
          className="header-title"
          style={{
            margin: 0,
            fontSize: paper ? 'calc(22px * var(--font-scale))' : 'calc(18px * var(--font-scale))',
            fontWeight: paper ? 400 : 600,
            fontStyle: paper ? 'italic' : 'normal',
            color: paper ? paperInk : 'var(--color-text)',
            fontFamily: 'var(--font-heading)',
            letterSpacing: paper ? '0' : '-0.01em',
          }}
        >
          Kanfei
        </h1>
        {paper && (
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 'calc(10px * var(--font-scale))',
              fontWeight: 500,
              letterSpacing: '0.20em',
              color: paperInkDim,
              textTransform: 'uppercase',
              whiteSpace: 'nowrap',
            }}
          >
            {`· ${themeTag} · STATION`}
          </span>
        )}
        {!paper && local && (() => {
          const { icon, color } = mapForecastIcon(local.text);
          return (
            <div
              className="header-forecast"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: 'calc(13px * var(--font-scale))',
                color: 'var(--color-text-secondary)',
                whiteSpace: 'nowrap',
                background: 'var(--color-bg-secondary)',
                border: '1px solid var(--color-border-light)',
                borderRadius: '20px',
                padding: '4px 12px 4px 8px',
              }}
            >
              <span style={{ display: 'flex', color }}>
                {icon}
              </span>
              <span className="header-forecast-text">{local.text}</span>
              <span style={{ color: trendArrow(local.trend).color, fontSize: 'calc(10px * var(--font-scale))' }}>
                {trendArrow(local.trend).symbol}
              </span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'calc(12px * var(--font-scale))', color: 'var(--color-text-muted)' }}>
                {local.confidence}%
              </span>
            </div>
          );
        })()}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {!paper && (
          <div
            className="header-hilo"
            style={{
              fontSize: 'calc(13px * var(--font-scale))',
              fontFamily: 'var(--font-gauge)',
              color: 'var(--color-text-secondary)',
              whiteSpace: 'nowrap',
            }}
          >
            <span style={{ color: 'var(--color-temp-hot, #ef4444)' }}>
              H {hi != null ? `${hi.toFixed(1)}°` : '--'}
            </span>
            {' / '}
            <span style={{ color: 'var(--color-temp-cold, #3b82f6)' }}>
              L {lo != null ? `${lo.toFixed(1)}°` : '--'}
            </span>
          </div>
        )}

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
            themes keep the pre-refactor accent-tinted background. */}
        <div
          role="group"
          aria-label="Persona"
          className="header-persona-switch"
          style={{
            display: 'flex',
            border: paper
              ? '1px solid rgba(237, 226, 196, 0.28)'
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
                  background: active ? 'var(--color-bg)' : 'transparent',
                  color: active ? 'var(--color-text)' : paperInkDim,
                  border: 'none',
                  borderLeft: i > 0 ? '1px solid rgba(237, 226, 196, 0.28)' : 'none',
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

        <select
          className="header-theme-select"
          value={themeName}
          onChange={(e) => setThemeName(e.target.value)}
          style={paper ? {
            background: 'transparent',
            color: paperInk,
            border: '1px solid rgba(237, 226, 196, 0.28)',
            borderRadius: '2px',
            padding: '6px 10px',
            fontSize: 'calc(11px * var(--font-scale))',
            fontFamily: 'var(--font-mono)',
            letterSpacing: '0.10em',
            cursor: 'pointer',
            outline: 'none',
          } : {
            background: 'var(--color-bg-secondary)',
            color: 'var(--color-text)',
            border: '1px solid var(--color-border)',
            borderRadius: '6px',
            padding: '6px 10px',
            fontSize: 'calc(13px * var(--font-scale))',
            fontFamily: 'var(--font-body)',
            cursor: 'pointer',
            outline: 'none',
          }}
        >
          {Object.values(themes).map((t) => (
            <option key={t.name} value={t.name} style={{ color: 'var(--color-text)', background: 'var(--color-bg-card)' }}>
              {t.label}
            </option>
          ))}
        </select>

        <button
          onClick={user?.authenticated ? logout : () => navigate("/login", { state: { from: location.pathname } })}
          style={paper ? {
            background: 'none',
            border: '1px solid rgba(237, 226, 196, 0.28)',
            borderRadius: '2px',
            padding: '6px 12px',
            fontSize: 'calc(11px * var(--font-scale))',
            fontFamily: 'var(--font-mono)',
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            color: paperInkDim,
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
          {user?.authenticated ? "Logout" : "Login"}
        </button>
      </div>
    </header>
  );
}
