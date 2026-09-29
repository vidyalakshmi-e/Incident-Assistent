// Provenance is never encoded by colour alone: every tag carries a line-style swatch (the same
// notation the causal chain uses: solid observed/original, dashed derived, dotted inferred) and a word.

const KINDS = {
  original: { color: "var(--ink)", stroke: "var(--ink)", dash: "", word: "original" },
  observed: { color: "var(--ink)", stroke: "var(--ink)", dash: "", word: "observed" },
  derived: { color: "var(--teal)", stroke: "var(--teal)", dash: "4 2.5", word: "derived" },
  synthetic: { color: "var(--amber-ink)", stroke: "var(--amber)", dash: "", word: "synthetic" },
  inferred: { color: "var(--violet)", stroke: "var(--violet)", dash: "0.1 3", word: "inferred" },
  missing: { color: "var(--gray)", stroke: "var(--gray)", dash: "", word: "missing" },
} as const;

export type ProvKind = keyof typeof KINDS;

export function provKind(tag: string | null | undefined): ProvKind {
  const t = (tag ?? "missing").split(/[\s(]/)[0].toLowerCase();
  return (t in KINDS ? t : "missing") as ProvKind;
}

export function Swatch({ kind, width = 16 }: { kind: ProvKind; width?: number }) {
  const k = KINDS[kind];
  if (kind === "missing") {
    return (
      <svg width={width} height="8" aria-hidden className="shrink-0">
        <rect x="1" y="2" width={width - 2} height="4" fill="none" stroke={k.stroke} strokeWidth="1" />
      </svg>
    );
  }
  return (
    <svg width={width} height="8" aria-hidden className="shrink-0">
      <line
        x1="1"
        y1="4"
        x2={width - 1}
        y2="4"
        stroke={k.stroke}
        strokeWidth={kind === "synthetic" ? 3 : 2}
        strokeDasharray={k.dash || undefined}
        strokeLinecap={kind === "inferred" ? "round" : "butt"}
      />
    </svg>
  );
}

export function ProvTag({
  tag,
  children,
  className = "",
}: {
  tag: string | null | undefined;
  children?: React.ReactNode;
  className?: string;
}) {
  const kind = provKind(tag);
  return (
    <span
      className={`cond inline-flex items-center gap-1.5 whitespace-nowrap text-[12.5px] font-semibold leading-none ${className}`}
      style={{ color: KINDS[kind].color }}
    >
      <Swatch kind={kind} />
      {children ?? KINDS[kind].word}
    </span>
  );
}

export function ProvLegend({ kinds = ["original", "derived", "synthetic", "inferred", "missing"] as ProvKind[] }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-x-4 gap-y-1.5">
      {kinds.map((k) => (
        <ProvTag key={k} tag={k} />
      ))}
    </span>
  );
}
