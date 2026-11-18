import { useEffect, useState } from 'react';

/**
 * The theme is one attribute on <html>: data-theme="dark" | "light".
 *
 * Tokens.css answers the same names twice, so nothing else in the app knows a
 * theme exists. Dark is the default because it is the brand's own ground; a
 * person who prefers light gets it on this device, and the public pages follow
 * the same attribute so the choice holds before and after signing in.
 */
export type Theme = 'dark' | 'light';

const KEY = 'echo-theme';

export function savedTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    /* private mode: the choice simply does not survive a reload */
  }
  return 'dark';
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', theme === 'light' ? '#f7f8fc' : '#080d1b');
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(savedTheme);

  useEffect(() => {
    applyTheme(theme);
    try {
      localStorage.setItem(KEY, theme);
    } catch {
      /* the attribute still applies for this page */
    }
  }, [theme]);

  return [theme, setTheme] as const;
}
