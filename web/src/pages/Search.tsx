import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import {
  CATEGORIES,
  formatDate,
  listMemories,
  type Category,
  type Memory,
  type Page,
} from '../lib/api';
import { errorMessage, useAuthFailureHandler } from '../lib/auth';

/**
 * One box, every word.
 *
 * The server searches a blind index — a scrambled fingerprint of each word — so
 * this page can look inside a note nobody, including the server, can read. The
 * request is debounced so typing a sentence does not fire a dozen queries.
 */
export default function Search() {
  const handleAuthFailure = useAuthFailureHandler();
  const [term, setTerm] = useState('');
  const [category, setCategory] = useState<Category | ''>('');
  const [results, setResults] = useState<Page<Memory> | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const timer = window.setTimeout(() => {
      setBusy(true);
      listMemories({
        q: term.trim() || undefined,
        category: category || undefined,
        limit: 40,
      })
        .then((page) => {
          if (!alive) return;
          setResults(page);
          setError(null);
        })
        .catch((caught) => {
          if (!alive) return;
          if (!handleAuthFailure(caught)) setError(errorMessage(caught));
        })
        .finally(() => {
          if (alive) setBusy(false);
        });
    }, 220);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [term, category, handleAuthFailure]);

  return (
    <div className="page page-narrow">
      <header className="page-head">
        <div>
          <p className="eyebrow">Search</p>
          <h1>Look through everything you saved</h1>
          <p className="page-sub">
            Every word you wrote, not just the title. The search runs on scrambled versions of your words, so your
            notes are never read in order to find them.
          </p>
        </div>
      </header>

      <div className="toolbar">
        <input
          className="search"
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          placeholder="Try “wedding”, “Amara”, “prescription”…"
          aria-label="Search your notes"
          autoFocus
        />
        <select
          className="filter"
          value={category}
          onChange={(event) => setCategory(event.target.value as Category | '')}
          aria-label="Category"
        >
          <option value="">Everything</option>
          {CATEGORIES.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </div>

      <p className="result-count" role="status">
        {busy
          ? 'Looking…'
          : results
            ? `${results.total} ${results.total === 1 ? 'note' : 'notes'}${results.total > results.items.length ? `, showing the first ${results.items.length}` : ''}`
            : ''}
      </p>

      {error ? <p className="form-error">{error}</p> : null}

      {!busy && results && results.items.length === 0 ? (
        <p className="empty">
          Nothing matched. Try a shorter word, or a name exactly as you wrote it down.
        </p>
      ) : null}

      <div className="results">
        {results?.items.map((memory) => (
          <article key={memory.id} className="result">
            <div className="result-head">
              <h2>{memory.title}</h2>
              <span className="chip chip-muted">{memory.category}</span>
            </div>
            <p className="result-body">{memory.content}</p>
            <p className="result-meta">
              Saved {formatDate(memory.created_at)}
              {memory.archived_at ? ' · in the archive' : ''}
            </p>
            <Link className="link-button" to="/vault">
              Open in my notes
            </Link>
          </article>
        ))}
      </div>
    </div>
  );
}
