import { Link } from 'react-router-dom';

import { formatDate } from '../lib/api';
import { useAuth } from '../lib/auth';
import { TEXT_SIZES, useTextSize } from '../lib/textSize';

/**
 * Who you are here, and how the reading feels.
 *
 * One account, one address, one key. The page states the facts it can prove from
 * the API — when the account started, whether the address is confirmed, whether a
 * code is asked for — rather than decorating a profile with things that are not real.
 */
export default function Profile() {
  const { user, signOut } = useAuth();
  const [textSize, setTextSize] = useTextSize();

  return (
    <div className="page page-narrow">
      <header className="page-head">
        <div>
          <p className="eyebrow">Your account</p>
          <h1>Profile</h1>
          <p className="page-sub">
            The one account behind your notes, your reminders and the console you run them from.
          </p>
        </div>
      </header>

      <div className="profile-card card">
        <span className="profile-monogram" aria-hidden="true">
          {(user?.email ?? '?').slice(0, 1).toUpperCase()}
        </span>
        <div>
          <p className="profile-email">{user?.email ?? '—'}</p>
          <p className="stat-hint">
            {user ? `Member since ${formatDate(user.created_at)}` : 'Loading your account…'}
          </p>
        </div>
      </div>

      <section className="report-section">
        <h2 className="section-title">The account in plain words</h2>
        <dl className="facts">
          <div>
            <dt>Email</dt>
            <dd>{user?.email ?? '—'}</dd>
          </div>
          <div>
            <dt>Email confirmed</dt>
            <dd>{user?.email_verified ? 'Yes' : 'Not yet'}</dd>
          </div>
          <div>
            <dt>Code at sign-in</dt>
            <dd>{user?.email_otp_enabled ? 'Asked for' : 'Password only'}</dd>
          </div>
          <div>
            <dt>Reminder email</dt>
            <dd>{user?.reminder_email_enabled ? 'On' : 'Off'}</dd>
          </div>
          <div>
            <dt>Admin console</dt>
            <dd>Same address, own code</dd>
          </div>
        </dl>
        <p className="stat-hint">
          One address opens both doors. The console also asks for a six-digit code; your notes do not, so the
          thing you use every day stays quick to open.
        </p>
      </section>

      <section className="report-section">
        <h2 className="section-title">Text size</h2>
        <p className="stat-hint">
          The same three sizes as the menu page. It applies to the whole app and is remembered on this device.
        </p>
        <div className="text-size-buttons profile-sizes">
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
      </section>

      <section className="report-section">
        <h2 className="section-title">Keep going</h2>
        <div className="sidebar-links profile-links">
          <Link className="ghost-button" to="/security">
            Password and security
          </Link>
          <Link className="ghost-button" to="/settings">
            Notifications and settings
          </Link>
          <Link className="ghost-button" to="/privacy">
            How privacy works
          </Link>
          <Link className="ghost-button" to="/architecture">
            How ECHO is built
          </Link>
        </div>
        <button type="button" className="ghost-button is-danger" onClick={signOut}>
          Sign out
        </button>
      </section>
    </div>
  );
}
