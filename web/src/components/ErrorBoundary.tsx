import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * A white screen tells nobody anything. If a page throws, show what happened and
 * offer a way back, instead of leaving the person staring at an empty document.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Kept in the console for a developer, and on screen for everyone else.
    console.error('ECHO page error', error, info.componentStack);
  }

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="splash">
        <div className="wordmark">ECHO</div>
        <h1>This page failed to load</h1>
        <p className="muted">{error.message}</p>
        <div className="form-actions">
          <button type="button" className="primary-button" onClick={() => this.setState({ error: null })}>
            Try again
          </button>
          <a className="ghost-button" href="/vault">
            Back to the vault
          </a>
        </div>
      </div>
    );
  }
}
