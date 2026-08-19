import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { useFeatureFlags } from '../../context/FeatureFlagsContext';
import { usePersona, type Persona } from '../../context/PersonaContext';
import { useTheme } from '../../context/ThemeContext';

interface SidebarProps {
  open: boolean;
  onClose: () => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

interface NavItem {
  to: string;
  label: string;
  icon: string;
}

const navItems: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: '▣' },
  { to: '/history', label: 'History', icon: '◷' },
  { to: '/forecast', label: 'Forecast', icon: '☁' },
  { to: '/astronomy', label: 'Astronomy', icon: '☽' },
  { to: '/map', label: 'Map', icon: '⦿' },
  { to: '/nowcast', label: 'Nowcast', icon: '⛅' },
  { to: '/spray', label: 'Spray', icon: '☘' },
  { to: '/settings', label: 'Settings', icon: '⚙' },
];

const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'];

/**
 * Persona-specific overlays on top of the feature-flag filter.
 *
 * ``order`` lists nav paths the persona reorders to the front — items
 * not named keep their original order behind them.  ``hide`` removes
 * paths from the persona view.  Both are additive to the
 * ``mapEnabled`` / ``nowcastEnabled`` / ``sprayEnabled`` flag filter
 * (which is checked first): a page hidden by feature flag stays
 * hidden regardless of persona.
 */
const PERSONA_NAV: Record<Persona, { order: string[]; hide: string[] }> = {
  everyday: { order: [], hide: [] },
  agriculture: {
    order: ['/', '/spray', '/forecast', '/nowcast', '/history', '/map', '/astronomy', '/settings'],
    hide: [],
  },
  weather_nerd: {
    order: [],
    hide: ['/spray'],
  },
};

function applyPersonaOrder(items: NavItem[], order: string[]): NavItem[] {
  if (order.length === 0) return items;
  const byPath = new Map(items.map((n) => [n.to, n]));
  const ordered: NavItem[] = [];
  const seen = new Set<string>();
  for (const path of order) {
    const n = byPath.get(path);
    if (n) { ordered.push(n); seen.add(path); }
  }
  for (const n of items) {
    if (!seen.has(n.to)) ordered.push(n);
  }
  return ordered;
}

export default function Sidebar({ open, onClose, collapsed = false, onToggleCollapse }: SidebarProps) {
  const { flags } = useFeatureFlags();
  const { persona } = usePersona();
  const { theme } = useTheme();
  const [showAll, setShowAll] = useState(false);

  // Paper themes render a fundamentally different sidebar per the
  // Design Agent's `1c-dashboard-glaisher-notebook.png` mock: same
  // cream shell background, but small-caps mono item labels, icons
  // on the RIGHT, no rounded-pill active state — the active row is
  // a full-width dark rectangle instead.
  const paper = theme.surface.ownsBackground;

  // Feature-flag filter always applies (see NavItem hide/order note above).
  const flagFiltered = navItems.filter((item) => {
    if (item.to === '/map') return flags.mapEnabled;
    if (item.to === '/nowcast') return flags.nowcastEnabled;
    if (item.to === '/spray') return flags.sprayEnabled;
    return true;
  });

  const { order, hide } = PERSONA_NAV[persona];
  const personaHiddenPaths = showAll ? [] : hide;
  const afterPersonaHide = flagFiltered.filter((n) => !personaHiddenPaths.includes(n.to));
  const visibleNavItems = applyPersonaOrder(afterPersonaHide, order);

  // Count items the persona is hiding right now (from the flag-passing
  // set only — a page killed by a feature flag isn't a persona hide).
  const hiddenByPersona = flagFiltered.filter((n) => hide.includes(n.to)).length;

  return (
    <>
      {/* Overlay for mobile */}
      {open && (
        <div
          className="sidebar-overlay"
          onClick={onClose}
          style={{
            position: 'fixed',
            inset: 0,
            top: '56px',
            background: 'rgba(0,0,0,0.4)',
            zIndex: 49,
            display: 'none',
          }}
        />
      )}

      <aside
        className={`sidebar ${open ? 'sidebar-open' : ''}`}
        style={{
          position: 'fixed',
          top: paper ? '60px' : '56px',
          left: 0,
          bottom: 0,
          width: collapsed ? '56px' : '220px',
          background: 'var(--color-sidebar-bg)',
          borderRight: paper
            ? `${theme.rules.hairline}px solid ${theme.rules.strong}`
            : '1px solid var(--color-border)',
          display: 'flex',
          flexDirection: 'column',
          padding: paper ? '18px 0' : '12px 0',
          zIndex: 50,
          overflowY: 'auto',
          overflowX: 'hidden',
          fontFamily: 'var(--font-body)',
          transition: 'transform 0.2s ease, width 0.2s ease',
        }}
      >
        <nav style={{ display: 'flex', flexDirection: 'column', gap: paper ? '0' : '2px', padding: paper ? '0 14px' : '0 8px', flex: 1 }}>
          {visibleNavItems.map((item, itemIdx) => {
            const iconHue = theme.nav?.iconHues?.[item.to];
            const showRoman = paper && theme.nav?.indexStyle === 'roman' && !collapsed;
            const separator = paper
              ? `${theme.rules.hairline}px ${theme.rules.style} ${theme.rules.strong}`
              : 'none';
            return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              onClick={onClose}
              title={collapsed ? item.label : undefined}
              style={({ isActive }) => (paper ? {
                display: 'flex',
                alignItems: 'center',
                justifyContent: collapsed ? 'center' : 'space-between',
                padding: collapsed ? '12px 0' : '11px 12px',
                textDecoration: 'none',
                fontFamily: 'var(--font-mono)',
                fontSize: 'calc(11px * var(--font-scale))',
                fontWeight: isActive ? 700 : 500,
                letterSpacing: '1.8px',
                textTransform: 'uppercase',
                color: isActive ? 'var(--color-bg)' : 'var(--color-text)',
                background: isActive ? 'var(--color-text)' : 'transparent',
                borderBottom: isActive || itemIdx === visibleNavItems.length - 1
                  ? 'none'
                  : separator,
                transition: 'color 0.15s ease, background 0.15s ease',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
              } : {
                display: 'flex',
                alignItems: 'center',
                gap: collapsed ? '0' : '10px',
                justifyContent: collapsed ? 'center' : 'flex-start',
                padding: collapsed ? '10px 0' : '10px 12px',
                borderRadius: '8px',
                textDecoration: 'none',
                fontSize: 'calc(14px * var(--font-scale))',
                fontWeight: isActive ? 600 : 400,
                color: isActive ? 'var(--color-accent)' : 'var(--color-text-secondary)',
                background: isActive ? 'var(--color-accent-muted)' : 'transparent',
                transition: 'background 0.15s ease, color 0.15s ease',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
              })}
            >
              {({ isActive }: { isActive: boolean }) => paper ? (
                <>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0, overflow: 'hidden' }}>
                    {showRoman && (
                      <span style={{
                        width: '26px',
                        fontFamily: 'var(--font-heading)',
                        fontSize: 'calc(12px * var(--font-scale))',
                        fontStyle: 'italic',
                        fontWeight: 600,
                        letterSpacing: '0',
                        textTransform: 'none',
                        color: isActive ? 'var(--color-bg)' : 'rgba(58, 45, 29, 0.84)',
                        flexShrink: 0,
                      }}>
                        {ROMAN[itemIdx]}
                      </span>
                    )}
                    {!collapsed && <span>{item.label}</span>}
                  </span>
                  <span style={{
                    fontSize: 'calc(15px * var(--font-scale))',
                    width: '18px',
                    textAlign: 'center',
                    flexShrink: 0,
                    color: isActive ? 'var(--color-bg)' : (iconHue ?? 'var(--color-text)'),
                    opacity: isActive ? 1 : (iconHue ? 1 : 0.55),
                  }}>
                    {item.icon}
                  </span>
                </>
              ) : (
                <>
                  <span style={{
                    fontSize: 'calc(16px * var(--font-scale))',
                    width: '20px',
                    textAlign: 'center',
                    flexShrink: 0,
                    color: isActive
                      ? 'var(--color-accent)'
                      : (iconHue ?? 'var(--color-text-secondary)'),
                  }}>
                    {item.icon}
                  </span>
                  {!collapsed && <span>{item.label}</span>}
                </>
              )}
            </NavLink>
            );
          })}

          {/* Reversible "N pages hidden" note — always render when the
              persona hides anything, so no page ever disappears
              silently.  Clicking Show/Hide re-includes them without
              changing the stored persona. */}
          {!collapsed && hiddenByPersona > 0 && (
            <div style={{
              marginTop: '12px',
              padding: '8px 12px',
              fontSize: 'calc(11px * var(--font-scale))',
              color: 'var(--color-text-muted)',
              fontFamily: 'var(--font-body)',
              lineHeight: 1.4,
            }}>
              {showAll ? (
                <>
                  Showing all pages.{' '}
                  <button
                    type="button"
                    onClick={() => setShowAll(false)}
                    style={{
                      background: 'none',
                      border: 'none',
                      padding: 0,
                      color: 'var(--color-accent)',
                      textDecoration: 'underline',
                      cursor: 'pointer',
                      font: 'inherit',
                    }}
                  >
                    Hide {hiddenByPersona} again
                  </button>
                </>
              ) : (
                <>
                  {hiddenByPersona} page{hiddenByPersona === 1 ? '' : 's'} hidden by this persona.{' '}
                  <button
                    type="button"
                    onClick={() => setShowAll(true)}
                    style={{
                      background: 'none',
                      border: 'none',
                      padding: 0,
                      color: 'var(--color-accent)',
                      textDecoration: 'underline',
                      cursor: 'pointer',
                      font: 'inherit',
                    }}
                  >
                    Show all pages
                  </button>
                </>
              )}
            </div>
          )}
        </nav>

        {/* About link — anchored at bottom */}
        <div style={{ padding: paper ? '0 14px' : '0 8px', marginTop: 'auto' }}>
          {/* Mammoth's stripe ribbon above the About row: three equal
              flex children, per the mock's `mammothNav`.  Themes that
              omit `nav.ribbon` render nothing here. */}
          {paper && theme.nav?.ribbon && theme.nav.ribbon.length > 0 && (
            <div style={{ display: 'flex', height: '3px', marginBottom: '8px' }}>
              {theme.nav.ribbon.map((c, i) => (
                <span key={i} style={{ flex: 1, background: c }} />
              ))}
            </div>
          )}
          <NavLink
            to="/about"
            onClick={onClose}
            title={collapsed ? 'About' : undefined}
            style={({ isActive }) => (paper ? {
              display: 'flex',
              alignItems: 'center',
              justifyContent: collapsed ? 'center' : 'space-between',
              padding: collapsed ? '12px 0' : '11px 12px',
              textDecoration: 'none',
              fontFamily: 'var(--font-mono)',
              fontSize: 'calc(11px * var(--font-scale))',
              fontWeight: isActive ? 700 : 500,
              letterSpacing: '1.8px',
              textTransform: 'uppercase',
              color: isActive ? 'var(--color-bg)' : 'var(--color-text)',
              background: isActive ? 'var(--color-text)' : 'transparent',
              transition: 'color 0.15s ease, background 0.15s ease',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
            } : {
              display: 'flex',
              alignItems: 'center',
              gap: collapsed ? '0' : '10px',
              justifyContent: collapsed ? 'center' : 'flex-start',
              padding: collapsed ? '10px 0' : '10px 12px',
              borderRadius: '8px',
              textDecoration: 'none',
              fontSize: 'calc(14px * var(--font-scale))',
              fontWeight: isActive ? 600 : 400,
              color: isActive ? 'var(--color-accent)' : 'var(--color-text-secondary)',
              background: isActive ? 'var(--color-accent-muted)' : 'transparent',
              transition: 'background 0.15s ease, color 0.15s ease',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
            })}
          >
            {({ isActive }: { isActive: boolean }) => paper ? (
              <>
                <span style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0, overflow: 'hidden' }}>
                  {theme.nav?.indexStyle === 'roman' && !collapsed && (
                    <span style={{
                      width: '26px',
                      fontFamily: 'var(--font-heading)',
                      fontSize: 'calc(12px * var(--font-scale))',
                      fontStyle: 'italic',
                      fontWeight: 600,
                      letterSpacing: '0',
                      textTransform: 'none',
                      color: isActive ? 'var(--color-bg)' : 'rgba(58, 45, 29, 0.84)',
                      flexShrink: 0,
                    }}>
                      {ROMAN[visibleNavItems.length]}
                    </span>
                  )}
                  {!collapsed && <span>About</span>}
                </span>
                <span style={{
                  fontSize: 'calc(15px * var(--font-scale))',
                  width: '18px',
                  textAlign: 'center',
                  flexShrink: 0,
                  color: isActive ? 'var(--color-bg)' : 'var(--color-text)',
                  opacity: isActive ? 1 : 0.55,
                }}>
                  {'ⓘ'}
                </span>
              </>
            ) : (
              <>
                <span style={{ fontSize: 'calc(16px * var(--font-scale))', width: '20px', textAlign: 'center', flexShrink: 0 }}>
                  {'ⓘ'}
                </span>
                {!collapsed && <span>About</span>}
              </>
            )}
          </NavLink>
        </div>

        {/* Collapse toggle (desktop only).  Kept on paper themes too —
            the mock omits it, but operators need a way to collapse the
            sidebar on narrow desktop windows.  Styled flat on paper to
            fit the cream shell instead of the boxed non-paper look. */}
        {onToggleCollapse && (
          <div style={{
            padding: paper ? '10px 14px' : '8px',
            borderTop: paper
              ? `${theme.rules.hairline}px ${theme.rules.style} ${theme.rules.strong}`
              : '1px solid var(--color-border)',
          }}>
            <button
              className="sidebar-collapse-btn"
              onClick={onToggleCollapse}
              title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              style={paper ? {
                background: 'transparent',
                border: 'none',
                color: 'var(--color-text)',
                cursor: 'pointer',
                padding: '4px 0',
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                opacity: 0.65,
                transition: 'opacity 0.15s ease',
              } : {
                background: 'var(--color-bg-secondary)',
                border: '1px solid var(--color-border)',
                borderRadius: '6px',
                color: 'var(--color-text-secondary)',
                cursor: 'pointer',
                padding: '8px 0',
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'background 0.15s ease, color 0.15s ease',
              }}
            >
              {/* Animated hamburger-to-arrow */}
              <div style={{
                width: '18px',
                height: '14px',
                position: 'relative',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}>
                <span style={{
                  display: 'block',
                  height: '2px',
                  background: 'currentColor',
                  borderRadius: '1px',
                  transformOrigin: 'right center',
                  transition: 'transform 0.3s ease, width 0.3s ease',
                  transform: collapsed ? 'none' : 'rotate(-30deg)',
                  width: collapsed ? '100%' : '60%',
                }} />
                <span style={{
                  display: 'block',
                  height: '2px',
                  background: 'currentColor',
                  borderRadius: '1px',
                  transition: 'transform 0.3s ease',
                  width: '100%',
                }} />
                <span style={{
                  display: 'block',
                  height: '2px',
                  background: 'currentColor',
                  borderRadius: '1px',
                  transformOrigin: 'right center',
                  transition: 'transform 0.3s ease, width 0.3s ease',
                  transform: collapsed ? 'none' : 'rotate(30deg)',
                  width: collapsed ? '100%' : '60%',
                }} />
              </div>
            </button>
          </div>
        )}
      </aside>
    </>
  );
}
