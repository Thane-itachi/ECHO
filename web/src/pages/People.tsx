import { useEffect, useState, type FormEvent } from 'react';

import {
  createCommitment,
  createPerson,
  deleteCommitment,
  deletePerson,
  formatDate,
  listCommitments,
  listPeople,
  remindCommitment,
  updateCommitment,
  updatePerson,
  type Commitment,
  type CommitmentKind,
  type Person,
} from '../lib/api';
import { errorMessage, useAuthFailureHandler } from '../lib/auth';

const KIND_WORDS: Record<CommitmentKind, string> = {
  promise: 'Promised',
  lent: 'Lent out',
  borrowed: 'Borrowed',
};

/** "in 3 days", "tomorrow", "2 days late" — plain words, no library. */
function dueWords(dueOn: string | null): string {
  if (!dueOn) return 'no date';
  const today = new Date();
  const due = new Date(`${dueOn}T09:00:00`);
  const days = Math.round((due.getTime() - new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()) / 86_400_000);
  if (days === 0) return 'today';
  if (days === 1) return 'tomorrow';
  if (days === -1) return 'yesterday';
  if (days < 0) return `${Math.abs(days)} days late`;
  if (days <= 14) return `in ${days} days`;
  return formatDate(dueOn);
}

export default function People() {
  const handleAuthFailure = useAuthFailureHandler();
  const [people, setPeople] = useState<Person[]>([]);
  const [name, setName] = useState('');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    listPeople()
      .then((page) => {
        if (alive) setPeople(page.items);
      })
      .catch((caught) => {
        if (!alive) return;
        if (!handleAuthFailure(caught)) setError(errorMessage(caught));
      });
    return () => {
      alive = false;
    };
  }, [reloadToken, handleAuthFailure]);

  function refresh() {
    setReloadToken((token) => token + 1);
  }

  async function add(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createPerson({ name: name.trim(), notes: notes.trim() || undefined });
      setName('');
      setNotes('');
      refresh();
    } catch (caught) {
      if (!handleAuthFailure(caught)) setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function remove(person: Person) {
    if (!window.confirm(`Remove ${person.name}? Memories that mention them stay in your vault.`)) return;
    try {
      await deletePerson(person.id);
      refresh();
    } catch (caught) {
      if (!handleAuthFailure(caught)) setError(errorMessage(caught));
    }
  }

  const open = people.find((person) => person.id === openId) ?? null;

  return (
    <div className="page page-narrow">
      <header className="page-head">
        <div>
          <p className="eyebrow">People</p>
          <h1>People, and what is still owed</h1>
          <p className="page-sub">
            Who someone is to you, the dates you keep, and every promise or borrowed thing that has not
            been settled yet.
          </p>
        </div>
      </header>

      {open ? (
        <PersonDetail
          person={open}
          onBack={() => setOpenId(null)}
          onChanged={refresh}
          onError={(message) => setError(message)}
          handleAuthFailure={handleAuthFailure}
        />
      ) : (
        <>
          <form className="inline-form" onSubmit={add}>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Name"
              maxLength={160}
              required
            />
            <input
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="How you know them (optional)"
              maxLength={4000}
            />
            <button type="submit" className="primary-button" disabled={busy || name.trim().length === 0}>
              {busy ? 'Adding…' : 'Add person'}
            </button>
          </form>

          {error ? <p className="form-error">{error}</p> : null}

          {people.length === 0 ? (
            <div className="empty empty-large">
              <p className="empty-title">No people yet</p>
              <p>Add the people whose promises, belongings and plans you want to track.</p>
            </div>
          ) : (
            <ul className="people">
              {people.map((person) => (
                <li key={person.id} className="person">
                  <button type="button" className="person-open" onClick={() => setOpenId(person.id)}>
                    <span className="person-name">{person.name}</span>
                    {person.relationship ? <span className="person-role">{person.relationship}</span> : null}
                    {person.notes ? <span className="person-notes">{person.notes}</span> : null}
                    <span className="person-date">
                      {person.open_commitments > 0
                        ? `${person.open_commitments} still owed`
                        : `Added ${formatDate(person.created_at)}`}
                      {person.key_dates.length > 0 ? ` · ${person.key_dates.length} date${person.key_dates.length === 1 ? '' : 's'} kept` : ''}
                    </span>
                  </button>
                  <button type="button" className="ghost-button" onClick={() => void remove(person)}>
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function PersonDetail({
  person,
  onBack,
  onChanged,
  onError,
  handleAuthFailure,
}: {
  person: Person;
  onBack: () => void;
  onChanged: () => void;
  onError: (message: string) => void;
  handleAuthFailure: (caught: unknown) => boolean;
}) {
  const [commitments, setCommitments] = useState<Commitment[]>([]);
  const [kind, setKind] = useState<CommitmentKind>('promise');
  const [text, setText] = useState('');
  const [dueOn, setDueOn] = useState('');
  const [relationship, setRelationship] = useState(person.relationship ?? '');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let alive = true;
    listCommitments({ person_id: person.id, status: 'all' })
      .then((page) => {
        if (alive) setCommitments(page.items);
      })
      .catch(() => {
        /* the page still works without the list; the form below reports its own errors */
      });
    return () => {
      alive = false;
    };
  }, [person.id, reload]);

  async function add(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      await createCommitment({
        kind,
        text: text.trim(),
        person_id: person.id,
        due_on: dueOn || null,
      });
      setText('');
      setDueOn('');
      setReload((token) => token + 1);
      onChanged();
    } catch (caught) {
      if (!handleAuthFailure(caught)) onError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function settle(row: Commitment) {
    try {
      await updateCommitment(row.id, { status: row.status === 'open' ? 'done' : 'open' });
      setReload((token) => token + 1);
      onChanged();
    } catch (caught) {
      if (!handleAuthFailure(caught)) onError(errorMessage(caught));
    }
  }

  async function remind(row: Commitment) {
    try {
      await remindCommitment(row.id);
      setNotice('Reminder set for nine in the morning. It also goes to your email if that is on.');
    } catch (caught) {
      if (!handleAuthFailure(caught)) onError(errorMessage(caught));
    }
  }

  async function drop(row: Commitment) {
    if (!window.confirm(`Forget "${row.text}"?`)) return;
    try {
      await deleteCommitment(row.id);
      setReload((token) => token + 1);
      onChanged();
    } catch (caught) {
      if (!handleAuthFailure(caught)) onError(errorMessage(caught));
    }
  }

  async function saveRelationship() {
    try {
      await updatePerson(person.id, { relationship: relationship.trim() || null });
      setNotice('Saved.');
      onChanged();
    } catch (caught) {
      if (!handleAuthFailure(caught)) onError(errorMessage(caught));
    }
  }

  const openRows = commitments.filter((row) => row.status === 'open');
  const settledRows = commitments.filter((row) => row.status !== 'open');

  return (
    <section className="person-detail">
      <button type="button" className="ghost-button" onClick={onBack}>
        ← All people
      </button>

      <header className="person-head">
        <h2>{person.name}</h2>
        <span className="muted">
          {openRows.length === 0 ? 'nothing owed' : `${openRows.length} still owed`}
          {person.notes ? ` · ${person.notes}` : ''}
        </span>
      </header>

      <div className="set-row">
        <span>
          <b>Who they are to you</b>
          <small>“my sister”, “my landlord”, “works at the bank” — encrypted like everything else.</small>
        </span>
        <span className="person-role-edit">
          <input
            value={relationship}
            onChange={(event) => setRelationship(event.target.value)}
            placeholder="relationship"
            maxLength={120}
          />
          <button type="button" className="ghost-button" onClick={() => void saveRelationship()}>
            Save
          </button>
        </span>
      </div>

      {person.key_dates.length > 0 ? (
        <div className="commit-block">
          <p className="section-title">Dates you keep</p>
          <ul className="a-kv-like">
            {person.key_dates.map((item) => (
              <li key={`${item.label}-${item.date}`}>
                <span>{item.label}</span>
                <span className="muted">{formatDate(item.date)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="commit-block">
        <p className="section-title">Still owed</p>
        {openRows.length === 0 ? (
          <p className="muted">Nothing open between you. Promises and borrowed things you add appear here.</p>
        ) : (
          <ul className="commit-list">
            {openRows.map((row) => (
              <li key={row.id} className="commit-row">
                <div>
                  <p className="commit-text">{row.text}</p>
                  <p className="commit-meta">
                    <span className="chip">{KIND_WORDS[row.kind]}</span>
                    <span className={row.due_on && dueWords(row.due_on).includes('late') ? 'commit-late' : 'muted'}>
                      {dueWords(row.due_on)}
                    </span>
                  </p>
                </div>
                <div className="commit-actions">
                  <button type="button" className="ghost-button" onClick={() => void remind(row)}>
                    Remind me
                  </button>
                  <button type="button" className="ghost-button" onClick={() => void settle(row)}>
                    Done
                  </button>
                  <button type="button" className="ghost-button" onClick={() => void drop(row)}>
                    Forget
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}

        <form className="commit-form" onSubmit={add}>
          <select value={kind} onChange={(event) => setKind(event.target.value as CommitmentKind)} aria-label="What kind">
            <option value="promise">I promised</option>
            <option value="lent">I lent out</option>
            <option value="borrowed">I borrowed</option>
          </select>
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={kind === 'promise' ? 'send the project document' : kind === 'lent' ? 'my drill' : 'their ladder'}
            maxLength={2000}
            required
          />
          <input
            type="date"
            value={dueOn}
            onChange={(event) => setDueOn(event.target.value)}
            aria-label="Settled by (optional)"
          />
          <button type="submit" className="primary-button" disabled={busy || text.trim().length === 0}>
            {busy ? 'Adding…' : 'Add'}
          </button>
        </form>
      </div>

      {notice ? <p className="commit-notice">{notice}</p> : null}

      {settledRows.length > 0 ? (
        <details className="commit-settled">
          <summary>{settledRows.length} settled</summary>
          <ul className="commit-list">
            {settledRows.map((row) => (
              <li key={row.id} className="commit-row is-settled">
                <div>
                  <p className="commit-text">{row.text}</p>
                  <p className="commit-meta">
                    <span className="chip">{KIND_WORDS[row.kind]}</span>
                    <span className="muted">{row.status}</span>
                  </p>
                </div>
                <div className="commit-actions">
                  <button type="button" className="ghost-button" onClick={() => void settle(row)}>
                    Reopen
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}
