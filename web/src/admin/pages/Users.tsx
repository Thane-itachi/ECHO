import { useEffect, useState } from 'react';

import { formatDate } from '../../lib/api';
import * as adminApi from '../../lib/admin';
import { adminErrorMessage, useAdminAuth } from '../AdminAuth';

export default function Users() {
  const { can } = useAdminAuth();
  const [rows, setRows] = useState<adminApi.AccountRow[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let alive = true;
    adminApi
      .listUsers()
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

  async function toggle(row: adminApi.AccountRow) {
    setBusyId(row.id);
    setError(null);
    try {
      await adminApi.setUserActive(row.id, !row.is_active);
      setReload((value) => value + 1);
    } catch (caught) {
      setError(adminErrorMessage(caught));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">Admin</p>
          <h1>User accounts</h1>
          <p className="page-sub">
            Disabling an account blocks sign in immediately; their memories stay intact and unreadable to you.
          </p>
        </div>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      {rows.length === 0 ? (
        <div className="empty empty-large">
          <p className="empty-title">No accounts yet</p>
          <p>Users appear here as soon as they register.</p>
        </div>
      ) : (
        <table className="admin-table">
          <thead>
            <tr>
              <th>Email</th>
              <th>Joined</th>
              <th>Status</th>
              {can('users:write') ? <th /> : null}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.email}</td>
                <td>{formatDate(row.created_at)}</td>
                <td>
                  <span className={row.is_active ? 'chip' : 'chip chip-muted'}>
                    {row.is_active ? 'active' : 'disabled'}
                  </span>
                </td>
                {can('users:write') ? (
                  <td>
                    <button
                      type="button"
                      className="ghost-button"
                      disabled={busyId === row.id}
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
      )}
    </div>
  );
}
