import { clean, label, pct } from "@/lib/format";
import type { ChainAggLink } from "@/lib/types";

import { ProvTag } from "../ui/ProvTag";

const STAGES = ["trigger", "technical_failure", "symptom", "business_impact", "resolution", "outcome"];

const style: Record<string, { stroke: string; dash?: string; cap?: "round" }> = {
  observed: { stroke: "var(--ink)" },
  original: { stroke: "var(--ink)" },
  derived: { stroke: "var(--teal)", dash: "6 4" },
  inferred: { stroke: "var(--violet)", dash: "0.1 5", cap: "round" },
  none: { stroke: "var(--line-2)", dash: "1 4" },
};

function dominant(l: ChainAggLink | undefined): string {
  if (!l) return "none";
  if (l.tag) return l.tag;
  if (l.tags && Object.keys(l.tags).length) return Object.entries(l.tags).sort((a, b) => b[1] - a[1])[0][0];
  return "inferred";
}

function isEmpty(l: ChainAggLink | undefined) {
  return !l || !l.statement || /insufficient evidence/i.test(l.statement);
}

function Node({ tag, empty }: { tag: string; empty: boolean }) {
  const s = style[empty ? "none" : tag] ?? style.inferred;
  return (
    <circle
      cx="8"
      cy="8"
      r="6"
      fill={empty ? "var(--sheet)" : tag === "observed" || tag === "original" ? "var(--ink)" : "var(--sheet)"}
      stroke={s.stroke}
      strokeWidth="2"
      strokeDasharray={empty ? "1.5 2.5" : undefined}
    />
  );
}

function Seg({ tag }: { tag: string }) {
  const s = style[tag] ?? style.inferred;
  return <line x1="18" y1="8" x2="100%" y2="8" stroke={s.stroke} strokeWidth="2.2" strokeDasharray={s.dash} strokeLinecap={s.cap} />;
}

function Body({ l, stage }: { l: ChainAggLink | undefined; stage: string }) {
  const empty = isEmpty(l);
  const tag = dominant(l);
  return (
    <>
      <p className="annot text-ink-3">{label(stage)}</p>
      <p className={`mt-1 text-[14px] leading-snug ${empty ? "text-ink-3" : "font-semibold text-ink"}`}>
        {empty ? "Not established" : clean(l!.statement)}
      </p>
      {!empty && (
        <div className="mt-1.5 flex flex-col gap-1">
          {l!.tags ? (
            <span className="flex flex-wrap gap-x-3 gap-y-1">
              {Object.entries(l!.tags)
                .sort((a, b) => b[1] - a[1])
                .map(([t, v]) => (
                  <ProvTag key={t} tag={t}>
                    {t} {pct(v)}
                  </ProvTag>
                ))}
            </span>
          ) : (
            <ProvTag tag={tag} />
          )}
          {l!.share !== undefined && (
            <span className="text-[12.5px] text-ink-3">
              {pct(l!.share)} of {l!.support} with this stage
            </span>
          )}
          {l!.evidence && <span className="text-[12.5px] leading-snug text-ink-3">{clean(l!.evidence)}</span>}
        </div>
      )}
    </>
  );
}

/**
 * Causal chain drawn as a front: Trigger → Technical failure → Symptom → Business impact →
 * Resolution → Outcome. Each segment and node carries its link's evidence tag: solid observed,
 * dashed derived, dotted inferred. Inferred links never look like observed ones.
 */
export function FrontChain({ links }: { links: ChainAggLink[] }) {
  const by = new Map(links.map((l) => [l.stage, l]));
  return (
    <div>
      <ol className="grid grid-cols-6 gap-x-3">
        {STAGES.map((st, i) => {
          const l = by.get(st);
          const next = by.get(STAGES[i + 1]);
          return (
            <li key={st} className="min-w-0">
              <svg height="16" className="block w-full overflow-visible" aria-hidden>
                {i < STAGES.length - 1 && <Seg tag={isEmpty(next) ? "none" : dominant(next)} />}
                <Node tag={dominant(l)} empty={isEmpty(l)} />
              </svg>
              <div className="mt-2.5 pr-2">
                <Body l={l} stage={st} />
              </div>
            </li>
          );
        })}
      </ol>
      <p className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[12.5px] text-ink-3">
        Line style is the evidence tag:
        <ProvTag tag="observed" />
        <ProvTag tag="derived" />
        <ProvTag tag="inferred" />
      </p>
    </div>
  );
}
