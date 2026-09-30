"use client";

import { useState } from "react";

import { postJSON } from "@/lib/api";
import { clean, fixed } from "@/lib/format";
import { useDesk, useDeskReady } from "@/lib/store";
import type { SearchResult } from "@/lib/types";

import { VerdictField } from "../assistant/Verdict";
import { Composer } from "../assistant/Composer";
import { IdLink } from "../ui/IdLink";
import { PageHeader, SectionTitle } from "../ui/Page";
import { Notice, Skel } from "../ui/States";

const EXAMPLES = [
  { label: "GPS time server", text: "The GPS time server in the data center lost satellite lock and trading hosts drift from UTC." },
  { label: "HR portal login loop", text: "Users cannot log in to the HR portal, they are sent back to the login page after entering credentials." },
  { label: "Tape library arm", text: "Robotic tape library arm is jammed and the offsite tape rotation cannot be performed." },
];

export function NoveltyView() {
  const ready = useDeskReady();
  const { novelty, set } = useDesk();
  const [text, setText] = useState(EXAMPLES[0].text);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function check() {
    setBusy(true);
    setError(null);
    try {
      const res = await postJSON<SearchResult>("/incidents/search", { query: text, top_k: 5 });
      set({ novelty: { text, result: res } });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const r = novelty?.result;
  const n = r?.novelty;

  return (
    <>
      <PageHeader
        title="Novel Incident Detection"
        lede="Is history similar enough to act on? If not, the incident is declared novel instead of forcing a weak match."
      />
      <Composer value={text} onChange={setText} onSubmit={check} busy={busy} submitLabel="Check novelty" presets={EXAMPLES} />
      {error && (
        <div className="mt-4">
          <Notice tone="error" title="Check failed">
            {error}
          </Notice>
        </div>
      )}

      {!ready ? null : busy ? (
        <div className="mt-10 flex flex-col gap-6" aria-busy>
          <Skel className="h-[118px] w-full rounded-none" />
          <Skel className="h-24 w-full" />
        </div>
      ) : (
        r &&
        n && (
          <div className="mt-10 flex flex-col gap-10">
            <div>
              <p className="mb-3 text-[14px] text-ink-3">&ldquo;{novelty!.text}&rdquo;</p>
              {n.is_novel === null || n.known_probability === null ? (
                <Notice tone="warn" title="Undetermined">
                  {clean(n.basis)}
                </Notice>
              ) : (
                <VerdictField novelty={n} />
              )}
            </div>
            <section>
              <SectionTitle meta={n.is_novel ? "shown for transparency, not used as a recommendation" : undefined}>
                Nearest historical incidents
              </SectionTitle>
              <ul className="flex flex-col">
                {r.results.slice(0, 3).map((x) => (
                  <li key={x.incident_id} className="border-b border-line py-2.5">
                    <div className="grid grid-cols-[7.5rem_minmax(0,1fr)_auto] items-baseline gap-4">
                      <IdLink id={x.incident_id} />
                      <span className="truncate text-[14.5px] text-ink">{clean(x.title)}</span>
                      <span className="num text-[14px] text-ink-2">relevance {fixed(x.scores.relevance_confidence, 3)}</span>
                    </div>
                    {x.description && (
                      <p className="mt-1 line-clamp-2 pl-[8.5rem] text-[13.5px] leading-relaxed text-ink-2">{clean(x.description)}</p>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          </div>
        )
      )}
    </>
  );
}
