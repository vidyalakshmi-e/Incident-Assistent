import { clean, hours, pct } from "@/lib/format";
import type { Strategy } from "@/lib/types";

import { Axis, Interval } from "../viz/Charts";
import { IdLink } from "../ui/IdLink";
import { ProvTag } from "../ui/ProvTag";

/**
 * Resolution Strategy Intelligence: the genuinely different ways this pattern was fixed, with real
 * reopen statistics (Wilson 95% CI) where at least 20 real outcomes exist. The ranked top pick is
 * marked, never hidden, and never the only option shown here.
 */
export function StrategyPanel({ strategies, topKey }: { strategies: Strategy[]; topKey?: string | null }) {
  if (!strategies.length) {
    return <p className="text-[14px] text-ink-2">No historical strategies are recorded for this pattern.</p>;
  }
  const withStats = strategies.filter((s) => s.stats_supported && s.reopen_ci_high !== undefined);
  const max = Math.max(0.1, Math.ceil(Math.max(0, ...withStats.map((s) => s.reopen_ci_high ?? 0)) * 20) / 20);

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[760px]">
        <div className="grid grid-cols-[minmax(0,2.4fr)_5.5rem_minmax(0,1.6fr)_5.5rem] items-end gap-5 border-b border-line pb-2">
          <span className="annot text-ink-3">Strategy</span>
          <span className="annot text-right text-ink-3">Incidents</span>
          <span className="flex flex-col gap-1">
            <span className="annot text-ink-3">Reopen rate, 95% CI</span>
            <Axis max={max} />
          </span>
          <span className="annot text-right text-ink-3">Median fix</span>
        </div>
        {strategies.map((s) => {
          const top = s.strategy_key === topKey;
          return (
            <div
              key={s.strategy_key}
              id={s.strategy_key}
              className={`grid scroll-mt-24 grid-cols-[minmax(0,2.4fr)_5.5rem_minmax(0,1.6fr)_5.5rem] items-start gap-5 border-b border-line py-4 ${
                top ? "bg-cobalt-soft/60" : ""
              }`}
            >
              <div className="min-w-0 pl-1">
                <p className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                  <IdLink id={s.strategy_key} />
                  {top && <span className="text-[12.5px] font-semibold text-cobalt">Current top pick</span>}
                  <span className="text-[12.5px] text-ink-3">{clean(s.kind)}</span>
                </p>
                <p className="mt-1 text-[15px] font-semibold text-ink">{clean(s.label)}</p>
                {s.representative_note && (
                  <p className="mt-1 line-clamp-2 text-[13.5px] leading-relaxed text-ink-2">{clean(s.representative_note)}</p>
                )}
                <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] text-ink-3">
                  <ProvTag tag={s.text_provenance}>wording {s.text_provenance}</ProvTag>
                  <span>
                    closure codes{" "}
                    {Object.entries(s.closure_codes)
                      .map(([k, v]) => `${k} ${v}`)
                      .join(", ")}
                  </span>
                </p>
              </div>
              <div className="text-right">
                <p className="num text-[15px] font-semibold text-ink">{s.n_incidents}</p>
                {s.share_of_documented !== undefined && (
                  <p className="num text-[12.5px] text-ink-3">{pct(s.share_of_documented)} of fixes</p>
                )}
              </div>
              <div className="pt-1">
                {s.stats_supported && s.reopen_rate !== undefined ? (
                  <>
                    <Interval value={s.reopen_rate} low={s.reopen_ci_low ?? 0} high={s.reopen_ci_high ?? 0} max={max} tone={top ? "cobalt" : "ink"} />
                    <p className="num mt-1.5 text-[12.5px] text-ink-2">
                      {pct(s.reopen_rate, 1)} ({pct(s.reopen_ci_low, 1)} to {pct(s.reopen_ci_high, 1)})
                    </p>
                  </>
                ) : (
                  <p className="text-[12.5px] leading-snug text-ink-3">No success statistics: too few real outcomes.</p>
                )}
              </div>
              <p className="num text-right text-[14px] text-ink">{s.stats_supported ? hours(s.median_resolution_hours) : "n/a"}</p>
            </div>
          );
        })}
        <p className="mt-3 text-[12.5px] text-ink-3">
          Outcome basis: {clean(strategies.find((s) => s.stats_supported)?.basis ?? strategies[0].basis)}.
        </p>
      </div>
    </div>
  );
}
