import { useEffect, useState, type FormEvent } from 'react';

import { formatDateTime } from '../../lib/api';
import * as adminApi from '../../lib/admin';
import { adminErrorMessage, useAdminAuth } from '../AdminAuth';

const ROLES: adminApi.AdminRole[] = ['founder', 'platform_admin', 'support_admin'];

export default function Admins() {
  const { identity, can } = useAdminAuth();
  const [rows, setRows] = useState<adminApi.AdminAccount[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [secret, setSecret] = useState<adminApi.AdminAccountCreated | null>(null);
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<adminApi.AdminRole>('support_admin');

  useEffect(() => {
    let alive = true;
    adminApi
      .listAdmins()
      .then((page) => {
        if (alive) setRows(page.items);
      })
      .catch((caught) => {
        if (alive) setError(adminErrorMessage(caught));
      });
    return () => {
      alive = false;
    };
  }, [reload]);

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await adminApi.createAdmin(email.trim(), password, role);
      setSecret(created);
      setEmail('');
      setPassword('');
      setReload((value) => value + 1);
    } catch (caught) {
      setError(adminErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function changeRole(row: adminApi.AdminAccount, nextRole: adminApi.AdminRole) {
    setError(null);
    try {
      await adminApi.setAdminRole(row.id, nextRole);
      setReload((value) => value + 1);
    } catch (caught) {
      setError(adminErrorMessage(caught));
    }
  }

  async function toggle(row: adminApi.AdminAccount) {
    setError(null);
    try {
      await adminApi.setAdminActive(row.id, !row.is_active);
      setReload((value) => value + 1);
    } catch (caught) {
      setError(adminErrorMessage(caught));
    }
  }

  async function rotate(row: adminApi.AdminAccount) {
    setError(null);
    try {
      setSecret(await adminApi.rotateAdminMfa(row.id));
    } catch (caught) {
      setError(adminErrorMessage(caught));
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">Admin</p>
          <h1>Administrators</h1>
          <p className="page-sub">
            Founder: everything. Platform admin: users, audit, health, analytics. Support admin: read-only triage.
            TOTP is required for every account and cannot be switched off.
          </p>
        </div>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      {secret ? (
        <div className="secret-card">
          <h2>Scan this now — it is shown once</h2>
          <p className="muted">{secret.email}</p>
          <code className="secret-value">{secret.totp_secret}</code>
          <p className="muted break-all">{secret.otpauth_url}</p>
          <button type="button" className="ghost-button" onClick={() => setSecret(null)}>
            I have saved it
          </button>
        </div>
      ) : null}

      <table className="admin-table">
        <thead>
          <tr>
            <th>Email</th>
            <th>Role</th>
            <th>Last sign in</th>
            <th>Status</th>
            {can('admins:write') ? <th>Actions</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.email}</td>
              <td>
                {can('admins:write') ? (
                  <select value={row.role} onChange={(event) => void changeRole(row, event.target.value as adminApi.AdminRole)}>
                    {ROLES.map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                ) : (
                  row.role
                )}
              </td>
              <td>{row.last_login_at ? formatDateTime(row.last_login_at) : 'never'}</td>
              <td>
                <span className={row.is_active ? 'chip' : 'chip chip-muted'}>{row.is_active ? 'active' : 'disabled'}</span>
              </td>
              {can('admins:write') ? (
                <td className="row-actions">
                  <button type="button" className="ghost-button" onClick={() => void rotate(row)}>
                    New MFA secret
                  </button>
                  <button
                    type="button"
                    className="ghost-button"
                    disabled={row.id === identity?.id}
                    onClick={() => void toggle(row)}
                  >
                    {row.is_active ? 'Disable' : 'Enable'}
                  </button>
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>

      {can('admins:write') ? (
        <section className="admin-section">
          <h2 className="section-title">Add an administrator</h2>
          <form className="inline-form" onSubmit={create}>
            <label className="field">
              <span>Email</span>
              <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
            </label>
            <label className="field">
              <span>Temporary password</span>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                minLength={12}
                required
              />
            </label>
            <label className="field">
              <span>Role</span>
              <select value={role} onChange={(event) => setRole(event.target.value as adminApi.AdminRole)}>
                {ROLES.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <button type="submit" className="primary-button" disabled={busy || !email.trim() || password.length < 12}>
              {busy ? 'Creating…' : 'Create'}
            </button>
          </form>
        </section>
      ) : null}
    </div>
  );
}
