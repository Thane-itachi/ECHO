import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet } from 'react-router-dom';

import { EchoMark } from '../components/Logo';
import NavIcon from '../components/NavIcon';
import { listProposals } from '../lib/api';
import { useAuth } from '../lib/auth';

/* Plain words, each with a picture. "Vault" and "captures" are the sort of words
   that mean nothing to someone who has not spent their life in software.

   The order is the order of the day: what needs you, what you saved, what you
   want to find, and only then the shelves. Nine destinations is what fits a
   phone as a 3 x 3 grid without a single one hiding past the edge. */
const NAV = [
  { to: '/dashboard', label: 'Today', short: 'Today', hint: 'What needs you', icon: 'today' },
  { to: '/vault', label: 'My notes', short: 'Notes', hint: 'Everything you have saved', icon: 'notes' },
  { to: '/ask', label: 'Ask a question', short: 'Ask', hint: 'Find one thing you saved', icon: 'ask' },
  { to: '/people', label: 'People', short: 'People', hint: 'Names you have saved', icon: 'people' },
  { to: '/proposals', label: 'Things to check', short: 'To check', hint: 'ECHO found these. Say yes or no.', icon: 'check' },
  { to: '/reminders', label: 'Reminders', short: 'Reminders', hint: 'Dates you must not miss', icon: 'bell' },
  { to: '/documents', label: 'Files', short: 'Files', hint: 'Papers and pictures you added', icon: 'files' },
  { to: '/search', label: 'Search', short: 'Search', hint: 'Look through every word', icon: 'search' },
  { to: '/reports', label: 'Reports', short: 'Reports', hint: 'What your memory holds', icon: 'chart' },
];

export default function Layout() {
  const { user } = useAuth();
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
        <div className="sidebar-top">
          <Link className="brand" to="/dashboard" aria-label="ECHO home">
            <EchoMark size={34} />
            <span className="brand-text">
              <span className="brand-mark">ECHO</span>
              <span className="brand-tagline">never forget what matters</span>
            </span>
          </Link>

          {/* One tap to the menu page, which now holds everything that used to
              fold out of this rail: text size, the account, and sign out. */}
          <Link className="sidebar-more" to="/menu">
            <span>Menu</span>
            <span aria-hidden="true">›</span>
          </Link>
        </div>

        <nav className="nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => (isActive ? 'nav-item is-active' : 'nav-item')}
            >
              <NavIcon name={item.icon} />
              <span className="nav-label">
                <span className="nav-long">{item.label}</span>
                <span className="nav-short">{item.short}</span>
                {item.to === '/proposals' && pending ? <span className="badge">{pending}</span> : null}
              </span>
              <span className="nav-hint">{item.hint}</span>
            </NavLink>
          ))}
        </nav>

        {/* Who you are, and the way into the menu. On a phone the whole rail is
            a bar, so this card is hidden there and the Menu button stands in. */}
        <Link className="foot-who" to="/menu">
          <span className="foot-monogram" aria-hidden="true">
            {(user?.email ?? '?').charAt(0).toUpperCase()}
          </span>
          <span className="foot-who-text">
            <small>Signed in as</small>
            <b>{user?.email}</b>
          </span>
          <span className="foot-go" aria-hidden="true">
            ›
          </span>
        </Link>
      </aside>

      <main className="main">
        <Outlet />
        <footer className="app-foot">
          <span className="app-foot-mark">ECHO</span>
          <span>kept by hand, sealed with your own key</span>
        </footer>
      </main>
    </div>
  );
}
