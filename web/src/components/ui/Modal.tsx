import { useEffect, useRef, type ReactNode } from 'react';

import { Button } from './Button';

/**
 * A modal that behaves: it takes focus, keeps Tab inside, closes on Escape and
 * on a backdrop click, and gives the page back the focus it stole. Anything
 * destructive goes through ConfirmationDialog so the wording is never improvised.
 */
export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  labelledBy,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  labelledBy?: string;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreRef = useRef<Element | null>(null);

  useEffect(() => {
    if (!open) return;
    restoreRef.current = document.activeElement;
    // Focus the panel itself, not its first button: a screen reader then reads
    // the dialog's own label, and Tab starts from the top in a predictable place.
    panelRef.current?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onClose();
        return;
      }
      const panel = panelRef.current;
      if (event.key !== 'Tab' || !panel) return;
      const items = Array.from(
        panel.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener('keydown', onKeyDown, true);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKeyDown, true);
      document.body.style.overflow = previousOverflow;
      (restoreRef.current as HTMLElement | null)?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="ui-modal-layer">
      <div className="ui-modal-backdrop" onClick={onClose} aria-hidden="true" />
      <div
        className="ui-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy ?? 'ui-modal-title'}
        tabIndex={-1}
        ref={panelRef}
      >
        <header className="ui-modal-head">
          <h2 id={labelledBy ?? 'ui-modal-title'} className="ui-modal-title">
            {title}
          </h2>
          <button type="button" className="ui-icon-btn" aria-label="Close" onClick={onClose}>
            <span aria-hidden="true">×</span>
          </button>
        </header>
        <div className="ui-modal-body">{children}</div>
        {footer ? <footer className="ui-modal-foot">{footer}</footer> : null}
      </div>
    </div>
  );
}

/**
 * The confirmation for anything that cannot be undone. The sentence describes
 * the consequence in plain words; the button says what it does ("Remove Daniel"),
 * never "OK".
 */
export function ConfirmationDialog({
  open,
  title,
  body,
  confirmLabel,
  cancelLabel = 'Keep it',
  destructive = true,
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  cancelLabel?: string;
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={title}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button variant={destructive ? 'danger' : 'primary'} onClick={onConfirm} disabled={busy}>
            {busy ? 'Working…' : confirmLabel}
          </Button>
        </>
      }
    >
      <p>{body}</p>
    </Modal>
  );
}
