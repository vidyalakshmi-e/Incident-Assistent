import type { ReactNode } from "react";

import { clean, pct } from "@/lib/format";

/* ------------------------------------------------------------------ distribution rows (no track) */
export function DistBars({
  dist,
  max = 5,
  format = (v: number) => pct(v),
  highlight,
}: {
  dist: Record<string, number>;
  max?: number;
  format?: (v: number) => string;
  highlight?: string | null;
}) {
  const rows = Object.entries(dist)
    .sort((a, b) => b[1] - a[1])
    .slice(0, max);
  const top = rows[0]?.[1] || 1;
  return (
    <ul className="flex flex-col gap-1.5">
      {rows.map(([k, v], i) => {
        const on = highlight ? k === highlight : i === 0;
        return (
          <li key={k} className="grid grid-cols-[minmax(5.5rem,1.5fr)_minmax(2rem,1fr)_2.6rem] items-center gap-2.5 text-[13.5px]">
            <span className={`truncate ${on ? "font-semibold text-ink" : k === "Unknown" ? "text-ink-3" : "text-ink-2"}`} title={k}>
              {clean(k)}
            </span>
            <span className="relative h-2">
              <span
                className="absolute inset-y-0 left-0"
                style={{ width: `${Math.max(1.5, (v / top) * 100)}%`, background: on ? "var(--ink)" : "var(--line-2)" }}
              />
            </span>
            <span className={`num text-right ${on ? "font-semibold text-ink" : "text-ink-3"}`}>{format(v)}</span>
          </li>
        );
      })}
    </ul>
  );
}

/* ------------------------------------------------------------------ interval plot (point + 95% CI) */
export function Interval({
  value,
  low,
  high,
  max,
  tone = "ink",
}: {
  value: number;
  low: number;
  high: number;
  max: number;
  tone?: "ink" | "cobalt";
}) {
  const P = (v: number) => `${(v / max) * 100}%`;
  const c = tone === "cobalt" ? "var(--cobalt)" : "var(--ink)";
  return (
    <span className="relative block h-4" aria-label={`${pct(value, 1)} (95% CI ${pct(low, 1)} to ${pct(high, 1)})`}>
      <span className="absolute top-1/2 h-px -translate-y-1/2" style={{ left: P(low), width: `calc(${P(high)} - ${P(low)})`, background: c }} />
      <span className="absolute top-1/2 h-2.5 w-px -translate-y-1/2" style={{ left: P(low), background: c }} />
      <span className="absolute top-1/2 h-2.5 w-px -translate-y-1/2" style={{ left: P(high), background: c }} />
      <span
        className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full"
        style={{ left: P(value), background: c, boxShadow: "0 0 0 2px var(--sheet)" }}
      />
    </span>
  );
}

export function Axis({ max, ticks = 4, format = (v: number) => pct(v) }: { max: number; ticks?: number; format?: (v: number) => string }) {
  return (
    <span className="relative block h-4">
      {Array.from({ length: ticks + 1 }, (_, i) => (i * max) / ticks).map((t, i) => (
        <span
          key={t}
          className="num absolute top-0 text-[11px] text-ink-3"
          style={{ left: `${(t / max) * 100}%`, transform: i === 0 ? "none" : i === ticks ? "translateX(-100%)" : "translateX(-50%)" }}
        >
          {format(t)}
        </span>
      ))}
    </span>
  );
}

/* ------------------------------------------------------------------ vertical bars */
export function Bars({
  data,
  height = 170,
  color = () => "var(--ink)",
  marker,
  yLabel,
  labelEvery = 1,
}: {
  data: { key: string; value: number }[];
  height?: number;
  color?: (d: { key: string; value: number }) => string;
  marker?: { index: number; label: string };
  yLabel?: string;
  labelEvery?: number;
}) {
  const W = 640;
  const padL = 34;
  const padB = 22;
  const H = height;
  const maxV = Math.max(1, ...data.map((d) => d.value));
  const bw = (W - padL) / Math.max(1, data.length);
  const padT = 16;
  const Y = (v: number) => padT + (H - padB - padT) * (1 - v / maxV);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={yLabel ?? "bar chart"}>
      <line x1={padL} y1={H - padB} x2={W} y2={H - padB} stroke="var(--ink-3)" />
      <line x1={padL} y1={Y(maxV)} x2={W} y2={Y(maxV)} stroke="var(--line)" strokeDasharray="3 4" />
      <text x={padL - 6} y={Y(maxV) + 4} textAnchor="end" className="num" style={{ fontSize: 11, fill: "var(--ink-3)" }}>
        {Math.round(maxV).toLocaleString("en-US")}
      </text>
      <text x={padL - 6} y={H - padB} textAnchor="end" className="num" style={{ fontSize: 11, fill: "var(--ink-3)" }}>
        0
      </text>
      {data.map((d, i) => (
        <g key={d.key}>
          <rect
            x={padL + i * bw + bw * 0.14}
            y={Y(d.value)}
            width={bw * 0.72}
            height={Math.max(0, H - padB - Y(d.value))}
            fill={color(d)}
          >
            <title>{`${d.key}: ${d.value.toLocaleString("en-US")}`}</title>
          </rect>
          {i % labelEvery === 0 && (
            <text x={padL + i * bw + bw / 2} y={H - 6} textAnchor="middle" className="num" style={{ fontSize: 10.5, fill: "var(--ink-3)" }}>
              {d.key}
            </text>
          )}
        </g>
      ))}
      {marker && (
        <g>
          <line
            x1={padL + marker.index * bw}
            y1={4}
            x2={padL + marker.index * bw}
            y2={H - padB}
            stroke="var(--red)"
            strokeWidth="1.6"
            strokeDasharray="4 3"
          />
          <text x={padL + marker.index * bw + 5} y={12} className="annot" style={{ fontSize: 10.5, fill: "var(--red)" }}>
            {marker.label}
          </text>
        </g>
      )}
    </svg>
  );
}

/* ------------------------------------------------------------------ proportion bar */
export function Proportion({
  parts,
  legend = true,
}: {
  parts: { key: string; value: number; color: string; label?: ReactNode }[];
  legend?: boolean;
}) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1;
  return (
    <div>
      <div className="flex h-3 w-full gap-px overflow-hidden">
        {parts.map((p) => (
          <span key={p.key} style={{ width: `${(p.value / total) * 100}%`, background: p.color }} title={`${p.key}: ${p.value}`} />
        ))}
      </div>
      {legend && (
        <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-ink-2">
          {parts.map((p) => (
            <span key={p.key} className="inline-flex items-center gap-1.5">
              <span className="inline-block size-2.5" style={{ background: p.color }} />
              {p.label ?? p.key}
              <span className="num font-semibold text-ink">{p.value.toLocaleString("en-US")}</span>
              <span className="num text-ink-3">{pct(p.value / total)}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
