export type Action = 'NO_ACTION' | 'RETRY_LATER' | 'STANDARD_PAYMENT_LINK' | 'ONE_BOUNDED_NUDGE'

export interface CaseSummary {
  case_id: string; amount_subunits: number; currency: string; state: string; source: string; payment_id: string;
  order_id?: string; recoverable_value_subunits: number | null; selected_action: Action | null; priority_score: number;
  natural_recovery_subunits: number; intervention_cost_subunits: number; failure_reason: string
}

export interface Readiness {
  status: string; database: string; test_mode: boolean; fixture_mode: boolean;
  openrouter_configured: boolean; razorpay_test_mode_configured: boolean;
  razorpay_test_mode_missing: string[]
}

export interface CheckoutOrder {
  order_id: string; amount_subunits: number; currency: string; key_id: string; mode_label: string
}

export interface ExecutionStatus {
  issued: boolean; case_id: string; action?: Action; provider_status?: string;
  provider_resource_id?: string; short_url?: string; error_code?: string; completed_at?: string
}

export interface CaseDetail {
  case: {
    case_id: string; source: string; amount_subunits: number; currency: string; payment_id: string; order_id?: string;
    occurred_at: string; failure: { reason: string; step: string; code: string }; evidence_quality: number;
    opt_out: boolean; contact_consent: boolean; quiet_hours: boolean; contacts_7d: number; attempt_count: number
  }
  state: string
  evidence: Array<{ evidence_id: string; path: string; value: unknown; trusted: boolean }>
}

export interface Future {
  action: Action; success_probability: number; no_action_probability: number; uplift: number; uplift_lower: number;
  probability_lower: number; probability_upper: number; direct_cost_subunits: number; downstream_cost_subunits: number;
  expected_incremental_value_subunits: number; conservative_incremental_value_subunits: number
}

export interface Decision {
  decision_id: string; selected_action: Action; status: string; reason_codes: string[];
  conservative_incremental_value_subunits: number; expected_incremental_value_subunits: number;
  evidence_snapshot_hash: string; policy_version: string;
  guardrail_results: Array<{ rule: string; passed: boolean; reason_code?: string }>
}

export interface Analysis {
  state: string
  diagnosis: { status: string; model: string; hypotheses: Array<{ cause: string; confidence: number; evidence_ids: string[] }>; unknowns: string[]; model_metadata?: { provider: string; fallback_used: boolean; fallback_reason?: string } }
  futures: Future[]
  challenge: { verdict: string; objections: string[]; checks_requested: string[]; evidence_ids: string[]; model_metadata?: { provider: string; fallback_used: boolean; fallback_reason?: string } }
  decision: Decision
}

export interface AuditEvent { sequence: number; event_type: string; event_hash: string; previous_event_hash?: string; payload_redacted: Record<string, unknown>; created_at: string }

export interface SurgeryResult {
  simulation_only: boolean; external_adapters_enabled: boolean; mutations: Record<string, unknown>;
  original_input_hash: string; cloned_input_hash: string; decision_hash: string;
  before: Decision; after: Decision; futures: Future[];
  comparison: Record<string, { before: string | number; after: string | number }>
}

export interface VariantMetrics {
  case_count: number; gross_recovered_subunits: number; natural_recovery_subunits: number;
  incremental_recovered_subunits: number; realized_incremental_net_value_subunits: number;
  expected_incremental_net_value_subunits: number | null; total_action_cost_subunits: number; recovery_roi: number;
  macro_brier: number | null; review_rate: number; abstain_rate: number; guardrail_violation_count: number;
  regret: { mean_subunits: number; median_subunits: number; p90_subunits: number; total_subunits: number; oracle_match_rate: number };
  no_action: { precision: number; recall: number; true_positive: number; false_positive: number; false_negative: number; true_negative: number }
}

export interface EvaluationReport {
  label: string; artifact_file: string; seed: number; run_timestamp: string; case_count: number;
  dataset_sha256: string; model_manifest_sha256: string; policy_hash: string;
  variants: Record<string, VariantMetrics>; ablations: Record<string, Record<string, unknown>>;
  failure_analysis: { case_id: string; selected_action: string; oracle_action: string; regret_subunits: number; explanation: string };
  freeze: { openrouter_model: string; prompt_hashes: Record<string, string> }
}

export interface ReplayCase {
  case_id: string; rules_action: Action; full_action: Action; status: string;
  natural_recovery_subunits: number; gross_recovered_subunits: number;
  incremental_recovered_subunits: number; action_cost_subunits: number;
  net_value_subunits: number; changed_by_ai: boolean; oracle_action: Action; latency_ms: number
}

export interface EvaluationReplay {
  label: string; case_count: number; run_hash: string; download_file: string; cases: ReplayCase[];
  ai_uplift: {
    decisions_changed: number; additional_net_value_subunits: number; safety_overrides: number;
    challenger_catches: number; challenger_scope: string;
    correct_no_action: number; human_reviews: number; rules_net_value_subunits: number;
    full_net_value_subunits: number; latency_p95_ms: number; external_model_cost_usd: number;
    confidence_interval_95: { lower_95: number; upper_95: number; method: string; repetitions: number };
    attribution_note: string
  }
}

export interface IntegrationProofData {
  mode: string; endpoint: string; webhook_signature_verified: boolean; payment_id: string;
  order_id?: string; event_id: string; webhook_received_at?: string; idempotency_key?: string;
  request: Record<string, unknown>; response: Record<string, unknown>;
  reconciliation: Record<string, unknown>;
  duplicate_event_suppression: { database_unique_key: string; stored_event_count: number; status: string }
}

export interface ProductionProofData {
  architecture: Array<{ name: string; detail: string }>;
  load_test: null | { label: string; run_timestamp: string; event_count: number; unique_event_count: number;
    duplicate_event_count: number; duplicate_suppression_rate: number; accepted_once_rate: number;
    throughput_events_per_second: number; p50_latency_ms: number; p95_latency_ms: number;
    estimated_compute_cost_usd: number; scope: string; run_hash: string };
  business_case: Record<string, string>
}
