import { useEffect, useState, type FormEvent } from 'react';
import { Link, NavLink, Outlet } from 'react-router-dom';

import { EchoMark } from '../components/Logo';
import NavIcon from '../components/NavIcon';
import NotificationToggle from '../components/NotificationToggle';
import { ApiError, getCapabilities, listProposals } from '../lib/api';
import { useAuth } from '../lib/auth';
import { TEXT_SIZES, useTextSize } from '../lib/textSize';

/* Plain words, each with a picture. "Vault" and "captures" are the sort of words
   that mean nothing to someone who has not spent their life in software. */
const NAV = [
  { to: '/vault', label: 'My notes', short: 'Notes', hint: 'Everything you have saved', icon: 'notes' },
  { to: '/ask', label: 'Ask a question', short: 'Ask', hint: 'Find one thing you saved', icon: 'ask' },
  { to: '/people', label: 'People', short: 'People', hint: 'Names you have saved', icon: 'people' },
  { to: '/proposals', label: 'Things to check', short: 'To check', hint: 'ECHO found these. Say yes or no.', icon: 'check' },
  { to: '/reminders', label: 'Reminders', short: 'Reminders', hint: 'Dates you must not miss', icon: 'bell' },
  { to: '/documents', label: 'Files', short: 'Files', hint: 'Papers and pictures you added', icon: 'files' },
];

export default function Layout() {
  const { user, signOut, setEmailOtp, setReminderEmail, changePassword, deleteAccount } = useAuth();
  const [pending, setPending] = useState<number | null>(null);
  const [otpBusy, setOtpBusy] = useState(false);
  const [otpError, setOtpError] = useState<string | null>(null);
  const [reminderBusy, setReminderBusy] = useState(false);
  // null until the deployment has answered. Only an explicit `false` disables the switch,
  // so an older server that does not know the question never locks the toggle.
  const [emailDelivery, setEmailDelivery] = useState<boolean | null>(null);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordNote, setPasswordNote] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [deletePassword, setDeletePassword] = useState('');
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [textSize, setTextSize] = useTextSize();
  // Phones show the six destinations and fold the rest of the sidebar away:
  // a settings column above the notes is the first thing that makes a phone
  // screen feel wrong. Wide screens ignore this and show everything.
  const [moreOpen, setMoreOpen] = useState(false);

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

  async function submitPassword(event: FormEvent) {
    event.preventDefault();
    setPasswordBusy(true);
    setPasswordError(null);
    setPasswordNote(null);
    try {
      await changePassword(currentPassword, newPassword);
      setCurrentPassword('');
      setNewPassword('');
      setPasswordNote('Password changed. Your other sessions have been signed out.');
    } catch (caught) {
      setPasswordError(
        caught instanceof ApiError && caught.status === 401
          ? 'That current password is not right.'
          : caught instanceof ApiError
            ? caught.message
            : 'Could not change the password.',
      );
    } finally {
      setPasswordBusy(false);
    }
  }

  async function submitDeletion(event: FormEvent) {
    event.preventDefault();
    setDeleteError(null);
    const sure = window.confirm(
      'Delete your vault? Every memory, person, reminder and document goes with it, and this cannot be undone.',
    );
    if (!sure) return;
    setDeleteBusy(true);
    try {
      await deleteAccount(deletePassword);
    } catch (caught) {
      setDeleteError(
        caught instanceof ApiError && caught.status === 401
          ? 'That password is not right.'
          : caught instanceof ApiError
            ? caught.message
            : 'Could not delete the vault.',
      );
    } finally {
      setDeleteBusy(false);
    }
  }

  useEffect(() => {
    let alive = true;
    getCapabilities()
      .then((caps) => {
        if (alive) setEmailDelivery(caps.email_delivery);
      })
      .catch(() => {
        /* the switch simply stays available; the server still refuses what it cannot do */
      });
    return () => {
      alive = false;
    };
  }, []);

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
          <Link className="brand" to="/" aria-label="ECHO home">
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
          <label className="sidebar-toggle">
            <input
              type="checkbox"
              checked={user?.email_otp_enabled ?? false}
              disabled={otpBusy || !user?.email_verified || emailDelivery === false}
              onChange={(event) => void toggleSignInCode(event.target.checked)}
            />
            <span>
              Email me a code at sign-in
              <small>
                {emailDelivery === false
                  ? 'Not available: this deployment has no mail provider, so a code could never arrive.'
                  : 'Your password, then six digits. Off by default.'}
              </small>
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

          <details className="sidebar-details">
            <summary>Change my password</summary>
            <form className="sidebar-form" onSubmit={(event) => void submitPassword(event)}>
              <input
                type="password"
                autoComplete="current-password"
                placeholder="current password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                required
              />
              <input
                type="password"
                autoComplete="new-password"
                placeholder="new password, 10+ characters"
                minLength={10}
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                required
              />
              <button type="submit" className="ghost-button" disabled={passwordBusy}>
                {passwordBusy ? 'Changing…' : 'Change password'}
              </button>
              {passwordError ? <p className="sidebar-note is-warning">{passwordError}</p> : null}
              {passwordNote ? <p className="sidebar-note">{passwordNote}</p> : null}
            </form>
          </details>

          <details className="sidebar-details">
            <summary>Delete my vault</summary>
            <form className="sidebar-form" onSubmit={(event) => void submitDeletion(event)}>
              <input
                type="password"
                autoComplete="current-password"
                placeholder="password"
                value={deletePassword}
                onChange={(event) => setDeletePassword(event.target.value)}
                required
              />
              <button type="submit" className="ghost-button is-danger" disabled={deleteBusy}>
                {deleteBusy ? 'Deleting…' : 'Delete everything'}
              </button>
              {deleteError ? <p className="sidebar-note is-warning">{deleteError}</p> : null}
            </form>
          </details>
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
