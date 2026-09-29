"use client";

import { Check } from "@phosphor-icons/react";
import Link from "next/link";
import { useId, useState } from "react";
import useSWR from "swr";

import { fetcher, postJSON } from "@/lib/api";
import { clean, date, period } from "@/lib/format";
import type { EscalationItem, EscalationsResponse, KbUpdate } from "@/lib/types";

import { Button } from "../ui/Button";
import { Disclosure } from "../ui/Disclosure";
import { Field, Input, TextArea } from "../ui/Form";
import { IdLink } from "../ui/IdLink";
import { PageHeader, SectionTitle } from "../ui/Page";
import { Empty, ErrorState, Notice, Skel } from "../ui/States";
import { EscalationPacket } from "../troubleshooting/EscalationPacket";

/** Pre-select from the URL: ?id=<escalation id> or ?session=<troubleshooting session id>. */
function fromUrl(): { id: number | null; session: string | null } {
  if (typeof window === "undefined") return { id: null, session: null };
  const q = new URLSearchParams(window.location.search);
  return { id: Number(q.get("id")) || null, session: q.get("session") };
}

function KbLine({ status, incidentId }: { status: string | null | undefined; incidentId: string }) {
  if (status === "added_to_kb")
    return (
      <>
        The fix passed the quality check and is now knowledge: <IdLink id={incidentId} /> can be retrieved for similar incidents.
      </>
    );
  if (status === "pending_review")
    return (
      <>
        The fix scored below the quality threshold, so it waits for a person on the{" "}
        <Link href="/knowledge" className="font-semibold text-cobalt hover:underline">
          Knowledge base
        </Link>{" "}
        page before it can become knowledge.
      </>
    );
  if (status === "pending_batch") return <>The knowledge-base update was deferred; the nightly batch will pick it up.</>;
  return <>The knowledge base was not changed.</>;
}

function RowItem({ e, on, onSelect }: { e: EscalationItem; on: boolean; onSelect: () => void }) {
  return (
    <li className="border-b border-line">
      <button
        type="button"
        onClick={onSelect}
        aria-current={on ? "true" : undefined}
        className={`flex w-full flex-col gap-1 px-3 py-3 text-left transition-colors duration-150 ${
          on ? "bg-cobalt-soft" : "hover:bg-paper-2"
        }`}
      >
        <span className="line-clamp-2 text-[14.5px] font-semibold leading-snug text-ink">
          {clean(e.packet.incident_summary) || e.incident_id}
        </span>
        <span className="num flex flex-wrap gap-x-3 text-[13px] text-ink-2">
          <span className="font-semibold">{e.tier}</span>
          <span>{e.team}</span>
          <span className="text-ink-3">{date(e.escalated_at)}</span>
        </span>
      </button>
    </li>
  );
}

function ResolveForm({ e, onDone }: { e: EscalationItem; onDone: (kb: KbUpdate | null) => void }) {
  const id = useId();
  const [notes, setNotes] = useState("");
  const [rootCause, setRootCause] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tooShort = notes.trim().length < 10;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const res = await postJSON<{ escalation: EscalationItem; kb_update: KbUpdate | null }>(
        `/escalations/${e.escalation_id}/resolve`,
        { resolution_notes: notes.trim(), root_cause: rootCause.trim() || null },
      );
      onDone(res.kb_update);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={(ev) => {
        ev.preventDefault();
        if (!tooShort && !busy) submit();
      }}
      className="flex flex-col gap-4 border border-line-2 bg-sheet p-5"
    >
      <SectionTitle meta={`as ${e.tier}, ${e.team}`}>Record the fix</SectionTitle>
      <Field label="What fixed it?" htmlFor={`${id}-n`} hint="The steps you took, specific enough for the next engineer to repeat.">
        <TextArea
          id={`${id}-n`}
          rows={4}
          value={notes}
          onChange={(ev) => setNotes(ev.target.value)}
          placeholder="e.g. Raised the connection pool limit from 50 to 200 on the CRM database and restarted the pool; timeouts stopped."
        />
      </Field>
      <Field label="Root cause, if you found it (optional)" htmlFor={`${id}-r`}>
        <Input id={`${id}-r`} value={rootCause} onChange={(ev) => setRootCause(ev.target.value)} placeholder="e.g. connection pool exhaustion" />
      </Field>
      {error && (
        <Notice tone="error" title="The fix was not recorded">
          {error}
        </Notice>
      )}
      <div className="flex items-center gap-4">
        <Button type="submit" variant="primary" loading={busy} disabled={tooShort} icon={<Check size={16} weight="bold" />}>
          Mark resolved
        </Button>
        <span className="text-[13px] text-ink-3">
          The fix then goes through the same quality check as any other before it becomes knowledge.
        </span>
      </div>
    </form>
  );
}

function Detail({ e, onResolved }: { e: EscalationItem; onResolved: () => void }) {
  const [kbNote, setKbNote] = useState<KbUpdate | null | undefined>(undefined);
  const p = e.packet;
  const rc = p.likely_root_cause;
  const next = p.recommended_next_diagnostic_action;
  const failed = p.failed_approaches_do_not_repeat ?? [];

  return (
    <article className="flex flex-col gap-7">
      <header>
        <h2 className="display text-[27px] font-bold leading-[1.15] text-ink">{clean(p.incident_summary) || e.incident_id}</h2>
        <p className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[14px] text-ink-2">
          <span>
            Escalated to <span className="font-semibold text-ink">{e.tier}</span>, {e.team}
            {e.expertise ? ` (${e.expertise})` : ""}
          </span>
          <span className="num">{date(e.escalated_at)}</span>
          <span>
            incident <IdLink id={e.incident_id} />
          </span>
          {e.session_id && (
            <span>
              from troubleshooting session <span className="font-mono text-[12.5px] text-ink">{e.session_id}</span>
            </span>
          )}
        </p>
        <p className="mt-3 max-w-[70ch] text-[15px] leading-relaxed text-ink">
          <span className="font-semibold">Why it was escalated:</span> {period(e.reason)}
        </p>
      </header>

      {e.status === "resolved" && e.resolution ? (
        <Notice title={`Resolved by ${e.resolution.resolved_by}, ${date(e.resolution.resolved_at)}.`}>
          {period(e.resolution.resolution_notes)}
          {e.resolution.root_cause ? ` Root cause: ${period(e.resolution.root_cause)}` : ""}{" "}
          <KbLine status={kbNote === undefined ? e.resolution.kb_status : kbNote?.status} incidentId={e.incident_id} />
        </Notice>
      ) : null}

      <dl className="border-t border-line-2 text-[14.5px]">
        <div className="grid grid-cols-[11rem_minmax(0,1fr)] gap-4 border-b border-line py-2.5">
          <dt className="text-ink-2">Likely root cause</dt>
          <dd className="text-ink">
            {rc?.statement && rc.statement !== "insufficient evidence" ? (
              <>
                <span className="font-semibold">{clean(rc.statement)}</span>
                {rc.certainty && (
                  <span className="text-ink-2">
                    , {rc.certainty} ({rc.support} of {rc.of_retrieved} retrieved incidents)
                  </span>
                )}
              </>
            ) : (
              <span className="text-ink-2">Insufficient evidence.</span>
            )}
          </dd>
        </div>
        <div className="grid grid-cols-[11rem_minmax(0,1fr)] gap-4 border-b border-line py-2.5">
          <dt className="text-ink-2">Suggested next step</dt>
          <dd className="text-ink">
            {clean(next?.action) || "None."} {next?.kind && <span className="text-ink-3">({clean(next.kind)})</span>}
          </dd>
        </div>
        <div className="grid grid-cols-[11rem_minmax(0,1fr)] gap-4 border-b border-line py-2.5">
          <dt className="text-ink-2">Tried and failed</dt>
          <dd className="flex flex-wrap gap-x-3 gap-y-1">
            {failed.length ? (
              failed.map((k) => (
                <span key={k} className="line-through decoration-red decoration-[1.5px]">
                  <IdLink id={k} />
                </span>
              ))
            ) : (
              <span className="text-ink-2">Nothing yet.</span>
            )}
          </dd>
        </div>
      </dl>

      {e.status === "open" && (
        <ResolveForm
          e={e}
          onDone={(kb) => {
            setKbNote(kb);
            onResolved();
          }}
        />
      )}

      <div className="border-b border-line">
        <Disclosure title="Full escalation packet" meta={p.packet_id}>
          <EscalationPacket p={p} />
        </Disclosure>
      </div>
    </article>
  );
}

export function EscalationsView() {
  const { data, error, mutate } = useSWR<EscalationsResponse>("/escalations", fetcher);
  const [pick, setPick] = useState(fromUrl);
  const items = data?.escalations ?? [];
  const open = items.filter((e) => e.status === "open");
  const done = items.filter((e) => e.status === "resolved");
  const selected =
    items.find((e) => e.escalation_id === pick.id) ??
    items.find((e) => pick.session && e.session_id === pick.session) ??
    open[0] ??
    items[0];

  return (
    <>
      <PageHeader
        title="Escalations"
        lede="Incidents the system handed to L2 or L3. Read what was already tried, fix the problem, then record what fixed it here."
      />
      {error ? (
        <ErrorState error={error} onRetry={() => mutate()} />
      ) : !data ? (
        <Skel className="h-64 w-full" />
      ) : items.length === 0 ? (
        <Empty title="Nothing has been escalated">
          An incident lands here when guided troubleshooting runs out of evidence-backed steps, or when an engineer escalates it.
        </Empty>
      ) : (
        <div className="grid grid-cols-12 gap-x-12">
          <div className="col-span-4 flex flex-col gap-8">
            <section>
              <SectionTitle meta={`${open.length} waiting`}>Open</SectionTitle>
              {open.length ? (
                <ul className="border-t border-line-2">
                  {open.map((e) => (
                    <RowItem key={e.escalation_id} e={e} on={e === selected} onSelect={() => setPick({ id: e.escalation_id, session: null })} />
                  ))}
                </ul>
              ) : (
                <p className="text-[14px] text-ink-3">Nothing is waiting.</p>
              )}
            </section>
            {done.length > 0 && (
              <section>
                <SectionTitle meta={`${done.length}`}>Resolved</SectionTitle>
                <ul className="border-t border-line-2">
                  {done.map((e) => (
                    <RowItem key={e.escalation_id} e={e} on={e === selected} onSelect={() => setPick({ id: e.escalation_id, session: null })} />
                  ))}
                </ul>
              </section>
            )}
          </div>
          <div className="col-span-8">
            {selected && (
              <Detail
                key={selected.escalation_id}
                e={selected}
                onResolved={() => {
                  setPick({ id: selected.escalation_id, session: null });
                  mutate();
                }}
              />
            )}
          </div>
        </div>
      )}
    </>
  );
}
