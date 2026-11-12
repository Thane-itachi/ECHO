import { useEffect, useMemo, useState, type FormEvent } from 'react';

import {
  CATEGORIES,
  archiveMemory,
  createMemory,
  deleteMemory,
  formatDate,
  listMemories,
  restoreMemory,
  updateMemory,
  type Category,
  type Memory,
  type Page,
} from '../lib/api';
import { errorMessage, useAuthFailureHandler } from '../lib/auth';
import RelatedMemories from '../components/RelatedMemories';

interface Draft {
  title: string;
  content: string;
  category: Category;
}

const EMPTY_DRAFT: Draft = { title: '', content: '', category: 'general' };

function MemoryForm({
  initial,
  submitLabel,
  busy,
  error,
  onSubmit,
  onCancel,
}: {
  initial: Draft;
  submitLabel: string;
  busy: boolean;
  error: string | null;
  onSubmit: (draft: Draft) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(initial);

  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit(draft);
  }

  return (
    <form className="form detail-form" onSubmit={submit}>
      <label className="field">
        <span>Title</span>
        <input
          value={draft.title}
          maxLength={200}
          onChange={(event) => setDraft({ ...draft, title: event.target.value })}
          placeholder="John borrowed my laptop"
          required
        />
      </label>

      <label className="field">
        <span>What happened</span>
        <textarea
          value={draft.content}
          rows={7}
          maxLength={20000}
          onChange={(event) => setDraft({ ...draft, content: event.target.value })}
          placeholder="He took it yesterday and promised to bring it back tomorrow."
          required
        />
      </label>

      <label className="field">
        <span>Category</span>
        <select
          value={draft.category}
          onChange={(event) => setDraft({ ...draft, category: event.target.value as Category })}
        >
          {CATEGORIES.map((category) => (
            <option key={category} value={category}>
              {category}
            </option>
          ))}
        </select>
      </label>

      {error ? <p className="form-error">{error}</p> : null}

      <div className="form-actions">
        <button type="submit" className="primary-button" disabled={busy}>
          {busy ? 'Saving…' : submitLabel}
        </button>
        <button type="button" className="ghost-button" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </form>
  );
}

export default function Vault() {
  const handleAuthFailure = useAuthFailureHandler();

  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [category, setCategory] = useState<Category | ''>('');
  const [includeArchived, setIncludeArchived] = useState(false);
  const [page, setPage] = useState<Page<Memory> | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [composing, setComposing] = useState(false);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query.trim()), 250);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    let alive = true;
    listMemories({ q: debounced, category, include_archived: includeArchived, limit: 200 })
      .then((result) => {
        if (!alive) return;
        setPage(result);
        setSelectedId((current) => (current && result.items.some((item) => item.id === current) ? current : result.items[0]?.id ?? null));
      })
      .catch((caught) => {
        if (!alive) return;
        if (handleAuthFailure(caught)) return;
        setError(errorMessage(caught));
      });
    return () => {
      alive = false;
    };
  }, [debounced, category, includeArchived, reloadToken, handleAuthFailure]);

  const items = page?.items ?? [];
  const selected = useMemo(() => items.find((item) => item.id === selectedId) ?? null, [items, selectedId]);

  function refresh() {
    setReloadToken((token) => token + 1);
  }

  async function save(draft: Draft) {
    setBusy(true);
    setError(null);
    try {
      if (composing) {
        const created = await createMemory({
          title: draft.title,
          content: draft.content,
          category: draft.category,
        });
        setComposing(false);
        setSelectedId(created.id);
      } else if (selected) {
        await updateMemory(selected.id, {
          title: draft.title,
          content: draft.content,
          category: draft.category,
        });
        setEditing(false);
      }
      refresh();
    } catch (caught) {
      if (!handleAuthFailure(caught)) setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function toggleArchive(memory: Memory) {
    setBusy(true);
    try {
      if (memory.archived_at) await restoreMemory(memory.id);
      else await archiveMemory(memory.id);
      refresh();
    } catch (caught) {
      if (!handleAuthFailure(caught)) setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function remove(memory: Memory) {
    if (!window.confirm(`Delete “${memory.title}” permanently?`)) return;
    setBusy(true);
    try {
      await deleteMemory(memory.id);
      setSelectedId(null);
      refresh();
    } catch (caught) {
      if (!handleAuthFailure(caught)) setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  const showForm = composing || (editing && selected !== null);

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">Memory Vault</p>
          <h1>Everything worth keeping</h1>
          <p className="page-sub">
            {page ? `${page.total} ${page.total === 1 ? 'memory' : 'memories'}` : 'Loading…'}
            {debounced ? ` matching “${debounced}”` : ''}
          </p>
        </div>
        <button
          type="button"
          className="primary-button"
          onClick={() => {
            setComposing(true);
            setEditing(false);
            setError(null);
          }}
        >
          New memory
        </button>
      </header>

      <div className="toolbar">
        <input
          className="search"
          type="search"
          placeholder="Search titles and contents…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <select className="filter" value={category} onChange={(event) => setCategory(event.target.value as Category | '')}>
          <option value="">All categories</option>
          {CATEGORIES.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
        <label className="toggle">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(event) => setIncludeArchived(event.target.checked)}
          />
          <span>Include archived</span>
        </label>
      </div>

      {error ? <p className="form-error">{error}</p> : null}

      <div className="vault">
        <div className="vault-list">
          {items.length === 0 && !composing ? (
            <div className="empty">
              <p className="empty-title">Nothing here yet</p>
              <p>
                {debounced
                  ? 'No memory matches that. Try a different word, or clear the search.'
                  : 'Tell ECHO one thing worth remembering: who borrowed what, what you promised, when the boiler gets serviced.'}
              </p>
            </div>
          ) : null}

          {items.map((memory) => (
            <button
              key={memory.id}
              type="button"
              className={memory.id === selectedId && !composing ? 'memory-card is-active' : 'memory-card'}
              onClick={() => {
                setSelectedId(memory.id);
                setComposing(false);
                setEditing(false);
                setError(null);
              }}
            >
              <span className="memory-card-top">
                <span className="chip">{memory.category}</span>
                {memory.archived_at ? <span className="chip chip-muted">archived</span> : null}
                {memory.source === 'ai_extraction' ? <span className="chip chip-ai">captured</span> : null}
              </span>
              <span className="memory-card-title">{memory.title}</span>
              <span className="memory-card-snippet">{memory.content.slice(0, 130)}</span>
              <span className="memory-card-date">{formatDate(memory.created_at)}</span>
            </button>
          ))}
        </div>

        <div className="vault-detail">
          {showForm ? (
            <MemoryForm
              key={composing ? 'create' : selected?.id ?? 'edit'}
              initial={
                composing || !selected
                  ? EMPTY_DRAFT
                  : { title: selected.title, content: selected.content, category: selected.category }
              }
              submitLabel={composing ? 'Save memory' : 'Save changes'}
              busy={busy}
              error={error}
              onSubmit={save}
              onCancel={() => {
                setComposing(false);
                setEditing(false);
                setError(null);
              }}
            />
          ) : selected ? (
            <article className="detail">
              <div className="detail-head">
                <span className="chip">{selected.category}</span>
                {selected.archived_at ? <span className="chip chip-muted">archived</span> : null}
                {selected.confidence !== null ? (
                  <span className="chip chip-ai">confidence {Math.round(selected.confidence * 100)}%</span>
                ) : null}
              </div>
              <h2>{selected.title}</h2>
              <p className="detail-body">{selected.content}</p>

              <dl className="meta">
                <div>
                  <dt>Recorded</dt>
                  <dd>{formatDate(selected.created_at)}</dd>
                </div>
                <div>
                  <dt>Last updated</dt>
                  <dd>{formatDate(selected.updated_at)}</dd>
                </div>
                <div>
                  <dt>Source</dt>
                  <dd>{selected.source === 'ai_extraction' ? 'Captured, then approved' : 'You'}</dd>
                </div>
              </dl>

              <RelatedMemories memoryId={selected.id} candidates={items} />

              <div className="detail-actions">
                <button type="button" className="primary-button" onClick={() => setEditing(true)} disabled={busy}>
                  Edit
                </button>
                <button type="button" className="ghost-button" onClick={() => void toggleArchive(selected)} disabled={busy}>
                  {selected.archived_at ? 'Restore' : 'Archive'}
                </button>
                <button type="button" className="danger-button" onClick={() => void remove(selected)} disabled={busy}>
                  Delete
                </button>
              </div>
            </article>
          ) : (
            <div className="empty empty-large">
              <p className="empty-title">Pick a memory</p>
              <p>Select something on the left to read it in full.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
