"use client";

import { PaperPlaneRight, Star, ThumbsDown, ThumbsUp } from "@phosphor-icons/react";
import { useState } from "react";
import useSWR from "swr";

import { fetcher, postJSON } from "@/lib/api";
import { useDesk, useDeskReady } from "@/lib/store";
import type { FeedbackSummary, KbUpdate } from "@/lib/types";

import { KbUpdateNotice } from "../troubleshooting/PostmortemView";
import { Button } from "../ui/Button";
import { Field, Input, Segmented, TextArea, Toggle } from "../ui/Form";
import { IdLink, IdList } from "../ui/IdLink";
import { PageHeader } from "../ui/Page";
import { Notice, Skel } from "../ui/States";

const REASONS = ["wrong incident", "wrong resolution", "incomplete", "outdated", "escalation required", "other"] as const;
const QUESTIONS = [
  ["root_cause_correct", "Was the root cause right?"],
  ["pattern_correct", "Was the pattern family right?"],
  ["troubleshooting_resolved", "Did troubleshooting resolve it?"],
  ["escalation_appropriate", "Was escalation appropriate?"],
] as const;

type Tri = "unanswered" | "yes" | "no";

/** A star rating read as how much of the problem was resolved: rating / 5. */
const RESOLVED_WORD: Record<number, string> = {
  1: "Barely resolved",
  2: "Partly resolved",
  3: "Mostly resolved, some left",
  4: "Nearly fully resolved",
  5: "Fully resolved",
};

function Meter({ percent, big = false }: { percent: number | null; big?: boolean }) {
  return (
    <div className="flex items-center gap-4">
      <span className={`num display shrink-0 leading-none font-bold text-ink ${big ? "min-w-[6.5rem] text-[44px]" : "min-w-[3.6rem] text-[26px]"}`}>
        {percent === null ? "n/a" : `${percent}%`}
      </span>
      <div className="relative h-3 min-w-0 flex-1 overflow-hidden bg-paper-2" role="img" aria-label={percent === null ? "no rating" : `${percent} percent resolved`}>
        <div className="absolute inset-y-0 left-0 bg-cobalt transition-[width] duration-300" style={{ width: `${percent ?? 0}%` }} />
      </div>
    </div>
  );
}

function StarRating({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div role="radiogroup" aria-label="How much of the problem was resolved" className="flex items-center gap-1">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          aria-label={`${n} of 5, ${n * 20} percent resolved`}
          onClick={() => onChange(value === n ? 0 : n)}
          className="grid size-10 place-items-center rounded-[3px] text-amber transition-transform duration-150 hover:scale-110 focus-visible:outline-2 focus-visible:outline-cobalt active:scale-95"
        >
          <Star size={30} weight={n <= value ? "fill" : "regular"} className={n <= value ? "text-amber" : "text-line-2"} />
        </button>
      ))}
    </div>
  );
}
type Change = { incident_id: string; influence_before: number; influence_after: number };
type Result = {
  recorded: boolean;
  penalised_records: string[];
  influence_changes: Change[];
  kb_update: KbUpdate | null;
  resolved_percent: number | null;
  summary?: FeedbackSummary;
  /** What was submitted, so the outcome message can say why nothing changed. */
  negative: boolean;
  hadEvidence: boolean;
};

export function FeedbackView() {
  const ready = useDeskReady();
  const { feedbackPrefill, analysis, session } = useDesk();
  const [incidentDraft, setIncidentId] = useState<string | null>(null);
  const [sessionDraft, setSessionId] = useState<string | null>(null);
  const [helpful, setHelpful] = useState<"yes" | "no" | "skip">("skip");
  const [reasons, setReasons] = useState<string[]>([]);
  const [answers, setAnswers] = useState<Record<string, Tri>>({});
  const [comment, setComment] = useState("");
  const [rating, setRating] = useState(0);
  const summary = useSWR<FeedbackSummary>("/feedback/summary", fetcher);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);

  const incidentId = incidentDraft ?? feedbackPrefill?.incidentId ?? session?.incident_id ?? analysis?.incident_id ?? "";
  const sessionId =
    sessionDraft ?? feedbackPrefill?.sessionId ?? (session && session.incident_id === incidentId ? session.session_id : "");

  const supporting = feedbackPrefill?.supporting ?? analysis?.top_resolution?.supporting_incidents ?? [];
  const tri = (k: string) => (answers[k] === "yes" ? true : answers[k] === "no" ? false : null);

  async function submit() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const negative = helpful === "no" || reasons.some((x) => ["wrong resolution", "outdated", "wrong incident"].includes(x));
      const r = await postJSON<Omit<Result, "negative" | "hadEvidence">>("/incidents/feedback", {
        incident_id: incidentId.trim(),
        session_id: sessionId.trim() || null,
        helpful: helpful === "skip" ? null : helpful === "yes",
        reasons,
        root_cause_correct: tri("root_cause_correct"),
        pattern_correct: tri("pattern_correct"),
        troubleshooting_resolved: tri("troubleshooting_resolved"),
        escalation_appropriate: tri("escalation_appropriate"),
        comment: comment.trim() || null,
        rating: rating || null,
        supporting_incident_ids: supporting.length ? supporting : null,
      });
      setResult({ ...r, negative, hadEvidence: supporting.length > 0 });
      void summary.mutate(r.summary, { revalidate: false });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Feedback"
        lede="Your rating changes knowledge records: it lowers the influence of evidence that misled, and resolved incidents enter the knowledge base. No model is retrained."
      />
      {!ready ? (
        <Skel className="h-96 w-full max-w-[760px]" />
      ) : (
        <div className="grid gap-x-14 gap-y-10 lg:grid-cols-12">
          <form
            className="flex flex-col gap-7 lg:col-span-7"
            onSubmit={(e) => {
              e.preventDefault();
              if (incidentId.trim()) submit();
            }}
          >
            <div className="grid gap-5 sm:grid-cols-2">
              <Field label="Incident ID" htmlFor="fb-inc" hint={!incidentId.trim() ? "Required. Analyse an incident first, or paste an ID." : "Prefilled from your last analysis or session."}>
                <Input id="fb-inc" value={incidentId} onChange={(e) => setIncidentId(e.target.value)} className="font-mono" />
              </Field>
              <Field label="Troubleshooting session" htmlFor="fb-ses" hint="Optional">
                <Input id="fb-ses" value={sessionId} onChange={(e) => setSessionId(e.target.value)} className="font-mono" />
              </Field>
            </div>

            <div className="flex flex-col gap-3 border border-line-2 bg-sheet p-5">
              <span className="text-[15px] font-semibold text-ink">How much of the problem was resolved?</span>
              <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
                <StarRating value={rating} onChange={setRating} />
                <span className="text-[14px] text-ink-2">{rating ? RESOLVED_WORD[rating] : "Pick 1 to 5 stars. Optional."}</span>
              </div>
              {rating > 0 && <Meter percent={rating * 20} big />}
              <p className="text-[12.5px] leading-snug text-ink-3">5 stars means fully resolved (100%). Each star is 20%.</p>
            </div>

            <div className="flex flex-col gap-2">
              <span className="text-[13.5px] font-semibold text-ink">Was the recommendation helpful?</span>
              <Segmented
                label="Helpful"
                value={helpful}
                onChange={setHelpful}
                options={[
                  { value: "yes", tone: "good", label: <span className="inline-flex items-center gap-1.5"><ThumbsUp size={15} /> Helpful</span> },
                  { value: "no", tone: "bad", label: <span className="inline-flex items-center gap-1.5"><ThumbsDown size={15} /> Not helpful</span> },
                  { value: "skip", label: "Skip" },
                ]}
              />
            </div>

            <div className="flex flex-col gap-2">
              <span className="text-[13.5px] font-semibold text-ink">What was wrong? (optional)</span>
              <div className="flex flex-wrap gap-2">
                {REASONS.map((r) => (
                  <Toggle key={r} on={reasons.includes(r)} onClick={() => setReasons(reasons.includes(r) ? reasons.filter((x) => x !== r) : [...reasons, r])}>
                    {r}
                  </Toggle>
                ))}
              </div>
            </div>

            <div className="flex flex-col">
              {QUESTIONS.map(([k, q]) => (
                <div key={k} className="flex flex-wrap items-center justify-between gap-3 border-b border-line py-3 first:border-t">
                  <span className="text-[14.5px] text-ink">{q}</span>
                  <Segmented
                    size="sm"
                    label={q}
                    value={answers[k] ?? "unanswered"}
                    onChange={(v) => setAnswers({ ...answers, [k]: v })}
                    options={[
                      { value: "yes", label: "Yes" },
                      { value: "no", label: "No" },
                      { value: "unanswered", label: "Not sure" },
                    ]}
                  />
                </div>
              ))}
            </div>

            <Field label="Comment" htmlFor="fb-c" hint="Optional. What should the next engineer know?">
              <TextArea id="fb-c" rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
            </Field>

            <div>
              <Button type="submit" variant="primary" size="lg" loading={busy} disabled={!incidentId.trim()} icon={<PaperPlaneRight size={16} />}>
                Submit feedback
              </Button>
            </div>
          </form>

          <aside className="flex flex-col gap-5 lg:col-span-5">
            <div className="border border-line-2 bg-sheet p-5">
              <p className="text-[15px] font-semibold text-ink">Resolved, by your ratings</p>
              {summary.data && summary.data.rated > 0 ? (
                <>
                  <div className="mt-3">
                    <Meter percent={summary.data.resolved_percent} big />
                  </div>
                  <p className="num mt-3 text-[13.5px] text-ink-2">
                    {summary.data.rated} {summary.data.rated === 1 ? "rating" : "ratings"}, average {summary.data.average_rating} of 5,{" "}
                    {summary.data.fully_resolved} fully resolved.
                  </p>
                  <div className="mt-3 flex flex-col gap-1">
                    {[5, 4, 3, 2, 1].map((n) => {
                      const c = summary.data!.distribution[String(n)] ?? 0;
                      return (
                        <div key={n} className="grid grid-cols-[2.6rem_minmax(0,1fr)_1.8rem] items-center gap-2 text-[12.5px] text-ink-3">
                          <span className="num">{n * 20}%</span>
                          <div className="relative h-1.5 bg-paper-2" aria-hidden>
                            <div className="absolute inset-y-0 left-0 bg-ink-3" style={{ width: `${(c / summary.data!.rated) * 100}%` }} />
                          </div>
                          <span className="num text-right">{c}</span>
                        </div>
                      );
                    })}
                  </div>
                </>
              ) : (
                <p className="mt-2 text-[13.5px] leading-relaxed text-ink-3">
                  {summary.error ? "The summary could not be loaded." : "No star ratings yet. The first one sets the figure."}
                </p>
              )}
            </div>
            {supporting.length > 0 && (
              <div className="border-t border-line pt-4">
                <p className="text-[14px] font-semibold text-ink">The rated recommendation was backed by</p>
                <div className="mt-2">
                  <IdList ids={supporting} max={10} />
                </div>
                <p className="mt-2 text-[13px] leading-relaxed text-ink-3">
                  Rating it not helpful, or wrong, lowers these records&apos; influence in future rankings.
                </p>
              </div>
            )}
            {error && (
              <Notice tone="error" title="Feedback was not recorded">
                {error}
              </Notice>
            )}
            {result && (
              <div className="flex flex-col gap-3">
                {result.resolved_percent !== null && (
                  <div className="border border-line-2 bg-sheet p-4">
                    <p className="mb-2 text-[13.5px] font-semibold text-ink-2">This rating: resolved</p>
                    <Meter percent={result.resolved_percent} />
                  </div>
                )}
                <Notice title="Feedback recorded">
                  {result.influence_changes.length
                    ? "Lowered how much these records count in future rankings (saved, so it survives a restart): "
                    : result.negative && !result.hadEvidence
                      ? "No record's influence changed: this rating was not attached to any historical records. Analyse an incident first, then rate it. "
                      : !result.negative
                        ? "No record's influence changed: only a not-helpful, wrong-resolution, outdated or wrong-incident rating lowers it. "
                        : "No record's influence changed. "}
                  {result.influence_changes.map((c, i) => (
                    <span key={c.incident_id}>
                      {i > 0 && ", "}
                      <IdLink id={c.incident_id} />{" "}
                      <span className="num">
                        {c.influence_before.toFixed(2)} &rarr; {c.influence_after.toFixed(2)}
                      </span>
                    </span>
                  ))}
                  {result.influence_changes.length > 0 && "."}
                  {!result.kb_update && " The incident is not a resolved live incident, so the knowledge base was not updated."}
                </Notice>
                {result.kb_update && <KbUpdateNotice k={result.kb_update} />}
              </div>
            )}
          </aside>
        </div>
      )}
    </>
  );
}
