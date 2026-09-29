import type { ReactNode } from "react";

import type { EvidenceChain } from "@/lib/types";

/**
 * The report as written, with every phrase the query-understanding lexicon matched marked in place
 * and its technical concept attached inline.
 */
export function AnnotatedReport({ qu }: { qu: EvidenceChain["query_understood"] }) {
  const text = qu.original;
  const hits = qu.matched_phrases
    .map((m) => {
      const i = text.toLowerCase().indexOf(m.phrase.toLowerCase());
      return { ...m, i };
    })
    .filter((m) => m.i >= 0)
    .sort((a, b) => a.i - b.i);

  const parts: ReactNode[] = [];
  let at = 0;
  for (const h of hits) {
    if (h.i < at) continue;
    parts.push(text.slice(at, h.i));
    parts.push(
      <span key={h.i}>
        <mark className="concept whitespace-nowrap text-ink">{text.slice(h.i, h.i + h.phrase.length)}</mark>
        <span className="annot ml-1 align-[1px] text-cobalt">{h.maps_to}</span>
      </span>,
    );
    at = h.i + h.phrase.length;
  }
  parts.push(text.slice(at));

  return (
    <div>
      <blockquote className="m-0 max-w-[62ch] text-[17px] leading-[1.75] text-ink">{parts}</blockquote>
      <div className="mt-4 flex flex-col gap-2 text-[13.5px] text-ink-2">
        {qu.technical_concepts.length > 0 && (
          <p>
            <span className="text-ink-3">Concepts added to the search: </span>
            {qu.technical_concepts.join(", ")}
          </p>
        )}
        <p className="num text-ink-3">
          Specificity {qu.specificity?.toFixed(2) ?? "n/a"}, {qu.is_vague ? "treated as vague" : "specific enough"}
          {qu.hints && Object.keys(qu.hints).length
            ? `. Hints: ${Object.entries(qu.hints)
                .map(([k, v]) => `${k} ${v}`)
                .join(", ")}`
            : ""}
          .
        </p>
      </div>
    </div>
  );
}
