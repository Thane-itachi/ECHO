import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button } from '../components/ui';
import { Link, useSearchParams } from 'react-router-dom';

import { EchoLogo, EchoMark } from '../components/Logo';
import { ApiError } from '../lib/api';
import * as api from '../lib/api';
import { errorMessage, useAuth, useAuthFailureHandler } from '../lib/auth';

type Step = 'signin' | 'signup' | 'verify' | 'otp' | 'forgot' | 'reset';

const RESEND_SECONDS = 60;

/** A six digit field that behaves like a person expects. */
function CodeField({
  value,
  onChange,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        className="code-input"
        inputMode="numeric"
        autoComplete="one-time-code"
        pattern="[0-9]*"
        maxLength={6}
        value={value}
        onChange={(event) => onChange(event.target.value.replace(/\D/g, '').slice(0, 6))}
        required
      />
    </label>
  );
}

export default function Login() {
  const { signIn, signInWithCode, verifyEmail } = useAuth();
  const handleAuthFailure = useAuthFailureHandler();

  // The homepage can send someone straight to the sign-up form.
  const [params] = useSearchParams();
  const [step, setStep] = useState<Step>(params.get('start') === 'signup' ? 'signup' : 'signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [devCode, setDevCode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [slow, setSlow] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const timer = useRef<number | null>(null);

  // Five seconds is long enough to worry someone: say the work is still going.
  useEffect(() => {
    if (!busy) {
      setSlow(false);
      return;
    }
    const handle = window.setTimeout(() => setSlow(true), 5000);
    return () => window.clearTimeout(handle);
  }, [busy]);

  useEffect(() => {
    if (cooldown <= 0) return;
    timer.current = window.setTimeout(() => setCooldown((left) => left - 1), 1000);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [cooldown]);

  function go(next: Step) {
    setStep(next);
    setError(null);
    setNotice(null);
    setCode('');
  }

  function fail(caught: unknown) {
    // Sign-in failures are answers, not expired sessions: handle them here first.
    if (caught instanceof ApiError) {
      if (caught.code === 'email_code_required') {
        const hinted = (caught.details as { dev_code?: string | null } | undefined)?.dev_code;
        if (hinted) setDevCode(hinted);
        setPassword(password);
        setCooldown(RESEND_SECONDS);
        setNotice('We emailed you a six digit code. It is good for five minutes.');
        go('otp');
        return;
      }
      if (caught.code === 'email_not_verified') {
        setNotice('One more step: confirm your address with the code we just emailed you.');
        setCooldown(RESEND_SECONDS);
        go('verify');
        return;
      }
      if (caught.code === 'invalid_code') {
        setError(caught.message);
        return;
      }
    }
    if (!handleAuthFailure(caught)) setError(errorMessage(caught));
  }

  async function submitSignin(event: FormEvent) {
    event.preventDefault();
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      setError('This device is offline. Check your connection, then press Sign in again.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await signIn(email.trim(), password);
    } catch (caught) {
      fail(caught);
    } finally {
      setBusy(false);
    }
  }

  async function submitSignup(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await api.register(email.trim(), password);
      setDevCode(created.dev_code ?? null);
      setCooldown(RESEND_SECONDS);
      setNotice(`We sent a six digit code to ${email.trim()}. It expires in five minutes.`);
      go('verify');
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (step === 'otp') await signInWithCode(email.trim(), password, code);
      else if (step === 'verify') await verifyEmail(email.trim(), code);
      else if (step === 'reset') {
        await api.resetPassword(email.trim(), code, newPassword);
        setPassword('');
        setNewPassword('');
        setDevCode(null);
        go('signin');
        // After go(), which clears the notice: the confirmation has to survive.
        setNotice('Password changed. Sign in with the new one.');
      }
    } catch (caught) {
      fail(caught);
    } finally {
      setBusy(false);
    }
  }

  async function submitForgot(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const receipt = await api.forgotPassword(email.trim());
      setDevCode(receipt.dev_code ?? null);
      setCooldown(RESEND_SECONDS);
      setNotice(`If that address has an account, a six digit code is on its way to ${email.trim()}.`);
      go('reset');
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    if (cooldown > 0 || busy) return;
    setError(null);
    try {
      const receipt = await api.sendVerificationCode(email.trim());
      setDevCode(receipt.dev_code ?? null);
      setCooldown(RESEND_SECONDS);
      setNotice('Another code is on its way. The previous one no longer works.');
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  const heading =
    step === 'signup'
      ? 'Make your account'
      : step === 'verify'
        ? 'Check your email'
        : step === 'otp'
          ? 'Enter your code'
          : step === 'forgot'
            ? 'Forgot your password'
            : step === 'reset'
              ? 'Make a new password'
              : 'Welcome back';

  return (
    <div className="auth-screen">
      <section className="auth-story">
        <EchoMark size={300} className="auth-watermark" />
        <EchoLogo size={46} tagline className="auth-lockup" />
        <h1>
          Never forget
          <br />
          <em>what matters.</em>
        </h1>
        <p>
          The laptop John borrowed. The promise you made on Tuesday. The thing your landlord said he would fix.
          ECHO keeps it and hands it back the moment you ask.
        </p>
        <ul className="story-points">
          <li>Only you can read your notes. Nobody else, not even an administrator.</li>
          <li>Nothing is saved without you saying yes.</li>
          <li>What you search stays yours alone.</li>
        </ul>
        <p className="story-sign">Kept by hand. Yours to read, and no one else&rsquo;s.</p>
      </section>

      <section className="auth-panel">
        <Link className="auth-home" to="/">
          ← Back to the homepage
        </Link>
        <div className="auth-card">
          {step === 'signin' || step === 'signup' ? (
            <div className="auth-tabs">
              <button
                type="button"
                className={step === 'signin' ? 'tab is-active' : 'tab'}
                onClick={() => go('signin')}
              >
                I already have an account
              </button>
              <button
                type="button"
                className={step === 'signup' ? 'tab is-active' : 'tab'}
                onClick={() => go('signup')}
              >
                I am new here
              </button>
            </div>
          ) : (
            <p className="auth-step-kicker">{heading}</p>
          )}

          {notice ? <p className="auth-notice">{notice}</p> : null}
          {devCode ? (
            <p className="auth-dev">Local development, no mail provider: your code is {devCode}</p>
          ) : null}

          {step === 'signin' || step === 'signup' ? (
            <form onSubmit={step === 'signup' ? submitSignup : submitSignin} className="form">
              <label className="field">
                <span>Your email</span>
                <input
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
              </label>

              <label className="field">
                <span>Your password</span>
                <input
                  type="password"
                  autoComplete={step === 'signup' ? 'new-password' : 'current-password'}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  minLength={step === 'signup' ? 10 : undefined}
                  required
                />
                {step === 'signup' ? <small>At least 10 characters.</small> : null}
              </label>

              {error ? <p className="form-error">{error}</p> : null}

              <Button variant="primary" type="submit" disabled={busy}>
                {busy ? (step === 'signup' ? 'Making your account…' : 'Signing in…') : step === 'signup' ? 'Make my account' : 'Sign in'}
              </Button>
              {busy && slow ? (
                <p className="auth-fine" role="status">
                  Still working. A slow connection can take a few seconds. Please keep this page open.
                </p>
              ) : null}

              {step === 'signup' ? (
                <p className="auth-fine">
                  We email you a 6-digit code to check the address is yours. There is no link to click.
                </p>
              ) : (
                <button
                  type="button"
                  className="link-button"
                  onClick={() => {
                    setNotice(null);
                    go('forgot');
                  }}
                >
                  Forgot your password?
                </button>
              )}
            </form>
          ) : null}

          {step === 'verify' ? (
            <form onSubmit={submitCode} className="form">
              <label className="field">
                <span>Your email</span>
                <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
              </label>
              <CodeField value={code} onChange={setCode} label="The 6 digits from the email" />
              {error ? <p className="form-error">{error}</p> : null}
              <Button variant="primary" type="submit" disabled={busy || code.length !== 6}>
                {busy ? 'Checking…' : 'Check the code and sign in'}
              </Button>
              <div className="auth-row">
                <button type="button" className="link-button" onClick={resend} disabled={cooldown > 0}>
                  {cooldown > 0 ? `Send another code in ${cooldown}s` : 'Send another code'}
                </button>
                <button type="button" className="link-button" onClick={() => go('signin')}>
                  Back to sign in
                </button>
              </div>
            </form>
          ) : null}

          {step === 'otp' ? (
            <form onSubmit={submitCode} className="form">
              <CodeField value={code} onChange={setCode} label="The 6 digits from the email" />
              <p className="auth-fine">
                This account asks for a code every time you sign in. The code works once and expires in 5 minutes.
              </p>
              {error ? <p className="form-error">{error}</p> : null}
              <Button variant="primary" type="submit" disabled={busy || code.length !== 6}>
                {busy ? 'Checking…' : 'Open my vault'}
              </Button>
              <div className="auth-row">
                <button type="button" className="link-button" onClick={resend} disabled={cooldown > 0}>
                  {cooldown > 0 ? `Send another code in ${cooldown}s` : 'Send another code'}
                </button>
                <button type="button" className="link-button" onClick={() => go('signin')}>
                  Use my password instead
                </button>
              </div>
            </form>
          ) : null}

          {step === 'forgot' ? (
            <form onSubmit={submitForgot} className="form">
              <label className="field">
                <span>Email</span>
                <input
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
              </label>
              {error ? <p className="form-error">{error}</p> : null}
              <Button variant="primary" type="submit" disabled={busy}>
                {busy ? 'One moment…' : 'Email me a reset code'}
              </Button>
              <button type="button" className="link-button" onClick={() => go('signin')}>
                Back to sign in
              </button>
            </form>
          ) : null}

          {step === 'reset' ? (
            <form onSubmit={submitCode} className="form">
              <CodeField value={code} onChange={setCode} label="Six digits from the email" />
              <label className="field">
                <span>New password</span>
                <input
                  type="password"
                  autoComplete="new-password"
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  minLength={10}
                  required
                />
                <small>At least 10 characters. This signs out your other devices.</small>
              </label>
              {error ? <p className="form-error">{error}</p> : null}
              <Button
                type="submit"
                variant="primary"
                block
                disabled={busy || code.length !== 6 || newPassword.length < 10}
              >
                {busy ? 'Saving…' : 'Set my new password'}
              </Button>
              <button type="button" className="link-button" onClick={() => go('signin')}>
                Back to sign in
              </button>
            </form>
          ) : null}
        </div>
      </section>
    </div>
  );
}
