import { ButtonLink } from '../components/ui';

import NavIcon from '../components/NavIcon';
import { useAuth } from '../lib/auth';

const CARDS = [
  {
    icon: 'notes',
    title: 'Write it down once',
    body: 'Who borrowed the laptop. What you promised on Tuesday. The date the boiler gets serviced. One thing at a time, in your own words.',
  },
  {
    icon: 'ask',
    title: 'Ask for it back',
    body: 'Type a question the way you would say it out loud. ECHO answers from your own notes and shows you the note it used.',
  },
  {
    icon: 'bell',
    title: 'Let the date find you',
    body: 'A reminder rings on the day, and can arrive in your email as well. Nothing important slips past because you were busy.',
  },
];

const STEPS = [
  { title: 'Save a note', body: 'Type it, or let ECHO pick it out of something you said.' },
  { title: 'Say yes', body: 'Nothing is kept until you agree. Anything you say no to is gone.' },
  { title: 'Ask later', body: 'One box for questions. Plain answers, with the note they came from.' },
];

export default function Home() {
  const { user } = useAuth();

  return (
    <main className="public-main">
      <section className="hero">
        <p className="eyebrow">A private place to keep what matters</p>
        <h1>
          Never forget
          <br />
          <span className="hero-em">what matters.</span>
        </h1>
        <p className="hero-lede">
          The things you mean to remember are small and easy to lose. Write them down once and ask for them
          later, in your own words, from any phone or computer.
        </p>

        <div className="hero-actions">
          {user ? (
            <>
              <ButtonLink variant="primary" to="/dashboard">
                Open ECHO
              </ButtonLink>
              <ButtonLink variant="secondary" to="/ask">
                Ask a question
              </ButtonLink>
            </>
          ) : (
            <>
              <ButtonLink variant="primary" to="/login?start=signup">
                Create an account
              </ButtonLink>
              <ButtonLink variant="secondary" to="/login">
                I already have an account
              </ButtonLink>
            </>
          )}
        </div>

        <ul className="hero-promises">
          <li>Only you can read your notes. Not even an administrator can.</li>
          <li>Nothing is saved without you saying yes.</li>
          <li>The words are big on purpose, and there is a Text size control at the bottom of this page.</li>
        </ul>
      </section>

      <section className="public-cards" aria-label="What ECHO does">
        {CARDS.map((card) => (
          <article className="public-card" key={card.title}>
            <span className="public-card-icon">
              <NavIcon name={card.icon} />
            </span>
            <h2>{card.title}</h2>
            <p>{card.body}</p>
          </article>
        ))}
      </section>

      <section className="public-band">
        <div className="public-band-head">
          <h2>How it works, in three steps</h2>
          <ButtonLink variant="secondary" to="/how-it-works">
            Read it all
          </ButtonLink>
        </div>
        <ol className="steps">
          {STEPS.map((step) => (
            <li key={step.title}>
              <strong>{step.title}</strong>
              <span>{step.body}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="public-band is-quiet">
        <div className="public-band-head">
          <h2>Your notes stay yours</h2>
          <ButtonLink variant="secondary" to="/privacy">
            What is kept, and who can see it
          </ButtonLink>
        </div>
        <p className="public-lede">
          Every note is locked with your key before it is stored, so what sits on the server is unreadable
          to anyone but you. Searching stays yours too: nobody sees what you looked for.
        </p>
      </section>

      <section className="public-band is-quiet">
        <div className="public-band-head">
          <h2>Stuck, or not sure where to start?</h2>
          <ButtonLink variant="secondary" to="/help">
            Read the questions
          </ButtonLink>
        </div>
        <p className="public-lede">
          Plain answers about saving a note, asking a question, reminders, making the words bigger, and
          getting everything back out again.
        </p>
      </section>
    </main>
  );
}
