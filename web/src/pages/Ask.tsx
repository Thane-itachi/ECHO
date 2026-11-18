import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';

import { Button } from '../components/ui';

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
          <p className="eyebrow">Ask a question</p>
          <h1>Ask about anything you saved</h1>
          <p className="page-sub">
            ECHO answers using your own notes and shows you which one it used. If it cannot find an answer, it
            says so instead of making one up.
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
        <Button variant="primary" type="submit" disabled={busy || question.trim().length === 0}>
          {busy ? 'Thinking…' : 'Ask'}
        </Button>
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
            <span className={`chip ${answer.grounding === 'none' ? '' : 'chip-ai'}`}>
              {answer.grounding === 'record'
                ? 'from a saved record'
                : answer.grounding === 'inferred'
                  ? 'paraphrased from your notes'
                  : 'nothing saved answers this'}
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
