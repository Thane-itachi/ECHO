import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import {
  CATEGORIES,
  formatDate,
  listDocuments,
  listMemories,
  listPeople,
  listReminders,
  parseUtc,
  type Memory,
  type Person,
  type Reminder,
} from '../lib/api';
import { errorMessage, useAuthFailureHandler } from '../lib/auth';

interface Report {
  memories: Memory[];
  people: Person[];
  reminders: Reminder[];
  documentTotal: number;
}

/** Every note, a page at a time, up to the point where a chart stops meaning anything. */
async function loadEveryMemory(): Promise<Memory[]> {
  const collected: Memory[] = [];
  for (let offset = 0; offset < 500; offset += 100) {
    const page = await listMemories({ limit: 100, offset });
    collected.push(...page.items);
    if (page.items.length === 0 || collected.length >= page.total) break;
  }
  return collected;
}

/**
 * What the memory holds, counted — never inferred.
 *
 * Every number on this page is a count of rows in the reader's own account, and
 * the page says the day it was counted. No engagement metrics, no invented
 * "insights": a person should be able to check any figure here by opening a list.
 */
export default function Reports() {
  const handleAuthFailure = useAuthFailureHandler();
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([loadEveryMemory(), listPeople(), listReminders(), listDocuments()])
      .then(([memories, people, reminders, documents]) => {
        if (!alive) return;
        setReport({
          memories,
          people: people.items,
          reminders: reminders.items,
          documentTotal: documents.total,
        });
      })
      .catch((caught) => {
        if (!alive) return;
        if (!handleAuthFailure(caught)) setError(errorMessage(caught));
      });
    return () => {
      alive = false;
    };
  }, [handleAuthFailure]);

  if (error) {
    return (
      <div className="page page-narrow">
        <p className="form-error">{error}</p>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="page page-narrow">
        <p className="page-sub">Counting…</p>
      </div>
    );
  }

  const byCategory = CATEGORIES.map((category) => ({
    category,
    count: report.memories.filter((memory) => memory.category === category).length,
  }))
    .filter((row) => row.count > 0)
    .sort((a, b) => b.count - a.count);

  const monthBuckets = (() => {
    const start = new Date();
    start.setDate(1);
    const buckets: { key: string; label: string; count: number }[] = [];
    for (let back = 5; back >= 0; back -= 1) {
      const month = new Date(start.getFullYear(), start.getMonth() - back, 1);
      buckets.push({
        key: `${month.getFullYear()}-${month.getMonth()}`,
        label: month.toLocaleDateString(undefined, { month: 'short' }),
        count: 0,
      });
    }
    report.memories.forEach((memory) => {
      const date = parseUtc(memory.created_at);
      const bucket = buckets.find((item) => item.key === `${date.getFullYear()}-${date.getMonth()}`);
      if (bucket) bucket.count += 1;
    });
    return buckets;
  })();

  const busiestMonth = monthBuckets.reduce((best, item) => (item.count > best.count ? item : best), monthBuckets[0]);
  const liveReminders = report.reminders.filter((item) => item.status !== 'cancelled').length;
  const categoryTop = byCategory[0]?.count ?? 1;
  const tallestMonth = Math.max(...monthBuckets.map((item) => item.count), 1);

  const peopleCounts = report.people
    .map((person) => ({
      name: person.name,
      count: report.memories.filter((memory) => memory.person_id === person.id).length,
    }))
    .filter((row) => row.count > 0)
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);

  return (
    <div className="page page-narrow">
      <header className="page-head">
        <div>
          <p className="eyebrow">Insights</p>
          <h1>What your memory holds</h1>
          <p className="page-sub">
            Counted from your own notes on {formatDate(new Date().toISOString())}. Nothing here is a guess, and
            nothing here leaves your account.
          </p>
        </div>
      </header>

      <div className="report-hero">
        <p className="stat-label">Notes kept</p>
        <p className="report-number">{report.memories.length}</p>
        <p className="stat-hint">
          across {byCategory.length} {byCategory.length === 1 ? 'kind' : 'kinds'} of note
        </p>
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-label">People</span>
          <span className="stat-value">{report.people.length}</span>
          <span className="stat-hint">names attached to a note</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Reminders</span>
          <span className="stat-value">{liveReminders}</span>
          <span className="stat-hint">still on your list</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Files</span>
          <span className="stat-value">{report.documentTotal}</span>
          <span className="stat-hint">papers and pictures</span>
        </div>
      </div>

      <section className="report-section">
        <h2 className="section-title">Notes by month</h2>
        <div className="chart">
          <div className="chart-columns">
            {monthBuckets.map((month) => {
              const height = Math.max(4, Math.round((month.count / tallestMonth) * 100));
              return (
                <div key={month.key} className="chart-bar" title={`${month.count} notes in ${month.label}`}>
                  <span className="chart-bar-fill" style={{ height: `${height}%` }} />
                </div>
              );
            })}
          </div>
          <div className="chart-columns chart-axis">
            {monthBuckets.map((month) => (
              <span key={month.key} className="chart-label">
                {month.label}
              </span>
            ))}
          </div>
        </div>
        <p className="stat-hint">
          {busiestMonth && busiestMonth.count > 0
            ? `Busiest month: ${busiestMonth.label}, with ${busiestMonth.count} notes.`
            : 'Nothing written down in the last six months.'}
        </p>
      </section>

      <section className="report-section">
        <h2 className="section-title">What you keep</h2>
        {byCategory.length === 0 ? (
          <p className="empty">No notes yet, so there is nothing to count.</p>
        ) : (
          <div className="bars">
            {byCategory.map((row) => (
              <div key={row.category} className="bar">
                <span>{row.category}</span>
                <i style={{ width: `${Math.max(4, Math.round((row.count / categoryTop) * 100))}%` }} />
                <b>{row.count}</b>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="report-section">
        <h2 className="section-title">Who you mention</h2>
        {peopleCounts.length === 0 ? (
          <p className="empty">
            No name is attached to a note yet. Attaching a person is what turns a note into a history of them.
          </p>
        ) : (
          <dl className="facts">
            {peopleCounts.map((row) => (
              <div key={row.name}>
                <dt>{row.name}</dt>
                <dd>
                  {row.count} {row.count === 1 ? 'note' : 'notes'}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <p className="stat-hint">
        Looking for one note rather than a count? <Link to="/search">Search the words</Link>.
      </p>
    </div>
  );
}
