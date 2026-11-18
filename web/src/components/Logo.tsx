import { useId } from 'react';

/**
 * The ECHO mark, as the owner drew it.
 *
 * Three concentric arcs open to the upper right, four beads resting where they
 * end, and a gradient that runs from blue at the top left to violet at the
 * bottom right. No plate behind it: the arcs carry the shape on their own, so
 * the same drawing sits on the navy rail, on paper, on the sign-in panel and in
 * a browser tab.
 *
 * Geometry is measured from the owner's artwork (arcs at radii 103, 80 and 53
 * around a shared centre, a 115 degree opening centred 40 degrees above the
 * horizon). Colour comes from CSS tokens so light and dark stay legible.
 */
const C = 108;

/* Each ring, with the angles where it stops. Measured from the owner's artwork:
   all three open toward the right (a 144 degree mouth on the
   horizon), and the mouth rotates a couple of degrees as the rings get smaller. */
const ARCS = [
  { r: 103, from: 72, to: -72 },
  { r: 80, from: 70, to: -66 },
  { r: 53, from: 66, to: -76 },
];

function point(r: number, deg: number) {
  const rad = (deg * Math.PI) / 180;
  return { x: C + r * Math.cos(rad), y: C + r * Math.sin(rad) };
}

function arcPath({ r, from, to }: { r: number; from: number; to: number }) {
  const a = point(r, from);
  const b = point(r, to);
  return `M${a.x.toFixed(2)} ${a.y.toFixed(2)}A${r} ${r} 0 1 1 ${b.x.toFixed(2)} ${b.y.toFixed(2)}`;
}

/* Four beads, one at each end of the two outer rings, nudged a few degrees past
   the cap so they read as separate bodies rather than thick line ends. */
const BEAD_GAP = 8;
const BEADS = ARCS.slice(0, 2).flatMap(({ r, from, to }) => [
  point(r, from + BEAD_GAP),
  point(r, to - BEAD_GAP),
]);

export function EchoMark({ size = 30, className = '' }: { size?: number; className?: string }) {
  const raw = useId();
  const id = `echo-arcs-${raw.replace(/[^a-zA-Z0-9-]/g, '')}`;
  /* The drawing is measured at 216 units. At 30px a faithful 6.5-unit stroke
     lands under one device pixel and the mark turns to dust, so the line thickens
     as the mark shrinks. Large sizes keep the artwork's own weight. */
  const stroke = Math.max(6.5, 345 / size);
  const bead = stroke * 1.35;

  return (
    <svg
      className={`echo-mark${className ? ` ${className}` : ''}`}
      width={size}
      height={size}
      viewBox="0 0 216 216"
      role="img"
      aria-label="ECHO"
    >
      <defs>
        <linearGradient id={id} x1="0.12" y1="0.04" x2="0.88" y2="0.96">
          <stop offset="0" stopColor="var(--mark-arc-from)" />
          <stop offset="1" stopColor="var(--mark-arc-to)" />
        </linearGradient>
      </defs>

      <g fill="none" stroke={`url(#${id})`} strokeWidth={stroke.toFixed(2)} strokeLinecap="round">
        {ARCS.map((arc) => (
          <path key={arc.r} d={arcPath(arc)} />
        ))}
      </g>
      <g fill={`url(#${id})`}>
        {BEADS.map((b, i) => (
          <circle key={i} cx={b.x.toFixed(2)} cy={b.y.toFixed(2)} r={bead.toFixed(2)} />
        ))}
      </g>
    </svg>
  );
}

/** Mark and word, the way the owner's lockup sets them. */
export function EchoLogo({
  size = 32,
  tagline = false,
  className = '',
}: {
  size?: number;
  tagline?: boolean;
  className?: string;
}) {
  return (
    <span className={`echo-lockup${className ? ` ${className}` : ''}`}>
      <EchoMark size={size} />
      <span className="echo-lockup-text">
        <span className="echo-wordmark" style={{ fontSize: `${Math.round(size * 0.86)}px` }}>
          ECHO
        </span>
        {tagline ? (
          <span className="echo-tagline" style={{ fontSize: `${Math.max(10, Math.round(size * 0.26))}px` }}>
            Remember. Organize. Thrive.
          </span>
        ) : null}
      </span>
    </span>
  );
}

export default EchoMark;
