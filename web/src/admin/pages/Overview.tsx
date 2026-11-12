import { useEffect, useState } from 'react';

import * as adminApi from '../../lib/admin';
import { adminErrorMessage, useAdminAuth } from '../AdminAuth';

export default function Overview() {
  const { can } = useAdminAuth();
  const [stats, setStats] = useState<adminApi.PlatformStats | null>(null);
  const [health, setHealth] = useState<adminApi.Health | null>(null);
  const [analytics, setAnalytics] = useState<adminApi.Analytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const [nextStats, nextHealth, nextAnalytics] = await Promise.all([
          adminApi.stats(),
          can('system:read') ? adminApi.health().catch(() => null) : Promise.resolve(null),
          adminApi.analytics(14),
        ]);
        if (!alive) return;
        setStats(nextStats);
        setHealth(nextHealth);
        setAnalytics(nextAnalytics);
      } catch (caught) {
        if (alive) setError(adminErrorMessage(caught));
      }
    }
    void load();
    return () => {
      alive = false;
    };
  }, [can]);

  const peak = Math.max(1, ...(analytics?.points ?? []).map((point) => point.memories));

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">Admin</p>
          <h1>Platform overview</h1>
          <p className="page-sub">Aggregate numbers only. No memory content is ever readable from this console.</p>
        </div>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      <div className="stat-grid">
        {[
          { label: 'Users', value: stats?.users_total, hint: `${stats?.users_active ?? 0} active` },
          { label: 'Memories', value: stats?.memories_total, hint: 'not archived' },
          { label: 'Pending captures', value: stats?.proposals_pending, hint: 'awaiting approval' },
          { label: 'Notifications queued', value: stats?.outbox_pending, hint: 'outbox' },
        ].map((card) => (
          <div key={card.label} className="stat-card">
            <span className="stat-label">{card.label}</span>
            <span className="stat-value">{card.value ?? '—'}</span>
            <span className="stat-hint">{card.hint}</span>
          </div>
        ))}
      </div>

      {health ? (
        <section className="admin-section">
          <h2 className="section-title">System health</h2>
          <div className="health-row">
            <span className={health.status === 'ok' ? 'chip' : 'chip chip-muted'}>status: {health.status}</span>
            <span className="chip">database: {health.database}</span>
            <span className="chip">jobs queued: {health.jobs_queued}</span>
            <span className={health.jobs_failed ? 'chip chip-ai' : 'chip'}>jobs failed: {health.jobs_failed}</span>
            <span className="chip">outbox pending: {health.outbox_pending}</span>
            <span className="chip">admins active: {health.admins_active}</span>
            <span className="chip">admins idle &gt; 30d: {health.admins_without_recent_login}</span>
          </div>
        </section>
      ) : null}

      {analytics ? (
        <section className="admin-section">
          <h2 className="section-title">Last {analytics.window_days} days</h2>
          {analytics.points.length === 0 ? (
            <p className="muted">No activity recorded in this window yet.</p>
          ) : (
            <div className="chart" role="img" aria-label="Memories created per day">
              {analytics.points.map((point) => (
                <div key={point.day} className="chart-bar">
                  <div className="chart-columns">
                    <span className="chart-bar-fill" style={{ height: `${(point.memories / peak) * 100}%` }} title={`${point.memories} memories`} />
                  </div>
                  <span className="chart-label">{point.day.slice(5)}</span>
                </div>
              ))}
            </div>
          )}
          <p className="muted">
            Approvals: {analytics.proposals_approved} approved, {analytics.proposals_rejected} rejected
            {analytics.approval_rate !== null ? ` (${Math.round(analytics.approval_rate * 100)}% approval rate)` : ''}.
          </p>
        </section>
      ) : null}
    </div>
  );
}
