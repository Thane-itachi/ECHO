import type { ReactNode } from 'react';

/**
 * Card is the one container the product uses. No second card style: a card is a
 * titled surface with a hairline border, and anything that needs to stand out
 * says so with a Badge or an accent rule rather than a different box.
 */
export function Card({
  title,
  action,
  children,
  tone = 'plain',
  className,
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  tone?: 'plain' | 'accent' | 'quiet';
  className?: string;
}) {
  return (
    <section className={['ui-card', `ui-card--${tone}`, className ?? ''].filter(Boolean).join(' ')}>
      {title || action ? (
        <header className="ui-card-head">
          {title ? <h2 className="ui-card-title">{title}</h2> : null}
          {action ? <div className="ui-card-action">{action}</div> : null}
        </header>
      ) : null}
      <div className="ui-card-body">{children}</div>
    </section>
  );
}

export type BadgeTone = 'neutral' | 'brand' | 'success' | 'warning' | 'danger' | 'info';

export function Badge({
  children,
  tone = 'neutral',
  dot,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  dot?: boolean;
}) {
  return (
    <span className={`ui-badge ui-badge--${tone}`}>
      {dot ? <span className="ui-badge-dot" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

/** A person, as a circle with initials. No image upload exists yet, so this is the whole avatar. */
export function Avatar({ name, size = 36 }: { name: string; size?: number }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
  return (
    <span className="ui-avatar" style={{ width: size, height: size, fontSize: size * 0.36 }} aria-hidden="true">
      {initials || '?'}
    </span>
  );
}

export function Divider() {
  return <hr className="ui-divider" />;
}
