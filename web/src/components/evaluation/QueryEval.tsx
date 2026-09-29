import Link from "next/link";

import { clean, fixed } from "@/lib/format";
import type { QueryEvaluation } from "@/lib/types";

type Grade = QueryEvaluation["grade"];

// Good reads as the app's positive colour (cobalt), Fair as caution (amber), Poor as alert (red).
export const GRADE: Record<Grade, { text: string; bar: string; word: string }> = {
  good: { text: "text-cobalt", bar: "bg-cobalt", word: "Relevant query" },
  fair: { text: "text-amber-ink", bar: "bg-amber", word: "Partly relevant" },
  poor: { text: "text-red", bar: "bg-red", word: "Not answerable" },
};

export function GradeTag({ grade, label }: { grade: Grade; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 font-bold ${GRADE[grade].text}`}>
      <span aria-hidden className={`inline-block size-2.5 ${GRADE[grade].bar}`} />
      {label}
    </span>
  );
}

/** A 0 to 1 bar. `bands` draws the Fair and Good cut-offs as hairlines. */
function Bar({ value, tone, bands }: { value: number | null; tone: string; bands?: { good: number; fair: number } }) {
  return (
    <div
      role="img"
      aria-label={value === null ? "not available" : `${Math.round(value * 100)} out of 100`}
      className="relative h-2 w-full bg-paper-2"
    >
      {value !== null && <div className={`absolute inset-y-0 left-0 ${tone}`} style={{ width: `${Math.max(0.5, value * 100)}%` }} />}
      {bands &&
        [bands.fair, bands.good].map((b) => (
          <span key={b} aria-hidden className="absolute -inset-y-1 w-px bg-line-2" style={{ left: `${b * 100}%` }} />
        ))}
    </div>
  );
}

/** Full evaluation of one query: grade, score, what the score is made of, and how to improve the query. */
export function EvalCard({ e, query }: { e: QueryEvaluation; query?: string }) {
  const g = GRADE[e.grade];
  return (
    <section aria-label="Query evaluation" className="border border-line-2 bg-sheet">
      <div className="grid gap-x-10 gap-y-4 px-5 py-5 lg:grid-cols-[15rem_minmax(0,1fr)]">
        <div>
          <p className="annot text-ink-3">{g.word}</p>
          <p className={`display mt-1 text-[34px] leading-none font-bold ${g.text}`}>{e.label}</p>
          <p className="num mt-2 text-[15px] text-ink-2">
            score <span className="font-semibold text-ink">{fixed(e.score, 3)}</span> of 1
          </p>
          <div className="mt-3">
            <Bar value={e.score} tone={g.bar} bands={e.bands} />
            <p className="num mt-1.5 flex justify-between text-[11.5px] text-ink-3">
              <span>0</span>
              <span>fair {fixed(e.bands.fair)}</span>
              <span>good {fixed(e.bands.good)}</span>
              <span>1</span>
            </p>
          </div>
        </div>
        <div className="min-w-0">
          {query && <p className="mb-2 truncate text-[13.5px] text-ink-3" title={query}>&ldquo;{query}&rdquo;</p>}
          <p className="max-w-[68ch] text-[15.5px] leading-relaxed text-ink">{clean(e.summary)}</p>
          {e.notes.length > 0 && (
            <ul className="mt-3 flex flex-col gap-1">
              {e.notes.map((n) => (
                <li key={n} className="text-[14px] text-amber-ink">
                  {clean(n)}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <dl className="border-t border-line px-5 pt-1 pb-3">
        {e.components.map((c) => (
          <div key={c.key} className="grid items-baseline gap-x-6 gap-y-1 border-b border-line py-2.5 last:border-b-0 lg:grid-cols-[15rem_minmax(0,1fr)_4rem]">
            <dt className="text-[14px] font-semibold text-ink">{c.label}</dt>
            <dd className="min-w-0">
              <Bar value={c.value} tone="bg-ink" />
              <span className="mt-1 block text-[12.5px] text-ink-3">{clean(c.detail)}</span>
            </dd>
            <dd className="num text-right text-[15px] font-semibold text-ink">{fixed(c.value, 3)}</dd>
          </div>
        ))}
      </dl>
      <p className="border-t border-line px-5 py-2.5 text-[12.5px] text-ink-3">{clean(e.basis)}</p>
    </section>
  );
}

/** One line under the Assistant's verdict: the grade of this query and a way into the breakdown. */
export function EvalStrip({ e }: { e: QueryEvaluation }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border border-line-2 bg-sheet px-4 py-2.5">
      <span className="annot text-ink-3">Query evaluation</span>
      <span className="text-[15px]">
        <GradeTag grade={e.grade} label={e.label} />
      </span>
      <span className="num text-[14px] font-semibold text-ink">{fixed(e.score, 3)}</span>
      <span className="min-w-0 flex-1 truncate text-[13.5px] text-ink-2" title={clean(e.summary)}>
        {clean(e.summary)}
      </span>
      <Link href="/evaluation" className="text-[13.5px] font-semibold text-cobalt hover:underline">
        Details
      </Link>
    </div>
  );
}
