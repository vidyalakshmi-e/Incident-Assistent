"use client";

import { ArrowLeft } from "@phosphor-icons/react";
import { useRouter } from "next/navigation";
import useSWR from "swr";

import { fetcher } from "@/lib/api";
import { clean, date } from "@/lib/format";

import { Skel } from "../ui/States";

/* eslint-disable @typescript-eslint/no-explicit-any */
interface Record_ {
  incident: Record<string, any>;
  fingerprint: Record<string, any> | null;
}

const FIELDS: [string, string][] = [
  ["open_time", "Open time"],
  ["status", "Status"],
  ["priority", "Priority"],
  ["environment", "Environment"],
  ["impact_scope", "Affected scope"],
];

function show(k: string, v: unknown): string {
  return k === "open_time" ? date(String(v)) : clean(String(v));
}

export function IncidentView({ id }: { id: string }) {
  const router = useRouter();
  const rec = useSWR<Record_>(`/incidents/${encodeURIComponent(id)}`, fetcher);

  const back = (
    <button type="button" onClick={() => router.back()} className="inline-flex items-center gap-1.5 text-[13.5px] font-semibold text-ink-2 hover:text-cobalt">
      <ArrowLeft size={15} weight="bold" /> Back
    </button>
  );

  // A record the knowledge base does not hold is simply shown as its ID, with no warning.
  if (rec.error && rec.error.status !== 404)
    return (
      <div className="flex flex-col gap-6">
        {back}
        <p className="text-[14px] text-ink-2">This incident could not be loaded.</p>
      </div>
    );
  if (!rec.data && !rec.error)
    return (
      <div className="flex flex-col gap-5" aria-busy>
        {back}
        <Skel className="h-9 w-2/3" />
        <Skel className="h-24 w-full" />
      </div>
    );

  const inc = rec.data?.incident;
  const fp = rec.data?.fingerprint;
  const rows = FIELDS.map(([k, name]) => [name, k, inc?.[k] ?? fp?.[k]] as const).filter(
    ([, , v]) => v !== null && v !== undefined && v !== "" && v !== "Unknown",
  );

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-4">
        {back}
        <div>
          <h1 className="display text-[29px] font-bold leading-[1.15] text-ink">{clean(inc?.title) || id}</h1>
          {inc?.title && <p className="mt-1.5 font-mono text-[13px] text-ink">{inc.incident_id}</p>}
        </div>
      </header>

      {inc?.description ? (
        <p className="max-w-[65ch] text-[16px] leading-relaxed text-ink">{clean(inc.description)}</p>
      ) : (
        inc && <p className="text-[14px] text-ink-3">This record has no description text.</p>
      )}

      {rows.length > 0 && (
        <dl className="flex max-w-[520px] flex-col">
          {rows.map(([name, k, v]) => (
            <div key={k} className="grid grid-cols-[9.5rem_minmax(0,1fr)] items-baseline gap-3 border-b border-line py-1.5 text-[14px]">
              <dt className="text-ink-3">{name}</dt>
              <dd className="num min-w-0 text-ink">{show(k, v)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
