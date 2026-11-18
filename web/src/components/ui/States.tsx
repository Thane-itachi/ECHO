import type { ReactNode } from 'react';

/**
 * The four things a page can be other than "ready": empty, loading, broken, or
 * waiting on a decision. Written once so a blank screen always explains itself.
 */
export function EmptyState({
  title,
  children,
  action,
  icon,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="ui-empty">
      {icon ? <div className="ui-empty-icon" aria-hidden="true">{icon}</div> : null}
      <p className="ui-empty-title">{title}</p>
      {children ? <div className="ui-empty-body">{children}</div> : null}
      {action ? <div className="ui-empty-action">{action}</div> : null}
    </div>
  );
}

export function ErrorState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="ui-error" role="alert">
      <p className="ui-error-title">That did not work</p>
      <p className="ui-error-body">{message}</p>
      {action ? <div className="ui-error-action">{action}</div> : null}
    </div>
  );
}

export function Skeleton({ width = '100%', height = 12 }: { width?: string | number; height?: number }) {
  return <span className="ui-skeleton" style={{ width, height }} aria-hidden="true" />;
}

export function SkeletonRows({ rows = 3 }: { rows?: number }) {
  return (
    <div className="ui-skeleton-rows" role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} width={index % 2 ? '72%' : '100%'} />
      ))}
    </div>
  );
}
