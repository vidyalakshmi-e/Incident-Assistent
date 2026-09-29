"use client";

import useSWR from "swr";

import { fetcher } from "@/lib/api";
import { clean, int } from "@/lib/format";
import type { Health } from "@/lib/types";

type State = "ok" | "degraded" | "down";

const stateColor: Record<State, string> = { ok: "var(--cobalt)", degraded: "var(--amber)", down: "var(--red)" };

function Row({ label, value, state, title }: { label: string; value: string; state?: State; title?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-[5px]" title={title}>
      <span className="annot shrink-0 text-ink-3">{label}</span>
      <span className="flex min-w-0 items-center gap-1.5 text-right text-[12.5px] font-medium text-ink">
        {state && (
          <span
            aria-label={state}
            className="inline-block size-[7px] shrink-0"
            style={{ background: stateColor[state] }}
          />
        )}
        <span className="truncate">{value}</span>
      </span>
    </div>
  );
}

/** Live component status from GET /health: which mode every answer on this desk is produced in. */
export function StatusStation() {
  const { data, error, isLoading } = useSWR<Health>("/health", fetcher, { refreshInterval: 30_000 });

  if (error) {
    return (
      <div className="border-t border-line pt-3">
        <Row label="API" value="offline" state="down" title={String(error.message ?? error)} />
        <p className="mt-1 text-[12px] leading-snug text-ink-3">Start it with uvicorn backend.main:app --port 8000</p>
      </div>
    );
  }
  if (isLoading || !data) {
    return (
      <div className="flex flex-col gap-2 border-t border-line pt-3" aria-busy>
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="skel h-3.5" />
        ))}
      </div>
    );
  }

  const reranked = !data.reranker.provider.includes("none");
  return (
    <div className="border-t border-line pt-2.5">
      <Row
        label="LLM"
        value={data.llm.available ? data.llm.model : "Retrieval-only"}
        state={data.llm.available ? "ok" : "degraded"}
        title={clean(data.llm.available ? data.llm.provider : data.llm.reason ?? data.llm.mode)}
      />
      <Row
        label="Retrieval"
        value={data.vector_store.ok ? (reranked ? "Hybrid, reranked" : "Hybrid, unreranked") : "Keyword-only"}
        state={data.vector_store.ok && reranked ? "ok" : "degraded"}
        title={`${data.vector_store.detail}; reranker ${data.reranker.provider}`}
      />
      <Row label="Knowledge" value={`${int(data.knowledge_base.records)} records`} />
      <Row label="Families" value={String(data.knowledge_base.families)} />
      <Row label="Escalation" value={data.escalation_tiers.join(" → ")} />
    </div>
  );
}
