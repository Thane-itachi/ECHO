import { NavLink, Outlet } from 'react-router-dom';

import { useAdminAuth } from './AdminAuth';
import { EchoMark } from '../components/Logo';

const NAV = [
  { to: '/admin', label: 'Overview', permission: 'stats:read', end: true },
  { to: '/admin/users', label: 'Users', permission: 'users:read' },
  { to: '/admin/admins', label: 'Administrators', permission: 'admins:read' },
  { to: '/admin/audit', label: 'Audit log', permission: 'audit:read' },
  { to: '/admin/security', label: 'Security', permission: 'security:read' },
];

const ROLE_LABEL: Record<string, string> = {
  founder: 'Founder',
  platform_admin: 'Platform admin',
  support_admin: 'Support admin',
};

export default function AdminShell() {
  const { identity, signOut } = useAdminAuth();

  return (
    <div className="shell admin-shell">
      <aside className="sidebar">
        <div className="brand">
          <EchoMark size={34} />
          <span className="brand-text">
            <span className="brand-mark">ECHO</span>
            <span className="brand-tagline">admin console</span>
          </span>
        </div>

        <nav className="nav">
          {NAV.filter((item) => identity?.permissions.includes(item.permission)).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => (isActive ? 'nav-item is-active' : 'nav-item')}
            >
              <span className="nav-label">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="account">
            <span className="account-label">{ROLE_LABEL[identity?.role ?? ''] ?? 'Admin'}</span>
            <span className="account-email">{identity?.email}</span>
          </div>
          <a className="ghost-button" href="/vault">
            Back to vault
          </a>
          <button type="button" className="ghost-button" onClick={signOut}>
            Sign out
          </button>
        </div>
      </aside>

      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
