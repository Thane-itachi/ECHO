import { useEffect, useMemo, useState, type FormEvent } from 'react';

import {
  cancelReminder,
  createReminder,
  formatDateTime,
  listReminders,
  parseUtc,
  relativeDue,
  toDateTimeLocal,
  type Reminder,
} from '../lib/api';
import { errorMessage, useAuthFailureHandler } from '../lib/auth';

export default function Reminders() {
  const handleAuthFailure = useAuthFailureHandler();
  const [items, setItems] = useState<Reminder[]>([]);
  const [title, setTitle] = useState('');
  const [dueAt, setDueAt] = useState(() => toDateTimeLocal(new Date(Date.now() + 24 * 60 * 60 * 1000)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let alive = true;
    listReminders()
      .then((page) => {
        if (alive) setItems(page.items);
      })
      .catch((caught) => {
        if (!alive) return;
        if (!handleAuthFailure(caught)) setError(errorMessage(caught));
      });
    return () => {
      alive = false;
    };
  }, [reloadToken, handleAuthFailure]);

  const { upcoming, past } = useMemo(() => {
    const now = Date.now();
    const active = items.filter((item) => item.status !== 'cancelled');
    return {
      upcoming: active
        .filter((item) => parseUtc(item.due_at).getTime() >= now)
        .sort((a, b) => parseUtc(a.due_at).getTime() - parseUtc(b.due_at).getTime()),
      past: active
        .filter((item) => parseUtc(item.due_at).getTime() < now)
        .sort((a, b) => parseUtc(b.due_at).getTime() - parseUtc(a.due_at).getTime()),
    };
  }, [items]);

  async function add(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // datetime-local is browser-local; the API wants an absolute instant.
      const due = new Date(dueAt);
      await createReminder({ title: title.trim(), due_at: due.toISOString() });
      setTitle('');
      setDueAt(toDateTimeLocal(new Date(Date.now() + 24 * 60 * 60 * 1000)));
      setReloadToken((token) => token + 1);
    } catch (caught) {
      if (!handleAuthFailure(caught)) setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function cancel(reminder: Reminder) {
    try {
      await cancelReminder(reminder.id);
      setReloadToken((token) => token + 1);
    } catch (caught) {
      if (!handleAuthFailure(caught)) setError(errorMessage(caught));
    }
  }

  return (
    <div className="page page-narrow">
      <header className="page-head">
        <div>
          <p className="eyebrow">Reminders</p>
          <h1>Promises with a date</h1>
          <p className="page-sub">
            Each reminder becomes one durable job. It fires once, even if the server restarts in between.
          </p>
        </div>
      </header>

      <form className="inline-form" onSubmit={add}>
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Return John's laptop"
          maxLength={200}
          required
        />
        <input
          type="datetime-local"
          value={dueAt}
          onChange={(event) => setDueAt(event.target.value)}
          required
        />
        <button type="submit" className="primary-button" disabled={busy || title.trim().length === 0}>
          {busy ? 'Scheduling…' : 'Set reminder'}
        </button>
      </form>

      {error ? <p className="form-error">{error}</p> : null}

      <section className="reminder-section">
        <h2 className="section-title">Upcoming</h2>
        {upcoming.length === 0 ? (
          <p className="muted">Nothing scheduled.</p>
        ) : (
          <ul className="reminders">
            {upcoming.map((reminder) => (
              <li key={reminder.id} className="reminder">
                <div>
                  <p className="reminder-title">{reminder.title}</p>
                  <p className="reminder-when">
                    {formatDateTime(reminder.due_at)} · {relativeDue(reminder.due_at)}
                  </p>
                </div>
                <div className="reminder-actions">
                  <span className={reminder.status === 'notified' ? 'chip chip-ai' : 'chip'}>{reminder.status}</span>
                  <button type="button" className="ghost-button" onClick={() => void cancel(reminder)}>
                    Cancel
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {past.length > 0 ? (
        <section className="reminder-section">
          <h2 className="section-title">Already due</h2>
          <ul className="reminders">
            {past.map((reminder) => (
              <li key={reminder.id} className="reminder is-past">
                <div>
                  <p className="reminder-title">{reminder.title}</p>
                  <p className="reminder-when">
                    {formatDateTime(reminder.due_at)} · {relativeDue(reminder.due_at)}
                  </p>
                </div>
                <span className="chip chip-muted">{reminder.status}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
