"use client";

import { ArrowRight, CircleDashed, PencilSimple, ThumbsUp } from "@phosphor-icons/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { postJSON } from "@/lib/api";
import { clean, familyParts, pct } from "@/lib/format";
import { useDesk, useDeskReady } from "@/lib/store";
import { announceNewIncident } from "@/lib/toast";
import type { Analysis } from "@/lib/types";

import { EvalStrip } from "../evaluation/QueryEval";
import { Button, ButtonLink } from "../ui/Button";
import { Disclosure } from "../ui/Disclosure";
import { Field, Select } from "../ui/Form";
import { IdLink } from "../ui/IdLink";
import { PageHeader, SectionTitle } from "../ui/Page";
import { ProvTag } from "../ui/ProvTag";
import { Notice, Skel } from "../ui/States";
import { StationPlot } from "../viz/StationPlot";
import { AnnotatedReport } from "./AnnotatedReport";
import { Composer, DEMO_REPORT } from "./Composer";
import { EvidenceChain } from "./EvidenceChain";
import { RankedFix } from "./RankedFix";
import { TopSolutions } from "./TopSolutions";
import { Triage } from "./Triage";
import { VerdictField } from "./Verdict";

export function ModeStrip({ labels }: { labels: string[] }) {
  if (!labels?.length) return null;
  const retrievalOnly = labels.some((l) => /retrieval-only/i.test(l));
  return (
    <Notice tone="warn" compact title={labels.map(clean).join(". ")}>
      {retrievalOnly
        ? "Every result comes from historical evidence and computed scores; no text was generated."
        : "A fallback is active; affected results are labelled."}
    </Notice>
  );
}

function ResultSkeleton() {
  return (
    <div aria-busy aria-label="Analysing" className="mt-10 flex flex-col gap-8">
      <Skel className="h-[118px] w-full rounded-none" />
      <div className="flex max-w-[860px] flex-col gap-4">
        <Skel className="h-4 w-40" />
        <Skel className="h-8 w-4/5" />
        <Skel className="h-4 w-full" />
        <Skel className="h-4 w-11/12" />
        <Skel className="mt-6 h-12 w-2/3" />
        <Skel className="mt-4 h-20 w-full" />
      </div>
    </div>
  );
}

function NovelRoute({ a }: { a: Analysis }) {
  const router = useRouter();
  const set = useDesk((s) => s.set);
  const reportText = useDesk((s) => s.reportText);
  return (
    <article className="flex flex-col gap-5">
      <div>
        <h2 className="display text-[27px] font-bold leading-[1.15] text-ink">Route to fresh investigation</h2>
        <p className="mt-3 max-w-[62ch] text-[15.5px] leading-relaxed text-ink-2">
          <span className="font-semibold text-ink">No historical fix is recommended.</span> Nothing in the knowledge base is
          similar enough to act on. The nearest analogs are shown for transparency only; their root causes and fixes are not
          used as evidence.
        </p>
      </div>
      {a.escalation_proposal && (
        <dl className="grid gap-x-8 gap-y-3 border-t border-line pt-5 sm:grid-cols-2">
          <div>
            <dt className="annot text-ink-3">Proposed tier</dt>
            <dd className="mt-1 text-[15px] font-semibold text-ink">
              {a.escalation_proposal.tier} to {a.escalation_proposal.suggested_team}
            </dd>
          </div>
          <div>
            <dt className="annot text-ink-3">Routing basis</dt>
            <dd className="mt-1 text-[13.5px] leading-relaxed text-ink-2">{clean(a.escalation_proposal.routing_basis)}</dd>
          </div>
        </dl>
      )}
      <div className="flex flex-wrap gap-3">
        <Button
          variant="primary"
          icon={<ArrowRight size={16} weight="bold" />}
          onClick={() => {
            set({ tsPrefill: { incidentId: a.incident_id, text: reportText }, session: null, sessionMessages: [] });
            router.push("/troubleshooting");
          }}
        >
          Open a troubleshooting session
        </Button>
        <ButtonLink href="/novelty" icon={<CircleDashed size={16} />}>
          How novelty is decided
        </ButtonLink>
      </div>
    </article>
  );
}

function AnalysisResult({ a }: { a: Analysis }) {
  const router = useRouter();
  const set = useDesk((s) => s.set);
  const reportText = useDesk((s) => s.reportText);
  const novel = a.novelty.is_novel === true;
  const top = a.top_resolution;
  const rc = a.likely_root_cause;
  const fam = a.pattern_family;

  return (
    <div className="mt-6 flex flex-col gap-10">
      <div className="flex flex-col gap-3">
        <ModeStrip labels={a.mode_labels} />
        <VerdictField novelty={a.novelty} family={fam} escalation={a.escalation_proposal} runId={a.incident_id} />
        {a.query_evaluation && <EvalStrip e={a.query_evaluation} />}
      </div>

      <section>
        <div className="max-w-[860px]">
          {novel ? (
            <NovelRoute a={a} />
          ) : top ? (
            <RankedFix
              r={top}
              actions={
                <>
                  <Button
                    variant="primary"
                    icon={<ArrowRight size={16} weight="bold" />}
                    onClick={() => {
                      set({ tsPrefill: { incidentId: a.incident_id, text: reportText }, session: null, sessionMessages: [] });
                      router.push("/troubleshooting");
                    }}
                  >
                    Start guided troubleshooting
                  </Button>
                  <Button
                    icon={<ThumbsUp size={16} />}
                    onClick={() => {
                      set({ feedbackPrefill: { incidentId: a.incident_id, supporting: top.supporting_incidents } });
                      router.push("/feedback");
                    }}
                  >
                    Rate this recommendation
                  </Button>
                </>
              }
            />
          ) : (
            <Notice tone="warn" title="No evidence-backed resolution found">
              Retrieval found no historical fix strong enough to rank. Try adding detail to the report.
            </Notice>
          )}
        </div>
      </section>

      {!novel && (a.top_solutions?.length ?? 0) > 0 && (
        <section className="border-t border-line pt-9">
          <SectionTitle meta={`${a.top_solutions!.length} ranked by confidence`}>Top solutions</SectionTitle>
          <TopSolutions items={a.top_solutions!} filtered={a.filtered_as_irrelevant?.length ?? 0} />
        </section>
      )}

      <section className="grid gap-x-12 gap-y-8 border-t border-line pt-9 lg:grid-cols-12">
        <div className="lg:col-span-5">
          <SectionTitle>How the report was read</SectionTitle>
          <AnnotatedReport qu={a.evidence_chain.query_understood} />
        </div>
        <div className="lg:col-span-7">
          <SectionTitle meta="enriched fingerprint">What the system extracted</SectionTitle>
          <StationPlot fp={a.fingerprint} />
        </div>
      </section>

      <section className="flex flex-col gap-6 border-t border-line pt-9">
        <div className="grid gap-x-12 gap-y-6 lg:grid-cols-12">
          <div className="lg:col-span-5">
            <SectionTitle>Pattern family</SectionTitle>
            {fam && !novel ? (
              <div>
                <p className="flex items-baseline gap-2.5">
                  <IdLink id={fam.family_id} className="text-[14px]" />
                  <span className="text-[17px] font-semibold text-ink">{clean(familyParts(fam.name).rootCause)}</span>
                </p>
                <p className="mt-1 text-[14px] text-ink-2">
                  {familyParts(fam.name).scope}, {fam.size} incidents, {pct(fam.vote_share)} of retrieved votes.
                </p>
                <Link href={`/patterns/${fam.family_id}`} className="mt-2 inline-block text-[14px] font-semibold text-cobalt hover:underline">
                  Open the family
                </Link>
              </div>
            ) : (
              <p className="text-[14px] text-ink-2">No family matched with enough evidence.</p>
            )}
          </div>
          <div className="lg:col-span-7">
            <SectionTitle>Likely root cause</SectionTitle>
            {rc.status === "computed" ? (
              <div>
                <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="text-[17px] font-semibold text-ink">{clean(rc.statement)}</span>
                  <ProvTag tag="inferred" />
                </p>
                <p className="mt-1 text-[14px] text-ink-2">
                  {sentenceCase(rc.certainty)}, supported by {pct(rc.share_of_retrieved)} of the retrieved evidence.{" "}
                  <span className="text-ink-3">{clean(rc.note)}</span>
                </p>
              </div>
            ) : (
              <p className="text-[14px] text-ink-2">
                <span className="font-semibold text-ink">Insufficient evidence.</span> {clean(rc.reason)}
              </p>
            )}
          </div>
        </div>
        <div>
          <h3 className="mb-3 text-[15px] font-semibold text-ink-2">Triage, predicted from the text</h3>
          <Triage c={a.classification} />
        </div>
      </section>

      <div className="border-b border-line">
        <Disclosure title="Why did the system recommend this?" meta="evidence chain">
          <EvidenceChain ch={a.evidence_chain} />
        </Disclosure>
        {a.llm_synthesis && (
          <Disclosure title="LLM synthesis" meta="generated, separate from the evidence">
            <ProvTag tag="inferred">LLM-generated</ProvTag>
            <p className="mt-2 max-w-[70ch] whitespace-pre-line text-[15px] leading-relaxed text-ink">{a.llm_synthesis.text}</p>
          </Disclosure>
        )}
      </div>
    </div>
  );
}

function ReportStrip({ text, onEdit }: { text: string; onEdit: () => void }) {
  return (
    <div className="flex items-center gap-4 border border-line-2 bg-sheet py-2 pr-2 pl-4 sm:pl-5">
      <p className="min-w-0 flex-1 truncate text-[15px] text-ink" title={text}>
        <span className="mr-2 font-semibold">Report</span>
        <span className="text-ink-2">&ldquo;{text}&rdquo;</span>
      </p>
      <Button size="sm" variant="ghost" icon={<PencilSimple size={15} />} onClick={onEdit}>
        Edit report
      </Button>
    </div>
  );
}

function sentenceCase(s?: string) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : "";
}

export function AssistantView() {
  const ready = useDeskReady();
  const { reportText, analysis, set, logEval } = useDesk();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [facts, setFacts] = useState({ priority: "", environment: "", scope: "" });
  const [editing, setEditing] = useState(false);
  const text = ready ? reportText || DEMO_REPORT : DEMO_REPORT;

  async function analyze() {
    setBusy(true);
    setError(null);
    const hints: Record<string, string> = {};
    if (facts.environment) hints.environment = facts.environment;
    if (facts.scope) hints.impact_scope = facts.scope;
    try {
      const res = await postJSON<Analysis>("/incidents/analyze", {
        text,
        hints: Object.keys(hints).length ? hints : null,
        fields: facts.priority ? { priority: facts.priority } : null,
      });
      set({ analysis: res, reportText: text });
      announceNewIncident(res.incident_id);
      if (res.query_evaluation) logEval({ text, from: "assistant", evaluation: res.query_evaluation });
      setEditing(false);
      // The report folds to one line, so the verdict lands in view; move focus there for keyboard and screen readers.
      requestAnimationFrame(() => document.querySelector<HTMLElement>("section[aria-label=Verdict]")?.focus({ preventScroll: true }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Incident Assistant"
        lede="Describe the incident in your own words. You get one ranked, evidence-backed first step and the history behind it."
      />
      {!ready ? (
        <Skel className="h-[196px] w-full rounded-none" />
      ) : analysis && !editing && !busy ? (
        <ReportStrip text={text} onEdit={() => setEditing(true)} />
      ) : (
        <Composer
          value={text}
          onChange={(v) => set({ reportText: v })}
          onSubmit={analyze}
          busy={busy}
          submitLabel="Analyze"
          footer={
            <details className="disclosure border-t border-line">
              <summary className="cursor-pointer px-4 py-2.5 text-[13px] font-semibold text-ink-2 hover:text-cobalt sm:px-5">
                Known facts (optional)
              </summary>
              <div className="grid gap-4 px-4 pb-4 sm:grid-cols-3 sm:px-5">
                <Field label="Priority, if known">
                  <Select value={facts.priority} onChange={(e) => setFacts({ ...facts, priority: e.target.value })}>
                    <option value="">Not known</option>
                    {["1", "2", "3", "4", "5"].map((p) => (
                      <option key={p}>{p}</option>
                    ))}
                  </Select>
                </Field>
                <Field label="Environment">
                  <Select value={facts.environment} onChange={(e) => setFacts({ ...facts, environment: e.target.value })}>
                    <option value="">Not known</option>
                    <option>Production</option>
                    <option>Staging</option>
                    <option>Development</option>
                  </Select>
                </Field>
                <Field label="Affected scope">
                  <Select value={facts.scope} onChange={(e) => setFacts({ ...facts, scope: e.target.value })}>
                    <option value="">Not known</option>
                    <option>single user</option>
                    <option>multiple users</option>
                    <option>team</option>
                    <option>organization-wide</option>
                  </Select>
                </Field>
              </div>
            </details>
          }
        />
      )}
      {error && (
        <div className="mt-4">
          <Notice tone="error" title="Analysis failed">
            {error}
          </Notice>
        </div>
      )}
      {busy ? <ResultSkeleton /> : ready && analysis ? <AnalysisResult key={analysis.incident_id} a={analysis} /> : null}
      {ready && !analysis && !busy && (
        <p className="mt-6 max-w-[70ch] text-[14.5px] leading-relaxed text-ink-3">
          Nothing analysed yet. <span className="text-ink-2">Memory leak</span> is the walkthrough report;{" "}
          <span className="text-ink-2">Tape robot</span> is an incident the knowledge base has never seen.
        </p>
      )}
    </>
  );
}
