import { useEffect, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';

import { listProposals } from '../lib/api';
import { useAuth } from '../lib/auth';

const NAV = [
  { to: '/vault', label: 'Memory Vault', hint: 'Everything you have told ECHO' },
  { to: '/ask', label: 'Ask ECHO', hint: 'Find what you have stored' },
  { to: '/people', label: 'People', hint: 'Who your memories are about' },
  { to: '/proposals', label: 'Captures', hint: 'Wait for your approval' },
  { to: '/reminders', label: 'Reminders', hint: 'Promises with a date' },
];

export default function Layout() {
  const { user, signOut } = useAuth();
  const [pending, setPending] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    listProposals('pending')
      .then((page) => {
        if (alive) setPending(page.total);
      })
      .catch(() => {
        /* the badge is decoration; never block the app for it */
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">ECHO</span>
          <span className="brand-tagline">never forget what matters</span>
        </div>

        <nav className="nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => (isActive ? 'nav-item is-active' : 'nav-item')}
            >
              <span className="nav-label">
                {item.label}
                {item.to === '/proposals' && pending ? <span className="badge">{pending}</span> : null}
              </span>
              <span className="nav-hint">{item.hint}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="account">
            <span className="account-label">Signed in as</span>
            <span className="account-email">{user?.email}</span>
          </div>
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
