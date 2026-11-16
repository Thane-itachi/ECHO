/**
 * One plain picture per place in the app.
 *
 * A word alone assumes the reader can read it. A word with a picture of the thing
 * does not: a notebook for what you saved, a question mark for asking, a bell for
 * what is about to ring. Drawn rather than imported so they weigh nothing and share
 * the text colour, including when the row is selected.
 */
const PATHS: Record<string, string> = {
  // a notebook, spine on the left
  notes: 'M6 3h11a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm2 0v18M11 8h5M11 12h5M11 16h3',
  // a question mark in a speech bubble
  ask: 'M21 12a8 8 0 1 1-3.2-6.4M9.8 9.2a2.2 2.2 0 1 1 3.3 1.9c-.7.4-1.1 1-1.1 1.8v.4m0 3.4h.01',
  // two people
  people:
    'M8 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm8.5 1a2.8 2.8 0 1 0 0-5.6M2.5 20a5.5 5.5 0 0 1 11 0M15 14.4a4.7 4.7 0 0 1 6.5 4.3',
  // a checklist
  check: 'M4 6h3l1.5 1.5L12 4M4 12h3l1.5 1.5L12 10M4 18h3l1.5 1.5L12 16M15 6h5M15 12h5M15 18h5',
  // a bell
  bell: 'M18 8a6 6 0 1 0-12 0c0 5-2 6-2 6h16s-2-1-2-6M10.3 20a2 2 0 0 0 3.4 0',
  // a folder
  files: 'M3 7a2 2 0 0 1 2-2h4l2 2.5h6a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z',
  // a calendar page, for the day you are in
  today: 'M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6Zm0 4h16M8 3v3M16 3v3M8 14h3',
  // a magnifying glass
  search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm5.7-.3L21 21',
  // three bars on a baseline
  chart: 'M4 4v16h16M8 17v-5M12 17V8M16 17v-8M20 17v-3',
  // one person
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-8 8a8 8 0 0 1 16 0',
  // a shield with a tick
  shield: 'M12 3l8 3v6c0 5-3.4 8.3-8 9-4.6-.7-8-4-8-9V6l8-3Zm-3 8.7 2.2 2.2 4.3-4.4',
  // a cog
  gear: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm8.5-3a8.5 8.5 0 0 0-.1-1.3l1.9-1.5-1.9-3.3-2.2 1a8.6 8.6 0 0 0-2.2-1.3L15.6 3h-3.8l-.4 2.6a8.6 8.6 0 0 0-2.2 1.3l-2.2-1-1.9 3.3 1.9 1.5a8.5 8.5 0 0 0 0 2.6l-1.9 1.5 1.9 3.3 2.2-1a8.6 8.6 0 0 0 2.2 1.3l.4 2.6h3.8l.4-2.6a8.6 8.6 0 0 0 2.2-1.3l2.2 1 1.9-3.3-1.9-1.5c.06-.43.1-.86.1-1.3Z',
};

export default function NavIcon({ name }: { name: string }) {
  const path = PATHS[name] ?? PATHS.notes;
  return (
    <svg
      className="nav-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.9}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={path} />
    </svg>
  );
}
