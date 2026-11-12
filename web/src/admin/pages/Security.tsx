import { useEffect, useState } from 'react';

import { formatDateTime } from '../../lib/api';
import * as adminApi from '../../lib/admin';
import { adminErrorMessage, useAdminAuth } from '../AdminAuth';

export default function Security() {
  const { can } = useAdminAuth();
  const [security, setSecurity] = useState<adminApi.Security | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [granted, setGranted] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    adminApi
      .security()
      .then((value) => {
        if (alive) setSecurity(value);
      })
      .catch((caught) => {
        if (alive) setError(adminErrorMessage(caught));
      });
    return () => {
      alive = false;
    };
  }, []);

  async function breakGlass() {
    setError(null);
    try {
      const result = await adminApi.emergencyAccess(reason.trim());
      setGranted(`Emergency token issued for ${Math.round(result.expires_in / 60)} minutes.`);
      setReason('');
    } catch (caught) {
      setError(adminErrorMessage(caught));
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">Admin</p>
          <h1>Security</h1>
          <p className="page-sub">
            Sign-in failures, disabled accounts, and the audit trail of sensitive actions.
          </p>
        </div>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      <div className="stat-grid">
        {[
          { label: 'Failed admin sign-ins', value: security?.failed_admin_logins_24h, hint: 'last 24 hours' },
          { label: 'Failed user sign-ins', value: security?.failed_user_logins_24h, hint: 'last 24 hours' },
          { label: 'Disabled admins', value: security?.disabled_admins, hint: 'cannot sign in' },
          { label: 'Disabled users', value: security?.inactive_users, hint: 'blocked accounts' },
        ].map((card) => (
          <div key={card.label} className="stat-card">
            <span className="stat-label">{card.label}</span>
            <span className="stat-value">{card.value ?? '—'}</span>
            <span className="stat-hint">{card.hint}</span>
          </div>
        ))}
      </div>

      <section className="admin-section">
        <h2 className="section-title">Recent sensitive events</h2>
        {security && security.recent_events.length > 0 ? (
          <ul className="event-list">
            {security.recent_events.map((event, index) => (
              <li key={`${event.action}-${index}`} className="event">
                <code>{event.action}</code>
                <span className="muted">{formatDateTime(event.created_at)}</span>
                {Object.keys(event.detail ?? {}).length ? (
                  <span className="detail-cell">{JSON.stringify(event.detail)}</span>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">Nothing recorded yet.</p>
        )}
      </section>

      {can('emergency:access') ? (
        <section className="admin-section">
          <h2 className="section-title">Break-glass access</h2>
          <p className="muted">
            Issues a fifteen-minute token marked elevated, and writes your reason to the audit trail. Use it only when
            something is broken and you need a way in now.
          </p>
          <div className="inline-form">
            <label className="field">
              <span>Reason (recorded)</span>
              <input
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="e.g. founder account locked out during incident 42"
              />
            </label>
            <button
              type="button"
              className="danger-button"
              disabled={reason.trim().length < 5}
              onClick={() => void breakGlass()}
            >
              Request emergency token
            </button>
          </div>
          {granted ? <p className="muted">{granted}</p> : null}
        </section>
      ) : null}
    </div>
  );
}
