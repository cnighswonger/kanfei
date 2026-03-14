import { NavLink } from 'react-router-dom';
import { useFeatureFlags } from '../../context/FeatureFlagsContext';

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
  { to: '/', label: 'Dashboard', icon: '\u25A3' },
  { to: '/history', label: 'History', icon: '\u25F7' },
  { to: '/forecast', label: 'Forecast', icon: '\u2601' },
  { to: '/astronomy', label: 'Astronomy', icon: '\u263D' },
  { to: '/nowcast', label: 'Nowcast', icon: '\u26C5' },
  { to: '/spray', label: 'Spray', icon: '\u2618' },
  { to: '/settings', label: 'Settings', icon: '\u2699' },
];

export default function Sidebar({ open, onClose, collapsed = false, onToggleCollapse }: SidebarProps) {
  const { flags } = useFeatureFlags();

  const visibleNavItems = navItems.filter((item) => {
    if (item.to === '/nowcast') return flags.nowcastEnabled;
    if (item.to === '/spray') return flags.sprayEnabled;
    return true;
  });

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
          top: '56px',
          left: 0,
          bottom: 0,
          width: collapsed ? '56px' : '220px',
          background: 'var(--color-sidebar-bg)',
          borderRight: '1px solid var(--color-border)',
          display: 'flex',
          flexDirection: 'column',
          padding: '12px 0',
          zIndex: 50,
          overflowY: 'auto',
          overflowX: 'hidden',
          fontFamily: 'var(--font-body)',
          transition: 'transform 0.2s ease, width 0.2s ease',
        }}
      >
        <nav style={{ display: 'flex', flexDirection: 'column', gap: '2px', padding: '0 8px', flex: 1 }}>
          {visibleNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              onClick={onClose}
              title={collapsed ? item.label : undefined}
              style={({ isActive }) => ({
                display: 'flex',
                alignItems: 'center',
                gap: collapsed ? '0' : '10px',
                justifyContent: collapsed ? 'center' : 'flex-start',
                padding: collapsed ? '10px 0' : '10px 12px',
                borderRadius: '8px',
                textDecoration: 'none',
                fontSize: '14px',
                fontWeight: isActive ? 600 : 400,
                color: isActive ? 'var(--color-accent)' : 'var(--color-text-secondary)',
                background: isActive ? 'var(--color-accent-muted)' : 'transparent',
                transition: 'background 0.15s ease, color 0.15s ease',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
              })}
            >
              <span style={{ fontSize: '16px', width: '20px', textAlign: 'center', flexShrink: 0 }}>
                {item.icon}
              </span>
              {!collapsed && <span>{item.label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* About link — anchored at bottom */}
        <div style={{ padding: '0 8px', marginTop: 'auto' }}>
          <NavLink
            to="/about"
            onClick={onClose}
            title={collapsed ? 'About' : undefined}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: collapsed ? '0' : '10px',
              justifyContent: collapsed ? 'center' : 'flex-start',
              padding: collapsed ? '10px 0' : '10px 12px',
              borderRadius: '8px',
              textDecoration: 'none',
              fontSize: '14px',
              fontWeight: isActive ? 600 : 400,
              color: isActive ? 'var(--color-accent)' : 'var(--color-text-secondary)',
              background: isActive ? 'var(--color-accent-muted)' : 'transparent',
              transition: 'background 0.15s ease, color 0.15s ease',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
            })}
          >
            <span style={{ fontSize: '16px', width: '20px', textAlign: 'center', flexShrink: 0 }}>
              {'\u24D8'}
            </span>
            {!collapsed && <span>About</span>}
          </NavLink>
        </div>

        {/* Collapse toggle (desktop only) */}
        {onToggleCollapse && (
          <div style={{ padding: '8px', borderTop: '1px solid var(--color-border)' }}>
            <button
              className="sidebar-collapse-btn"
              onClick={onToggleCollapse}
              title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              style={{
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
