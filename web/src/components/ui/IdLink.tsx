import Link from "next/link";

import { isFamilyId, isIncidentId } from "@/lib/format";

// Every record ID is addressable: incidents open their record, families their pattern page,
// strategy keys the strategy inside the family.
export function hrefFor(id: string): string | null {
  if (isIncidentId(id)) return `/incidents/${encodeURIComponent(id)}`;
  if (isFamilyId(id)) return `/patterns/${id}`;
  const s = /^(F\d{3,})-S\d+$/.exec(id);
  if (s) return `/patterns/${s[1]}#${id}`;
  return null;
}

export function IdLink({ id, className = "" }: { id: string; className?: string }) {
  const href = hrefFor(id);
  // Short IDs stay on one line; a long one (e.g. a strategy key "INC:NEW-20260929083305-B484") wraps inside its
  // own column instead of running into the text beside it.
  const cls = `font-mono text-[12.5px] tracking-tight ${id.length > 16 ? "[overflow-wrap:anywhere]" : "whitespace-nowrap"} ${className}`;
  if (!href) return <span className={cls}>{id}</span>;
  return (
    <Link
      href={href}
      className={`${cls} text-ink underline decoration-line-2 underline-offset-[3px] transition-colors hover:text-cobalt hover:decoration-cobalt`}
    >
      {id}
    </Link>
  );
}

export function IdList({ ids, max = 6 }: { ids: string[]; max?: number }) {
  const shown = ids.slice(0, max);
  return (
    <span className="inline-flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
      {shown.map((id) => (
        <IdLink key={id} id={id} />
      ))}
      {ids.length > max && <span className="text-[12.5px] text-ink-3">+{ids.length - max} more</span>}
    </span>
  );
}
