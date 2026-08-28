from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Action(StrEnum):
    NO_ACTION = "NO_ACTION"
    RETRY_LATER = "RETRY_LATER"
    STANDARD_PAYMENT_LINK = "STANDARD_PAYMENT_LINK"
    ONE_BOUNDED_NUDGE = "ONE_BOUNDED_NUDGE"


class CaseState(StrEnum):
    INGESTED = "INGESTED"
    NORMALIZED = "NORMALIZED"
    DIAGNOSED = "DIAGNOSED"
    DIAGNOSIS_ABSTAINED = "DIAGNOSIS_ABSTAINED"
    SIMULATED = "SIMULATED"
    SIMULATION_FAILED = "SIMULATION_FAILED"
    CHALLENGED = "CHALLENGED"
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    ACTION_READY = "ACTION_READY"
    NO_ACTION = "NO_ACTION"
    ABSTAIN = "ABSTAIN"
    EXECUTING = "EXECUTING"
    LINK_ISSUED = "LINK_ISSUED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    NUDGE_DRAFTED = "NUDGE_DRAFTED"
    RECOVERED = "RECOVERED"
    NOT_RECOVERED = "NOT_RECOVERED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    EVALUATED = "EVALUATED"


class DecisionStatus(StrEnum):
    ACTION_READY = "ACTION_READY"
    NO_ACTION = "NO_ACTION"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    ABSTAIN = "ABSTAIN"


class ReasonCode(StrEnum):
    MAX_CONSERVATIVE_INV = "MAX_CONSERVATIVE_INV"
    ALL_GUARDRAILS_PASS = "ALL_GUARDRAILS_PASS"
    NON_POSITIVE_VALUE = "NON_POSITIVE_VALUE"
    LOW_EVIDENCE_QUALITY = "LOW_EVIDENCE_QUALITY"
    HIGH_UNCERTAINTY = "HIGH_UNCERTAINTY"
    TEST_MODE_REQUIRED = "TEST_MODE_REQUIRED"
    TERMINAL_PAYMENT = "TERMINAL_PAYMENT"
    OPT_OUT = "OPT_OUT"
    QUIET_HOURS = "QUIET_HOURS"
    CONTACT_BUDGET_EXCEEDED = "CONTACT_BUDGET_EXCEEDED"
    INTERVENTION_BUDGET_EXCEEDED = "INTERVENTION_BUDGET_EXCEEDED"
    RETRY_BUDGET_EXCEEDED = "RETRY_BUDGET_EXCEEDED"
    ACTIVE_LINK_EXISTS = "ACTIVE_LINK_EXISTS"
    LOWER_CONSERVATIVE_INV = "LOWER_CONSERVATIVE_INV"


class Failure(StrictModel):
    code: str
    description: str
    source: str
    step: str
    reason: str


class PaymentFailureCase(StrictModel):
    case_id: str
    source: str
    source_event_id: str
    payment_id: str
    order_id: str | None = None
    merchant_id: str
    customer_ref: str
    amount_subunits: int = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    status: str
    method: str
    failure: Failure
    attempt_count: int = Field(ge=0)
    contacts_7d: int = Field(ge=0)
    opt_out: bool
    contact_consent: bool
    quiet_hours: bool
    alternate_method_available: bool
    evidence_quality: float = Field(ge=0, le=1)
    occurred_at: datetime
    decision_at: datetime
    evidence_ids: list[str]


class EvidenceItem(StrictModel):
    evidence_id: str
    case_id: str
    kind: str
    path: str
    value: Any
    source: str
    observed_at: datetime
    available_at: datetime
    sha256: str
    sensitivity: str = "operational"
    trusted: bool = True


class Hypothesis(StrictModel):
    cause: str
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str]
    contradicting_evidence_ids: list[str]
    candidate_actions: list[Action]


class ModelCallMetadata(StrictModel):
    provider: str
    model: str
    request_id: str
    prompt_version: str
    schema_version: str
    latency_ms: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    response_hash: str
    input_hash: str | None = None
    prompt_hash: str | None = None
    schema_hash: str | None = None
    repaired: bool = False
    cached: bool = False
    fallback_used: bool = False
    fallback_reason: str | None = None


class Diagnosis(StrictModel):
    diagnosis_id: str
    case_id: str
    taxonomy_version: str
    status: str
    hypotheses: list[Hypothesis]
    unknowns: list[str]
    model: str
    prompt_version: str
    created_at: datetime
    model_metadata: ModelCallMetadata | None = None


class FutureEstimate(StrictModel):
    action: Action
    success_probability: float = Field(ge=0, le=1)
    probability_lower: float = Field(ge=0, le=1)
    probability_upper: float = Field(ge=0, le=1)
    no_action_probability: float = Field(ge=0, le=1)
    uplift: float = Field(ge=-1, le=1)
    uplift_lower: float = Field(ge=-1, le=1)
    direct_cost_subunits: int = Field(ge=0)
    downstream_cost_subunits: int = Field(ge=0)
    expected_incremental_value_subunits: int
    conservative_incremental_value_subunits: int
    model_version: str
    calibration_version: str

    @model_validator(mode="after")
    def bounds_are_ordered(self) -> FutureEstimate:
        if not self.probability_lower <= self.success_probability <= self.probability_upper:
            raise ValueError("probability bounds must contain the point estimate")
        return self


class Challenge(StrictModel):
    challenge_id: str
    proposed_action: Action
    verdict: str
    objections: list[str]
    checks_requested: list[str]
    evidence_ids: list[str]
    unknowns: list[str]
    prompt_version: str
    model_metadata: ModelCallMetadata | None = None


class GuardrailResult(StrictModel):
    rule: str
    passed: bool
    action: Action | None = None
    reason_code: ReasonCode | None = None


class Decision(StrictModel):
    decision_id: str
    case_id: str
    selected_action: Action
    status: DecisionStatus
    reason_codes: list[ReasonCode]
    blocked_actions: dict[str, list[ReasonCode]]
    guardrail_results: list[GuardrailResult]
    expected_incremental_value_subunits: int
    conservative_incremental_value_subunits: int
    evidence_snapshot_hash: str
    policy_version: str
    model_versions: list[str]
    created_at: datetime


class Notify(StrictModel):
    sms: bool = False
    email: bool = False


class ActionCommand(StrictModel):
    command_id: str
    decision_id: str
    action: Action
    amount_subunits: int = Field(ge=0)
    currency: str
    reference_id: str
    expires_at: datetime
    notify: Notify = Field(default_factory=Notify)
    reminder_enable: bool = False
    idempotency_key: str
    policy_signature: str


class AuditEvent(StrictModel):
    audit_id: str
    case_id: str
    sequence: int = Field(ge=1)
    event_type: str
    actor_type: str
    actor_id: str
    input_hash: str | None = None
    output_hash: str | None = None
    payload_redacted: dict[str, Any]
    previous_event_hash: str | None = None
    event_hash: str
    created_at: datetime


class AnalyzeResponse(StrictModel):
    case_id: str
    state: CaseState
    diagnosis: Diagnosis
    futures: list[FutureEstimate]
    challenge: Challenge
    decision: Decision
    trace_id: str
