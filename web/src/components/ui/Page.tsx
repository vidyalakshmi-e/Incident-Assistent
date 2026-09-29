import type { ReactNode } from "react";

export function PageHeader({ title, lede, aside }: { title: ReactNode; lede?: ReactNode; aside?: ReactNode }) {
  return (
    <header className="flex flex-col gap-4 pb-6 lg:flex-row lg:items-end lg:justify-between">
      <div className="min-w-0">
        <h1 className="display text-[29px] font-bold leading-[1.1] text-ink">{title}</h1>
        {lede && <p className="mt-2 max-w-[62ch] text-[15.5px] leading-relaxed text-ink-2">{lede}</p>}
      </div>
      {aside && <div className="shrink-0">{aside}</div>}
    </header>
  );
}

export function SectionTitle({ children, meta, id }: { children: ReactNode; meta?: ReactNode; id?: string }) {
  return (
    <div id={id} className="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <h2 className="text-[18.5px] font-bold leading-tight text-ink">{children}</h2>
      {meta && <span className="text-[13.5px] text-ink-3">{meta}</span>}
    </div>
  );
}

/** Hairline module grid: modules packed edge to edge, separated by 1px rules (no padded cards). */
export function ModuleGrid({ children, cols = "sm:grid-cols-2 lg:grid-cols-4" }: { children: ReactNode; cols?: string }) {
  return (
    <div className={`grid grid-cols-1 gap-px overflow-hidden border border-line bg-line ${cols}`}>{children}</div>
  );
}

export function Module({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`bg-sheet px-4 py-3.5 ${className}`}>{children}</div>;
}

/** Dense ruled fact rows: label left, tabular value right, hairline between rows. No tiles. */
export function Facts({
  items,
  cols = "sm:grid-cols-2 lg:grid-cols-3",
}: {
  items: { label: ReactNode; value: ReactNode; sub?: ReactNode; tone?: "weak" }[];
  cols?: string;
}) {
  return (
    <dl className={`grid grid-cols-1 gap-x-10 border-t border-line-2 ${cols}`}>
      {items.map((i, n) => (
        <div key={n} className="flex items-baseline justify-between gap-4 border-b border-line py-[7px]">
          <dt className="min-w-0 text-[13.5px] leading-snug text-ink-2">
            {i.label}
            {i.sub && <span className={`block text-[12px] ${i.tone === "weak" ? "text-amber-ink" : "text-ink-3"}`}>{i.sub}</span>}
          </dt>
          <dd className="num shrink-0 text-[15px] font-semibold text-ink">{i.value}</dd>
        </div>
      ))}
    </dl>
  );
}
