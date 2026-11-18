import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Link } from 'react-router-dom';

/**
 * The three buttons. One component, three ranks, so "which button" is a choice
 * about meaning rather than about CSS: primary for the one action a screen is
 * for, secondary for everything else, danger for anything that destroys.
 */
export type ButtonVariant = 'primary' | 'secondary' | 'danger';
export type ButtonSize = 'md' | 'sm';

interface Common {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
  icon?: ReactNode;
  block?: boolean;
  className?: string;
}

function classes({ variant = 'primary', size = 'md', block, className }: Common) {
  return ['ui-btn', `ui-btn--${variant}`, `ui-btn--${size}`, block ? 'ui-btn--block' : '', className ?? '']
    .filter(Boolean)
    .join(' ');
}

export function Button({
  variant,
  size,
  icon,
  block,
  className,
  children,
  ...rest
}: Common & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={classes({ variant, size, block, className, children })} {...rest}>
      {icon ? <span className="ui-btn-icon" aria-hidden="true">{icon}</span> : null}
      {children}
    </button>
  );
}

export function ButtonLink({
  to,
  variant,
  size,
  icon,
  block,
  className,
  children,
}: Common & { to: string }) {
  return (
    <Link to={to} className={classes({ variant, size, block, className, children })}>
      {icon ? <span className="ui-btn-icon" aria-hidden="true">{icon}</span> : null}
      {children}
    </Link>
  );
}

/** A square button for a single glyph. The label is required, never inferred. */
export function IconButton({
  label,
  children,
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; children: ReactNode }) {
  return (
    <button
      type="button"
      className={['ui-icon-btn', className ?? ''].filter(Boolean).join(' ')}
      aria-label={label}
      title={label}
      {...rest}
    >
      <span aria-hidden="true">{children}</span>
    </button>
  );
}
