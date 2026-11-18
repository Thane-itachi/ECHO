import { Link, NavLink } from 'react-router-dom';
import { Button } from '../components/ui';

import { useAuth } from '../lib/auth';
import { TEXT_SIZES, useTextSize } from '../lib/textSize';

/**
 * The block that used to fold out of the bottom of the sidebar, on a page of its
 * own: the reading size, who you are signed in as, and the pages that are not
 * notes. None of it is about your memories, which is the whole reason it does
 * not belong in the rail beside them.
 */

const ACCOUNT = [
  { to: '/profile', label: 'Your account', hint: 'Your name and address' },
  { to: '/security', label: 'Security', hint: 'Password, sign-in codes, deleting your notes' },
  { to: '/settings', label: 'Settings', hint: 'Reminder email and phone notifications' },
];

const ABOUT = [
  { to: '/help', label: 'Questions', hint: 'Plain answers to the ten that come up' },
  { to: '/privacy', label: 'Privacy', hint: 'What is encrypted, and what is not' },
  { to: '/architecture', label: 'How ECHO is built', hint: 'The blueprint, and what is deliberately missing' },
];

export default function Menu() {
  const { user, signOut } = useAuth();
  const [textSize, setTextSize] = useTextSize();
  const initial = (user?.email ?? '?').charAt(0).toUpperCase();

  return (
    <div className="page page-narrow">
      <header className="page-head">
        <div>
          <p className="eyebrow">Menu</p>
          <h1>Your account, and everything else</h1>
          <p className="page-sub">
            The reading size, who you are signed in as, and the pages that are not notes.
          </p>
        </div>
      </header>

      <section className="report-section">
        <h2 className="section-title">Reading</h2>
        <div className="set-list">
          <div className="set-row">
            <span>
              <b>Text size</b>
              <small>The whole app, remembered on this device.</small>
            </span>
            <span className="text-size-buttons">
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
            </span>
          </div>
        </div>
      </section>

      <section className="report-section">
        <h2 className="section-title">Signed in as</h2>
        <Link className="who-card" to="/profile">
          <span className="who-monogram" aria-hidden="true">
            {initial}
          </span>
          <span className="who-text">
            <b title={user?.email}>{user?.email}</b>
            <small>Open your account</small>
          </span>
          <span className="who-go" aria-hidden="true">
            ›
          </span>
        </Link>
      </section>

      <section className="report-section">
        <h2 className="section-title">Your account</h2>
        <nav className="menu-list" aria-label="Your account">
          {ACCOUNT.map((item) => (
            <NavLink key={item.to} className="menu-row" to={item.to}>
              <span className="menu-row-text">
                <b>{item.label}</b>
                <small>{item.hint}</small>
              </span>
            </NavLink>
          ))}
          <a className="menu-row" href="/admin">
            <span className="menu-row-text">
              <b>Admin console</b>
              <small>The console, with its own sign-in</small>
            </span>
          </a>
        </nav>
      </section>

      <section className="report-section">
        <h2 className="section-title">About ECHO</h2>
        <nav className="menu-list" aria-label="About ECHO">
          {ABOUT.map((item) => (
            <NavLink key={item.to} className="menu-row" to={item.to}>
              <span className="menu-row-text">
                <b>{item.label}</b>
                <small>{item.hint}</small>
              </span>
            </NavLink>
          ))}
        </nav>
      </section>

      <div className="menu-signout">
        <Button variant="secondary" type="button" onClick={signOut}>
          Sign out
        </Button>
        <p className="menu-note">Everything in your vault is sealed with your own key.</p>
      </div>
    </div>
  );
}
