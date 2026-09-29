// The product mark: a station-model circle (half filled, as on a synoptic plot) with one wind barb.
export function Mark({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 26 26" aria-hidden className="shrink-0">
      <circle cx="11" cy="15" r="7" fill="none" stroke="var(--ink)" strokeWidth="1.8" />
      <path d="M11 8 A7 7 0 0 0 11 22 Z" fill="var(--ink)" />
      <path d="M16 10 L23.5 2.5" stroke="var(--cobalt)" strokeWidth="1.8" strokeLinecap="square" />
      <path d="M23.5 2.5 L25.2 6.4 M20.8 5.2 L22.5 9.1" stroke="var(--cobalt)" strokeWidth="1.8" />
    </svg>
  );
}
