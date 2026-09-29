import { clean } from "@/lib/format";
import type { TSession } from "@/lib/types";

type Mark = { kind: "failed" | "worked" | "unknown" | "current" | "open" | "clarify" | "escalated" | "novel"; title: string; sub?: string };

const glyph: Record<Mark["kind"], { stroke: string; fill: string; dash?: string }> = {
  failed: { stroke: "var(--red-fill)", fill: "var(--red-fill)" },
  worked: { stroke: "var(--cobalt-fill)", fill: "var(--cobalt-fill)" },
  unknown: { stroke: "var(--ink-3)", fill: "var(--paper-2)" },
  current: { stroke: "var(--cobalt)", fill: "var(--sheet)" },
  open: { stroke: "var(--line-2)", fill: "var(--sheet)", dash: "1.5 2.5" },
  clarify: { stroke: "var(--amber)", fill: "var(--amber)" },
  escalated: { stroke: "var(--ink)", fill: "var(--amber)" },
  novel: { stroke: "var(--red)", fill: "var(--sheet)" },
};

function marks(s: TSession): Mark[] {
  const out: Mark[] = [];
  const byRound = [...s.attempts].sort((a, b) => a.round - b.round);
  const clar = [...s.clarifications];
  for (const a of byRound) {
    const c = clar.find((q) => (q.at_round ?? 0) < a.round && !out.some((m) => m.title === q.question));
    if (c) out.push({ kind: "clarify", title: c.question, sub: c.learned ? `Learned ${c.learned}` : c.declined ? "Skipped" : "Awaiting answer" });
    const r = a.engineer_response;
    out.push({
      kind: r === "FAILED" ? "failed" : r === "WORKED" ? "worked" : r === "UNKNOWN" ? "unknown" : "current",
      title: clean(a.step_description),
      sub: r === "PENDING" ? `Round ${a.round}, waiting for your answer` : `Round ${a.round}, ${r.toLowerCase()}`,
    });
  }
  for (const c of clar) if (!out.some((m) => m.title === c.question)) out.push({ kind: "clarify", title: c.question, sub: c.learned ? `Learned ${c.learned}` : c.declined ? "Skipped" : "Awaiting answer" });
  if (s.status === "escalated" || s.escalation) out.push({ kind: "escalated", title: `Escalated to ${s.escalation?.tier ?? "next tier"}`, sub: clean(s.escalation_reason ?? s.escalation?.reason) });
  else if (s.status === "novel") out.push({ kind: "novel", title: "No historical playbook", sub: "Novel incident" });
  else if (s.status === "active" || s.status === "awaiting_clarification") {
    const used = s.attempts.length;
    for (let i = used; i < s.max_rounds; i++) out.push({ kind: "open", title: `Round ${i + 1}`, sub: "Not reached" });
  }
  return out;
}

/**
 * The session drawn as one track: every attempt stays on it after it fails, like a crease in the
 * sheet, so the current step is always read against what was already tried.
 */
export function AttemptTrack({ s }: { s: TSession }) {
  const ms = marks(s);
  return (
    <ol className="grid gap-x-3 gap-y-4" style={{ gridTemplateColumns: `repeat(${Math.max(ms.length, 3)}, minmax(0, 1fr))` }}>
      {ms.map((m, i) => {
        const g = glyph[m.kind];
        return (
          <li key={i} className="min-w-0">
            <svg height="18" className="block w-full overflow-visible" aria-hidden>
              {i < ms.length - 1 && (
                <line
                  x1="20"
                  y1="9"
                  x2="100%"
                  y2="9"
                  stroke={ms[i + 1].kind === "open" ? "var(--line-2)" : "var(--ink-3)"}
                  strokeWidth="1.5"
                  strokeDasharray={ms[i + 1].kind === "open" ? "2 4" : undefined}
                />
              )}
              {m.kind === "clarify" ? (
                <rect x="2" y="2" width="14" height="14" transform="rotate(45 9 9)" fill={g.fill} stroke={g.stroke} strokeWidth="1.5" />
              ) : (
                <circle cx="9" cy="9" r="7" fill={g.fill} stroke={g.stroke} strokeWidth="2" strokeDasharray={g.dash} />
              )}
              {m.kind === "failed" && <path d="M5.5 5.5 L12.5 12.5 M12.5 5.5 L5.5 12.5" stroke="var(--on-red)" strokeWidth="1.8" />}
              {m.kind === "worked" && <path d="M5 9.5 L8 12 L13 6.5" fill="none" stroke="var(--on-cobalt)" strokeWidth="1.9" />}
              {m.kind === "current" && <circle cx="9" cy="9" r="3" fill="var(--cobalt)" />}
            </svg>
            <p
              className={`mt-2 line-clamp-2 text-[13.5px] leading-snug ${
                m.kind === "failed" ? "text-ink-3 line-through decoration-red/70" : m.kind === "open" ? "text-ink-3" : "font-semibold text-ink"
              }`}
              title={m.title}
            >
              {m.title}
            </p>
            {m.sub && <p className="mt-0.5 line-clamp-2 text-[12.5px] text-ink-3">{m.sub}</p>}
          </li>
        );
      })}
    </ol>
  );
}
