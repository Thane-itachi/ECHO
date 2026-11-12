import { useEffect, useState } from 'react';

import { formatDateTime } from '../../lib/api';
import * as adminApi from '../../lib/admin';
import { adminErrorMessage } from '../AdminAuth';

export default function Audit() {
  const [entries, setEntries] = useState<adminApi.AuditEntry[]>([]);
  const [filter, setFilter] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    adminApi
      .audit(200)
      .then((page) => {
        if (alive) setEntries(page.items);
      })
      .catch((caught) => {
        if (alive) setError(adminErrorMessage(caught));
      });
    return () => {
      alive = false;
    };
  }, []);

  const shown = entries.filter((entry) => !filter || entry.action.includes(filter));

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">Admin</p>
          <h1>Audit log</h1>
          <p className="page-sub">
            Who did what, including failed sign-in attempts and break-glass access with its stated reason.
          </p>
        </div>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      <div className="toolbar">
        <input
          className="search"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Filter by action, e.g. admin.login_failed"
          aria-label="Filter audit entries"
        />
      </div>

      {shown.length === 0 ? (
        <p className="muted">No entries match.</p>
      ) : (
        <table className="admin-table">
          <thead>
            <tr>
              <th>When</th>
              <th>Action</th>
              <th>Actor</th>
              <th>Target</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((entry) => (
              <tr key={entry.id}>
                <td className="nowrap">{formatDateTime(entry.created_at)}</td>
                <td>
                  <code>{entry.action}</code>
                </td>
                <td>
                  {entry.actor_type}
                  {entry.actor_id ? ` · ${entry.actor_id.slice(0, 8)}` : ''}
                </td>
                <td>
                  {entry.target_type ?? '—'}
                  {entry.target_id ? ` · ${entry.target_id.slice(0, 8)}` : ''}
                </td>
                <td className="detail-cell">
                  {Object.keys(entry.detail ?? {}).length ? JSON.stringify(entry.detail) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
