import { useEffect } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';

import { EchoMark } from './Logo';
import { useAuth } from '../lib/auth';
import { TEXT_SIZES, useTextSize } from '../lib/textSize';

/* The four pages anyone can read, signed in or not. Same words as the menu
   inside the app, because "privacy policy" is not a phrase that helps anybody. */
const PAGES = [
  { to: '/', label: 'Home', title: 'ECHO. Never forget what matters.' },
  { to: '/how-it-works', label: 'How it works', title: 'How ECHO works' },
  { to: '/privacy', label: 'Your privacy', title: 'Your privacy. ECHO' },
  { to: '/help', label: 'Questions', title: 'Questions people ask. ECHO' },
];

/** Header, footer and the text size control, shared by every public page. */
export default function PublicLayout() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const [textSize, setTextSize] = useTextSize();

  // A link at the bottom of a long page should open the next page at its top,
  // and the tab should say which page you are on.
  useEffect(() => {
    window.scrollTo(0, 0);
    const page = PAGES.find((entry) => entry.to === pathname);
    document.title = page ? page.title : 'ECHO';
  }, [pathname]);

  return (
    <div className="public-shell">
      <header className="public-header">
        <Link className="public-brand" to="/" aria-label="ECHO home">
          <EchoMark size={32} />
          <span className="public-wordmark">ECHO</span>
        </Link>

        <nav className="public-links" aria-label="Pages anyone can read">
          {PAGES.map((page) => (
            <NavLink key={page.to} to={page.to} end={page.to === '/'}>
              {page.label}
            </NavLink>
          ))}
        </nav>

        <div className="public-actions">
          {user ? (
            <Link className="primary-button" to="/vault">
              Open my notes
            </Link>
          ) : (
            <>
              <Link className="ghost-button" to="/login">
                Sign in
              </Link>
              <Link className="primary-button" to="/login?start=signup">
                Create an account
              </Link>
            </>
          )}
        </div>
      </header>

      <Outlet />

      <footer className="public-footer">
        <div className="public-footer-inner">
          <div className="public-footer-brand">
            <EchoMark size={26} />
            <span>ECHO. Never forget what matters.</span>
          </div>

          <nav aria-label="More pages">
            {PAGES.map((page) => (
              <NavLink key={page.to} to={page.to} end={page.to === '/'}>
                {page.label}
              </NavLink>
            ))}
            <Link to={user ? '/vault' : '/login'}>{user ? 'My notes' : 'Sign in'}</Link>
          </nav>

          <div className="text-size-inline">
            <span className="text-size-label">Text size</span>
            <div className="text-size-inline-buttons">
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
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
