import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from 'react';

/**
 * One field component, so every input in the product has the same label
 * placement, the same help text, the same error line and a real <label for>.
 * An input without a visible label is a bug, not a style choice.
 */
interface FieldShell {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  hideLabel?: boolean;
  children: (id: string, describedBy: string | undefined) => ReactNode;
}

function FieldShell({ label, hint, error, hideLabel, children }: FieldShell) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined;
  return (
    <div className={['ui-field', error ? 'has-error' : ''].filter(Boolean).join(' ')}>
      <label className={hideLabel ? 'ui-visually-hidden' : 'ui-field-label'} htmlFor={id}>
        {label}
      </label>
      {children(id, describedBy)}
      {hint && !error ? (
        <p className="ui-field-hint" id={hintId}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className="ui-field-error" id={errorId} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function TextInput({
  label,
  hint,
  error,
  hideLabel,
  ...rest
}: Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> & {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  hideLabel?: boolean;
}) {
  return (
    <FieldShell label={label} hint={hint} error={error} hideLabel={hideLabel}>
      {(id, describedBy) => (
        <input
          id={id}
          className="ui-input"
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          {...rest}
        />
      )}
    </FieldShell>
  );
}

export function SelectInput({
  label,
  hint,
  error,
  hideLabel,
  children,
  ...rest
}: Omit<SelectHTMLAttributes<HTMLSelectElement>, 'id'> & {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  hideLabel?: boolean;
}) {
  return (
    <FieldShell label={label} hint={hint} error={error} hideLabel={hideLabel}>
      {(id, describedBy) => (
        <select id={id} className="ui-select" aria-describedby={describedBy} {...rest}>
          {children}
        </select>
      )}
    </FieldShell>
  );
}

/** The search box, with its own magnifier and a clear button that a keyboard can reach. */
export function SearchBar({
  value,
  onChange,
  placeholder = 'Search',
  label = 'Search',
  onClear,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  label?: string;
  onClear?: () => void;
}) {
  return (
    <div className="ui-search">
      <svg viewBox="0 0 20 20" aria-hidden="true" className="ui-search-icon">
        <circle cx="9" cy="9" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
        <path d="M13 13l4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
      <label className="ui-visually-hidden" htmlFor="ui-search-input">
        {label}
      </label>
      <input
        id="ui-search-input"
        type="search"
        className="ui-search-input"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
      {value ? (
        <button
          type="button"
          className="ui-search-clear"
          aria-label="Clear search"
          onClick={() => {
            onChange('');
            onClear?.();
          }}
        >
          ×
        </button>
      ) : null}
    </div>
  );
}
