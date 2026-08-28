from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from recourse.agents.fallbacks import CAUSE_ACTIONS, challenge_fallback, diagnosis_fallback
from recourse.agents.openrouter import OpenRouterStructuredModel
from recourse.agents.provider import StructuredModel, StructuredModelError, StructuredModelResult
from recourse.agents.schemas import ChallengeOutput, DiagnosisCause, DiagnosisOutput
from recourse.config import Settings
from recourse.domain.models import Action, Challenge, Diagnosis, FutureEstimate, Hypothesis, ModelCallMetadata, PaymentFailureCase
from recourse.evidence.resolver import EvidenceResolutionError, minimize_evidence, resolve_evidence_ids

ROOT = Path(__file__).resolve().parents[5]
TAXONOMY = [item.value for item in DiagnosisCause]


def _asset(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _schema(name: str) -> dict:
    return json.loads(_asset(f"prompts/schemas/{name}-v1.json"))


def _metadata(result: StructuredModelResult) -> ModelCallMetadata:
    return ModelCallMetadata(
        provider=result.provider, model=result.model, request_id=result.request_id,
        prompt_version=result.prompt_version, schema_version=result.schema_version,
        latency_ms=result.latency_ms, input_tokens=result.input_tokens, output_tokens=result.output_tokens,
        response_hash=result.response_hash, repaired=result.repaired, cached=result.cached,
        input_hash=result.input_hash, prompt_hash=result.prompt_hash, schema_hash=result.schema_hash,
    )


def _verify_challenge(output: ChallengeOutput, case: PaymentFailureCase,
                      proposed: FutureEstimate, settings: Settings) -> None:
    """Reject model objections that are not deterministically true in stored fields."""
    truths = {
        "NONE": True,
        "ALREADY_PAID": case.status in {"paid", "captured"},
        "TEST_MODE_REQUIRED": not settings.test_mode,
        "LOW_EVIDENCE_QUALITY": case.evidence_quality < .70,
        "OPT_OUT": case.opt_out or not case.contact_consent,
        "QUIET_HOURS": case.quiet_hours,
        "CONTACT_BUDGET": case.contacts_7d >= 2,
        "ATTEMPT_BUDGET": case.attempt_count >= 2,
        "HIGH_UNCERTAINTY": proposed.probability_upper - proposed.probability_lower > .35,
        "NON_POSITIVE_VALUE": proposed.conservative_incremental_value_subunits <= 1000,
    }
    reason = output.objection_reason.value
    if reason in {"ACTIVE_LINK_EXISTS", "PROVIDER_UNHEALTHY", "DUPLICATE_ACTION"}:
        raise EvidenceResolutionError(f"{reason} requires a deterministic provider check")
    if reason != "NONE" and not truths.get(reason, False):
        raise EvidenceResolutionError(f"unsupported objection: {reason}")
    if output.verdict == "OBJECTION" and reason == "NONE":
        raise EvidenceResolutionError("objection verdict requires a reason")
    if output.verdict == "NO_BLOCKING_OBJECTION" and reason != "NONE":
        raise EvidenceResolutionError("non-blocking verdict contradicts objection reason")


async def run_diagnosis(case: PaymentFailureCase, evidence: list[dict], settings: Settings,
                        provider: StructuredModel | None = None) -> Diagnosis:
    request_id = f"orq_diag_{uuid.uuid4().hex}"
    minimized = minimize_evidence(evidence)
    model = provider or OpenRouterStructuredModel(settings)
    input_json = {
        "failure": case.failure.model_dump(mode="json"), "method": case.method,
        "attempt_count": case.attempt_count, "evidence_quality": case.evidence_quality,
        "failure_taxonomy": TAXONOMY, "allowed_evidence_ids": [item["evidence_id"] for item in minimized],
        "known_unknowns": ["issuer_realtime_state"], "evidence": minimized,
    }
    try:
        result = await model.generate(
            schema=_schema("diagnosis"), system_prompt=_asset("prompts/diagnose-v1.txt"),
            input_json=input_json, timeout_seconds=settings.openrouter_timeout_seconds,
            request_id=request_id, purpose="diagnosis",
        )
        output = DiagnosisOutput.model_validate(result.content)
        ids = [evidence_id for item in output.hypotheses for evidence_id in (*item.evidence_ids, *item.contradicting_evidence_ids)]
        resolve_evidence_ids(ids, minimized, case.decision_at)
        if any(item.cause == DiagnosisCause.POSSIBLE_LOW_INTENT for item in output.hypotheses):
            supported = any(item["path"] == "synthetic.friction_signal" for item in minimized)
            if not supported:
                raise EvidenceResolutionError("POSSIBLE_LOW_INTENT lacks explicit synthetic behavioral evidence")
        return Diagnosis(
            diagnosis_id=f"diag_{uuid.uuid4().hex}", case_id=case.case_id,
            taxonomy_version="failure-taxonomy-v1", status=output.status,
            hypotheses=[Hypothesis(
                cause=item.cause, confidence=item.confidence, evidence_ids=item.evidence_ids,
                contradicting_evidence_ids=item.contradicting_evidence_ids,
                candidate_actions=CAUSE_ACTIONS[item.cause],
            ) for item in output.hypotheses], unknowns=output.unknowns, model=result.model,
            prompt_version=result.prompt_version, created_at=datetime.now(timezone.utc), model_metadata=_metadata(result),
        )
    except (StructuredModelError, EvidenceResolutionError, ValueError) as exc:
        reason = exc.code if isinstance(exc, StructuredModelError) else "EVIDENCE_RESOLUTION_FAILED"
        return diagnosis_fallback(case, minimized, request_id, reason)


async def run_challenge(case: PaymentFailureCase, evidence: list[dict], futures: list[FutureEstimate],
                        proposed_action: Action, settings: Settings,
                        provider: StructuredModel | None = None) -> Challenge:
    request_id = f"orq_chal_{uuid.uuid4().hex}"
    minimized = minimize_evidence(evidence)
    model = provider or OpenRouterStructuredModel(settings)
    proposed = next(future for future in futures if future.action == proposed_action)
    input_json = {
        "proposed_action": proposed_action, "future_estimate": proposed.model_dump(mode="json"),
        "state": {
            "payment_status": case.status, "test_mode": settings.test_mode, "opt_out": case.opt_out,
            "contact_consent": case.contact_consent, "quiet_hours": case.quiet_hours,
            "contacts_7d": case.contacts_7d, "attempt_count": case.attempt_count,
            "intervention_already_executed": False, "active_link_exists": False,
        },
        "policy_limits": {"max_contacts_7d": 2, "max_attempts": 1, "min_conservative_inv_subunits": 1000},
        "allowed_evidence_ids": [item["evidence_id"] for item in minimized], "evidence": minimized,
    }
    try:
        result = await model.generate(
            schema=_schema("challenge"), system_prompt=_asset("prompts/challenge-v1.txt"),
            input_json=input_json, timeout_seconds=settings.openrouter_timeout_seconds,
            request_id=request_id, purpose="challenge",
        )
        output = ChallengeOutput.model_validate(result.content)
        resolve_evidence_ids(output.evidence_ids, minimized, case.decision_at)
        _verify_challenge(output, case, proposed, settings)
        return Challenge(
            challenge_id=f"chal_{uuid.uuid4().hex}", proposed_action=proposed_action,
            verdict=output.verdict, objections=[] if output.objection_reason == "NONE" else [output.objection_reason],
            checks_requested=[item.value for item in output.missing_checks], evidence_ids=output.evidence_ids,
            unknowns=[item.value for item in output.missing_checks], prompt_version=result.prompt_version,
            model_metadata=_metadata(result),
        )
    except (StructuredModelError, EvidenceResolutionError, ValueError) as exc:
        reason = exc.code if isinstance(exc, StructuredModelError) else "EVIDENCE_RESOLUTION_FAILED"
        return challenge_fallback(case, proposed_action, futures, request_id, reason)
