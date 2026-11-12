import { useEffect, useState, type FormEvent } from 'react';

import { createPerson, deletePerson, formatDate, listPeople, type Person } from '../lib/api';
import { errorMessage, useAuthFailureHandler } from '../lib/auth';

export default function People() {
  const handleAuthFailure = useAuthFailureHandler();
  const [people, setPeople] = useState<Person[]>([]);
  const [name, setName] = useState('');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

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

  async function add(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createPerson({ name: name.trim(), notes: notes.trim() || undefined });
      setName('');
      setNotes('');
      setReloadToken((token) => token + 1);
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
      setReloadToken((token) => token + 1);
    } catch (caught) {
      if (!handleAuthFailure(caught)) setError(errorMessage(caught));
    }
  }

  return (
    <div className="page page-narrow">
      <header className="page-head">
        <div>
          <p className="eyebrow">People</p>
          <h1>Who your memories are about</h1>
          <p className="page-sub">Link a memory to a person and ECHO can gather everything about them in one place.</p>
        </div>
      </header>

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
              <div>
                <p className="person-name">{person.name}</p>
                {person.notes ? <p className="person-notes">{person.notes}</p> : null}
                <p className="person-date">Added {formatDate(person.created_at)}</p>
              </div>
              <button type="button" className="ghost-button" onClick={() => void remove(person)}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
