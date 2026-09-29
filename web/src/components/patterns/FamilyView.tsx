"use client";

import { ArrowLeft } from "@phosphor-icons/react";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

import { fetcher } from "@/lib/api";
import { clean, familyParts } from "@/lib/format";
import type { FamilyDetail } from "@/lib/types";

import { IdLink } from "../ui/IdLink";
import { ErrorState, Skel } from "../ui/States";

export function FamilyView({ id }: { id: string }) {
  const [allMembers, setAllMembers] = useState(false);
  const { data: f, error, mutate } = useSWR<FamilyDetail>(`/patterns/${id}`, fetcher);

  const back = (
    <Link href="/patterns" className="inline-flex items-center gap-1.5 text-[13.5px] font-semibold text-ink-2 hover:text-cobalt">
      <ArrowLeft size={15} weight="bold" /> All families
    </Link>
  );
  if (error) return (<div className="flex flex-col gap-6">{back}<ErrorState error={error} onRetry={() => mutate()} /></div>);
  if (!f)
    return (
      <div className="flex flex-col gap-5" aria-busy>
        {back}
        <Skel className="h-9 w-2/3" />
        <Skel className="mt-6 h-48 w-full" />
      </div>
    );

  const fp = familyParts(f.name);

  return (
    <div className="flex flex-col gap-10">
      <header className="flex flex-col gap-4">
        {back}
        <div>
          <h1 className="display text-[31px] font-bold leading-[1.1] text-ink">{clean(fp.rootCause)}</h1>
          <p className="mt-1.5 flex items-baseline gap-3 text-[14px] text-ink-2">
            <span className="font-mono text-[13px] text-ink">{f.family_id}</span>
            <span>{fp.scope}</span>
            <span>{f.size} incidents</span>
          </p>
        </div>
      </header>

      <section>
        <ul className="flex flex-col">
          {(allMembers ? f.members_sample : f.members_sample.slice(0, 10)).map((m) => (
            <li key={m.incident_id} className="grid gap-x-5 gap-y-1 border-b border-line py-3 md:grid-cols-[7.5rem_minmax(0,1fr)]">
              <IdLink id={m.incident_id} />
              <span className="min-w-0">
                <span className="block text-[14.5px] font-semibold text-ink">{clean(m.title)}</span>
                <span className="mt-0.5 block text-[14px] leading-relaxed text-ink-2">{clean(m.description)}</span>
              </span>
            </li>
          ))}
        </ul>
        {f.members_sample.length > 10 && (
          <button
            type="button"
            onClick={() => setAllMembers(!allMembers)}
            className="mt-3 text-[14px] font-semibold text-cobalt hover:underline"
          >
            {allMembers ? "Show fewer" : `Show all ${f.members_sample.length}`}
          </button>
        )}
      </section>
    </div>
  );
}
