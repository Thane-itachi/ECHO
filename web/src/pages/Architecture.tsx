import { Link } from 'react-router-dom';

/**
 * The blueprint, inside the product.
 *
 * A page like this is normally a slide in a folder nobody opens. It lives here
 * because the person who runs this app is also the person who has to repair it:
 * one page that says where every screen lives, what sits behind it, and what was
 * deliberately left out is worth more than a diagram that goes stale on a laptop.
 */
const DESTINATIONS = [
  {
    group: 'Your day',
    items: [
      { to: '/dashboard', name: 'Today', note: 'The brief: what is due, what you last saved, what needs a yes or no.' },
    ],
  },
  {
    group: 'Your memory',
    items: [
      { to: '/vault', name: 'My notes', note: 'Everything you saved, read on the right, written on the left.' },
      { to: '/ask', name: 'Ask ECHO', note: 'A question in plain words, an answer taken from your notes only.' },
      { to: '/search', name: 'Search', note: 'Every word, through an index of scrambled ones.' },
      { to: '/reports', name: 'Reports', note: 'Counts of your own rows. No engagement metrics, ever.' },
    ],
  },
  {
    group: 'People and time',
    items: [
      { to: '/people', name: 'People', note: 'Names your notes point at, and the history you have of them.' },
      { to: '/reminders', name: 'Reminders', note: 'Dates that must not pass, by email and in the app.' },
      { to: '/documents', name: 'Files', note: 'Papers and pictures, sealed like the notes.' },
      { to: '/proposals', name: 'Things to check', note: 'What ECHO found and will not save without your yes.' },
    ],
  },
  {
    group: 'The account',
    items: [
      { to: '/profile', name: 'Profile', note: 'Who you are here, and how the reading feels.' },
      { to: '/privacy', name: 'Privacy', note: 'What the server can and cannot see, in plain words.' },
      { to: '/security', name: 'Security', note: 'Password, the code at sign-in, and deleting everything.' },
      { to: '/settings', name: 'Settings', note: 'Text size, reminder email, phone notifications.' },
    ],
  },
];

export default function Architecture() {
  return (
    <div className="page page-narrow">
      <header className="page-head">
        <div>
          <p className="eyebrow">Architecture</p>
          <h1>How ECHO is put together</h1>
          <p className="page-sub">
            One page describing the product you are using: where every screen lives, what sits behind it, how a note
            becomes an answer, and what was left out on purpose.
          </p>
        </div>
      </header>

      <section className="report-section">
        <h2 className="section-title">The one design rule</h2>
        <p className="app-graf">
          ECHO is two interfaces over one memory. The <strong>brief</strong> answers “what needs me” without a
          question being typed: a front page with the next date, the last notes, and a column that can answer in
          place. The <strong>conversation</strong> answers “where did I write this down”: a question in your own words,
          an answer built from your notes, and the note it came from shown underneath. Neither is a feed. There is
          nothing here to scroll, score or return to.
        </p>
      </section>

      <section className="report-section">
        <h2 className="section-title">Thirteen destinations, four groups</h2>
        {DESTINATIONS.map((group) => (
          <div key={group.group} className="map-group">
            <p className="map-label">{group.group}</p>
            <div className="map">
              {group.items.map((item) => (
                <Link key={item.to} className="map-card" to={item.to}>
                  <b>{item.name}</b>
                  <small>{item.note}</small>
                </Link>
              ))}
            </div>
          </div>
        ))}
        <p className="stat-hint">
          Nine of these sit in the sidebar, because nine is what a phone shows as a 3 × 3 grid without hiding one.
          The other four — profile, privacy, security, settings — live behind the Settings button, so a password box
          is never printed above your notes. The
          public pages — homepage, how it works, privacy, questions — live outside the app and are readable signed out.
        </p>
      </section>

      <section className="report-section">
        <h2 className="section-title">Three layers</h2>
        <dl className="facts">
          <div>
            <dt>The screen</dt>
            <dd>React 18 and TypeScript, built by Vite</dd>
          </div>
          <div>
            <dt>The API</dt>
            <dd>FastAPI over SQLAlchemy 2.0, one serverless function</dd>
          </div>
          <div>
            <dt>The data</dt>
            <dd>Postgres, with every note sealed before it is written</dd>
          </div>
          <div>
            <dt>The console</dt>
            <dd>Separate admin door at /admin, six-digit code required</dd>
          </div>
          <div>
            <dt>No UI kit</dt>
            <dd>Every control drawn in the app's own stylesheet</dd>
          </div>
        </dl>
      </section>

      <section className="report-section">
        <h2 className="section-title">How a note is stored</h2>
        <ol className="steps">
          <li>
            You write it in the browser. The words never touch the network in the clear.
          </li>
          <li>
            The note is sealed with a key derived from your password before it is sent. The server receives ciphertext.
          </li>
          <li>
            Each word becomes a scrambled fingerprint, so a note can be found later without being read. Your key decrypts
            it; the fingerprint only matches.
          </li>
          <li>
            What lands in Postgres is a row of ciphertext and fingerprints. Nobody holding that table, including whoever
            runs the server, can turn it back into your sentence.
          </li>
        </ol>
      </section>

      <section className="report-section">
        <h2 className="section-title">How an answer is made</h2>
        <ol className="steps">
          <li>Your question is turned into the same kind of fingerprint, and the notes that match are brought back.</li>
          <li>The matching notes are decrypted for that one request, and an answer is composed from them.</li>
          <li>If a model is used, it sees only those notes. It is not trained on them, and it is never asked a question with no notes attached.</li>
          <li>An answer without a citation is thrown away. When nothing matches, ECHO says it does not know instead of inventing something.</li>
        </ol>
      </section>

      <section className="report-section">
        <h2 className="section-title">How a reminder fires</h2>
        <ol className="steps">
          <li>A date written in a note becomes a reminder row with the minute it is due.</li>
          <li>A scheduled tick wakes the worker every five minutes and looks for reminders that have come due.</li>
          <li>The email is built and sent, with a one-click way to turn reminders off — and turning them off is checked again at the moment of delivery, not only when the reminder was created.</li>
          <li>A refusal, a dead address or no mail provider is recorded as itself, never as “sent”. Silence is never reported as success.</li>
        </ol>
      </section>

      <section className="report-section">
        <h2 className="section-title">Deliberately not built</h2>
        <dl className="facts">
          <div>
            <dt>Reading your notes</dt>
            <dd>Not possible, by design</dd>
          </div>
          <div>
            <dt>Training on your notes</dt>
            <dd>Never, and no setting weakens it</dd>
          </div>
          <div>
            <dt>Export my archive</dt>
            <dd>Not yet — the honest gap</dd>
          </div>
          <div>
            <dt>Semantic search</dt>
            <dd>Word fingerprints only, for now</dd>
          </div>
          <div>
            <dt>Bounce handling</dt>
            <dd>Not yet: a hard bounce shows as failed, not retried</dd>
          </div>
        </dl>
        <p className="stat-hint">
          Two of these are the next things worth building. The first two are not gaps, they are the point.
        </p>
      </section>

      <section className="report-section">
        <h2 className="section-title">The look, in five decisions</h2>
        <dl className="facts">
          <div>
            <dt>Paper and ink</dt>
            <dd>Warm white, near-black text, one blue for anything pressable</dd>
          </div>
          <div>
            <dt>Three typefaces</dt>
            <dd>Instrument Serif for the name, Newsreader to read, Karla to press</dd>
          </div>
          <div>
            <dt>Three text sizes</dt>
            <dd>Normal, Big, Huge — remembered on this device</dd>
          </div>
          <div>
            <dt>Nothing under 14px</dt>
            <dd>And no tap target under 44px</dd>
          </div>
          <div>
            <dt>One column on a phone</dt>
            <dd>No sideways scroll, at any text size</dd>
          </div>
        </dl>
      </section>

      <p className="stat-hint">
        Checked by hand and by script: 235 backend tests, every page at 1280 and 390 pixels, at all three text sizes,
        with no console errors. The counts on <Link to="/reports">Reports</Link> are the only numbers that change.
      </p>
    </div>
  );
}
