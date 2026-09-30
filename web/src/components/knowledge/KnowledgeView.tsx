"use client";

import { ArrowClockwise, Check, X } from "@phosphor-icons/react";
import { useState } from "react";
import useSWR from "swr";

import { fetcher, postJSON } from "@/lib/api";
import { clean, date, fixed, label } from "@/lib/format";
import type { KbEvolution } from "@/lib/types";

import { Button } from "../ui/Button";
import { IdLink, IdList } from "../ui/IdLink";
import { PageHeader, SectionTitle } from "../ui/Page";
import { ProvTag } from "../ui/ProvTag";
import { Empty, ErrorState, Notice, Skel } from "../ui/States";

export function KnowledgeView() {
  const ev = useSWR<KbEvolution>("/kb/evolution", fetcher);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tone: "info" | "error"; text: string } | null>(null);

  async function run() {
    setBusy("batch");
    setMsg(null);
    try {
      const r = await postJSON<{ processed: number }>("/kb/evolve", {});
      setMsg({ tone: "info", text: `Processed ${r.processed} pending resolved incident${r.processed === 1 ? "" : "s"}.` });
      await ev.mutate();
    } catch (e) {
      setMsg({ tone: "error", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  }

  async function review(id: string, approve: boolean) {
    setBusy(id);
    try {
      await postJSON(`/kb/review/${encodeURIComponent(id)}`, { approve });
      await ev.mutate();
    } catch (e) {
      setMsg({ tone: "error", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Knowledge Base"
        lede="Resolved incidents become knowledge once they pass a quality check. Fixes that score too low wait here for a person to approve or reject them."
        aside={
          <Button icon={<ArrowClockwise size={16} />} loading={busy === "batch"} onClick={run}>
            Process resolved incidents
          </Button>
        }
      />
      {msg && (
        <div className="mb-6">
          <Notice tone={msg.tone}>{msg.text}</Notice>
        </div>
      )}

      {ev.error ? (
        <ErrorState error={ev.error} onRetry={() => ev.mutate()} />
      ) : !ev.data ? (
        <Skel className="h-32 w-full" />
      ) : (
        <div className="grid gap-x-12 gap-y-10 lg:grid-cols-12">
          <section className="lg:col-span-7">
            <SectionTitle meta={`${ev.data.recently_added.length} records`}>Recently added</SectionTitle>
            {ev.data.recently_added.length === 0 ? (
              <Empty title="Nothing added yet">
                Resolve an incident in Troubleshooting (answer <span className="text-ink">It worked</span>), then generate the
                postmortem or submit feedback. It lands here and becomes retrievable.
              </Empty>
            ) : (
              <ul className="flex flex-col">
                {ev.data.recently_added.map((r) => (
                  <li key={r.incident_id} className="border-b border-line py-3.5">
                    <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[13.5px] text-ink-2">
                      <IdLink id={r.incident_id} />
                      <span>
                        family <IdLink id={r.family_id} />
                      </span>
                      <span className="num">
                        quality {fixed(r.quality)} ({r.tier})
                      </span>
                      <span className="num text-ink-3">added {date(r.added_at)}</span>
                    </p>
                    <p className="mt-1 text-[15px] font-semibold text-ink">{clean(r.title)}</p>
                    <p className="mt-0.5 text-[14px] leading-relaxed text-ink-2">{clean(r.resolution_notes)}</p>
                    <p className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-ink-3">
                      {(["description", "resolution_notes", "category"] as const).map((k) => (
                        <span key={k} className="inline-flex items-center gap-1.5">
                          {label(k).toLowerCase()} <ProvTag tag={r.provenance?.[k]} />
                        </span>
                      ))}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="lg:col-span-5">
            <SectionTitle meta={`${ev.data.pending_review.length} waiting`}>Manual review</SectionTitle>
            {ev.data.pending_review.length === 0 ? (
              <div className="flex flex-col gap-2 text-[14px] leading-relaxed text-ink-2">
                <p>
                  Nothing is waiting. This is the safety gate for new knowledge: a fix that scores below{" "}
                  <span className="num text-ink">{fixed(ev.data.quality_threshold)}</span> is held here instead of being
                  added or thrown away.
                </p>
                <p className="text-ink-3">
                  So far {ev.data.gate.passed} passed the gate, {ev.data.gate.held} were held
                  {ev.data.gate.rejected ? `, ${ev.data.gate.rejected} rejected` : ""}. A vague note such as
                  &ldquo;restarted&rdquo; or &ldquo;closed&rdquo; is what lands here; a specific fix with a cause passes.
                </p>
              </div>
            ) : (
              <ul className="flex flex-col">
                {ev.data.pending_review.map((r) => (
                  <li key={r.incident_id} className="border-b border-line py-3.5">
                    <p className="flex flex-wrap items-baseline gap-x-3 text-[13.5px] text-ink-2">
                      <IdLink id={r.incident_id} />
                      <span className="num">quality {fixed(r.quality)}</span>
                    </p>
                    <p className="mt-1 text-[14px] text-ink">{clean(r.resolution_notes)}</p>
                    <p className="mt-1 text-[12.5px] text-amber-ink">{Array.isArray(r.flags) ? r.flags.join(", ") : String(r.flags)}</p>
                    <div className="mt-2.5 flex gap-2">
                      <Button size="sm" variant="primary" icon={<Check size={14} weight="bold" />} loading={busy === r.incident_id} onClick={() => review(r.incident_id, true)}>
                        Approve
                      </Button>
                      <Button size="sm" variant="danger" icon={<X size={14} weight="bold" />} disabled={busy === r.incident_id} onClick={() => review(r.incident_id, false)}>
                        Reject
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {ev.data.pending_candidates.length > 0 && (
              <p className="mt-4 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-[13.5px] text-ink-2">
                Resolved but not processed yet:
                <IdList ids={ev.data.pending_candidates} max={8} />
                <span>Process them with the button above.</span>
              </p>
            )}
          </section>
        </div>
      )}
    </>
  );
}
