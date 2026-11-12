import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { EchoMark } from '../../components/Logo';
import * as adminApi from '../../lib/admin';
import { ApiError } from '../../lib/api';

/**
 * Administrator enrolment.
 *
 * The page exists so that a password is never sent to anybody. Three beats:
 *
 * 1. they choose a password (and confirm it, because a typo here is a lockout),
 * 2. they scan a QR that only ever appears on this screen once, and prove it worked
 *    by typing the code their phone shows,
 * 3. the link burns and they sign in normally.
 *
 * Nothing on this page is a shortcut into the console: step 2 is mandatory, and the
 * server refuses the link until it sees a valid code.
 */

type Stage = 'loading' | 'form' | 'secret' | 'done' | 'broken';

function daysFromNow(iso: string): string {
  const when = new Date(iso);
  const hours = Math.max(0, Math.round((when.getTime() - Date.now()) / 3_600_000));
  if (hours < 1) return 'in under an hour';
  if (hours < 48) return `in ${hours} hours`;
  return `in ${Math.round(hours / 24)} days`;
}

export default function AdminEnrol() {
  const [params] = useSearchParams();
  const token = (params.get('token') ?? '').trim();

  const [stage, setStage] = useState<Stage>('loading');
  const [invite, setInvite] = useState<adminApi.EnrolmentInfo | null>(null);
  const [granted, setGranted] = useState<adminApi.EnrolmentGranted | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    if (!token) {
      setProblem('This page needs the link you were given, including its token.');
      setStage('broken');
      return;
    }
    try {
      setInvite(await adminApi.enrolmentInfo(token));
      setStage('form');
    } catch (caught) {
      setProblem(
        caught instanceof ApiError ? caught.message : 'That enrolment link could not be opened.',
      );
      setStage('broken');
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const tooShort = password.length > 0 && password.length < 10;
  const mismatch = confirm.length > 0 && confirm !== password;
  const canSubmit = password.length >= 10 && password === confirm && !busy;

  async function submitPassword(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setProblem(null);
    try {
      const result = await adminApi.startEnrolment(token, password);
      setGranted(result);
      setStage('secret');
      // the password is gone from memory as soon as it is hashed server-side
      setPassword('');
      setConfirm('');
    } catch (caught) {
      setProblem(caught instanceof ApiError ? caught.message : 'The password could not be saved.');
    } finally {
      setBusy(false);
    }
  }

  async function confirmSecret(event: FormEvent) {
    event.preventDefault();
    if (!granted || code.length !== 6 || busy) return;
    setBusy(true);
    setProblem(null);
    try {
      await adminApi.confirmEnrolment(token, code);
      setStage('done');
    } catch (caught) {
      setProblem(
        caught instanceof ApiError
          ? caught.message
          : 'That code did not match. Check the clock on your phone and try the next one.',
      );
    } finally {
      setBusy(false);
    }
  }

  async function copySecret() {
    if (!granted) return;
    try {
      await navigator.clipboard.writeText(granted.totp_secret);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="enrol-screen">
      <div className="enrol-card">
        <div className="brand enrol-brand">
          <EchoMark size={32} />
          <span className="brand-text">
            <span className="brand-mark">ECHO</span>
            <span className="brand-tagline">administrator enrolment</span>
          </span>
        </div>

        {stage === 'loading' ? <p className="muted">Opening your link…</p> : null}

        {stage === 'broken' ? (
          <>
            <h1>This link can’t be used</h1>
            <p className="page-sub">{problem}</p>
            <p className="muted">
              Links work once and expire after three days. Ask whoever sent it for a fresh one, then open
              that instead of this page.
            </p>
            <Link className="primary-button" to="/admin/login">
              Go to sign in
            </Link>
          </>
        ) : null}

        {stage === 'form' && invite ? (
          <>
            <h1>Set your own password</h1>
            <p className="page-sub">
              This link is for <strong>{invite.email}</strong> and expires {daysFromNow(invite.expires_at)}.
              You choose the password here, so nobody else ever knows it, including whoever sent the link.
            </p>
            <form className="auth-card" onSubmit={submitPassword}>
              <label className="field">
                <span>Password</span>
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="new-password"
                  autoFocus
                  required
                  minLength={10}
                />
                <small>
                  {tooShort ? 'At least 10 characters.' : 'Ten characters or more. A phrase you’ll remember.'}
                </small>
              </label>
              <label className="field">
                <span>Again</span>
                <input
                  type="password"
                  value={confirm}
                  onChange={(event) => setConfirm(event.target.value)}
                  autoComplete="new-password"
                  required
                />
                <small>{mismatch ? 'These two don’t match yet.' : 'Same password, typed twice.'}</small>
              </label>
              {problem ? <p className="form-error">{problem}</p> : null}
              <button type="submit" className="primary-button" disabled={!canSubmit}>
                {busy ? 'Saving…' : 'Continue to the authenticator'}
              </button>
            </form>
            <p className="muted">
              Next you’ll scan one QR code with an authenticator app. Every sign-in asks for the six digits it
              shows, so nobody gets in with a password alone.
            </p>
          </>
        ) : null}

        {stage === 'secret' && granted ? (
          <>
            <h1>Scan this, once</h1>
            <p className="page-sub">
              Add ECHO to your authenticator app. This is the only time the secret is shown, so finish now:
              if you close the page you’ll need a new link.
            </p>
            <div className="auth-card enrol-secret">
              <img className="enrol-qr" src={granted.qr_data_uri} alt="QR code for your authenticator app" />
              <div className="enrol-secret-text">
                <span className="enrol-label">Can’t scan? Type this key</span>
                <code className="enrol-key">{granted.totp_secret.match(/.{1,4}/g)?.join(' ')}</code>
                <button type="button" className="ghost-button" onClick={copySecret}>
                  {copied ? 'Copied' : 'Copy key'}
                </button>
                <span className="enrol-hint">Account name: {granted.email}</span>
              </div>
            </div>
            <form className="auth-card" onSubmit={confirmSecret}>
              <label className="field">
                <span>Six digits from the app</span>
                <input
                  value={code}
                  onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="000000"
                  autoFocus
                  required
                />
                <small>This proves the app and the server share the same secret.</small>
              </label>
              {problem ? <p className="form-error">{problem}</p> : null}
              <button type="submit" className="primary-button" disabled={busy || code.length !== 6}>
                {busy ? 'Checking…' : 'Finish enrolment'}
              </button>
            </form>
          </>
        ) : null}

        {stage === 'done' && granted ? (
          <>
            <h1>You’re the administrator</h1>
            <p className="page-sub">
              {granted.email} is enrolled as {granted.role.replace('_', ' ')}. The link is used up now, and
              only your password and your authenticator open this console.
            </p>
            <Link className="primary-button" to="/admin/login">
              Sign in to the console
            </Link>
          </>
        ) : null}
      </div>
    </div>
  );
}
