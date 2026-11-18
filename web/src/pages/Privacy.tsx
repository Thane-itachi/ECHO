import { Link } from 'react-router-dom';
import { ButtonLink } from '../components/ui';

export default function Privacy() {
  return (
    <main className="public-main">
      <section className="hero is-short">
        <p className="eyebrow">Your privacy</p>
        <h1>Your notes are yours</h1>
        <p className="hero-lede">
          A promise about privacy is only worth the machinery behind it. This is what ECHO does with what
          you write, in plain words and without the small print.
        </p>
      </section>

      <div className="prose">
        <section>
          <h2>Only you can read your notes</h2>
          <p>
            Every note, and every file, is locked on your own device before it is sent, using a key derived
            from your password. What is stored on the server is ciphertext: a wall of unreadable characters.
          </p>
          <p>
            This is not a setting you have to find and switch on. It is how the app is built. Even an
            administrator looking straight at the database sees nothing they can read. Your password is
            never stored, only a salted fingerprint of it, which cannot be turned back into the password.
          </p>
        </section>

        <section>
          <h2>What is kept about you</h2>
          <ul>
            <li>Your email address, so you can sign in and get a reminder.</li>
            <li>Your notes and files, locked as described above.</li>
            <li>When you signed in, and what you changed, so an unusual login can be spotted.</li>
            <li>Whether you want reminders by email, and whether you want a code at sign-in.</li>
          </ul>
          <p>That is the whole list. There is no profile, no advertising identifier and no tracking pixel.</p>
        </section>

        <section>
          <h2>Your searches stay yours</h2>
          <p>
            To find a note quickly, ECHO keeps a scrambled index of the words in your notes. The index is
            built with your key, so a search term cannot be read by anyone else and nobody can see what you
            were looking for.
          </p>
        </section>

        <section>
          <h2>What ECHO never does</h2>
          <ul>
            <li>It does not sell your information, and it has nothing to advertise to you.</li>
            <li>It does not let staff read your notes, because they cannot.</li>
            <li>It does not share your notes with another company to answer a question.</li>
            <li>It does not keep a copy of your notes after you delete your vault.</li>
          </ul>
        </section>

        <section>
          <h2>Taking everything away again</h2>
          <p>
            The menu has <strong>Delete my vault</strong>. It asks for your password, then removes your
            files first and your account and notes with it. There is no waiting period and no copy kept
            afterwards. You can also change your password from the same menu at any time; that signs you out
            of your other devices.
          </p>
        </section>

        <section>
          <h2>If something looks wrong</h2>
          <p>
            If you think someone else has been in your account, change your password from the menu straight
            away, then read <Link to="/help">the questions page</Link> for what to do next. Never send your
            password to anybody, including someone who says they run this site.
          </p>
        </section>

        <section className="prose-actions">
          <ButtonLink variant="secondary" to="/how-it-works">
            How ECHO works
          </ButtonLink>
          <ButtonLink variant="secondary" to="/help">
            Questions people ask
          </ButtonLink>
        </section>
      </div>
    </main>
  );
}
