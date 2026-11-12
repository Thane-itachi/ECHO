import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';

import { adminErrorMessage, useAdminAuth } from '../AdminAuth';

export default function AdminLogin() {
  const { identity, signIn } = useAdminAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [totp, setTotp] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A successful sign-in must actually open the console. Without this the form just
  // sat there looking as though nothing happened.
  useEffect(() => {
    if (identity) navigate('/admin', { replace: true });
  }, [identity, navigate]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email.trim(), password, totp.trim());
      navigate('/admin', { replace: true });
    } catch (caught) {
      setError(adminErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-screen">
      <div className="auth-panel">
        <div className="brand">
          <span className="brand-mark">ECHO</span>
          <span className="brand-tagline">admin console</span>
        </div>
        <h1>Administrator sign in</h1>
        <p className="page-sub">
          Every administrator has a second factor. There is no password-only path into this console.
        </p>
        <form className="auth-card" onSubmit={submit}>
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <label className="field">
            <span>Authenticator code</span>
            <input
              value={totp}
              onChange={(event) => setTotp(event.target.value.replace(/\D/g, '').slice(0, 6))}
              inputMode="numeric"
              placeholder="6 digits"
              required
            />
          </label>
          {error ? <p className="form-error">{error}</p> : null}
          <button type="submit" className="primary-button" disabled={busy || totp.length !== 6}>
            {busy ? 'Verifying…' : 'Enter console'}
          </button>
        </form>
        <p className="muted">
          Locked out? Run <code>python -m app.scripts.create_admin --email you@example.com --rotate</code> on the
          server and scan the new secret.
        </p>
      </div>
    </div>
  );
}
