import { useId } from 'react';

/**
 * The ECHO mark.
 *
 * A pressed bookplate: a cream E on a leather plate, held by a hairline frame.
 * The plate has the faintest gradient so it reads as material rather than a
 * colour swatch, and the letter sits a touch above centre the way type does.
 *
 * Colour comes from CSS (--mark-tile-hi / --mark-tile-lo / --mark-ink) so one
 * component serves the sidebar, the sign-in panel, the loading screens and the
 * admin console, light or dark.
 */
export function EchoMark({ size = 30, className = '' }: { size?: number; className?: string }) {
  const raw = useId();
  const id = `echo-plate-${raw.replace(/[^a-zA-Z0-9-]/g, '')}`;

  return (
    <svg
      className={`echo-mark${className ? ` ${className}` : ''}`}
      width={size}
      height={size}
      viewBox="0 0 48 48"
      role="img"
      aria-label="ECHO"
    >
      <defs>
        <linearGradient id={id} x1="0.1" y1="0" x2="0.75" y2="1">
          <stop offset="0" stopColor="var(--mark-tile-hi)" />
          <stop offset="1" stopColor="var(--mark-tile-lo)" />
        </linearGradient>
      </defs>

      <rect width="48" height="48" rx="11.5" fill={`url(#${id})`} />
      <rect className="echo-mark-frame" x="4.2" y="4.2" width="39.6" height="39.6" rx="8" />

      <g className="echo-mark-strokes">
        <rect x="12.1" y="11" width="3.3" height="23" rx="1.65" />
        <rect x="12.1" y="11" width="22.8" height="3.3" rx="1.65" />
        {/* the middle arm runs a touch short: the optical correction a type designer makes */}
        <rect x="12.1" y="20.85" width="21.8" height="3.3" rx="1.65" />
        <rect x="12.1" y="30.7" width="22.8" height="3.3" rx="1.65" />
      </g>
    </svg>
  );
}

export default EchoMark;
