import { useEffect, useRef, useState } from 'react';

import {
  deleteDocument,
  downloadDocument,
  formatDate,
  listDocuments,
  uploadDocument,
  type Document,
} from '../lib/api';
import { errorMessage, useAuthFailureHandler } from '../lib/auth';

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function Documents() {
  const handleAuthFailure = useAuthFailureHandler();
  const fileInput = useRef<HTMLInputElement>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let alive = true;
    listDocuments()
      .then((page) => {
        if (alive) setDocuments(page.items);
      })
      .catch((caught) => {
        if (!alive) return;
        if (!handleAuthFailure(caught)) setError(errorMessage(caught));
      });
    return () => {
      alive = false;
    };
  }, [reload, handleAuthFailure]);

  async function upload(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await uploadDocument(file);
      setReload((value) => value + 1);
    } catch (caught) {
      if (!handleAuthFailure(caught)) setError(errorMessage(caught));
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = '';
    }
  }

  async function remove(document: Document) {
    setBusy(true);
    setError(null);
    try {
      await deleteDocument(document.id);
      setReload((value) => value + 1);
    } catch (caught) {
      if (!handleAuthFailure(caught)) setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function download(document: Document) {
    setError(null);
    try {
      await downloadDocument(document.id, document.filename);
    } catch (caught) {
      if (!handleAuthFailure(caught)) setError(errorMessage(caught));
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">Documents</p>
          <h1>Receipts, certificates, anything on paper</h1>
          <p className="page-sub">
            Files are encrypted with your key before they touch the disk. Nobody else, including an administrator,
            can open them.
          </p>
        </div>
      </header>

      <div className="toolbar">
        <input
          ref={fileInput}
          type="file"
          onChange={(event) => void upload(event.target.files?.[0])}
          disabled={busy}
          aria-label="Choose a document to upload"
        />
        <span className="muted">Up to 10 MB per file.</span>
      </div>

      {error ? <p className="form-error">{error}</p> : null}

      {documents.length === 0 ? (
        <div className="empty empty-large">
          <p className="empty-title">No documents yet</p>
          <p>Upload a receipt or a certificate and it will be stored encrypted.</p>
        </div>
      ) : (
        <ul className="documents">
          {documents.map((document) => (
            <li key={document.id} className="document">
              <div>
                <span className="document-name">{document.filename}</span>
                <span className="memory-card-date">
                  {humanSize(document.size_bytes)} · {formatDate(document.created_at)}
                </span>
              </div>
              <div className="row-actions">
                <button type="button" className="ghost-button" onClick={() => void download(document)}>
                  Download
                </button>
                <button type="button" className="danger-button" disabled={busy} onClick={() => void remove(document)}>
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
