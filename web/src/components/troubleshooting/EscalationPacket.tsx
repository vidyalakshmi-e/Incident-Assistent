import { clean, clock, period } from "@/lib/format";
import type { Attempt, EscalationPacket as Packet } from "@/lib/types";

import { Disclosure } from "../ui/Disclosure";
import { IdLink } from "../ui/IdLink";
import { ProvTag } from "../ui/ProvTag";
import { Table } from "../ui/Table";

export function AttemptTable({ attempts }: { attempts: Attempt[] }) {
  return (
    <Table
      rows={attempts}
      rowKey={(a) => a.attempt_id}
      cols={[
        { key: "r", head: "Round", cell: (a) => a.round, width: "4rem" },
        { key: "s", head: "Step", cell: (a) => <span className="font-medium">{clean(a.step_description)}</span> },
        { key: "k", head: "Strategy", cell: (a) => (a.strategy_key ? <IdLink id={a.strategy_key} /> : "n/a") },
        {
          key: "e",
          head: "Answer",
          cell: (a) => (
            <span
              className={`font-semibold ${
                a.engineer_response === "FAILED" ? "text-red" : a.engineer_response === "WORKED" ? "text-cobalt" : "text-ink-2"
              }`}
            >
              {a.engineer_response.toLowerCase()}
            </span>
          ),
        },
        { key: "t", head: "At", cell: (a) => <span className="font-mono text-[12px] text-ink-2">{clock(a.responded_at ?? a.timestamp)}</span> },
        {
          key: "x",
          head: "Excluded next",
          cell: (a) => (a.excluded_from_next_suggestion ? "yes" : "no"),
        },
      ]}
    />
  );
}

/** Structured escalation packet: everything the next tier needs, including what was already tried. */
export function EscalationPacket({ p, showHistory = true }: { p: Packet; showHistory?: boolean }) {
  const rc = p.likely_root_cause ?? {};
  const na = p.recommended_next_diagnostic_action;
  return (
    <section aria-label="Escalation packet" className="flex flex-col gap-7">
      <div className="grid gap-x-8 gap-y-3 bg-amber px-5 py-5 text-on-amber sm:px-7 lg:grid-cols-[auto_minmax(0,1fr)]">
        <div>
          <h3 className="display text-[30px] leading-none font-bold">Escalated to {p.tier}</h3>
          <p className="mt-1.5 text-[13px]">
            Packet <span className="font-mono">{p.packet_id}</span>
          </p>
        </div>
        <div className="min-w-0 lg:border-l lg:border-on-amber/25 lg:pl-8">
          <p className="text-[19px] font-semibold leading-snug">
            {p.suggested_team}
            {p.suggested_expertise ? `, ${p.suggested_expertise}` : ""}
          </p>
          <p className="mt-1 text-[14px]">Reason: {clean(p.reason)}</p>
          <p className="mt-0.5 text-[13.5px] opacity-80">
            {period(p.tier_reasons.join("; "))} Tier order {p.tier_order.join(" → ")}.
          </p>
        </div>
      </div>

      <dl className="grid gap-x-10 gap-y-6 md:grid-cols-2">
        <div>
          <dt className="annot text-ink-3">Likely root cause</dt>
          <dd className="mt-1.5 text-[15px] text-ink">
            {rc.statement ? (
              <>
                <span className="font-semibold">{clean(rc.statement)}</span>{" "}
                <span className="text-ink-2">
                  ({rc.certainty}
                  {rc.support !== undefined ? `, ${rc.support} of ${rc.of_retrieved ?? "?"} incidents` : ""})
                </span>
              </>
            ) : (
              <span className="text-ink-2">Insufficient evidence.</span>
            )}
          </dd>
        </div>
        <div>
          <dt className="annot text-ink-3">Recommended next diagnostic action</dt>
          <dd className="mt-1.5 flex flex-col gap-1 text-[15px] text-ink">
            <span className="font-semibold">{clean(na?.action) || "None available"}</span>
            {na && <ProvTag tag={/historical/.test(na.kind) ? "derived" : "missing"}>{clean(na.kind)}</ProvTag>}
          </dd>
        </div>
        <div>
          <dt className="annot text-ink-3">Clarification before escalating</dt>
          <dd className="mt-1.5 text-[14.5px] text-ink-2">
            {p.clarification?.attempted ? (
              <ul className="flex flex-col gap-1.5">
                {p.clarification.notes.map((c) => (
                  <li key={c.question}>
                    Asked &ldquo;{c.question}&rdquo;, learned <span className="font-semibold text-ink">{clean(c.learned)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              "No clarification was attempted."
            )}
          </dd>
        </div>
        <div>
          <dt className="annot text-ink-3">Do not repeat</dt>
          <dd className="mt-1.5 text-[14.5px] text-ink">
            {p.failed_approaches_do_not_repeat?.length ? (
              <ul className="flex flex-col gap-1">
                {p.failed_approaches_do_not_repeat.map((f) => (
                  <li key={f} className="text-ink-3 line-through decoration-red decoration-[1.5px]">
                    <IdLink id={f} />
                  </li>
                ))}
              </ul>
            ) : (
              <span className="text-ink-2">Nothing failed yet.</span>
            )}
          </dd>
        </div>
        {!!p.checks_performed?.length && (
          <div className="md:col-span-2">
            <dt className="annot text-ink-3">Checks performed</dt>
            <dd className="mt-1.5">
              <ul className="grid gap-x-8 gap-y-1 text-[14px] text-ink-2 md:grid-cols-2">
                {p.checks_performed.map((c) => (
                  <li key={c}>{clean(c)}</li>
                ))}
              </ul>
            </dd>
          </div>
        )}
      </dl>

      {showHistory && !!p.resolution_attempt_history?.length && (
        <div>
          <h4 className="mb-3 text-[15px] font-semibold text-ink">Resolution-attempt history</h4>
          <AttemptTable attempts={p.resolution_attempt_history} />
        </div>
      )}

      <div className="border-b border-line">
        <Disclosure title="Raw packet" meta="JSON sent to the next tier">
          <pre className="max-h-[420px] overflow-auto bg-paper-2 p-4 font-mono text-[12px] leading-relaxed text-ink-2">
            {JSON.stringify(p, null, 2)}
          </pre>
        </Disclosure>
      </div>
    </section>
  );
}
