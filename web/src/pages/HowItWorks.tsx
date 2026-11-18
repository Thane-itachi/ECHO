import { ButtonLink } from '../components/ui';

export default function HowItWorks() {
  return (
    <main className="public-main">
      <section className="hero is-short">
        <p className="eyebrow">How it works</p>
        <h1>Small things, kept properly</h1>
        <p className="hero-lede">
          ECHO is one place for the things you mean to remember. There are only a few moves to learn, and
          each one is a single button.
        </p>
      </section>

      <div className="prose">
        <section>
          <h2>1. Save a note</h2>
          <p>
            Open <strong>My notes</strong> and press <strong>New memory</strong>. Give it a short title and
            write the thing itself in your own words. There is no special format and nothing to fill in
            twice.
          </p>
          <p className="example">
            Title: Laptop lent to John
            <br />
            Note: John took the grey laptop home on Tuesday. He said he would bring it back on Friday.
          </p>
          <p>
            Every note gets a category, so the list can be filtered later: promise, person, date, money,
            or simply something to remember.
          </p>
        </section>

        <section>
          <h2>2. Say yes to what ECHO spots</h2>
          <p>
            If something you write sounds worth keeping, ECHO puts it in{' '}
            <strong>Things to check</strong> rather than saving it behind your back. You see the sentence it
            noticed, and you say yes or no.
          </p>
          <p>
            Yes saves it once. No makes it disappear. Nothing is ever kept on your behalf without that
            answer, and ECHO will not invent a note that you did not write.
          </p>
        </section>

        <section>
          <h2>3. Ask in your own words</h2>
          <p>
            <strong>Ask a question</strong> takes a normal sentence. ECHO looks through your notes and
            answers, then shows you the note it used so you can check it yourself.
          </p>
          <ul>
            <li>Who has my laptop?</li>
            <li>When did the plumber say he was coming?</li>
            <li>What did I promise Ngozi?</li>
          </ul>
          <p>
            If the answer is not in your notes, ECHO says so plainly instead of guessing. That is the whole
            point: a wrong answer you trust is worse than no answer.
          </p>
        </section>

        <section>
          <h2>4. Dates ring on the day</h2>
          <p>
            A note with a date in it can become a reminder. On the day itself the reminder appears in{' '}
            <strong>Reminders</strong>, and if you have turned on <strong>Email me reminders</strong> it
            arrives in your inbox too.
          </p>
          <p>
            Each reminder rings once. You can turn the email off at any time from the menu, and one click
            in the email turns it off as well.
          </p>
        </section>

        <section>
          <h2>5. Papers and pictures</h2>
          <p>
            Receipts, certificates and photographs go in <strong>Files</strong>. They are locked with your
            key before they are stored, exactly like your notes, and only you can open them again.
          </p>
        </section>

        <section>
          <h2>What ECHO will not do</h2>
          <ul>
            <li>It will not read your notes to anyone else, and no member of staff can open them.</li>
            <li>It will not save something you said no to.</li>
            <li>It will not make up an answer that your notes do not support.</li>
            <li>It will not sell, share or advertise anything to you.</li>
          </ul>
        </section>

        <section className="prose-actions">
          <ButtonLink variant="primary" to="/login?start=signup">
            Create an account
          </ButtonLink>
          <ButtonLink variant="secondary" to="/privacy">
            What is kept about me
          </ButtonLink>
          <ButtonLink variant="secondary" to="/help">
            Questions people ask
          </ButtonLink>
        </section>
      </div>
    </main>
  );
}
