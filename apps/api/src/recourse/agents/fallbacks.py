from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from recourse.agents.schemas import ChallengeOutput, DiagnosisCause, DiagnosisHypothesisOutput, DiagnosisOutput, ObjectionReason
from recourse.domain.audit import canonical_json
from recourse.domain.models import Action, Challenge, Diagnosis, FutureEstimate, Hypothesis, ModelCallMetadata, PaymentFailureCase

CAUSE_ACTIONS = {
    DiagnosisCause.AUTHENTICATION_FRICTION: [Action.RETRY_LATER, Action.STANDARD_PAYMENT_LINK],
    DiagnosisCause.INSUFFICIENT_FUNDS_SIGNAL: [Action.NO_ACTION],
    DiagnosisCause.INSTRUMENT_RESTRICTED: [Action.STANDARD_PAYMENT_LINK],
    DiagnosisCause.INSTRUMENT_EXPIRED_OR_INVALID: [Action.STANDARD_PAYMENT_LINK],
    DiagnosisCause.NETWORK_OR_GATEWAY_TRANSIENT: [Action.RETRY_LATER],
    DiagnosisCause.METHOD_FRICTION: [Action.STANDARD_PAYMENT_LINK],
    DiagnosisCause.MERCHANT_CONFIGURATION: [Action.NO_ACTION],
    DiagnosisCause.CUSTOMER_ABORTED: [Action.NO_ACTION],
    DiagnosisCause.REPEATED_ATTEMPT_EXHAUSTION: [Action.NO_ACTION],
    DiagnosisCause.POSSIBLE_LOW_INTENT: [Action.NO_ACTION],
    DiagnosisCause.UNKNOWN: [Action.NO_ACTION],
}


def map_failure(case: PaymentFailureCase) -> DiagnosisCause:
    reason = case.failure.reason.lower()
    if "otp" in reason or "authentication" in case.failure.step.lower():
        return DiagnosisCause.AUTHENTICATION_FRICTION
    if "insufficient" in reason:
        return DiagnosisCause.INSUFFICIENT_FUNDS_SIGNAL
    if any(token in reason for token in ("expired", "invalid_card", "invalid_instrument")):
        return DiagnosisCause.INSTRUMENT_EXPIRED_OR_INVALID
    if any(token in reason for token in ("network", "timeout", "gateway")):
        return DiagnosisCause.NETWORK_OR_GATEWAY_TRANSIENT
    if "support" in reason or "method" in case.failure.step.lower():
        return DiagnosisCause.METHOD_FRICTION
    if "cancel" in reason or "abort" in reason:
        return DiagnosisCause.CUSTOMER_ABORTED
    if case.attempt_count >= 2:
        return DiagnosisCause.REPEATED_ATTEMPT_EXHAUSTION
    return DiagnosisCause.UNKNOWN


def fallback_metadata(*, purpose: str, request_id: str, reason: str, content: dict) -> ModelCallMetadata:
    content_hash = hashlib.sha256(canonical_json(content).encode()).hexdigest()
    return ModelCallMetadata(
        provider="deterministic", model=f"{purpose}-rules-v1", request_id=request_id,
        prompt_version=f"{purpose}-fallback-v1", schema_version=f"{purpose}-v1",
        latency_ms=0, response_hash=content_hash, input_hash=content_hash,
        prompt_hash=hashlib.sha256(f"{purpose}-fallback-v1".encode()).hexdigest(),
        schema_hash=hashlib.sha256(f"{purpose}-v1".encode()).hexdigest(),
        fallback_used=True, fallback_reason=reason,
    )


def diagnosis_fallback(case: PaymentFailureCase, evidence: list[dict], request_id: str, reason: str) -> Diagnosis:
    cause = map_failure(case)
    evidence_ids = [item["evidence_id"] for item in evidence if item["evidence_id"] in case.evidence_ids][:2]
    raw = DiagnosisOutput(
        status="SUPPORTED" if cause != DiagnosisCause.UNKNOWN else "INSUFFICIENT_EVIDENCE",
        hypotheses=[DiagnosisHypothesisOutput(
            cause=cause, confidence=.84 if cause != DiagnosisCause.UNKNOWN else .45,
            evidence_ids=evidence_ids, contradicting_evidence_ids=[],
        )], unknowns=["issuer_realtime_state"], evidence_quality_assessment=case.evidence_quality,
    )
    return Diagnosis(
        diagnosis_id=f"diag_{uuid.uuid4().hex}", case_id=case.case_id,
        taxonomy_version="failure-taxonomy-v1", status=raw.status,
        hypotheses=[Hypothesis(
            cause=item.cause, confidence=item.confidence, evidence_ids=item.evidence_ids,
            contradicting_evidence_ids=item.contradicting_evidence_ids, candidate_actions=CAUSE_ACTIONS[item.cause],
        ) for item in raw.hypotheses], unknowns=raw.unknowns, model="diagnosis-rules-v1",
        prompt_version="diagnose-fallback-v1", created_at=datetime.now(timezone.utc),
        model_metadata=fallback_metadata(purpose="diagnosis", request_id=request_id, reason=reason, content=raw.model_dump(mode="json")),
    )


def challenge_fallback(case: PaymentFailureCase, proposed_action: Action, futures: list[FutureEstimate], request_id: str, reason: str) -> Challenge:
    objections: list[str] = []
    if proposed_action == Action.ONE_BOUNDED_NUDGE:
        if case.opt_out or not case.contact_consent:
            objections.append(ObjectionReason.OPT_OUT)
        if case.quiet_hours:
            objections.append(ObjectionReason.QUIET_HOURS)
        if case.contacts_7d >= 2:
            objections.append(ObjectionReason.CONTACT_BUDGET)
    if proposed_action == Action.RETRY_LATER and case.attempt_count >= 2:
        objections.append(ObjectionReason.ATTEMPT_BUDGET)
    proposed = next(future for future in futures if future.action == proposed_action)
    if proposed.conservative_incremental_value_subunits <= 1000:
        objections.append(ObjectionReason.NON_POSITIVE_VALUE)
    if case.evidence_quality < .70:
        objections.append(ObjectionReason.LOW_EVIDENCE_QUALITY)
    content = {"verdict": "BLOCKING_OBJECTION" if objections else "NO_BLOCKING_OBJECTION", "objections": [str(item) for item in objections]}
    return Challenge(
        challenge_id=f"chal_{uuid.uuid4().hex}", proposed_action=proposed_action,
        verdict=content["verdict"], objections=[str(item) for item in objections],
        checks_requested=["active_link_exists", "order_already_paid", "command_idempotency"],
        evidence_ids=case.evidence_ids[2:4], unknowns=[] if objections else ["provider_health_at_execution"],
        prompt_version="challenge-fallback-v1",
        model_metadata=fallback_metadata(purpose="challenge", request_id=request_id, reason=reason, content=content),
    )
