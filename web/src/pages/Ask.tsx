import { useState } from 'react';
import { Link } from 'react-router-dom';

import { formatDate, listMemories, type Memory } from '../lib/api';
import { errorMessage, useAuthFailureHandler } from '../lib/auth';

export default function Ask() {
  const handleAuthFailure = useAuthFailureHandler();
  const [question, setQuestion] = useState('');
  const [asked, setAsked] = useState<string | null>(null);
  const [results, setResults] = useState<Memory[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search(term: string) {
    setBusy(true);
    setError(null);
    try {
      const page = await listMemories({ q: term, limit: 20, include_archived: true });
      setResults(page.items);
      setAsked(term);
    } catch (caught) {
      if (!handleAuthFailure(caught)) setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page page-narrow">
      <header className="page-head">
        <div>
          <p className="eyebrow">Ask ECHO</p>
          <h1>Ask about anything you stored</h1>
          <p className="page-sub">
            Right now this is retrieval, not conversation: ECHO shows the memories that match your words. The
            assistant that answers in sentences is the next milestone.
          </p>
        </div>
      </header>

      <form
        className="ask-bar"
        onSubmit={(event) => {
          event.preventDefault();
          const term = question.trim();
          if (term) void search(term);
        }}
      >
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Who borrowed my laptop?"
          aria-label="Ask ECHO"
        />
        <button type="submit" className="primary-button" disabled={busy || question.trim().length === 0}>
          {busy ? 'Looking…' : 'Ask'}
        </button>
      </form>

      <div className="suggestions">
        {['laptop', 'borrowed', 'promised', 'boiler'].map((term) => (
          <button
            key={term}
            type="button"
            className="pill"
            onClick={() => {
              setQuestion(term);
              void search(term);
            }}
          >
            {term}
          </button>
        ))}
      </div>

      {error ? <p className="form-error">{error}</p> : null}

      {results ? (
        <section className="results">
          <p className="results-head">
            {results.length === 0
              ? `Nothing in your vault mentions “${asked}”.`
              : results.length === 1
                ? `1 memory mentions “${asked}”.`
                : `${results.length} memories mention “${asked}”.`}
          </p>
          {results.map((memory) => (
            <article key={memory.id} className="result">
              <div className="detail-head">
                <span className="chip">{memory.category}</span>
                <span className="memory-card-date">{formatDate(memory.created_at)}</span>
              </div>
              <h3>{memory.title}</h3>
              <p>{memory.content}</p>
            </article>
          ))}
          {results.length === 0 ? (
            <p className="results-hint">
              <Link to="/vault">Open the vault</Link> to add what you remember.
            </p>
          ) : null}
        </section>
      ) : (
        <div className="empty empty-large">
          <p className="empty-title">Nothing asked yet</p>
          <p>Try “who borrowed my laptop”, or a name, or a place.</p>
        </div>
      )}
    </div>
  );
}
