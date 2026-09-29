"use client";

import { ArrowCounterClockwise, Check, FileText, ThumbsUp, X } from "@phosphor-icons/react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { postJSON } from "@/lib/api";
import { clean, clock, familyParts, fixed, period } from "@/lib/format";
import { useDesk, useDeskReady } from "@/lib/store";
import type { AgentMessage, KbUpdate, Postmortem, TSession } from "@/lib/types";

import { AgentMessages } from "../assistant/AgentTrace";
import { ModeStrip } from "../assistant/AssistantView";
import { Composer, DEMO_REPORT } from "../assistant/Composer";
import { RankedFix } from "../assistant/RankedFix";
import { Button, ButtonLink } from "../ui/Button";
import { Disclosure } from "../ui/Disclosure";
import { Input } from "../ui/Form";
import { IdLink } from "../ui/IdLink";
import { PageHeader, SectionTitle } from "../ui/Page";
import { Notice, Skel } from "../ui/States";
import { AttemptTrack } from "./AttemptTrack";
import { AttemptTable, EscalationPacket } from "./EscalationPacket";
import { PostmortemView } from "./PostmortemView";

type TsResponse = { session: TSession; agent_messages?: AgentMessage[] };

function StatusWord({ s }: { s: TSession }) {
  const map: Record<string, [string, string]> = {
    active: ["In progress", "text-cobalt"],
    awaiting_clarification: ["One question first", "text-amber-ink"],
    resolved: ["Resolved", "text-cobalt"],
    escalated: ["Escalated", "text-amber-ink"],
    novel: ["Novel incident", "text-red"],
  };
  const [w, c] = map[s.status] ?? [s.status, "text-ink"];
  return <span className={`font-semibold ${c}`}>{w}</span>;
}

function Clarify({ s, call, busy }: { s: TSession; call: (p: object) => void; busy: boolean }) {
  const q = s.clarification!;
  const [choice, setChoice] = useState(q.options[0] ?? "");
  const [own, setOwn] = useState("");
  const useOwn = choice === "__own";
  return (
    <section className="border border-line-2 bg-sheet">
      <div className="bg-amber-soft px-5 py-4 sm:px-6">
        <h2 className="display text-[23px] font-bold leading-snug text-ink">{q.question}</h2>
        <p className="mt-1 text-[14px] text-ink-2">
          Asked once, before {s.round >= s.max_rounds ? "escalating" : "the next step"}. Why: {clean(q.reason)}
        </p>
      </div>
      <fieldset className="flex flex-col gap-1 px-5 py-4 sm:px-6">
        <legend className="sr-only">Answer</legend>
        {[...q.options, "__own"].map((o) => (
          <label
            key={o}
            className={`flex cursor-pointer items-center gap-3 rounded-[3px] px-3 py-2.5 text-[15px] transition-colors ${
              choice === o ? "bg-cobalt-soft text-ink" : "text-ink-2 hover:bg-paper"
            }`}
          >
            <input type="radio" name="clarify" checked={choice === o} onChange={() => setChoice(o)} className="size-4 accent-[var(--cobalt)]" />
            {o === "__own" ? "Something else, in my words" : o}
          </label>
        ))}
        {useOwn && <Input autoFocus value={own} onChange={(e) => setOwn(e.target.value)} placeholder="Your answer" className="mt-2" aria-label="Your answer" />}
        <div className="mt-3 flex flex-wrap gap-3">
          <Button
            variant="primary"
            loading={busy}
            disabled={useOwn && !own.trim()}
            onClick={() => call({ action: "clarify", session_id: s.session_id, answer: useOwn ? own : choice })}
          >
            Answer
          </Button>
          <Button disabled={busy} onClick={() => call({ action: "clarify", session_id: s.session_id, declined: true })}>
            Skip, I don&apos;t know
          </Button>
        </div>
      </fieldset>
    </section>
  );
}

function Session({ s, reset }: { s: TSession; reset: () => void }) {
  const { sessionMessages, postmortem, set } = useDesk();
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState("");

  async function call(payload: object, tag = "call") {
    setBusy(tag);
    setError(null);
    try {
      const res = await postJSON<TsResponse>("/incidents/troubleshoot", payload);
      set({ session: res.session, sessionMessages: [...sessionMessages, ...(res.agent_messages ?? [])] });
      setNotes("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function makePostmortem() {
    setBusy("pm");
    setError(null);
    try {
      const res = await postJSON<{ postmortem: Postmortem; kb_update: KbUpdate | null }>("/postmortem", {
        incident_id: s.incident_id,
        feed_to_kb: true,
      });
      set({ postmortem: res });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const cs = s.current_step;
  const failed = s.attempts.filter((a) => a.engineer_response === "FAILED");
  const pm = postmortem?.postmortem.incident_id === s.incident_id ? postmortem : null;

  return (
    <div className="flex flex-col gap-10">
      <div className="flex flex-col gap-5 border-b border-line pb-7">
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
          <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[14px] text-ink-2">
            <StatusWord s={s} />
            <span>
              Session <span className="font-mono text-[12.5px] text-ink">{s.session_id}</span>
            </span>
            <span>
              Incident <IdLink id={s.incident_id} />
            </span>
            <span className="num">
              Round {Math.min(s.round, s.max_rounds)} of {s.max_rounds}
            </span>
            {s.family && (
              <span>
                Pattern <IdLink id={s.family.family_id} /> {clean(familyParts(s.family.name).rootCause)}, match {fixed(s.family.match_strength)}
              </span>
            )}
          </p>
          <Button size="sm" variant="ghost" icon={<ArrowCounterClockwise size={15} />} onClick={reset}>
            New session
          </Button>
        </div>
        <p className="max-w-[80ch] text-[14.5px] leading-relaxed text-ink-2">&ldquo;{s.query}&rdquo;</p>
        <AttemptTrack s={s} />
      </div>

      <ModeStrip labels={s.mode_labels} />
      {error && <Notice tone="error" title="The step could not be recorded">{error}</Notice>}

      {s.status === "active" && cs && (
        <section className="grid gap-x-12 gap-y-8 lg:grid-cols-12">
          <div className="lg:col-span-8">
            <RankedFix
              r={cs}
              compact
              lead={`Round ${cs.round ?? s.round}: have you tried this?`}
            />
          </div>
          <div className="flex flex-col gap-5 lg:col-span-4">
            <div className="border border-line-2 bg-sheet p-5">
              <p className="text-[15px] font-semibold text-ink">What happened when you tried it?</p>
              <label className="mt-3 block text-[13px] font-semibold text-ink-2" htmlFor="notes">
                Notes for the attempt log (optional)
              </label>
              <Input id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} className="mt-1.5" placeholder="e.g. memory back to 40% for ten minutes" />
              <div className="mt-4 grid grid-cols-2 gap-2">
                <Button
                  variant="primary"
                  icon={<Check size={16} weight="bold" />}
                  loading={busy === "WORKED"}
                  disabled={!!busy}
                  onClick={() => call({ action: "respond", session_id: s.session_id, attempt_id: cs.attempt_id, response: "WORKED", notes: notes || null }, "WORKED")}
                >
                  It worked
                </Button>
                <Button
                  variant="danger"
                  icon={<X size={16} weight="bold" />}
                  loading={busy === "FAILED"}
                  disabled={!!busy}
                  onClick={() => call({ action: "respond", session_id: s.session_id, attempt_id: cs.attempt_id, response: "FAILED", notes: notes || null }, "FAILED")}
                >
                  It failed
                </Button>
                <Button
                  loading={busy === "UNKNOWN"}
                  disabled={!!busy}
                  onClick={() => call({ action: "respond", session_id: s.session_id, attempt_id: cs.attempt_id, response: "UNKNOWN", notes: notes || null }, "UNKNOWN")}
                >
                  Not sure
                </Button>
                <Button
                  variant="ghost"
                  loading={busy === "esc"}
                  disabled={!!busy}
                  onClick={() => call({ action: "escalate", session_id: s.session_id, reason: "requested by engineer" }, "esc")}
                >
                  Escalate now
                </Button>
              </div>
              <p className="mt-3 text-[12.5px] leading-snug text-ink-3">
                A failed step is excluded from every later suggestion, along with near-identical actions.
              </p>
            </div>
            {failed.length > 0 && (
              <div>
                <p className="text-[13.5px] font-semibold text-ink-2">Will not be suggested again</p>
                <ul className="mt-1.5 flex flex-col gap-1 text-[14px]">
                  {failed.map((a) => (
                    <li key={a.attempt_id} className="text-ink-3 line-through decoration-red/70">
                      {clean(a.step_description)}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </section>
      )}

      {s.status === "awaiting_clarification" && s.clarification && <Clarify s={s} call={(p) => call(p, "clar")} busy={busy === "clar"} />}

      {s.status === "resolved" && (
        <section className="flex flex-col gap-7">
          <div className="bg-cobalt-fill px-5 py-5 text-on-cobalt sm:px-7">
            <p className="display text-[27px] font-bold leading-tight">Resolved</p>
            <p className="mt-1 text-[16px]">
              by <span className="font-semibold">{clean(s.resolved_by?.step_description)}</span>
            </p>
            <p className="mt-2 max-w-[70ch] text-[14px] opacity-85">
              Close the loop: the postmortem and your rating feed the knowledge base, so this incident becomes retrievable
              knowledge.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" icon={<FileText size={16} />} loading={busy === "pm"} disabled={!!pm} onClick={makePostmortem}>
              {pm ? "Postmortem generated" : "Generate postmortem and update the knowledge base"}
            </Button>
            <Button
              icon={<ThumbsUp size={16} />}
              onClick={() => {
                set({ feedbackPrefill: { incidentId: s.incident_id, sessionId: s.session_id, supporting: s.resolved_by?.source_incident_ids } });
                router.push("/feedback");
              }}
            >
              Rate this session
            </Button>
          </div>
          {pm && (
            <div>
              <SectionTitle meta={`generated ${clock(pm.postmortem.generated_at)}`}>Postmortem</SectionTitle>
              <PostmortemView p={pm.postmortem} kb={pm.kb_update} />
            </div>
          )}
        </section>
      )}

      {s.status === "novel" && !s.escalation && (
        <section className="flex flex-col gap-5">
          <div className="bg-red-fill px-5 py-5 text-on-red sm:px-7">
            <p className="display text-[27px] font-bold leading-tight">No historical playbook</p>
            <p className="mt-1 text-[15px]">{period(s.novelty.verdict)} Route to a fresh investigation.</p>
          </div>
          <div>
            <Button variant="primary" loading={busy === "esc"} onClick={() => call({ action: "escalate", session_id: s.session_id, reason: "novel incident" }, "esc")}>
              Escalate for fresh investigation
            </Button>
          </div>
        </section>
      )}

      {s.escalation &&
        (s.escalation_resolution ? (
          <Notice title={`Resolved by ${s.escalation_resolution.resolved_by}.`}>
            {period(s.escalation_resolution.resolution_notes)}
            {s.escalation_resolution.root_cause ? ` Root cause: ${period(s.escalation_resolution.root_cause)}` : ""}
          </Notice>
        ) : (
          <Notice
            tone="warn"
            title={`Waiting for ${s.escalation.tier}.`}
            action={<ButtonLink href={`/escalations?session=${encodeURIComponent(s.session_id)}`}>Open in Escalations</ButtonLink>}
          >
            The {s.escalation.tier} engineer reads this packet and records what fixed it on the Escalations page.
          </Notice>
        ))}
      {s.escalation && <EscalationPacket p={s.escalation} showHistory={false} />}

      <div className="flex flex-col gap-4">
        <SectionTitle meta="formal attempt tracking">Attempt log</SectionTitle>
        <AttemptTable attempts={s.attempts} />
      </div>

      <div className="border-b border-line">
        {s.clarifications.length > 0 && (
          <Disclosure title="Clarifications" meta={`${s.clarifications.length} asked, at most one per session`}>
            <ul className="flex flex-col gap-2 text-[14.5px]">
              {s.clarifications.map((c) => (
                <li key={c.question}>
                  <span className="text-ink-3">{clean(c.trigger).replace(/_/g, " ")}: </span>
                  <span className="text-ink">&ldquo;{c.question}&rdquo;</span>
                  <span className="text-ink-2"> {c.learned ? `learned ${c.learned}` : c.declined ? "skipped" : "pending"}</span>
                </li>
              ))}
            </ul>
          </Disclosure>
        )}
        <Disclosure title="Session timeline and agent messages" meta={`${s.events.length} events`}>
          <div className="grid gap-10 lg:grid-cols-2">
            <ol className="flex flex-col">
              {s.events.map((e, i) => (
                <li key={i} className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-3 border-b border-line py-1.5 text-[13.5px]">
                  <span className="font-mono text-[12px] text-ink-3">{clock(e.at)}</span>
                  <span className="text-ink">{e.kind.replace(/_/g, " ")}</span>
                </li>
              ))}
            </ol>
            <AgentMessages messages={sessionMessages} />
          </div>
        </Disclosure>
      </div>
    </div>
  );
}

export function TroubleshootingView() {
  const ready = useDeskReady();
  const { session, tsPrefill, reportText, set } = useDesk();
  const [draft, setText] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const text = draft ?? (tsPrefill?.text || reportText || DEMO_REPORT);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const res = await postJSON<TsResponse>("/incidents/troubleshoot", {
        action: "start",
        text,
        incident_id: tsPrefill?.incidentId ?? null,
      });
      set({ session: res.session, sessionMessages: res.agent_messages ?? [], tsPrefill: null, postmortem: null });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Guided Troubleshooting"
        lede="One step at a time. Every attempt is recorded, failed approaches are never suggested again, and one clarifying question may come before escalation."
      />
      {!ready ? (
        <Skel className="h-[180px] w-full rounded-none" />
      ) : session ? (
        <Session s={session} reset={() => set({ session: null, sessionMessages: [], tsPrefill: null })} />
      ) : (
        <>
          <Composer
            value={text}
            onChange={setText}
            onSubmit={start}
            busy={busy}
            submitLabel="Start troubleshooting"
            label={tsPrefill?.incidentId ? `Incident ${tsPrefill.incidentId}` : "Incident report"}
          />
          {error && (
            <div className="mt-4">
              <Notice tone="error" title="Could not start a session">
                {error}
              </Notice>
            </div>
          )}
          <p className="mt-6 max-w-[72ch] text-[14.5px] leading-relaxed text-ink-3">
            For the walkthrough, start with <span className="text-ink-2">Memory leak</span> and answer{" "}
            <span className="text-ink-2">It failed</span> three times: the system asks one question, then builds an escalation
            packet. Answer <span className="text-ink-2">It worked</span> instead to close the loop into the knowledge base.
          </p>
        </>
      )}
    </>
  );
}
