import { clean, fixed, pct } from "@/lib/format";
import type { Resolution } from "@/lib/types";

import { IdLink } from "../ui/IdLink";

function Bar({ value }: { value: number | null }) {
  const w = value === null ? 0 : Math.max(2, Math.min(100, value * 100));
  return (
    <div className="flex items-center gap-3">
      <div className="relative h-2 w-full min-w-0 overflow-hidden bg-paper-2" aria-hidden>
        <div className="absolute inset-y-0 left-0 bg-cobalt" style={{ width: `${w}%` }} />
      </div>
      <span className="num w-[3.2rem] shrink-0 text-right text-[15px] font-semibold text-ink">{value === null ? "n/a" : pct(value, value < 0.1 ? 1 : 0)}</span>
    </div>
  );
}

/**
 * The five best-supported solutions for the report, each with the confidence the ranker computed from
 * evidence (relevance x agreement x provenance). The LLM only judges relevance and wording; it never sets a score.
 */
export function TopSolutions({ items, filtered = 0 }: { items: Resolution[]; filtered?: number }) {
  if (items.length === 0) return null;
  return (
    <div>
      <ol className="border-t border-line-2">
        {items.map((r, i) => (
          <li key={r.strategy_key} className="grid grid-cols-[2rem_minmax(0,1fr)_15rem] items-start gap-x-5 gap-y-1 border-b border-line py-3.5">
            <span className="num display pt-px text-[20px] leading-none font-bold text-ink-3">{i + 1}</span>
            <div className="min-w-0">
              <p className="text-[15.5px] leading-snug font-semibold [overflow-wrap:anywhere] text-ink">{clean(r.action)}</p>
              <p className="mt-1 line-clamp-2 text-[13.5px] leading-snug [overflow-wrap:anywhere] text-ink-2">
                {r.guidance?.reason ? `${clean(r.guidance.reason)} ` : ""}
                <span className="text-ink-3">
                  Backed by {r.supporting_incidents.length} past {r.supporting_incidents.length === 1 ? "incident" : "incidents"}, strategy{" "}
                </span>
                <IdLink id={r.strategy_key} />
              </p>
            </div>
            <div className="pt-0.5">
              <Bar value={r.confidence} />
              {r.confidence_components && (
                <p className="num mt-1 text-right text-[12px] text-ink-3">
                  relevance {fixed(r.confidence_components.max_relevance)} &times; agreement {fixed(r.confidence_components.agreement)}
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>
      <p className="mt-3 max-w-[80ch] text-[12.5px] leading-snug text-ink-3">
        Confidence is computed from the evidence, not guessed by the language model.
        {filtered > 0 && ` ${filtered} more ${filtered === 1 ? "candidate was" : "candidates were"} left out because they do not fit this report.`}
      </p>
    </div>
  );
}
