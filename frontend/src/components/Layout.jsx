import { NavLink, Outlet } from 'react-router-dom';
import './Layout.css';

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: '📊' },
  { to: '/jobs', label: 'Jobs', icon: '📋' },
  { to: '/create', label: 'Create Job', icon: '➕' },
  { to: '/dlq', label: 'Dead Letter Queue', icon: '💀' },
  { to: '/workflows', label: 'Workflows', icon: '🔗' },
];

export default function Layout() {
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar__brand">
          <span className="sidebar__logo">⚡</span>
          <h1 className="sidebar__title">Job Scheduler</h1>
        </div>

        <nav className="sidebar__nav">
          {NAV_ITEMS.map(({ to, label, icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `sidebar__link ${isActive ? 'sidebar__link--active' : ''}`
              }
            >
              <span className="sidebar__link-icon">{icon}</span>
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__footer">
          <span className="sidebar__version">v1.0.0</span>
        </div>
      </aside>

      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
