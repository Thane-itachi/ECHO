import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';

import { Button, ButtonLink, Card, EmptyState } from '../components/ui';

import {
  ask,
  dueCommitments,
  remindCommitment,
  type Commitment,
  formatDate,
  formatDateTime,
  listMemories,
  listPeople,
  listProposals,
  listReminders,
  parseUtc,
  relativeDue,
  type AskAnswer,
  type Memory,
  type Proposal,
  type Reminder,
} from '../lib/api';
import { errorMessage, useAuthFailureHandler } from '../lib/auth';

interface Brief {
  memories: Memory[];
  memoryTotal: number;
  peopleTotal: number;
  reminders: Reminder[];
  proposals: Proposal[];
}

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning.';
  if (hour < 17) return 'Good afternoon.';
  return 'Good evening.';
}

function longDate(): string {
  return new Date().toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

/**
 * The front page of the app: a short brief, not a wall of notes.
 *
 * Four questions, in the order a person actually asks them: what is coming,
 * what did I just save, what is waiting for a decision, and can I ask something
 * without leaving the page. The answer column is the same /ask endpoint the
 * full page uses, so nothing here is a mock conversation.
 */
export default function Dashboard() {
  const handleAuthFailure = useAuthFailureHandler();
  const [brief, setBrief] = useState<Brief | null>(null);
  const [owed, setOwed] = useState<Commitment[]>([]);
  const [owedNotice, setOwedNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([
      listMemories({ limit: 4 }),
      listPeople(),
      listReminders(),
      listProposals('pending'),
      dueCommitments(14).catch(() => ({ items: [], total: 0 })),
    ])
      .then(([memories, people, reminders, proposals, due]) => {
        if (!alive) return;
        setOwed(due.items);
        setBrief({
          memories: memories.items,
          memoryTotal: memories.total,
          peopleTotal: people.total,
          reminders: reminders.items,
          proposals: proposals.items,
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

  const now = Date.now();
  const upcoming = (brief?.reminders ?? [])
    .filter((item) => item.status !== 'cancelled' && parseUtc(item.due_at).getTime() >= now)
    .sort((a, b) => parseUtc(a.due_at).getTime() - parseUtc(b.due_at).getTime());
  const next = upcoming[0] ?? null;

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">{longDate()}</p>
          <h1>{greeting()}</h1>
          <p className="page-sub">
            What needs you, what you last wrote down, and a question you can ask without looking for anything.
          </p>
        </div>
        <div className="today-actions">
          <ButtonLink variant="secondary" to="/vault">
            Write a note
          </ButtonLink>
          <ButtonLink variant="secondary" to="/ask">
            Ask ECHO
          </ButtonLink>
        </div>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      {!brief && !error ? <p className="page-sub">Opening your day…</p> : null}

      {brief ? (
        <>
          {next ? (
            <div className="next-up">
              <div>
                <p className="stat-label">Next up</p>
                <p className="next-up-title">{next.title}</p>
                <p className="next-up-when">
                  {relativeDue(next.due_at)} · {formatDateTime(next.due_at)}
                </p>
              </div>
              <ButtonLink variant="secondary" to="/reminders">
                All reminders
              </ButtonLink>
            </div>
          ) : (
            <div className="next-up">
              <div>
                <p className="stat-label">Next up</p>
                <p className="next-up-title">Nothing is due.</p>
                <p className="next-up-when">No reminder is waiting in the next few days.</p>
              </div>
              <ButtonLink variant="secondary" to="/reminders">
                Add a reminder
              </ButtonLink>
            </div>
          )}

          <div className="stat-grid">
            {[
              { label: 'Notes kept', value: brief.memoryTotal, hint: 'sealed with your key' },
              { label: 'People', value: brief.peopleTotal, hint: 'names your notes mention' },
              { label: 'Reminders ahead', value: upcoming.length, hint: 'still to come' },
              { label: 'Things to check', value: brief.proposals.length, hint: 'ECHO is waiting on you' },
            ].map((stat) => (
              <Card key={stat.label} className="stat-card" tone="quiet">
                <span className="stat-label">{stat.label}</span>
                <span className="stat-value">{stat.value}</span>
                <span className="stat-hint">{stat.hint}</span>
              </Card>
            ))}
          </div>

          <div className="today">
            <div className="today-main">
              <section>
                <h2 className="section-title">Coming up</h2>
                {upcoming.length === 0 ? (
                  <EmptyState title="No date is close">When you write one down, it appears here.</EmptyState>
                ) : (
                  upcoming.slice(0, 3).map((item) => (
                    <Link key={item.id} className="row-link" to="/reminders">
                      <span className="row-link-title">{item.title}</span>
                      <span className="row-link-sub">{relativeDue(item.due_at)}</span>
                      <span className="row-link-when">{formatDateTime(item.due_at)}</span>
                    </Link>
                  ))
                )}
              </section>

              <section>
                <h2 className="section-title">Owed, and due soon</h2>
                {owed.length === 0 ? (
                  <p className="empty">
                    Nothing promised in the next two weeks. Open someone to see everything still owed.
                  </p>
                ) : (
                  owed.slice(0, 4).map((row) => (
                    <div key={row.id} className="row-link owed-row">
                      <Link className="owed-main" to="/people">
                        <span className="row-link-title">
                          {row.person_name ? `${row.person_name}: ` : ''}
                          {row.text}
                        </span>
                        <span className="row-link-sub">
                          {row.kind === 'lent' ? 'you lent it' : row.kind === 'borrowed' ? 'you borrowed it' : 'you promised'}
                        </span>
                      </Link>
                      <span className="row-link-when">{row.due_on ? formatDate(row.due_on) : 'no date'}</span>
                      <Button
                        variant="secondary"
                        size="sm"
                        className="owed-remind"
                        onClick={() => {
                          void remindCommitment(row.id)
                            .then(() => setOwedNotice('Reminder set. It also goes to your email if that is on.'))
                            .catch((caught) => setOwedNotice(errorMessage(caught)));
                        }}
                      >
                        Remind me
                      </Button>
                    </div>
                  ))
                )}
                {owedNotice ? <p className="commit-notice">{owedNotice}</p> : null}
              </section>

              <section>
                <h2 className="section-title">Recently saved</h2>
                {brief.memories.length === 0 ? (
                  <EmptyState title="Nothing saved yet">The first note is the hardest one.</EmptyState>
                ) : (
                  brief.memories.map((memory) => (
                    <Link key={memory.id} className="row-link" to="/vault">
                      <span className="row-link-title">{memory.title}</span>
                      <span className="row-link-sub">{memory.content}</span>
                      <span className="row-link-when">{formatDate(memory.created_at)}</span>
                    </Link>
                  ))
                )}
              </section>

              <section>
                <h2 className="section-title">Worth a look</h2>
                {brief.proposals.length === 0 ? (
                  <EmptyState title="Nothing needs a yes or no">ECHO will ask when it finds something worth keeping.</EmptyState>
                ) : (
                  brief.proposals.slice(0, 2).map((proposal) => (
                    <Link key={proposal.id} className="row-link" to="/proposals">
                      <span className="row-link-title">{proposal.title}</span>
                      <span className="row-link-sub">{proposal.content}</span>
                      <span className="row-link-when">Check</span>
                    </Link>
                  ))
                )}
              </section>
            </div>

            <aside className="today-rail">
              <AskDock />
            </aside>
          </div>
        </>
      ) : null}
    </div>
  );
}

interface Turn {
  question: string;
  answer?: AskAnswer;
  error?: string;
}

const DOCK_SUGGESTIONS = ['What is coming up?', 'Anything I owe someone?', 'What did I save about work?'];

function AskDock() {
  const handleAuthFailure = useAuthFailureHandler();
  const [question, setQuestion] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);

  const submit = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text) return;
      setQuestion('');
      setTurns((prev) => [...prev, { question: text }]);
      setBusy(true);
      try {
        const answer = await ask(text);
        setTurns((prev) => {
          const next = [...prev];
          next[next.length - 1] = { question: text, answer };
          return next;
        });
      } catch (caught) {
        if (!handleAuthFailure(caught)) {
          setTurns((prev) => {
            const next = [...prev];
            next[next.length - 1] = { question: text, error: errorMessage(caught) };
            return next;
          });
        }
      } finally {
        setBusy(false);
      }
    },
    [handleAuthFailure],
  );

  return (
    <section className="dock" aria-label="Ask ECHO">
      <div className="dock-head">
        <h2>Ask ECHO</h2>
        <Link className="link-button" to="/ask">
          Open
        </Link>
      </div>

      <div className="dock-thread">
        {turns.length === 0 ? (
          <p className="dock-intro">
            Ask about anything you have written down. The answer comes from your notes, and the note it used is
            shown underneath.
          </p>
        ) : null}

        {turns.map((turn, index) => (
          <div key={`${index}-${turn.question}`} className="dock-turn">
            <p className="dock-q">{turn.question}</p>
            {turn.answer ? (
              <div className="dock-a">
                <p>{turn.answer.answer}</p>
                {turn.answer.citations.length > 0 ? (
                  <span className="dock-cite">
                    {turn.answer.grounding === 'inferred' ? 'Paraphrased from ' : 'From '}
                    {turn.answer.citations[0].title} · {formatDate(turn.answer.citations[0].created_at)}
                  </span>
                ) : (
                  <span className="dock-cite">Nothing saved answers this</span>
                )}
              </div>
            ) : null}
            {turn.error ? <p className="dock-a form-error">{turn.error}</p> : null}
            {!turn.answer && !turn.error ? <p className="dock-a muted">Reading your notes…</p> : null}
          </div>
        ))}
      </div>

      <form
        className="dock-form"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          void submit(question);
        }}
      >
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="What needs me this week?"
          aria-label="Ask ECHO"
        />
        <button type="submit" className="dock-send" disabled={busy || question.trim().length === 0}>
          Ask
        </button>
      </form>

      <div className="dock-suggest">
        {DOCK_SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            className="chip"
            disabled={busy}
            onClick={() => void submit(suggestion)}
          >
            {suggestion}
          </button>
        ))}
      </div>
    </section>
  );
}
