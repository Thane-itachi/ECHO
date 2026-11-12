import { useState, type FormEvent } from 'react';

import { errorMessage, useAuth, useAuthFailureHandler } from '../lib/auth';

type Mode = 'signin' | 'signup';

export default function Login() {
  const { signIn, signUp } = useAuth();
  const handleAuthFailure = useAuthFailureHandler();
  const [mode, setMode] = useState<Mode>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === 'signup') await signUp(email.trim(), password);
      else await signIn(email.trim(), password);
    } catch (caught) {
      if (!handleAuthFailure(caught)) setError(errorMessage(caught));
      setBusy(false);
    }
  }

  return (
    <div className="auth-screen">
      <section className="auth-story">
        <div className="wordmark">ECHO</div>
        <h1>
          Never forget
          <br />
          what matters.
        </h1>
        <p>
          The laptop John borrowed. The promise you made on Tuesday. The thing your landlord said he would fix.
          ECHO keeps it and hands it back the moment you ask.
        </p>
        <ul className="story-points">
          <li>Memories are encrypted per person, at rest.</li>
          <li>Nothing is filed from a conversation without your approval.</li>
          <li>Search only ever touches your own vault.</li>
        </ul>
      </section>

      <section className="auth-panel">
        <div className="auth-card">
          <div className="auth-tabs">
            <button
              type="button"
              className={mode === 'signin' ? 'tab is-active' : 'tab'}
              onClick={() => {
                setMode('signin');
                setError(null);
              }}
            >
              Sign in
            </button>
            <button
              type="button"
              className={mode === 'signup' ? 'tab is-active' : 'tab'}
              onClick={() => {
                setMode('signup');
                setError(null);
              }}
            >
              Create account
            </button>
          </div>

          <form onSubmit={submit} className="form">
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

            <label className="field">
              <span>Password</span>
              <input
                type="password"
                autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                minLength={mode === 'signup' ? 10 : undefined}
                required
              />
              {mode === 'signup' ? <small>At least 10 characters.</small> : null}
            </label>

            {error ? <p className="form-error">{error}</p> : null}

            <button type="submit" className="primary-button" disabled={busy}>
              {busy ? 'One moment…' : mode === 'signup' ? 'Create my vault' : 'Open my vault'}
            </button>
          </form>
        </div>
      </section>
    </div>
  );
}
