import Link from "next/link";

import { clean, familyParts, fixed } from "@/lib/format";
import type { EscalationPacket, FamilyMatch, Novelty } from "@/lib/types";

/** Live analysis IDs encode their UTC issue time: NEW-yyyymmddHHMMSS-XXXX. */
function issuedAt(id?: string): string | null {
  const m = id ? /^NEW-\d{8}(\d{2})(\d{2})(\d{2})-/.exec(id) : null;
  return m ? `${m[1]}:${m[2]}:${m[3]} UTC` : null;
}

/**
 * The verdict owns a full flat field of colour: cobalt for a known pattern, red for a novel
 * incident, ink for undetermined. It is the first thing read after an analysis, and it closes
 * with an issuance line like a forecast bulletin.
 */
export function VerdictField({
  novelty,
  family,
  escalation,
  runId,
}: {
  novelty: Novelty;
  family?: Pick<FamilyMatch, "family_id" | "name" | "match_strength"> & { size?: number } | null;
  escalation?: EscalationPacket | null;
  runId?: string;
}) {
  const novel = novelty.is_novel === true;
  const undetermined = novelty.is_novel === null || novelty.known_probability === null;
  const bg = undetermined ? "bg-ink text-paper" : novel ? "bg-red-fill text-on-red" : "bg-cobalt-fill text-on-cobalt";
  const fam = familyParts(family?.name);
  const issued = issuedAt(runId);

  return (
    <section aria-label="Verdict" tabIndex={-1} className={`${bg} scroll-mt-6 outline-none`}>
      <div className="grid gap-x-8 gap-y-5 px-5 pt-5 pb-4 sm:px-7 sm:pt-6 lg:grid-cols-[minmax(0,15rem)_minmax(0,1fr)_auto]">
        <div>
          <h2 className="display text-[27px] font-bold leading-[1.05]">
            {undetermined ? "Undetermined" : novel ? "Novel incident" : "Known pattern"}
          </h2>
          <p className="mt-1.5 text-[14px] leading-snug opacity-85">
            {undetermined
              ? clean(novelty.basis)
              : novel
                ? "No sufficiently similar history. No low-confidence fix is forced."
                : "Matched to historical incidents."}
          </p>
        </div>

        <div className="min-w-0 border-current/25 lg:border-l lg:pl-8">
          {!novel && !undetermined && family && (
            <>
              <p className="text-[20px] font-semibold leading-snug">{clean(fam.rootCause)}</p>
              <p className="mt-1 text-[13.5px] opacity-85">
                Pattern family{" "}
                <Link href={`/patterns/${family.family_id}`} className="font-mono font-semibold underline underline-offset-[3px]">
                  {family.family_id}
                </Link>
                , {fam.scope}
                {family.size ? `, ${family.size} incidents` : ""}, match strength {fixed(family.match_strength)}
              </p>
            </>
          )}
          {novel && (
            <>
              <p className="text-[20px] font-semibold leading-snug">{clean(novelty.recommended_route) || "Fresh investigation"}</p>
              <p className="mt-1 text-[13.5px] opacity-85">
                Recommended route
                {escalation
                  ? `, proposed ${escalation.tier} to ${escalation.suggested_team}${
                      escalation.tier_reasons?.length ? ` (${clean(escalation.tier_reasons.join("; "))})` : ""
                    }`
                  : ""}
                .
              </p>
              {family && (
                <p className="mt-1 text-[13.5px] opacity-85">
                  Nearest family {family.family_id} matches at {fixed(family.match_strength)}, below the threshold, so it is not used as evidence.
                </p>
              )}
            </>
          )}
        </div>

        {!undetermined && (
          <div className="lg:text-right">
            <p className="num display text-[34px] font-bold leading-none">{fixed(novelty.known_probability, 3)}</p>
            <p className="num mt-1.5 text-[13px] opacity-85">
              P(known pattern), {novel ? "below" : "above"} the validated threshold {fixed(novelty.threshold, 3)}
            </p>
          </div>
        )}
      </div>
      {runId && (
        <p className="num flex flex-wrap gap-x-4 border-t border-current/20 px-5 py-2 text-[12.5px] opacity-80 sm:px-7">
          <span>
            Analysis{" "}
            <Link href={`/incidents/${encodeURIComponent(runId)}`} className="font-mono underline underline-offset-[3px]">
              {runId}
            </Link>
          </span>
          {issued && <span>issued {issued}</span>}
          <span>valid for the knowledge base as indexed at issue</span>
        </p>
      )}
    </section>
  );
}
