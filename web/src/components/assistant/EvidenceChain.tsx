import type { ReactNode } from "react";

import { clean, familyParts, fixed, label, pct, period } from "@/lib/format";
import type { EvidenceChain as EC } from "@/lib/types";

import { IdLink } from "../ui/IdLink";
import { ProvTag } from "../ui/ProvTag";
import { ConfidenceEquation } from "./RankedFix";

function Insufficient({ reason }: { reason?: string }) {
  return (
    <p className="text-[14px] text-ink-2">
      <span className="font-semibold text-ink">Insufficient evidence.</span> {clean(reason)}
    </p>
  );
}

function Step({ title, children, tag, last = false }: { title: string; children: ReactNode; tag?: string; last?: boolean }) {
  const dash = tag === "inferred" ? "0.1 5" : tag === "derived" ? "6 4" : undefined;
  const stroke = tag === "inferred" ? "var(--violet)" : tag === "derived" ? "var(--teal)" : "var(--ink)";
  return (
    <li className="grid grid-cols-[22px_minmax(0,1fr)] gap-x-3">
      <svg width="16" className="h-full overflow-visible" aria-hidden>
        {!last && <line x1="8" y1="20" x2="8" y2="100%" stroke="var(--line-2)" strokeWidth="1.5" />}
        <circle cx="8" cy="10" r="6" fill="var(--sheet)" stroke={stroke} strokeWidth="2" strokeDasharray={dash} strokeLinecap="round" />
      </svg>
      <div className="pb-7">
        <h4 className="text-[15.5px] font-semibold text-ink">{title}</h4>
        <div className="mt-2 text-[14px] leading-relaxed text-ink-2">{children}</div>
      </div>
    </li>
  );
}

/** The formal "Why did the system recommend this?" trace, read top to bottom. */
export function EvidenceChain({ ch }: { ch: EC }) {
  const qu = ch.query_understood;
  const fp = ch.extracted_fingerprint;
  const fam = ch.matched_incident_family;
  const rc = ch.root_cause_evidence;
  const re = ch.resolution_evidence;
  const llm = ch.llm_inference;
  const known = Object.entries(fp.values).filter(([, v]) => v !== "Unknown");
  const unknown = Object.entries(fp.values).filter(([, v]) => v === "Unknown").map(([k]) => label(k).toLowerCase());

  return (
    <ol className="max-w-[900px]">
      <Step title="The report was understood as">
        {qu.technical_concepts.length ? (
          <p>
            Technical concepts: <span className="text-ink">{qu.technical_concepts.join(", ")}</span>
          </p>
        ) : (
          <p>No technical concepts matched the lexicon.</p>
        )}
        {qu.matched_phrases.length > 0 && (
          <ul className="mt-1.5 flex flex-col gap-0.5">
            {qu.matched_phrases.map((m) => (
              <li key={m.phrase}>
                &ldquo;{m.phrase}&rdquo; → <span className="text-ink">{m.maps_to}</span>
              </li>
            ))}
          </ul>
        )}
        {!!qu.llm_expansion?.length && (
          <p className="mt-1.5 flex flex-wrap items-center gap-2">
            LLM expansion: {qu.llm_expansion.join(", ")} <ProvTag tag="inferred" />
          </p>
        )}
      </Step>

      <Step title="Fingerprint extracted">
        <ul className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
          {known.map(([k, v]) => (
            <li key={k} className="flex flex-wrap items-center gap-x-2">
              <span className="text-ink-3">{label(k)}</span>
              <span className="font-semibold text-ink">{clean(v)}</span>
              <ProvTag tag={fp.provenance[k]} />
            </li>
          ))}
        </ul>
        {unknown.length > 0 && <p className="mt-1.5 text-ink-3">Unknown, nothing invented: {unknown.join(", ")}.</p>}
      </Step>

      <Step title="Incident family matched" tag="derived">
        {fam.status === "insufficient evidence" || !fam.family_id ? (
          <Insufficient reason={fam.reason} />
        ) : (
          <>
            <p>
              <IdLink id={fam.family_id} /> <span className="font-semibold text-ink">{clean(familyParts(fam.name).rootCause)}</span>
            </p>
            <p className="num mt-1">
              Match strength <span className="font-semibold text-ink">{fixed(fam.match_strength)}</span> = vote share{" "}
              {fixed(fam.vote_share)} × best relevance {fixed(fam.max_relevance)}. Centroid similarity {fixed(fam.centroid_similarity)}.
            </p>
            {fam.runner_up && (
              <p className="mt-1 text-ink-3">
                Runner-up <IdLink id={fam.runner_up.family_id} /> at {fixed(fam.runner_up.match_strength)}.
              </p>
            )}
          </>
        )}
      </Step>

      <Step title="Evidence strength, computed" tag="derived">
        <ul className="flex flex-col gap-1">
          {Object.entries(ch.evidence_strength).map(([k, v]) => (
            <li key={k} className="grid grid-cols-[9rem_4rem_minmax(0,1fr)] gap-3">
              <span className="text-ink">{label(k)}</span>
              <span className="num font-semibold text-ink">{v.value === null ? "n/a" : fixed(v.value)}</span>
              <span className="text-ink-3">{clean(v.basis)}</span>
            </li>
          ))}
        </ul>
      </Step>

      <Step title="Historical incidents used as evidence">
        <ul className="flex flex-col gap-2">
          {ch.retrieved_incidents.map((r, i) =>
            r.incident_id ? (
              <li key={r.incident_id} className="flex flex-col gap-0.5">
                <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <IdLink id={r.incident_id} />
                  <span className="num text-ink">relevance {fixed(r.relevance_confidence)}</span>
                  {r.family && <span className="text-ink-3">family {r.family}</span>}
                  <ProvTag tag={r.text_provenance}>text {r.text_provenance}</ProvTag>
                </span>
                <span className="text-[13px] text-ink-3">{clean(r.why_retrieved)}</span>
              </li>
            ) : (
              <li key={i}>
                <Insufficient />
              </li>
            ),
          )}
        </ul>
      </Step>

      <Step title="Root-cause evidence" tag="inferred">
        {rc.status !== "computed" ? (
          <Insufficient reason={rc.reason} />
        ) : (
          <>
            <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="font-semibold text-ink">{clean(rc.statement)}</span>
              <span>
                ({rc.certainty}, {pct(rc.share_of_retrieved)} of retrieved incidents)
              </span>
              <ProvTag tag="inferred">inferred for this incident</ProvTag>
            </p>
            <p className="mt-1 text-ink-3">{clean(rc.note)}</p>
          </>
        )}
      </Step>

      <Step title="Resolution evidence" tag="derived">
        {re.status !== "computed" ? (
          <Insufficient reason={re.reason} />
        ) : (
          <div className="flex flex-col gap-3">
            <p>
              <span className="font-semibold text-ink">{clean(re.recommended_action)}</span>{" "}
              {re.strategy_key && (
                <>
                  (strategy <IdLink id={re.strategy_key} />)
                </>
              )}
            </p>
            <ConfidenceEquation r={{ confidence: re.confidence ?? null, confidence_components: re.confidence_components }} />
            <p className="flex flex-wrap gap-x-4">
              <ProvTag tag="original">{re.evidence_provenance?.original ?? 0} original records</ProvTag>
              <ProvTag tag="synthetic">{re.evidence_provenance?.synthetic ?? 0} synthetic records</ProvTag>
            </p>
          </div>
        )}
      </Step>

      <Step title="LLM inference, kept apart from the evidence" tag="inferred" last>
        {!llm.available ? (
          <p>
            <span className="font-semibold text-ink">{clean(llm.label) || "LLM unavailable"}.</span> No text was generated and
            nothing above was validated by a model.
          </p>
        ) : llm.synthesis ? (
          <>
            <ProvTag tag="inferred">LLM-generated synthesis</ProvTag>
            <p className="mt-1.5 whitespace-pre-line text-ink">{llm.synthesis.text}</p>
            {llm.validation && (
              <p className="mt-1.5 text-ink-3">
                Validation: {period(llm.validation.method)} Unsupported steps: {String(llm.validation.unsupported_steps)}
              </p>
            )}
          </>
        ) : (
          <p>The LLM was available but no synthesis was produced for this request.</p>
        )}
        <p className="num mt-3 text-[13px] text-ink-3">
          {pct(ch.completeness.ratio)} of evidence fields populated
          {ch.completeness.insufficient.length ? `; insufficient: ${ch.completeness.insufficient.map((s) => label(s.split(".").pop() ?? s).toLowerCase()).join(", ")}` : ""}.
        </p>
      </Step>
    </ol>
  );
}
