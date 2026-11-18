import { useEffect, useState, type FormEvent } from 'react';
import { Button } from '../components/ui';

import { ApiError, getCapabilities } from '../lib/api';
import { errorMessage, useAuth } from '../lib/auth';

/**
 * Getting in, and getting everyone else out.
 *
 * Three real controls live here — the password, the emailed sign-in code, and the
 * deletion of the whole vault — plus the one honest thing to say about sessions
 * before there is a device list: changing the password ends every other session.
 */
export default function Security() {
  const { user, signOut, setEmailOtp, changePassword, deleteAccount } = useAuth();

  const [emailDelivery, setEmailDelivery] = useState<boolean | null>(null);
  const [otpBusy, setOtpBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordNote, setPasswordNote] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);

  const [deletePassword, setDeletePassword] = useState('');
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getCapabilities()
      .then((caps) => {
        if (alive) setEmailDelivery(caps.email_delivery);
      })
      .catch(() => {
        /* the switch stays available; the server still refuses what it cannot do */
      });
    return () => {
      alive = false;
    };
  }, []);

  async function toggleSignInCode(enabled: boolean) {
    setOtpBusy(true);
    setProblem(null);
    setNotice(null);
    try {
      await setEmailOtp(enabled);
      setNotice(enabled ? 'A code will be asked for at your next sign-in.' : 'The code is off. Your password alone opens your notes.');
    } catch (caught) {
      setProblem(
        caught instanceof ApiError ? caught.message : 'Could not change that. Confirm your email address first.',
      );
    } finally {
      setOtpBusy(false);
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
      setPasswordNote('Password changed. Every other session has been signed out.');
    } catch (caught) {
      setPasswordError(
        caught instanceof ApiError && caught.status === 401
          ? 'That current password is not right.'
          : errorMessage(caught),
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
        caught instanceof ApiError && caught.status === 401 ? 'That password is not right.' : errorMessage(caught),
      );
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <div className="page page-narrow">
      <header className="page-head">
        <div>
          <p className="eyebrow">Security</p>
          <h1>How you get in</h1>
          <p className="page-sub">
            Your password, the extra code if you want one, and the switch that deletes everything. Nothing here is
            hidden behind a menu.
          </p>
        </div>
      </header>

      {notice ? <p className="sidebar-note">{notice}</p> : null}
      {problem ? <p className="form-error">{problem}</p> : null}

      <section className="report-section">
        <h2 className="section-title">Your password</h2>
        <p className="stat-hint">
          At least ten characters. Changing it signs out every other device, which is the fastest way to shut a door
          you no longer trust.
        </p>
        <form className="detail-form security-form" onSubmit={(event) => void submitPassword(event)}>
          <label className="field">
            <span>Current password</span>
            <input
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              required
            />
          </label>
          <label className="field">
            <span>New password</span>
            <input
              type="password"
              autoComplete="new-password"
              minLength={10}
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              required
            />
            <small>Ten characters or more.</small>
          </label>
          <Button variant="primary" type="submit" disabled={passwordBusy}>
            {passwordBusy ? 'Changing…' : 'Change my password'}
          </Button>
          {passwordError ? <p className="form-error">{passwordError}</p> : null}
          {passwordNote ? <p className="sidebar-note">{passwordNote}</p> : null}
        </form>
      </section>

      <section className="report-section">
        <h2 className="section-title">A code as well as your password</h2>
        <div className="set-list">
          <label className="set-row">
            <span>
              <b>Email me a code when I sign in</b>
              <small>
                {emailDelivery === false
                  ? 'Not available: this deployment has no mail provider, so a code could never arrive.'
                  : 'Six digits after your password. Off by default, because most people want in quickly.'}
              </small>
            </span>
            <span className="switch">
              <input
                type="checkbox"
                checked={user?.email_otp_enabled ?? false}
                disabled={otpBusy || !user?.email_verified || emailDelivery === false}
                onChange={(event) => void toggleSignInCode(event.target.checked)}
              />
              <span />
            </span>
          </label>
        </div>
        <p className="stat-hint">
          The admin console always asks for its own six-digit code, whether or not this one is on.
        </p>
      </section>

      <section className="report-section">
        <h2 className="section-title">This device</h2>
        <dl className="facts">
          <div>
            <dt>Signed in as</dt>
            <dd>{user?.email ?? '—'}</dd>
          </div>
          <div>
            <dt>Signed in through</dt>
            <dd>this browser</dd>
          </div>
          <div>
            <dt>Other devices</dt>
            <dd>A password change ends them</dd>
          </div>
        </dl>
        <Button variant="secondary" type="button" onClick={signOut}>
          Sign out of this device
        </Button>
      </section>

      <section className="report-section">
        <h2 className="section-title">Deleting everything</h2>
        <p className="stat-hint">
          This removes the account and every note, person, reminder and file inside it. There is no copy on our side
          to restore, because we cannot read the notes to make one.
        </p>
        <form className="detail-form security-form" onSubmit={(event) => void submitDeletion(event)}>
          <label className="field">
            <span>Your password</span>
            <input
              type="password"
              autoComplete="current-password"
              value={deletePassword}
              onChange={(event) => setDeletePassword(event.target.value)}
              required
            />
          </label>
          <button type="submit" className="danger-button" disabled={deleteBusy}>
            {deleteBusy ? 'Deleting…' : 'Delete my vault'}
          </button>
          {deleteError ? <p className="form-error">{deleteError}</p> : null}
        </form>
      </section>
    </div>
  );
}
