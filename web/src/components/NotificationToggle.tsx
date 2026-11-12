import { useEffect, useState } from 'react';

import { sendTestNotification } from '../lib/api';
import {
  disableNotifications,
  enableNotifications,
  notificationState,
  type NotificationState,
} from '../lib/notifications';

/**
 * "Notify me on this device".
 *
 * Every branch says what is true and what the user can do about it, because the two
 * failure modes here (permission blocked in browser settings, iPhone needing the site
 * on the Home Screen) look identical to a dead button otherwise.
 */
export default function NotificationToggle() {
  const [state, setState] = useState<NotificationState | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    notificationState()
      .then((next) => {
        if (alive) setState(next);
      })
      .catch(() => {
        if (alive) setState({ kind: 'off' });
      });
    return () => {
      alive = false;
    };
  }, []);

  async function toggle(on: boolean) {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const next = on ? await enableNotifications() : await disableNotifications();
      setState(next);
      setNote(on ? 'This device will now be notified.' : 'This device will stay quiet.');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'That did not work.');
      setState(await notificationState().catch(() => null));
    } finally {
      setBusy(false);
    }
  }

  async function sendTest() {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const result = await sendTestNotification();
      if (result.sent > 0) {
        setNote(`Sent to ${result.sent} device${result.sent === 1 ? '' : 's'}. Check your notifications.`);
      } else if (result.pruned > 0) {
        setNote('That device had gone away, so it was removed. Turn notifications on again.');
        setState(await notificationState().catch(() => null));
      } else {
        setError('The push service refused it. Try again in a moment.');
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not send a test notification.');
    } finally {
      setBusy(false);
    }
  }

  if (state === null) return null;

  if (state.kind === 'ios-not-installed') {
    return (
      <p className="sidebar-note">
        To get notifications on this iPhone, add ECHO to your Home Screen (Share, then Add to Home Screen) and
        open it from there. Apple only allows it for installed web apps.
      </p>
    );
  }

  if (state.kind === 'unsupported') {
    return <p className="sidebar-note">{state.detail}</p>;
  }

  if (state.kind === 'server-off') {
    return (
      <p className="sidebar-note">
        Notifications are not switched on for this installation: the server has no signing key yet.
      </p>
    );
  }

  if (state.kind === 'blocked') {
    return (
      <p className="sidebar-note">
        Notifications are blocked for this site. Allow them in your browser's site settings, then reload.
      </p>
    );
  }

  const on = state.kind === 'on';

  return (
    <div className="notify-block">
      <label className="sidebar-toggle">
        <input type="checkbox" checked={on} disabled={busy} onChange={(event) => void toggle(event.target.checked)} />
        <span>
          Notify me on this device
          <small>
            {on
              ? `On${state.devices > 1 ? ` and on ${state.devices - 1} other device${state.devices > 2 ? 's' : ''}` : ''}. A reminder reaches you with ECHO closed.`
              : 'A reminder reaches you even with ECHO closed.'}
          </small>
        </span>
      </label>
      {on ? (
        <button type="button" className="ghost-button notify-test" disabled={busy} onClick={() => void sendTest()}>
          Send a test notification
        </button>
      ) : null}
      {note ? <p className="sidebar-note">{note}</p> : null}
      {error ? <p className="sidebar-note notify-error">{error}</p> : null}
    </div>
  );
}
