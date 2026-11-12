/**
 * The ECHO mark: an E whose arms shorten and fade like a sound dying away.
 * One shape, three weights of voice: the letter reads at 16px, the fade reads
 * at 40px. Colour comes from CSS (--mark-tile / --mark-ink) so the same mark
 * can sit on paper, on ink, and in the admin console without a second file.
 */
export function EchoMark({ size = 30, className = '' }: { size?: number; className?: string }) {
  return (
    <svg
      className={`echo-mark${className ? ` ${className}` : ''}`}
      width={size}
      height={size}
      viewBox="0 0 40 40"
      role="img"
      aria-label="ECHO"
    >
      <rect className="echo-mark-tile" width="40" height="40" rx="11" />
      <g className="echo-mark-strokes">
        <rect x="11.4" y="10.9" width="3" height="18.2" rx="1.5" />
        <rect x="11.4" y="10.9" width="16.6" height="3" rx="1.5" />
        <rect x="11.4" y="18.5" width="15.2" height="3" rx="1.5" opacity="0.8" />
        <rect x="11.4" y="26.1" width="13.8" height="3" rx="1.5" opacity="0.62" />
      </g>
    </svg>
  );
}

export default EchoMark;
