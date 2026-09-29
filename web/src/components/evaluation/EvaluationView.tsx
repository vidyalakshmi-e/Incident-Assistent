"use client";

import { useState } from "react";

import { postJSON } from "@/lib/api";
import { clean, date, fixed, short } from "@/lib/format";
import { useDesk, useDeskReady, type EvalLogEntry } from "@/lib/store";
import type { QueryEvaluationResponse } from "@/lib/types";

import { Composer } from "../assistant/Composer";
import { IdLink } from "../ui/IdLink";
import { PageHeader, SectionTitle } from "../ui/Page";
import { Empty, Notice, Skel } from "../ui/States";
import { Table } from "../ui/Table";
import { EvalCard, GradeTag } from "./QueryEval";

// One of each kind of query, so the difference between a good and a bad evaluation is one click away.
const PRESETS = [
  { label: "Relevant", text: "The application is becoming slower and sometimes freezes when users try to open records. Restarting fixes it temporarily." },
  { label: "Vague", text: "the system feels slow and basic things take forever" },
  { label: "Unseen incident", text: "Robotic tape library arm is jammed and the offsite tape rotation cannot be performed." },
  { label: "Unrelated", text: "What is the best pizza recipe for a birthday party?" },
  { label: "Gibberish", text: "asdf qwerty zxcv" },
];

function componentValue(e: EvalLogEntry, key: string) {
  return e.evaluation.components.find((c) => c.key === key)?.value ?? null;
}

export function EvaluationView() {
  const ready = useDeskReady();
  const { evalLog, logEval } = useDesk();
  const [text, setText] = useState(PRESETS[0].text);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [extra, setExtra] = useState<QueryEvaluationResponse | null>(null);

  async function evaluate() {
    setBusy(true);
    setError(null);
    try {
      const res = await postJSON<QueryEvaluationResponse>("/evaluation/query", { text });
      logEval({ text, from: "evaluation", evaluation: res.evaluation });
      setExtra(res);
      setPicked(null); // show the newest entry, which is the one just added
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const shown = evalLog.find((x) => x.id === picked) ?? evalLog[0];
  const matches = extra && shown && extra.query === shown.text ? extra.top_matches : [];

  return (
    <>
      <PageHeader
        title="Query Evaluation"
        lede="Every query is scored on its own: how well the knowledge base can answer it. A clear, relevant report grades Good; an unrelated, empty or unseen one grades Poor."
      />
      <Composer
        value={text}
        onChange={setText}
        onSubmit={evaluate}
        busy={busy}
        submitLabel="Evaluate"
        presets={PRESETS}
        label="Query"
        hint="Anything you would type into the Assistant."
      />
      {error && (
        <div className="mt-4">
          <Notice tone="error" title="Evaluation failed">
            {error}
          </Notice>
        </div>
      )}

      <div className="mt-10 flex flex-col gap-10">
        {!ready ? (
          <Skel className="h-56 w-full" />
        ) : busy ? (
          <Skel className="h-56 w-full" />
        ) : shown ? (
          <div className="flex flex-col gap-6">
            <EvalCard e={shown.evaluation} query={shown.text} />
            {matches.length > 0 && (
              <section>
                <SectionTitle meta="the evidence behind the relevance score">Nearest historical incidents</SectionTitle>
                <ul className="flex flex-col">
                  {matches.map((m) => (
                    <li key={m.incident_id} className="grid grid-cols-[7.5rem_minmax(0,1fr)_auto] items-baseline gap-4 border-b border-line py-2.5">
                      <IdLink id={m.incident_id} />
                      <span className="truncate text-[14.5px] text-ink">{clean(m.title)}</span>
                      <span className="num text-[14px] text-ink-2">relevance {fixed(m.relevance, 3)}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        ) : (
          <Empty title="No query evaluated yet">
            Pick one of the examples above and press <span className="text-ink">Evaluate</span>. Queries you analyse in the
            Assistant are evaluated too and appear here.
          </Empty>
        )}

        {ready && evalLog.length > 0 && (
          <section className="border-t border-line pt-9">
            <SectionTitle meta={`${evalLog.length} this session, newest first; select a row to open it`}>Evaluated queries</SectionTitle>
            <Table
              rows={evalLog}
              rowKey={(r) => r.id}
              highlight={(r) => r.id === shown?.id}
              cols={[
                {
                  key: "q",
                  head: "Query",
                  cell: (r) => (
                    <button
                      type="button"
                      onClick={() => setPicked(r.id)}
                      className="max-w-[46ch] text-left text-ink hover:text-cobalt hover:underline"
                    >
                      {short(r.text, 90)}
                    </button>
                  ),
                },
                { key: "g", head: "Evaluation", cell: (r) => <GradeTag grade={r.evaluation.grade} label={r.evaluation.label} /> },
                { key: "s", head: "Score", align: "right", cell: (r) => <span className="font-semibold">{fixed(r.evaluation.score, 3)}</span> },
                { key: "r", head: "Relevance", align: "right", cell: (r) => fixed(componentValue(r, "relevance"), 3) },
                { key: "k", head: "P(known)", align: "right", cell: (r) => fixed(componentValue(r, "known"), 3) },
                { key: "f", head: "Fix confidence", align: "right", cell: (r) => fixed(componentValue(r, "fix"), 3) },
                { key: "from", head: "From", cell: (r) => <span className="text-ink-2">{r.from === "assistant" ? "Assistant" : "This page"}</span> },
                { key: "at", head: "Time", cell: (r) => <span className="text-ink-3">{date(r.at).slice(11)}</span> },
              ]}
            />
          </section>
        )}
      </div>
    </>
  );
}
