"use client";

import { PaperPlaneRight, ThumbsDown, ThumbsUp } from "@phosphor-icons/react";
import { useState } from "react";

import { postJSON } from "@/lib/api";
import { useDesk, useDeskReady } from "@/lib/store";
import type { KbUpdate } from "@/lib/types";

import { KbUpdateNotice } from "../troubleshooting/PostmortemView";
import { Button } from "../ui/Button";
import { Field, Input, Segmented, TextArea, Toggle } from "../ui/Form";
import { IdList } from "../ui/IdLink";
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
type Result = { recorded: boolean; penalised_records: string[]; kb_update: KbUpdate | null };

export function FeedbackView() {
  const ready = useDeskReady();
  const { feedbackPrefill, analysis, session } = useDesk();
  const [incidentDraft, setIncidentId] = useState<string | null>(null);
  const [sessionDraft, setSessionId] = useState<string | null>(null);
  const [helpful, setHelpful] = useState<"yes" | "no" | "skip">("skip");
  const [reasons, setReasons] = useState<string[]>([]);
  const [answers, setAnswers] = useState<Record<string, Tri>>({});
  const [comment, setComment] = useState("");
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
      const r = await postJSON<Result>("/incidents/feedback", {
        incident_id: incidentId.trim(),
        session_id: sessionId.trim() || null,
        helpful: helpful === "skip" ? null : helpful === "yes",
        reasons,
        root_cause_correct: tri("root_cause_correct"),
        pattern_correct: tri("pattern_correct"),
        troubleshooting_resolved: tri("troubleshooting_resolved"),
        escalation_appropriate: tri("escalation_appropriate"),
        comment: comment.trim() || null,
        supporting_incident_ids: supporting.length ? supporting : null,
      });
      setResult(r);
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
                <Notice title="Feedback recorded">
                  {result.penalised_records.length
                    ? `Lowered the influence of ${result.penalised_records.join(", ")}.`
                    : "No record's influence changed."}
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
