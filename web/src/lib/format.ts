// Display helpers. Backend strings use em-dashes as separators; the UI shows colons instead.

export function clean(s: string | null | undefined): string {
  if (!s) return "";
  return s
    .replace(/\s+[—–]\s+/g, ": ")
    .replace(/[—–]/g, "-")
    .replace(/…/g, "...");
}

export function sentence(s: string): string {
  const t = clean(s);
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : t;
}

const ACRONYMS: Record<string, string> = {
  bm25: "BM25", rrf: "RRF", llm: "LLM", ci: "CI", kb: "KB", nli: "NLI", mrr: "MRR", rag: "RAG", ragas: "RAGAS", id: "ID",
};

/** "technical_failure" -> "Technical failure"; keeps acronyms (BM25, RRF, CI, KB, LLM). */
export function label(key: string): string {
  const t = key
    .replace(/_/g, " ")
    .split(" ")
    .map((w) => ACRONYMS[w.toLowerCase()] ?? w)
    .join(" ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Cleaned sentence that ends in exactly one full stop. */
export function period(s: string | null | undefined): string {
  const t = clean(s).trim().replace(/[.\s]+$/, "");
  return t ? `${t}.` : "";
}

/** Truncate on a word boundary. */
export function short(s: string, n: number): string {
  if (s.length <= n) return s;
  const cut = s.slice(0, n).replace(/\s+\S*$/, "");
  return `${cut || s.slice(0, n)}...`;
}

/** "Application · slow response — memory leak / heap exhaustion" */
export function familyParts(name: string | null | undefined): { scope: string; rootCause: string } {
  if (!name) return { scope: "", rootCause: "" };
  const [head, ...rest] = name.split(/\s+[—–]\s+/);
  const rootCause = rest.join(": ");
  return { scope: head.replace(/\s*·\s*/g, " · "), rootCause: rootCause || head };
}

export function fixed(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  return v.toFixed(digits);
}

export function pct(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  return `${(v * 100).toFixed(digits)}%`;
}

export function int(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  return Math.round(v).toLocaleString("en-US");
}

export function hours(v: number | null | undefined): string {
  if (v === null || v === undefined) return "n/a";
  if (v < 1) return `${Math.round(v * 60)} min`;
  if (v < 48) return `${v.toFixed(v < 10 ? 1 : 0)} h`;
  return `${(v / 24).toFixed(1)} d`;
}

export function ms(v: number | null | undefined): string {
  if (v === null || v === undefined) return "n/a";
  if (v >= 1000) return `${(v / 1000).toFixed(1)} s`;
  if (v >= 10) return `${Math.round(v)} ms`;
  return `${v.toFixed(1)} ms`;
}

export function clock(iso: string | null | undefined): string {
  if (!iso) return "";
  const t = iso.includes("T") ? iso.split("T")[1] : iso.split(" ")[1] ?? iso;
  return t.slice(0, 8);
}

export function date(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  return iso.replace("T", " ").slice(0, 16);
}

export function isIncidentId(s: string): boolean {
  return /^(IM\d{5,}|INC-\d+|TKT-\d+|NEW-[\w-]+)$/.test(s);
}

export function isFamilyId(s: string): boolean {
  return /^F\d{3,}$/.test(s);
}

/** Top entry of a share distribution, ignoring "Unknown". */
export function topShare(d: Record<string, number> | undefined): [string, number] | null {
  if (!d) return null;
  const e = Object.entries(d)
    .filter(([k]) => k !== "Unknown")
    .sort((a, b) => b[1] - a[1])[0];
  return e ?? null;
}
