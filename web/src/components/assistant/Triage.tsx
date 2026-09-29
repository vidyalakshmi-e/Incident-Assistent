import { clean, pct } from "@/lib/format";
import type { Classification } from "@/lib/types";

import { DistBars } from "../viz/Charts";
import { Module, ModuleGrid } from "../ui/Page";

const KEYS = ["category", "priority", "impact", "urgency"] as const;

/** Classification with its full predicted distribution, so the probability behind each label shows. */
export function Triage({ c }: { c: Classification }) {
  return (
    <ModuleGrid cols="sm:grid-cols-2 xl:grid-cols-4">
      {KEYS.map((k) => {
        const d = c[k];
        return (
          <Module key={k}>
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-[13.5px] font-semibold text-ink-2">{k.charAt(0).toUpperCase() + k.slice(1)}</span>
              <span className="text-[12px] text-ink-3">{clean(d.provenance)}</span>
            </div>
            <p className="num mt-1 text-[22px] font-bold text-ink">
              {d.value ?? "n/a"}
              {d.probability ? <span className="ml-2 text-[14px] font-medium text-ink-3">{pct(d.probability)}</span> : null}
            </p>
            {d.distribution && (
              <div className="mt-3">
                <DistBars dist={d.distribution} max={k === "category" ? 4 : 4} highlight={d.value} />
              </div>
            )}
          </Module>
        );
      })}
    </ModuleGrid>
  );
}
