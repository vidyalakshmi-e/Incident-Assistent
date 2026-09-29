// Response shapes of the FastAPI backend (backend/api/routes.py). Only fields the UI reads are typed;
// everything else rides along untyped.

export type Provenance = "original" | "observed" | "derived" | "synthetic" | "inferred" | "missing";

export interface Dist {
  value: string | null;
  probability?: number | null;
  distribution?: Record<string, number>;
  provenance?: string;
}

export interface Classification {
  category: Dist;
  priority: Dist;
  impact: Dist;
  urgency: Dist;
}

export interface Novelty {
  verdict: string;
  is_novel: boolean | null;
  known_probability: number | null;
  threshold: number | null;
  features?: Record<string, number>;
  contributions?: Record<string, number>;
  basis?: string;
  recommended_route?: string;
}

export interface FamilyMatch {
  family_id: string;
  name: string;
  size: number;
  status: string;
  vote_share: number;
  max_relevance: number;
  centroid_similarity: number;
  match_strength: number;
  supporting_incidents: string[];
}

export interface ChainAggLink {
  stage: string;
  statement: string;
  share?: number;
  support?: number;
  coverage?: number;
  tags?: Record<string, number>;
  tag?: string;
  evidence?: string;
}

export interface StrategyStats {
  n_incidents: number;
  reopen_rate?: number;
  reopen_ci_low?: number;
  reopen_ci_high?: number;
  median_resolution_hours?: number;
  stats_supported: boolean;
  basis: string;
}

export interface Safety {
  destructive: boolean;
  disruptive: boolean;
  allowed: boolean;
  requires_human_confirmation: boolean;
  notes: string[];
  independent_sources?: number;
}

export interface Resolution {
  strategy_key: string;
  action: string;
  step: string;
  strategy_label?: string | null;
  expected_observation?: string | null;
  supporting_incidents: string[];
  evidence?: {
    incident_id: string;
    relevance_confidence: number;
    influence_weight: number;
    quality_tier: string;
    text_provenance: string;
    note?: string;
    duplicates?: number;
  }[];
  confidence: number | null;
  confidence_components?: Record<string, number>;
  confidence_basis?: string;
  evidence_provenance?: Record<string, number>;
  kind: string;
  strategy_stats?: StrategyStats;
  safety: Safety;
  attempt_id?: string;
  round?: number;
}

export interface Strategy {
  strategy_key: string;
  pattern_id?: string;
  label: string;
  representative_note?: string;
  representative_incident?: string;
  n_incidents: number;
  share_of_documented?: number;
  closure_codes: Record<string, number>;
  text_provenance: string;
  example_incident_ids?: string[];
  n_with_outcome?: number;
  stats_supported: boolean;
  reopen_rate?: number;
  reopen_ci_low?: number;
  reopen_ci_high?: number;
  median_resolution_hours?: number;
  mean_reassignments?: number;
  basis: string;
  kind: string;
}

export interface Similar {
  rank: number;
  incident_id: string;
  title: string | null;
  description: string | null;
  resolution_notes: string | null;
  metadata: Record<string, unknown> & { category?: string; ci_name?: string; open_time?: string; closure_code?: string };
  provenance: Record<string, string>;
  quality: { score: number; tier: string; flags: string[]; influence_weight: number };
  scores: {
    semantic_similarity?: number | null;
    semantic_rank?: number | null;
    bm25_score?: number | null;
    bm25_rank?: number | null;
    rrf_score?: number;
    rerank_logit?: number | null;
    relevance_confidence: number | null;
    confidence_basis?: string;
  };
  why_retrieved: {
    summary: string;
    matched_terms: string[];
    matched_concepts: string[];
    retrievers: string[];
  };
  duplicates_collapsed: number;
  family_id?: string;
}

export interface Fingerprint {
  values: Record<string, string>;
  provenance: Record<string, string>;
  evidence: Record<string, string>;
  symptoms?: string[];
}

export interface EvidenceChain {
  subject?: string;
  query_understood: {
    original: string;
    expanded_query?: string;
    technical_concepts: string[];
    matched_phrases: { phrase: string; maps_to: string; concepts?: string[] }[];
    hints?: Record<string, string>;
    specificity?: number;
    is_vague?: boolean;
    llm_expansion?: string[];
  };
  extracted_fingerprint: Fingerprint;
  matched_incident_family: {
    status?: string;
    reason?: string;
    family_id?: string;
    name?: string;
    match_strength?: number;
    vote_share?: number;
    max_relevance?: number;
    centroid_similarity?: number;
    runner_up?: { family_id: string; name: string; match_strength: number } | null;
    nearest_family_below_threshold?: { family_id: string; name: string; match_strength: number };
  };
  retrieved_incidents: {
    incident_id?: string;
    rank?: number;
    relevance_confidence?: number | null;
    why_retrieved?: string;
    family?: string;
    text_provenance?: string;
    quality_tier?: string;
    duplicates_collapsed?: number;
    status?: string;
  }[];
  root_cause_evidence: RootCause;
  resolution_evidence: {
    status: string;
    reason?: string;
    recommended_action?: string;
    strategy_key?: string;
    confidence?: number | null;
    confidence_basis?: string;
    confidence_components?: Record<string, number>;
    evidence_provenance?: Record<string, number>;
  };
  evidence_strength: Record<string, { value: number | null; status: string; basis: string }>;
  llm_inference: {
    available: boolean;
    label?: string;
    synthesis?: { text: string } | null;
    validation?: { method: string; unsupported_steps: unknown } | null;
  };
  completeness: { populated: string[]; insufficient: string[]; ratio: number; complete_core?: boolean };
}

export interface RootCause {
  status: string;
  reason?: string;
  statement?: string;
  certainty?: string;
  share_of_retrieved?: number;
  supporting_incidents?: string[];
  fields?: string[];
  provenance_breakdown?: Record<string, number>;
  note?: string;
  tag?: string;
}

export interface AgentMessage {
  sender: string;
  recipient: string;
  intent: string;
  summary: string;
  at?: string;
}

export interface EscalationPacket {
  packet_id: string;
  created_at: string;
  incident_id: string;
  session_id: string | null;
  reason: string;
  tier: string;
  tier_reasons: string[];
  tier_order: string[];
  suggested_team: string;
  suggested_expertise: string | null;
  routing_basis?: string;
  incident_summary?: string;
  likely_root_cause?: { statement?: string; certainty?: string; support?: number; of_retrieved?: number; status?: string };
  recommended_next_diagnostic_action?: { action: string; kind: string };
  clarification?: { attempted: boolean; notes: { trigger: string; question: string; learned: string }[] };
  checks_performed?: string[];
  failed_approaches_do_not_repeat?: string[];
  resolution_attempt_history?: Attempt[];
  [k: string]: unknown;
}

/** How well the knowledge base can answer one query (backend/evaluation/query_eval.py). */
export interface QueryEvaluation {
  score: number;
  grade: "good" | "fair" | "poor";
  label: string;
  summary: string;
  components: { key: string; label: string; value: number | null; detail: string }[];
  clarity: { specificity: number; tokens: number; is_vague: boolean; recognised_terms: number };
  notes: string[];
  bands: { good: number; fair: number };
  basis: string;
}

export interface QueryEvaluationResponse {
  query: string;
  evaluation: QueryEvaluation;
  family: { family_id: string; name: string; size: number; match_strength: number } | null;
  top_matches: { incident_id: string; title: string | null; relevance: number | null }[];
  mode_labels: string[];
}

export interface Analysis {
  incident_id: string;
  classification: Classification;
  novelty: Novelty;
  pattern_family: FamilyMatch | null;
  family_causal_chain: ChainAggLink[] | null;
  likely_root_cause: RootCause;
  top_resolution: Resolution | null;
  confidence: number | null;
  llm_synthesis: { text: string } | null;
  llm_validation: Record<string, unknown> | null;
  alternatives: Resolution[];
  strategy_panel: Strategy[];
  similar_incidents: Similar[];
  fingerprint: Fingerprint;
  escalation_proposal: EscalationPacket | null;
  query_evaluation: QueryEvaluation;
  evidence_chain: EvidenceChain;
  agent_messages: AgentMessage[];
  mode_labels: string[];
  timings_ms: Record<string, number>;
}

export interface SearchResult {
  query_understanding: EvidenceChain["query_understood"];
  results: Similar[];
  novelty: Novelty;
  fingerprint: Fingerprint;
  mode_labels: string[];
  candidates_considered: number;
  timings_ms: Record<string, number>;
}

export interface Attempt {
  attempt_id: string;
  incident_id?: string;
  session_id?: string;
  round: number;
  step_description: string;
  strategy_key: string | null;
  source_incident_ids?: string[];
  expected_observation: string | null;
  engineer_response: "PENDING" | "WORKED" | "FAILED" | "UNKNOWN" | string;
  timestamp: string;
  responded_at?: string | null;
  excluded_from_next_suggestion: boolean;
  confidence?: number | null;
  notes?: string | null;
}

export interface Clarification {
  field: string;
  question: string;
  options: string[];
  trigger: string;
  reason: string;
  asked_at?: string;
  at_round?: number;
  answer?: string;
  declined?: boolean;
  learned?: string;
}

/** One escalation as the next tier (L2/L3) sees it. */
export interface EscalationItem {
  escalation_id: number;
  incident_id: string;
  session_id: string | null;
  tier: string;
  team: string;
  expertise: string | null;
  reason: string;
  escalated_at: string;
  status: "open" | "resolved";
  packet: EscalationPacket;
  resolution: {
    resolved_by: string;
    resolution_notes: string;
    root_cause: string | null;
    kb_status: string | null;
    resolved_at: string;
  } | null;
}

export interface EscalationsResponse {
  open: number;
  escalations: EscalationItem[];
}

export interface TSession {
  session_id: string;
  incident_id: string;
  status: "active" | "awaiting_clarification" | "resolved" | "escalated" | "novel" | string;
  round: number;
  max_rounds: number;
  query: string;
  current_step: Resolution | null;
  clarification: Clarification | null;
  clarifications: Clarification[];
  attempts: Attempt[];
  alternatives: { strategy_key: string; action: string; confidence: number | null }[];
  excluded_strategies: string[];
  family: { family_id: string; name: string; match_strength: number; vote_share?: number } | null;
  novelty: Novelty;
  mode_labels: string[];
  escalation: EscalationPacket | null;
  escalation_reason: string | null;
  escalation_resolution?: { resolved_by: string; resolution_notes: string; root_cause: string | null; resolved_at: string } | null;
  resolved_by: Attempt | null;
  events: ({ at: string; kind: string } & Record<string, unknown>)[];
}

export interface Postmortem {
  incident_id: string;
  generated_at: string;
  what_happened: string;
  impact: { business_impact: string; impact_scope: string; provenance?: Record<string, string> };
  timeline: { at: string; event: string }[];
  root_cause: RootCause;
  pattern?: { family_id: string; name: string; match_strength: number } | null;
  resolution_attempt_history: Attempt[];
  final_fix: Attempt | null;
  preventive_recommendations: { recommendation: string; basis: string; framing: string }[];
}

export interface KbUpdate {
  incident_id: string;
  status: string;
  quality: { score: number; tier: string; flags: string[] };
  family_id?: string;
  family_created?: boolean;
  note?: string;
  retrievable?: boolean;
}

export interface Health {
  status: string;
  llm: { available: boolean; provider: string; model: string; reason?: string | null; mode?: string };
  embeddings: { provider: string; fallback_reason: string | null };
  reranker: { provider: string; fallback_reason: string | null };
  vector_store: { ok: boolean; detail: string; label: string | null };
  knowledge_base: { records: number; families: number };
  calibration: { cross_encoder: boolean; novelty: boolean };
  triage_models: boolean;
  escalation_tiers: string[];
}

export interface FamilySummary {
  family_id: string;
  name: string;
  size: number;
  status: string;
  members_original_text: number;
  members_synthetic_text: number;
  signature: Record<string, Record<string, number>>;
  cross_symptom?: { root_cause: string; root_cause_share: number; symptoms: Record<string, number>; finding: string } | null;
  n_strategies: number;
  recurrence_finding?: string | null;
}

export interface PatternsResponse {
  families: FamilySummary[];
  meta: { k_selected: number; silhouette_sweep: Record<string, number>; n_families: number; feature_weights: string };
  cross_symptom_findings: FamilySummary[];
  proactive: {
    ci_hotspots: {
      ci_name: string;
      ci_subcategory: string;
      total_incidents: number;
      max_in_14_days: number;
      window_start: string;
      top_closure_codes: Record<string, number>;
      reopen_rate: number;
      finding: string;
    }[];
    family_transitions: {
      window_days: number;
      transitions_considered: number;
      chains: { from: string; to: string; support: number; lift: number }[];
      tag: string;
      note: string;
    };
  };
}

export interface IncidentChain {
  incident_id: string;
  available: boolean;
  reason?: string;
  temporal_ordering?: { tag: string; open_time: string; resolved_time: string; reopen_time: string | null };
  links: ChainAggLink[];
  missing_stages?: string[];
  tag_counts?: Record<string, number>;
  chain_strength?: number;
}

export interface FamilyDetail extends FamilySummary {
  causal_chain: ChainAggLink[];
  recurrence: {
    status: string;
    members?: number;
    provenance_note?: string;
    first_seen?: string;
    last_seen?: string;
    monthly_counts?: Record<string, number>;
    median_days_between?: number;
    recurring_cis?: { ci_name: string; incidents: number; repeats_within_30d: number }[];
    reopen_rate?: number;
    finding?: string;
  } | null;
  strategies: Strategy[];
  members_sample: {
    incident_id: string;
    title: string | null;
    description: string | null;
    resolution_notes: string | null;
    open_time: string | null;
    ci_name: string | null;
    description_source: string;
    quality_tier?: string;
  }[];
  example_causal_chains: (IncidentChain | null)[];
}

export interface KbEvolution {
  events: Record<string, unknown>[];
  recently_added: {
    incident_id: string;
    family_id: string;
    quality: number;
    tier: string;
    added_at: string;
    title: string | null;
    resolution_notes: string | null;
    provenance?: Record<string, string>;
  }[];
  pending_review: { incident_id: string; quality: number; flags: string[] | string; resolution_notes: string | null }[];
  pending_candidates: string[];
  mode: string;
}

// The evaluation payload is large and heterogeneous; pages index into it defensively.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Evaluation = Record<string, any>;
