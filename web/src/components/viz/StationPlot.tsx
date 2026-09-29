import { clean, label } from "@/lib/format";
import type { Fingerprint } from "@/lib/types";

import { ProvTag, provKind } from "../ui/ProvTag";

const LEFT = ["component", "service", "dependency", "environment", "trigger"];
const RIGHT = ["symptom", "failure_type", "root_cause", "business_impact", "impact_scope"];
const ROW = 66;

const spoke: Record<string, { stroke: string; dash?: string; width: number }> = {
  original: { stroke: "var(--ink)", width: 1.6 },
  observed: { stroke: "var(--ink)", width: 1.6 },
  derived: { stroke: "var(--teal)", dash: "5 3", width: 1.6 },
  synthetic: { stroke: "var(--amber)", width: 2.4 },
  inferred: { stroke: "var(--violet)", dash: "0.1 4", width: 2 },
  missing: { stroke: "var(--line-2)", dash: "1 3", width: 1 },
};

function Cell({ field, fp, align }: { field: string; fp: Fingerprint; align: "left" | "right" }) {
  const v = fp.values[field];
  const known = v && v !== "Unknown";
  const ev = fp.evidence?.[field];
  return (
    <div
      className={`flex h-[66px] min-w-0 flex-col justify-center ${align === "right" ? "items-end text-right" : "items-start text-left"}`}
      title={ev ? `Evidence: ${clean(ev)}` : undefined}
    >
      <span className="annot text-ink-3">{label(field)}</span>
      <span className={`mt-0.5 max-w-full truncate text-[14px] leading-snug ${known ? "font-semibold text-ink" : "text-ink-3"}`} title={known ? clean(v) : undefined}>
        {known ? clean(v) : "unknown"}
      </span>
      {known && <ProvTag tag={fp.provenance[field]} className="mt-1" />}
    </div>
  );
}

/**
 * The enriched fingerprint drawn as a station plot. Ten fields hang off a station circle whose
 * fill shows the share of fields with a value (read like cloud cover in oktas); each spoke is drawn
 * in its field's provenance notation. Unknown fields stay unknown: nothing is invented.
 */
export function StationPlot({ fp }: { fp: Fingerprint }) {
  const fields = [...LEFT, ...RIGHT];
  const known = fields.filter((f) => fp.values[f] && fp.values[f] !== "Unknown").length;
  const frac = known / fields.length;
  const H = ROW * 5;
  const W = 150;
  const cx = W / 2;
  const cy = H / 2;
  const r = 24;
  const a = frac * 2 * Math.PI;
  const wedge =
    frac >= 1
      ? null
      : `M${cx},${cy} L${cx},${cy - r} A${r},${r} 0 ${a > Math.PI ? 1 : 0} 1 ${cx + r * Math.sin(a)},${cy - r * Math.cos(a)} Z`;

  return (
    <div>
      <div className="grid grid-cols-[minmax(0,1fr)_150px_minmax(0,1fr)] items-start gap-x-2">
        <div>
          {LEFT.map((f) => (
            <Cell key={f} field={f} fp={fp} align="right" />
          ))}
        </div>
        <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} aria-hidden className="overflow-visible">
          {[LEFT, RIGHT].map((col, ci) =>
            col.map((f, i) => {
              const y = ROW * i + ROW / 2;
              const x = ci === 0 ? 0 : W;
              const ang = Math.atan2(y - cy, x - cx);
              const s = spoke[provKind(fp.values[f] === "Unknown" ? "missing" : fp.provenance[f])];
              return (
                <line
                  key={f}
                  x1={cx + (r + 4) * Math.cos(ang)}
                  y1={cy + (r + 4) * Math.sin(ang)}
                  x2={x}
                  y2={y}
                  stroke={s.stroke}
                  strokeWidth={s.width}
                  strokeDasharray={s.dash}
                  strokeLinecap="round"
                />
              );
            }),
          )}
          <circle cx={cx} cy={cy} r={r} fill="var(--sheet)" stroke="var(--ink)" strokeWidth="2" />
          {frac >= 1 ? (
            <circle cx={cx} cy={cy} r={r} fill="var(--ink)" />
          ) : (
            frac > 0 && wedge && <path d={wedge} fill="var(--ink)" />
          )}
        </svg>
        <div>
          {RIGHT.map((f) => (
            <Cell key={f} field={f} fp={fp} align="left" />
          ))}
        </div>
      </div>

      <p className="mt-4 text-[12.5px] leading-snug text-ink-3">
        {known} of 10 fields have a value; the circle fills in proportion, like cloud cover on a
        station plot. Spokes use the provenance notation.
      </p>
    </div>
  );
}
