import { useEffect, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';

import { EchoMark } from '../components/Logo';
import NotificationToggle from '../components/NotificationToggle';
import { listProposals } from '../lib/api';
import { useAuth } from '../lib/auth';

const NAV = [
  { to: '/vault', label: 'Memory Vault', hint: 'Everything you have told ECHO' },
  { to: '/ask', label: 'Ask ECHO', hint: 'Find what you have stored' },
  { to: '/people', label: 'People', hint: 'Who your memories are about' },
  { to: '/proposals', label: 'Captures', hint: 'Wait for your approval' },
  { to: '/reminders', label: 'Reminders', hint: 'Promises with a date' },
  { to: '/documents', label: 'Documents', hint: 'Receipts and certificates, encrypted' },
];

export default function Layout() {
  const { user, signOut, setEmailOtp, setReminderEmail } = useAuth();
  const [pending, setPending] = useState<number | null>(null);
  const [otpBusy, setOtpBusy] = useState(false);
  const [otpError, setOtpError] = useState<string | null>(null);
  const [reminderBusy, setReminderBusy] = useState(false);

  async function toggleSignInCode(enabled: boolean) {
    setOtpBusy(true);
    setOtpError(null);
    try {
      await setEmailOtp(enabled);
    } catch {
      setOtpError('Could not change that. Confirm your email address first.');
    } finally {
      setOtpBusy(false);
    }
  }

  async function toggleReminderEmail(enabled: boolean) {
    setReminderBusy(true);
    setOtpError(null);
    try {
      await setReminderEmail(enabled);
    } catch {
      setOtpError('Could not change that just now. Try again in a moment.');
    } finally {
      setReminderBusy(false);
    }
  }

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
          <EchoMark size={34} />
          <span className="brand-text">
            <span className="brand-mark">ECHO</span>
            <span className="brand-tagline">never forget what matters</span>
          </span>
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
          <a className="ghost-button" href="/admin">
            Admin console
          </a>
          <button type="button" className="ghost-button" onClick={signOut}>
            Sign out
          </button>
          <label className="sidebar-toggle">
            <input
              type="checkbox"
              checked={user?.email_otp_enabled ?? false}
              disabled={otpBusy || !user?.email_verified}
              onChange={(event) => void toggleSignInCode(event.target.checked)}
            />
            <span>
              Email me a code at sign-in
              <small>Your password, then six digits. Off by default.</small>
            </span>
          </label>
          <label className="sidebar-toggle">
            <input
              type="checkbox"
              checked={user?.reminder_email_enabled ?? true}
              disabled={reminderBusy}
              onChange={(event) => void toggleReminderEmail(event.target.checked)}
            />
            <span>
              Email me reminders
              <small>A promise lands in your inbox when it comes due. One click turns it off.</small>
            </span>
          </label>
          <NotificationToggle />
          {otpError ? <p className="sidebar-note">{otpError}</p> : null}
          <p className="sidebar-note">
            Everything here is sealed with your own key.
          </p>
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
