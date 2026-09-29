import { clean, clock } from "@/lib/format";
import type { KbUpdate, Postmortem } from "@/lib/types";

import { IdLink } from "../ui/IdLink";
import { ProvTag } from "../ui/ProvTag";
import { Notice } from "../ui/States";

export function KbUpdateNotice({ k }: { k: KbUpdate }) {
  const added = k.status === "added_to_kb";
  return (
    <Notice tone={added ? "info" : "warn"} title={added ? "Added to the knowledge base" : `Knowledge base: ${clean(k.status).replace(/_/g, " ")}`}>
      Quality {k.quality.score.toFixed(2)} ({k.quality.tier}).{" "}
      {added ? (
        <>
          Assigned to family {k.family_id ? <IdLink id={k.family_id} /> : "n/a"}
          {k.family_created ? " (a new emerging family)" : ""}; it is now retrievable.
        </>
      ) : (
        clean(k.note)
      )}
    </Notice>
  );
}

export function PostmortemView({ p, kb }: { p: Postmortem; kb: KbUpdate | null }) {
  return (
    <article className="flex flex-col gap-7">
      {kb && <KbUpdateNotice k={kb} />}
      <div className="grid gap-x-10 gap-y-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-5">
          <div>
            <h4 className="annot text-ink-3">What happened</h4>
            <p className="mt-1.5 max-w-[65ch] text-[15.5px] leading-relaxed text-ink">{clean(p.what_happened)}</p>
          </div>
          <div>
            <h4 className="annot text-ink-3">Root cause</h4>
            <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[15px] text-ink">
              <span className="font-semibold">{clean(p.root_cause.statement) || "Insufficient evidence"}</span>
              {p.root_cause.tag && <ProvTag tag="inferred">{clean(p.root_cause.tag)}</ProvTag>}
            </p>
          </div>
          <div>
            <h4 className="annot text-ink-3">Final fix</h4>
            <p className="mt-1.5 text-[15px] font-semibold text-ink">{clean(p.final_fix?.step_description) || "None recorded"}</p>
          </div>
          <div>
            <h4 className="annot text-ink-3">Impact</h4>
            <p className="mt-1.5 flex flex-wrap items-center gap-x-3 text-[15px] text-ink">
              {clean(p.impact.business_impact)}, scope {clean(p.impact.impact_scope).toLowerCase()}
              {p.impact.provenance && <ProvTag tag={p.impact.provenance.business_impact} />}
            </p>
          </div>
          {p.preventive_recommendations.length > 0 && (
            <div>
              <h4 className="annot text-ink-3">Prevention</h4>
              <ul className="mt-1.5 flex flex-col gap-2">
                {p.preventive_recommendations.map((r) => (
                  <li key={r.recommendation} className="text-[14.5px] leading-relaxed text-ink">
                    {clean(r.recommendation)}
                    <span className="block text-[12.5px] text-ink-3">
                      {clean(r.framing)}; {clean(r.basis)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div>
          <h4 className="annot text-ink-3">Timeline</h4>
          <ol className="mt-2 flex flex-col">
            {p.timeline.map((t, i) => (
              <li key={i} className="grid grid-cols-[5rem_minmax(0,1fr)] gap-3 border-b border-line py-2 text-[14px]">
                <span className="font-mono text-[12px] text-ink-3">{clock(t.at)}</span>
                <span className="text-ink">{clean(t.event)}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </article>
  );
}
