from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from recourse.agents import run_challenge, run_diagnosis
from recourse.agents.explanations import verified_diagnosis_explanation
from recourse.config import Settings
from recourse.domain.audit import append_audit, canonical_json, sha256_json
from recourse.domain.models import (
    Action, ActionCommand, AnalyzeResponse, AuditEvent, CaseState, Challenge,
    Diagnosis, EvidenceItem, Failure, Hypothesis, PaymentFailureCase,
)
from recourse.domain.policy import decide
from recourse.domain.state_machine import require_transition
from recourse.domain.value import deterministic_futures
from recourse.persistence.tables import (
    AuditRow, CaseRow, ChallengeRow, DecisionRow, DiagnosisRow, EstimateRow,
    EvidenceRow, ExecutionRow, RawEventRow,
)


class WebhookEntity(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    amount: int = Field(ge=0)
    currency: str = "INR"
    status: str
    order_id: str | None = None
    method: str = "unknown"
    error_code: str | None = None
    error_description: str | None = None
    error_source: str | None = None
    error_step: str | None = None
    error_reason: str | None = None
    created_at: int | None = None
    notes: dict = Field(default_factory=dict)


class PaymentWrapper(BaseModel):
    model_config = ConfigDict(extra="ignore")
    entity: WebhookEntity


class WebhookPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: str
    payload: dict[str, PaymentWrapper]
    created_at: int | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def verify_signature(body: bytes, signature: str | None, secret: str) -> bool:
    if not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _customer_ref(value: str, secret: str) -> str:
    return "cust_hmac_" + hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()[:20]


EVIDENCE_FIELDS = {
    "failure_reason": ("payload.payment.entity.error_reason", lambda p: p.failure.reason),
    "failure_step": ("payload.payment.entity.error_step", lambda p: p.failure.step),
    "attempts": ("derived.attempt_count", lambda p: p.attempt_count),
    "consent": ("fixture.contact_consent", lambda p: p.contact_consent),
    "amount": ("payload.payment.entity.amount", lambda p: p.amount_subunits),
}


def _normalize(payload: WebhookPayload, event_id: str, settings: Settings, source: str) -> PaymentFailureCase:
    if payload.event != "payment.failed" or "payment" not in payload.payload:
        raise ValueError("the payment-failure normalizer accepts only payment.failed events")
    entity = payload.payload["payment"].entity
    notes = entity.notes
    customer_hash_secret = (
        settings.razorpay_webhook_secret if source == "razorpay_test_mode"
        else settings.command_signing_secret if source == "razorpay_api_verified"
        else settings.fixture_webhook_secret
    )
    occurred_at = datetime.fromtimestamp(entity.created_at or payload.created_at or int(utcnow().timestamp()), timezone.utc)
    case_id = "case_" + hashlib.sha256(f"{source}|{event_id}".encode()).hexdigest()[:24]
    evidence_ids = [f"ev_{name}_{case_id[-8:]}" for name in EVIDENCE_FIELDS]
    return PaymentFailureCase(
        case_id=case_id, source=source, source_event_id=event_id,
        payment_id=entity.id, order_id=entity.order_id, merchant_id=str(notes.get("merchant_id", "merchant_demo")),
        customer_ref=_customer_ref(
            str(notes.get("customer_ref", entity.id)),
            customer_hash_secret,
        ),
        amount_subunits=entity.amount, currency=entity.currency, status=entity.status, method=entity.method,
        failure=Failure(
            code=entity.error_code or "UNKNOWN", description=entity.error_description or "Unknown payment failure",
            source=entity.error_source or "unknown", step=entity.error_step or "unknown", reason=entity.error_reason or "unknown",
        ),
        attempt_count=int(notes.get("attempt_count", 1)), contacts_7d=int(notes.get("contacts_7d", 0)),
        opt_out=bool(notes.get("opt_out", False)), contact_consent=bool(notes.get("contact_consent", True)),
        quiet_hours=bool(notes.get("quiet_hours", False)),
        alternate_method_available=bool(notes.get("alternate_method_available", True)),
        evidence_quality=float(notes.get("evidence_quality", .92)), occurred_at=occurred_at,
        decision_at=utcnow(), evidence_ids=evidence_ids,
    )


def ingest_signed_event(session: Session, *, body: bytes, signature: str | None, event_id: str | None,
                        settings: Settings, source: str = "fixture", secret: str | None = None) -> tuple[PaymentFailureCase, bool]:
    signing_secret = secret if secret is not None else settings.fixture_webhook_secret
    if not verify_signature(body, signature, signing_secret):
        raise PermissionError("invalid webhook signature")
    if not event_id:
        raise ValueError("X-Razorpay-Event-Id is required")
    existing = session.scalar(select(CaseRow).where(CaseRow.source == source, CaseRow.source_event_id == event_id))
    if existing:
        return PaymentFailureCase.model_validate_json(existing.normalized_json), False
    try:
        payload = WebhookPayload.model_validate_json(body)
        normalized = _normalize(payload, event_id, settings, source)
    except (ValidationError, ValueError):
        raise
    now = utcnow()
    raw = RawEventRow(
        id=f"raw_{uuid.uuid4().hex}", provider_event_id=f"{source}:{event_id}", event_type=payload.event,
        raw_body=body, headers_redacted_json=canonical_json({"event_id": event_id}), signature_valid=True,
        body_sha256=hashlib.sha256(body).hexdigest(), received_at=now, processed_at=now,
    )
    row = CaseRow(
        id=normalized.case_id, source=normalized.source, source_event_id=event_id,
        payment_id=normalized.payment_id, order_id=normalized.order_id, merchant_id=normalized.merchant_id,
        customer_ref=normalized.customer_ref, amount_subunits=normalized.amount_subunits, currency=normalized.currency,
        state=CaseState.NORMALIZED, normalized_json=normalized.model_dump_json(), occurred_at=normalized.occurred_at,
        decision_at=normalized.decision_at, created_at=now, updated_at=now,
    )
    session.add_all([raw, row])
    session.flush()
    append_audit(session, case_id=normalized.case_id, event_type="CASE_INGESTED", payload={"source_event_id": event_id})
    append_audit(session, case_id=normalized.case_id, event_type="CASE_NORMALIZED", payload={"state": CaseState.NORMALIZED})
    for evidence_id, (name, (path, getter)) in zip(normalized.evidence_ids, EVIDENCE_FIELDS.items()):
        value = getter(normalized)
        item = EvidenceItem(
            evidence_id=evidence_id, case_id=normalized.case_id,
            kind="razorpay_payment_field" if source == "razorpay_test_mode" else "normalized_payment_field", path=path,
            value=value, source=f"{source}:payment.failed", observed_at=normalized.occurred_at,
            available_at=normalized.decision_at, sha256=sha256_json(value), trusted=True,
        )
        session.add(EvidenceRow(
            id=item.evidence_id, case_id=item.case_id, kind=item.kind, source_path=item.path,
            value_json=canonical_json(item.value), source=item.source, observed_at=item.observed_at,
            available_at=item.available_at, sha256=item.sha256, sensitivity=item.sensitivity,
            trusted=item.trusted, created_at=now,
        ))
    session.commit()
    return normalized, True


def _transition(session: Session, row: CaseRow, target: CaseState) -> None:
    current = CaseState(row.state)
    require_transition(current, target)
    row.state = target
    row.updated_at = utcnow()
    append_audit(session, case_id=row.id, event_type="STATE_TRANSITION", payload={"from": current, "to": target})


def _evidence_for_agents(session: Session, case_id: str) -> list[dict]:
    rows = session.scalars(select(EvidenceRow).where(EvidenceRow.case_id == case_id)).all()
    return [{
        "evidence_id": item.id, "kind": item.kind, "path": item.source_path,
        "value": json.loads(item.value_json), "source": item.source,
        "observed_at": item.observed_at, "available_at": item.available_at,
        "trusted": item.trusted,
    } for item in rows]


async def analyze_case(session: Session, case_id: str, settings: Settings) -> AnalyzeResponse:
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        session.execute(text("BEGIN IMMEDIATE"))
    row = session.get(CaseRow, case_id)
    if not row:
        raise LookupError("case not found")
    existing = session.scalar(select(DecisionRow).where(DecisionRow.case_id == case_id).order_by(DecisionRow.created_at.desc()))
    if existing:
        return get_analysis(session, case_id)
    case = PaymentFailureCase.model_validate_json(row.normalized_json)
    input_hash = sha256_json(case.model_dump(mode="json"))
    created = utcnow()
    evidence = _evidence_for_agents(session, case_id)
    diagnosis = await run_diagnosis(case, evidence, settings)
    futures = deterministic_futures(case.amount_subunits)
    proposed = max(futures, key=lambda future: future.conservative_incremental_value_subunits).action
    challenge = await run_challenge(case, evidence, futures, proposed, settings)
    explanation = verified_diagnosis_explanation(diagnosis)
    decision = decide(case, futures, test_mode=settings.test_mode)
    for state in (CaseState.DIAGNOSED, CaseState.SIMULATED, CaseState.CHALLENGED, CaseState.VERIFIED):
        _transition(session, row, state)
    terminal = CaseState(decision.status.value)
    _transition(session, row, terminal)
    session.add(DiagnosisRow(id=diagnosis.diagnosis_id, case_id=case_id, status=diagnosis.status,
                             payload_json=diagnosis.model_dump_json(), input_hash=input_hash, created_at=created))
    for future in futures:
        session.add(EstimateRow(
            id=f"est_{uuid.uuid4().hex}", case_id=case_id, action=future.action,
            probability=future.success_probability, lower=future.probability_lower, upper=future.probability_upper,
            baseline_probability=future.no_action_probability, uplift=future.uplift, uplift_lower=future.uplift_lower,
            direct_cost_subunits=future.direct_cost_subunits, downstream_cost_subunits=future.downstream_cost_subunits,
            expected_inv_subunits=future.expected_incremental_value_subunits,
            conservative_inv_subunits=future.conservative_incremental_value_subunits,
            model_version=future.model_version, calibration_version=future.calibration_version, created_at=created,
        ))
    session.add(ChallengeRow(id=challenge.challenge_id, case_id=case_id, payload_json=challenge.model_dump_json(), created_at=created))
    session.add(DecisionRow(
        id=decision.decision_id, case_id=case_id, input_hash=input_hash, selected_action=decision.selected_action,
        status=decision.status, payload_json=decision.model_dump_json(), created_at=created,
    ))
    append_audit(session, case_id=case_id, event_type="DECISION_CREATED", payload={
        "decision_id": decision.decision_id, "selected_action": decision.selected_action,
        "conservative_inv_subunits": decision.conservative_incremental_value_subunits,
    }, input_hash=input_hash, output_hash=sha256_json(decision.model_dump(mode="json")))
    append_audit(session, case_id=case_id, event_type="VERIFIED_EXPLANATION", payload=explanation,
                 input_hash=sha256_json(explanation["evidence_ids"]), output_hash=sha256_json(explanation))
    for purpose, metadata in (("DIAGNOSIS", diagnosis.model_metadata), ("CHALLENGE", challenge.model_metadata)):
        if metadata:
            append_audit(session, case_id=case_id, event_type=f"MODEL_{purpose}", payload={
                "provider": metadata.provider, "model": metadata.model,
                "request_id": metadata.request_id, "prompt_version": metadata.prompt_version,
                "schema_version": metadata.schema_version, "latency_ms": metadata.latency_ms,
                "fallback_used": metadata.fallback_used, "fallback_reason": metadata.fallback_reason,
                "prompt_hash": metadata.prompt_hash, "schema_hash": metadata.schema_hash,
            }, input_hash=metadata.input_hash, output_hash=metadata.response_hash)
    session.commit()
    return AnalyzeResponse(case_id=case_id, state=terminal, diagnosis=diagnosis, futures=futures,
                           challenge=challenge, decision=decision, trace_id=f"tr_{uuid.uuid4().hex}")


def get_analysis(session: Session, case_id: str) -> AnalyzeResponse:
    case_row = session.get(CaseRow, case_id)
    diagnosis_row = session.scalar(select(DiagnosisRow).where(DiagnosisRow.case_id == case_id).order_by(DiagnosisRow.created_at.desc()))
    challenge_row = session.scalar(select(ChallengeRow).where(ChallengeRow.case_id == case_id).order_by(ChallengeRow.created_at.desc()))
    decision_row = session.scalar(select(DecisionRow).where(DecisionRow.case_id == case_id).order_by(DecisionRow.created_at.desc()))
    if not all([case_row, diagnosis_row, challenge_row, decision_row]):
        raise LookupError("analysis not found")
    estimates = session.scalars(select(EstimateRow).where(EstimateRow.case_id == case_id)).all()
    action_order = {action.value: index for index, action in enumerate(Action)}
    estimates = sorted(estimates, key=lambda estimate: action_order[estimate.action])
    from recourse.domain.models import Decision, FutureEstimate
    futures = [FutureEstimate(
        action=e.action, success_probability=e.probability, probability_lower=e.lower,
        probability_upper=e.upper, no_action_probability=e.baseline_probability, uplift=e.uplift,
        uplift_lower=e.uplift_lower, direct_cost_subunits=e.direct_cost_subunits,
        downstream_cost_subunits=e.downstream_cost_subunits,
        expected_incremental_value_subunits=e.expected_inv_subunits,
        conservative_incremental_value_subunits=e.conservative_inv_subunits,
        model_version=e.model_version, calibration_version=e.calibration_version,
    ) for e in estimates]
    return AnalyzeResponse(
        case_id=case_id, state=CaseState(case_row.state),
        diagnosis=Diagnosis.model_validate_json(diagnosis_row.payload_json), futures=futures,
        challenge=Challenge.model_validate_json(challenge_row.payload_json),
        decision=Decision.model_validate_json(decision_row.payload_json), trace_id=f"tr_{uuid.uuid4().hex}",
    )


def build_command(case: PaymentFailureCase, decision, settings: Settings) -> ActionCommand:
    expires = utcnow() + timedelta(hours=24)
    raw_key = f"{case.case_id}|{decision.decision_id}|{decision.selected_action}"
    idempotency_key = hashlib.sha256(raw_key.encode()).hexdigest()
    unsigned = f"{decision.decision_id}|{idempotency_key}"
    signature = hmac.new(settings.command_signing_secret.encode(), unsigned.encode(), hashlib.sha256).hexdigest()
    return ActionCommand(
        command_id=f"cmd_{uuid.uuid4().hex}", decision_id=decision.decision_id,
        action=decision.selected_action, amount_subunits=case.amount_subunits, currency=case.currency,
        reference_id=f"rec_{case.case_id[-12:]}_{decision.decision_id[-12:]}", expires_at=expires,
        idempotency_key=idempotency_key, policy_signature=signature,
    )


def execute_noop(session: Session, case_id: str, settings: Settings) -> dict:
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        session.execute(text("BEGIN IMMEDIATE"))
    analysis = get_analysis(session, case_id)
    if analysis.decision.status.value != "ACTION_READY":
        return {"executed": False, "reason": analysis.decision.status, "command": None}
    existing = session.scalar(select(ExecutionRow).where(ExecutionRow.case_id == case_id))
    if existing:
        return {"executed": False, "reason": "DUPLICATE_ACTION", "command": json.loads(existing.request_redacted_json)}
    case_row = session.get(CaseRow, case_id)
    case = PaymentFailureCase.model_validate_json(case_row.normalized_json)
    command = build_command(case, analysis.decision, settings)
    _transition(session, case_row, CaseState.EXECUTING)
    target = {
        Action.STANDARD_PAYMENT_LINK: CaseState.LINK_ISSUED,
        Action.RETRY_LATER: CaseState.RETRY_SCHEDULED,
        Action.ONE_BOUNDED_NUDGE: CaseState.NUDGE_DRAFTED,
    }[command.action]
    now = utcnow()
    response = {"simulated": True, "provider_resource_id": f"sim_{command.command_id[-12:]}"}
    session.add(ExecutionRow(
        id=f"exe_{uuid.uuid4().hex}", case_id=case_id, decision_id=command.decision_id,
        command_id=command.command_id, action=command.action, idempotency_key=command.idempotency_key,
        provider_resource_id=response["provider_resource_id"], provider_status="simulated",
        request_redacted_json=command.model_dump_json(), response_redacted_json=canonical_json(response),
        started_at=now, completed_at=now,
    ))
    _transition(session, case_row, target)
    append_audit(session, case_id=case_id, event_type="ACTION_EXECUTED_NOOP", payload={
        "action": command.action, "command_id": command.command_id, **response,
    })
    session.commit()
    return {"executed": True, "reason": "SIMULATED_OFFLINE_ACTION", "command": command.model_dump(mode="json"),
            "state": target, "mode_label": "FIXTURE / OFFLINE SIMULATION — NO REAL MONEY"}


def list_audit(session: Session, case_id: str) -> list[AuditEvent]:
    rows = session.scalars(select(AuditRow).where(AuditRow.case_id == case_id).order_by(AuditRow.sequence)).all()
    return [AuditEvent(
        audit_id=r.id, case_id=r.case_id, sequence=r.sequence, event_type=r.event_type,
        actor_type=r.actor_type, actor_id=r.actor_id, input_hash=r.input_hash, output_hash=r.output_hash,
        payload_redacted=json.loads(r.payload_redacted_json), previous_event_hash=r.previous_event_hash,
        event_hash=r.event_hash, created_at=r.created_at,
    ) for r in rows]
