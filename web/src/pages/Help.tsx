import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

const QUESTIONS: { q: string; a: ReactNode }[] = [
  {
    q: 'What is ECHO for?',
    a: (
      <>
        Keeping the small things you mean to remember: who borrowed what, what you promised, when the
        boiler gets serviced. You write them once and ask for them later in your own words.
      </>
    ),
  },
  {
    q: 'How do I save something?',
    a: (
      <>
        Press <strong>My notes</strong> in the menu, then <strong>New memory</strong>. A short title and the
        thing itself is enough. Press <strong>Save</strong> and it is locked and stored.
      </>
    ),
  },
  {
    q: 'What are “Things to check” for?',
    a: (
      <>
        When ECHO spots something worth keeping in what you wrote, it waits there for your answer instead of
        saving it quietly. Say yes and it becomes a note. Say no and it is gone.
      </>
    ),
  },
  {
    q: 'How do I ask a question?',
    a: (
      <>
        Press <strong>Ask a question</strong> and type it the way you would say it: “Who has my laptop?”.
        The answer comes with the note it came from, so you can check it. If your notes do not hold the
        answer, ECHO says so rather than guessing.
      </>
    ),
  },
  {
    q: 'Why did a reminder not reach my email?',
    a: (
      <>
        Look for <strong>Email me reminders</strong> in the menu and make sure it is ticked. Reminders still
        appear in <strong>Reminders</strong> whether email is on or off, so nothing is lost. If it is ticked
        and still nothing arrives, the email may be in your spam folder.
      </>
    ),
  },
  {
    q: 'How do I make the words bigger?',
    a: (
      <>
        Inside the app, open <strong>Settings</strong> beside the ECHO name and choose Normal, Big or Huge.
        On the pages you are reading now, the same three buttons are at the bottom of the page. Your choice
        is remembered on the device you are using.
      </>
    ),
  },
  {
    q: 'I forgot my password.',
    a: (
      <>
        On the sign-in page press <strong>Forgot your password</strong>. A six digit code goes to your email
        address, and that code lets you set a new password. Nobody at ECHO can read your password or set it
        for you.
      </>
    ),
  },
  {
    q: 'Can I get my notes out, or delete them?',
    a: (
      <>
        The menu has <strong>Delete my vault</strong>, which asks for your password and then removes your
        files, your notes and your account. If you want a copy of something first, open the note and copy
        the text: because only you can read your notes, only you can take them out.
      </>
    ),
  },
  {
    q: 'Can the person who runs this site read my notes?',
    a: (
      <>
        No. Notes and files are locked with your key before they are stored, so what sits on the server
        cannot be read by an administrator either. The <Link to="/privacy">privacy page</Link> explains the
        machinery.
      </>
    ),
  },
  {
    q: 'Where do I start?',
    a: (
      <>
        Write one note today, the one thing you are most likely to forget. Then try asking for it back
        tomorrow. That is the whole habit. <Link to="/login?start=signup">Create an account</Link> if you
        have not already.
      </>
    ),
  },
];

export default function Help() {
  return (
    <main className="public-main">
      <section className="hero is-short">
        <p className="eyebrow">Questions people ask</p>
        <h1>Plain answers</h1>
        <p className="hero-lede">
          Press a question to read the answer. If yours is not here, the person who set up your account can
          help, and everything about privacy is on its own page.
        </p>
      </section>

      <div className="faq">
        {QUESTIONS.map((item) => (
          <details key={item.q}>
            <summary>{item.q}</summary>
            <p>{item.a}</p>
          </details>
        ))}
      </div>

      <div className="prose prose-actions">
        <Link className="ghost-button" to="/how-it-works">
          How ECHO works
        </Link>
        <Link className="ghost-button" to="/privacy">
          Your privacy
        </Link>
        <Link className="primary-button" to="/login">
          Sign in
        </Link>
      </div>
    </main>
  );
}
