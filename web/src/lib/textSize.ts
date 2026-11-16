import { useEffect, useState } from 'react';

/**
 * The three text sizes. Every measurement in the stylesheet is in rem, so setting
 * one attribute on <html> grows the whole page: headings, buttons, labels and the
 * words inside them. The public pages use this too, so the choice you make before
 * signing in still holds once you are inside.
 */
export type TextSize = 'normal' | 'large' | 'largest';

export const TEXT_SIZES: { value: TextSize; label: string }[] = [
  { value: 'normal', label: 'Normal' },
  { value: 'large', label: 'Big' },
  { value: 'largest', label: 'Huge' },
];

export function savedTextSize(): TextSize {
  try {
    const saved = localStorage.getItem('echo-text-size');
    if (saved === 'large' || saved === 'largest') return saved;
  } catch {
    /* private mode: the choice simply does not survive a reload */
  }
  return 'normal';
}

export function useTextSize() {
  const [textSize, setTextSize] = useState<TextSize>(savedTextSize);

  useEffect(() => {
    document.documentElement.dataset.textsize = textSize;
    try {
      localStorage.setItem('echo-text-size', textSize);
    } catch {
      /* private mode */
    }
  }, [textSize]);

  return [textSize, setTextSize] as const;
}
