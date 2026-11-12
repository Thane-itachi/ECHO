import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';

import { ask, formatDate, type AskAnswer } from '../lib/api';
import { errorMessage, useAuthFailureHandler } from '../lib/auth';

const SUGGESTIONS = [
  'Who borrowed my laptop?',
  'When did the plumber say he would come?',
  'What did I promise Ngozi?',
];

export default function Ask() {
  const handleAuthFailure = useAuthFailureHandler();
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(term: string) {
    if (!term.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setAnswer(await ask(term.trim()));
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
            Answers are quoted from your own memories and cited. ECHO does not invent an answer when your vault has
            nothing to say.
          </p>
        </div>
      </header>

      <form
        className="ask-bar"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          void submit(question);
        }}
      >
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Who borrowed my laptop?"
          aria-label="Ask ECHO"
        />
        <button type="submit" className="primary-button" disabled={busy || question.trim().length === 0}>
          {busy ? 'Thinking…' : 'Ask'}
        </button>
      </form>

      <div className="suggestions">
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            className="chip"
            onClick={() => {
              setQuestion(suggestion);
              void submit(suggestion);
            }}
          >
            {suggestion}
          </button>
        ))}
      </div>

      {error ? <p className="form-error">{error}</p> : null}

      {answer ? (
        <section className="answer">
          <div className="answer-head">
            <span className="chip chip-ai">
              {answer.mode === 'extractive' ? 'quoted from your vault' : answer.mode}
            </span>
            <span className="muted">
              {answer.matched === 0 ? 'no matching memory' : `${answer.matched} matching memor${answer.matched === 1 ? 'y' : 'ies'}`}
            </span>
          </div>
          <div className="answer-body">
            {answer.answer.split('\n').map((line, index) => (
              <p key={index}>{line}</p>
            ))}
          </div>

          {answer.citations.length > 0 ? (
            <>
              <h2 className="section-title">Sources</h2>
              <ol className="citations">
                {answer.citations.map((citation) => (
                  <li key={citation.memory_id}>
                    <Link to={`/vault?memory=${citation.memory_id}`}>{citation.title}</Link>
                    <span className="memory-card-date">{formatDate(citation.created_at)}</span>
                  </li>
                ))}
              </ol>
            </>
          ) : null}
        </section>
      ) : (
        <div className="empty">
          <p className="empty-title">Ask a question in your own words</p>
          <p>ECHO searches your vault by meaning of the words you stored, then quotes what it found.</p>
        </div>
      )}
    </div>
  );
}
