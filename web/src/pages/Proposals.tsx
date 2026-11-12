import { useEffect, useState, type FormEvent } from 'react';

import {
  CATEGORIES,
  approveProposal,
  formatDate,
  listProposals,
  rejectProposal,
  createProposal,
  type Category,
  type Proposal,
  type ProposalStatus,
} from '../lib/api';
import { errorMessage, useAuthFailureHandler } from '../lib/auth';

const TABS: { value: ProposalStatus; label: string }[] = [
  { value: 'pending', label: 'Waiting for you' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
];

export default function Proposals() {
  const handleAuthFailure = useAuthFailureHandler();
  const [status, setStatus] = useState<ProposalStatus>('pending');
  const [items, setItems] = useState<Proposal[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const [drafting, setDrafting] = useState(false);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [sourceText, setSourceText] = useState('');
  const [category, setCategory] = useState<Category>('general');

  useEffect(() => {
    let alive = true;
    listProposals(status)
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
  }, [status, reloadToken, handleAuthFailure]);

  async function decide(proposal: Proposal, action: 'approve' | 'reject') {
    setBusyId(proposal.id);
    setError(null);
    try {
      if (action === 'approve') await approveProposal(proposal.id);
      else await rejectProposal(proposal.id);
      setReloadToken((token) => token + 1);
    } catch (caught) {
      if (!handleAuthFailure(caught)) setError(errorMessage(caught));
    } finally {
      setBusyId(null);
    }
  }

  async function draft(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await createProposal({
        title: title.trim(),
        content: content.trim(),
        source_text: sourceText.trim() || content.trim(),
        category,
        confidence: 0.5,
      });
      setTitle('');
      setContent('');
      setSourceText('');
      setDrafting(false);
      setStatus('pending');
      setReloadToken((token) => token + 1);
    } catch (caught) {
      if (!handleAuthFailure(caught)) setError(errorMessage(caught));
    }
  }

  return (
    <div className="page page-narrow">
      <header className="page-head">
        <div>
          <p className="eyebrow">Captures</p>
          <h1>Nothing is filed without you</h1>
          <p className="page-sub">
            When ECHO drafts a memory from something you said, it waits here. Approving creates exactly one memory;
            the decision is recorded.
          </p>
        </div>
        <button type="button" className="ghost-button" onClick={() => setDrafting((value) => !value)}>
          {drafting ? 'Close' : 'Draft one by hand'}
        </button>
      </header>

      {drafting ? (
        <form className="form draft-form" onSubmit={draft}>
          <p className="draft-note">
            The extraction worker is not wired up yet, so this is the manual version of what it will write into
            this queue.
          </p>
          <label className="field">
            <span>Title</span>
            <input value={title} onChange={(event) => setTitle(event.target.value)} required maxLength={200} />
          </label>
          <label className="field">
            <span>Memory</span>
            <textarea value={content} onChange={(event) => setContent(event.target.value)} rows={4} required />
          </label>
          <label className="field">
            <span>What was actually said</span>
            <textarea
              value={sourceText}
              onChange={(event) => setSourceText(event.target.value)}
              rows={2}
              placeholder="john borrowed my laptop yesterday and promised it back tomorrow"
            />
          </label>
          <label className="field">
            <span>Category</span>
            <select value={category} onChange={(event) => setCategory(event.target.value as Category)}>
              {CATEGORIES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <div className="form-actions">
            <button type="submit" className="primary-button" disabled={!title.trim() || !content.trim()}>
              Add to the queue
            </button>
          </div>
        </form>
      ) : null}

      <div className="tab-row">
        {TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            className={status === tab.value ? 'tab is-active' : 'tab'}
            onClick={() => setStatus(tab.value)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {error ? <p className="form-error">{error}</p> : null}

      {items.length === 0 ? (
        <div className="empty empty-large">
          <p className="empty-title">
            {status === 'pending' ? 'Nothing waiting' : status === 'approved' ? 'Nothing approved yet' : 'Nothing rejected'}
          </p>
          <p>
            {status === 'pending'
              ? 'When ECHO proposes a memory from a conversation, it appears here for one tap of approval.'
              : 'Decisions you make stay in the list so you can see what was filed.'}
          </p>
        </div>
      ) : (
        <ul className="proposals">
          {items.map((proposal) => (
            <li key={proposal.id} className="proposal">
              <div className="detail-head">
                <span className="chip">{proposal.category}</span>
                {proposal.confidence !== null ? (
                  <span className="chip chip-ai">confidence {Math.round(proposal.confidence * 100)}%</span>
                ) : null}
                <span className="memory-card-date">
                  {proposal.status === 'pending' ? `Drafted ${formatDate(proposal.created_at)}` : `Decided ${formatDate(proposal.decided_at ?? proposal.created_at)}`}
                </span>
              </div>
              <h3>{proposal.title}</h3>
              <p className="proposal-body">{proposal.content}</p>
              <blockquote className="proposal-quote">“{proposal.source_text}”</blockquote>

              {proposal.status === 'pending' ? (
                <div className="proposal-actions">
                  <button
                    type="button"
                    className="primary-button"
                    disabled={busyId === proposal.id}
                    onClick={() => void decide(proposal, 'approve')}
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    className="ghost-button"
                    disabled={busyId === proposal.id}
                    onClick={() => void decide(proposal, 'reject')}
                  >
                    Reject
                  </button>
                </div>
              ) : (
                <p className="proposal-state">
                  {proposal.status === 'approved' ? 'Approved and filed in your vault.' : 'Rejected, nothing was filed.'}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
