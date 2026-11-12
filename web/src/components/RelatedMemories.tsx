import { useEffect, useState } from 'react';

import { createLink, listLinks, removeLink, type LinkedMemory, type Memory } from '../lib/api';
import { errorMessage, useAuthFailureHandler } from '../lib/auth';

export default function RelatedMemories({ memoryId, candidates }: { memoryId: string; candidates: Memory[] }) {
  const handleAuthFailure = useAuthFailureHandler();
  const [links, setLinks] = useState<LinkedMemory[]>([]);
  const [choice, setChoice] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    listLinks(memoryId)
      .then((page) => {
        if (alive) setLinks(page.items);
      })
      .catch(() => {
        /* a missing link list should never break reading a memory */
      });
    return () => {
      alive = false;
    };
  }, [memoryId]);

  const options = candidates.filter(
    (candidate) => candidate.id !== memoryId && !links.some((link) => link.id === candidate.id),
  );

  async function add() {
    if (!choice) return;
    setBusy(true);
    setError(null);
    try {
      const page = await createLink(memoryId, choice);
      setLinks(page.items);
      setChoice('');
    } catch (caught) {
      if (!handleAuthFailure(caught)) setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function drop(otherId: string) {
    setBusy(true);
    setError(null);
    try {
      const page = await removeLink(memoryId, otherId);
      setLinks(page.items);
    } catch (caught) {
      if (!handleAuthFailure(caught)) setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="related">
      <h3 className="section-title">Connected memories</h3>
      {links.length === 0 ? (
        <p className="muted">Nothing linked yet. Connect this to the memory it belongs with.</p>
      ) : (
        <ul className="related-list">
          {links.map((link) => (
            <li key={link.id}>
              <span>{link.title}</span>
              <span className="chip chip-muted">{link.kind}</span>
              <button type="button" className="ghost-button" disabled={busy} onClick={() => void drop(link.id)}>
                Unlink
              </button>
            </li>
          ))}
        </ul>
      )}

      {options.length > 0 ? (
        <div className="inline-form">
          <select value={choice} onChange={(event) => setChoice(event.target.value)} aria-label="Memory to connect">
            <option value="">Choose a memory…</option>
            {options.map((option) => (
              <option key={option.id} value={option.id}>
                {option.title}
              </option>
            ))}
          </select>
          <button type="button" className="ghost-button" disabled={busy || !choice} onClick={() => void add()}>
            Connect
          </button>
        </div>
      ) : null}

      {error ? <p className="form-error">{error}</p> : null}
    </section>
  );
}
