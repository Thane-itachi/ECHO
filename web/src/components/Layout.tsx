import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet } from 'react-router-dom';

import { EchoMark } from '../components/Logo';
import NavIcon from '../components/NavIcon';
import { listProposals } from '../lib/api';
import { useAuth } from '../lib/auth';
import { TEXT_SIZES, useTextSize } from '../lib/textSize';

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

/* The account pages live behind one row each, not a form in the sidebar: a
   password box printed under the notes is the wrong thing to meet on a phone. */
const ACCOUNT = [
  { to: '/profile', label: 'Your account' },
  { to: '/security', label: 'Security' },
  { to: '/settings', label: 'Settings' },
];

export default function Layout() {
  const { user, signOut } = useAuth();
  const [pending, setPending] = useState<number | null>(null);
  const [textSize, setTextSize] = useTextSize();
  // Phones show the nine destinations and fold the rest of the sidebar away:
  // a settings column above the notes is the first thing that makes a phone
  // screen feel wrong. Wide screens ignore this and show everything.
  const [moreOpen, setMoreOpen] = useState(false);

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

          <button
            type="button"
            className="sidebar-more"
            aria-expanded={moreOpen}
            aria-controls="sidebar-more-panel"
            onClick={() => setMoreOpen((open) => !open)}
          >
            <span>{moreOpen ? 'Hide' : 'Settings'}</span>
            <span aria-hidden="true">{moreOpen ? '▲' : '▼'}</span>
          </button>
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

        <div id="sidebar-more-panel" className={moreOpen ? 'sidebar-foot is-open' : 'sidebar-foot'}>
          <div className="text-size">
            <span>Text size</span>
            <div className="text-size-buttons">
              {TEXT_SIZES.map((size) => (
                <button
                  key={size.value}
                  type="button"
                  aria-pressed={textSize === size.value}
                  onClick={() => setTextSize(size.value)}
                >
                  {size.label}
                </button>
              ))}
            </div>
          </div>
          <div className="account">
            <span className="account-label">Signed in as</span>
            <span className="account-email">{user?.email}</span>
          </div>
          <div className="sidebar-links">
            {ACCOUNT.map((item) => (
              <Link key={item.to} className="ghost-button" to={item.to}>
                {item.label}
              </Link>
            ))}
            <Link className="ghost-button" to="/help">
              Questions
            </Link>
            <Link className="ghost-button" to="/privacy">
              Privacy
            </Link>
          </div>
          <a className="ghost-button" href="/admin">
            Admin console
          </a>
          <button type="button" className="ghost-button" onClick={signOut}>
            Sign out
          </button>
          <p className="sidebar-note">Everything here is sealed with your own key.</p>
        </div>
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
