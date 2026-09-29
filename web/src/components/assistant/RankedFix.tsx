import type { ReactNode } from "react";

import { clean, fixed } from "@/lib/format";
import type { Resolution } from "@/lib/types";

import { IdLink } from "../ui/IdLink";
import { Notice } from "../ui/States";

const COMPONENT_LABEL: Record<string, string> = {
  max_relevance: "best relevance",
  agreement: "evidence agreement",
  provenance_factor: "provenance factor",
};

/** Confidence shown as the computation it is, never a bare number. */
export function ConfidenceEquation({ r }: { r: Pick<Resolution, "confidence" | "confidence_components" | "confidence_basis"> }) {
  if (r.confidence === null || r.confidence === undefined) {
    return (
      <p className="text-[14px] text-ink-2">
        Confidence <span className="font-semibold text-ink">undetermined</span>: {clean(r.confidence_basis) || "no real signal available"}
      </p>
    );
  }
  const comps = Object.entries(r.confidence_components ?? {});
  return (
    <div className="flex flex-wrap items-end gap-x-3 gap-y-3">
      <div className="flex flex-col">
        <span className="num display text-[34px] font-bold leading-none text-ink">{fixed(r.confidence)}</span>
        <span className="mt-1 text-[12px] leading-none font-semibold text-ink-2">confidence</span>
      </div>
      {comps.length > 0 && (
        <div className="flex flex-wrap items-end gap-x-2.5 gap-y-2">
          <span className="num pb-[15px] text-[18px] text-ink-3">=</span>
          {comps.map(([k, v], i) => (
            <span key={k} className="flex items-end gap-2.5">
              {i > 0 && <span className="pb-[15px] text-[18px] text-ink-3">×</span>}
              <span className="flex flex-col">
                <span className="num text-[18px] font-semibold leading-none text-ink">{fixed(v)}</span>
                <span className="mt-1 text-[12px] leading-none text-ink-3">{COMPONENT_LABEL[k] ?? k.replace(/_/g, " ")}</span>
              </span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function SafetyNote({ r }: { r: Resolution }) {
  if (!r.safety?.notes?.length && !r.safety?.requires_human_confirmation) return null;
  return (
    <Notice tone="warn" title={r.safety.requires_human_confirmation ? "Needs human confirmation before you act." : undefined}>
      {r.safety.notes.map(clean).join(" ")}
    </Notice>
  );
}

/** The one ranked, evidence-backed next step. Shared by the assistant and troubleshooting. */
export function RankedFix({
  r,
  lead = "Recommended first step",
  actions,
  compact = false,
}: {
  r: Resolution;
  /** Leads the attribution line under the action, e.g. "Round 2: have you tried this?". */
  lead?: ReactNode;
  actions?: ReactNode;
  compact?: boolean;
}) {
  return (
    <article className="flex flex-col gap-6">
      <div>
        <h2 className={`display font-bold leading-[1.15] text-ink ${compact ? "text-[24px]" : "text-[27px]"}`}>
          {clean(r.action)}
        </h2>
        <p className="mt-1.5 text-[13.5px] text-ink-2">
          <span className="font-semibold text-ink">{lead}</span>, {clean(r.kind)}, strategy <IdLink id={r.strategy_key} />
        </p>
        <p className="mt-3 max-w-[68ch] text-[15.5px] leading-relaxed text-ink-2">{clean(r.step)}</p>
        {r.expected_observation && (
          <p className="mt-3 max-w-[68ch] text-[14.5px] leading-relaxed text-ink">
            <span className="font-semibold">Expected observation:</span> {clean(r.expected_observation)}
          </p>
        )}
      </div>

      <div className="border-t border-line pt-5">
        <ConfidenceEquation r={r} />
        {r.confidence_basis && !r.confidence_components && (
          <p className="mt-2 text-[12.5px] text-ink-3">{clean(r.confidence_basis)}</p>
        )}
      </div>

      <SafetyNote r={r} />
      {actions && <div className="flex flex-wrap gap-3">{actions}</div>}
    </article>
  );
}
