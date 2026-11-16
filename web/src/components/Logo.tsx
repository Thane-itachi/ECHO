import { useId } from 'react';

/**
 * The ECHO mark.
 *
 * A sound coming back: a dot, and three rings leaving it. It replaces the
 * pressed-leather E on 16 Nov 2026, and it says the product's own name rather
 * than its initial. The rings are concentric and evenly spaced so the shape
 * still reads at 20 pixels in a browser tab; the hairline frame is the
 * bookplate the app was built in, kept for continuity.
 *
 * Colour comes from CSS (--mark-tile-hi / --mark-tile-lo / --mark-ink) so one
 * component serves the sidebar, the sign-in panel, the loading screens and the
 * admin console.
 */
const RINGS = [
  { r: 7.5, x: 19.97, y1: 17.64, y2: 30.36 },
  { r: 13, x: 22.89, y1: 12.98, y2: 35.02 },
  { r: 18.5, x: 25.8, y1: 8.31, y2: 39.69 },
];

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

      <g className="echo-mark-rings">
        {RINGS.map((ring) => (
          <path
            key={ring.r}
            d={`M${ring.x} ${ring.y1}A${ring.r} ${ring.r} 0 0 1 ${ring.x} ${ring.y2}`}
          />
        ))}
      </g>
      <circle className="echo-mark-dot" cx="16" cy="24" r="3.2" />
    </svg>
  );
}

export default EchoMark;
