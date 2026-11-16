import { useState } from 'react';
import { Link } from 'react-router-dom';

import NotificationToggle from '../components/NotificationToggle';
import { ApiError } from '../lib/api';
import { errorMessage, useAuth } from '../lib/auth';
import { TEXT_SIZES, useTextSize } from '../lib/textSize';

/**
 * Everything that changes how ECHO behaves, in one place and in plain words.
 *
 * Only switches that do something real are here: the reminder email, the phone
 * notifications, and the text size. A settings page full of toggles that do
 * nothing is worse than a short one.
 */
export default function Settings() {
  const { user, setReminderEmail } = useAuth();
  const [textSize, setTextSize] = useTextSize();
  const [reminderBusy, setReminderBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function toggleReminderEmail(enabled: boolean) {
    setReminderBusy(true);
    setNote(null);
    try {
      await setReminderEmail(enabled);
      setNote(enabled ? 'Reminder email is on.' : 'Reminder email is off. Reminders still appear in the app.');
    } catch (caught) {
      setNote(caught instanceof ApiError ? caught.message : errorMessage(caught));
    } finally {
      setReminderBusy(false);
    }
  }

  return (
    <div className="page page-narrow">
      <header className="page-head">
        <div>
          <p className="eyebrow">Settings</p>
          <h1>How ECHO behaves</h1>
          <p className="page-sub">Saved as you change them. There is no save button to forget to press.</p>
        </div>
      </header>

      <section className="report-section">
        <h2 className="section-title">Reading</h2>
        <div className="set-list">
          <div className="set-row">
            <span>
              <b>Text size</b>
              <small>The whole app, remembered on this device. The menu page has the same three buttons.</small>
            </span>
            <span className="text-size-buttons">
              {TEXT_SIZES.map((size) => (
                <button
                  key={size.value}
                  type="button"
                  aria-pressed={textSize === size.value}
                  onClick={() => setTextSize(size.value)}
                >
                  {size.label}
                </button>
              ))}
            </span>
          </div>
        </div>
      </section>

      <section className="report-section">
        <h2 className="section-title">Being reminded</h2>
        <div className="set-list">
          <label className="set-row">
            <span>
              <b>Email me reminders</b>
              <small>A reminder lands in your inbox when it comes due. Reminders always appear in the app.</small>
            </span>
            <span className="switch">
              <input
                type="checkbox"
                checked={user?.reminder_email_enabled ?? true}
                disabled={reminderBusy}
                onChange={(event) => void toggleReminderEmail(event.target.checked)}
              />
              <span />
            </span>
          </label>
        </div>
        {note ? <p className="sidebar-note">{note}</p> : null}
        <div className="notify-block">
          <NotificationToggle />
        </div>
      </section>

      <section className="report-section">
        <h2 className="section-title">Your account</h2>
        <div className="sidebar-links profile-links">
          <Link className="ghost-button" to="/profile">
            Profile
          </Link>
          <Link className="ghost-button" to="/security">
            Password and security
          </Link>
          <Link className="ghost-button" to="/privacy">
            How privacy works
          </Link>
          <Link className="ghost-button" to="/architecture">
            How ECHO is built
          </Link>
          <Link className="ghost-button" to="/help">
            Questions
          </Link>
        </div>
      </section>

      <section className="report-section">
        <h2 className="section-title">How answers are made</h2>
        <dl className="facts">
          <div>
            <dt>Where answers come from</dt>
            <dd>Your notes, and only your notes</dd>
          </div>
          <div>
            <dt>When nothing matches</dt>
            <dd>ECHO says so instead of guessing</dd>
          </div>
          <div>
            <dt>Training on your notes</dt>
            <dd>Never</dd>
          </div>
        </dl>
        <p className="stat-hint">
          These are not settings. They are how the app is built, and there is no switch that weakens them.
        </p>
      </section>
    </div>
  );
}
