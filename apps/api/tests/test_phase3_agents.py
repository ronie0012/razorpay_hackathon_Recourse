from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from recourse.agents.orchestrator import run_challenge, run_diagnosis
from recourse.agents.provider import StructuredModelError, StructuredModelResult
from recourse.config import Settings
from recourse.domain.models import Action, PaymentFailureCase
from recourse.domain.value import deterministic_futures
from recourse.services import WebhookPayload, _normalize


class FakeModel:
    def __init__(self, content=None, error: StructuredModelError | None = None):
        self.content = content
        self.error = error

    async def generate(self, **kwargs):
        if self.error:
            raise self.error
        return StructuredModelResult(
            content=self.content, provider="test", model="pinned/test-model",
            prompt_version=f"{kwargs['purpose']}-v1", schema_version=f"{kwargs['purpose']}-v1",
            latency_ms=3, input_tokens=10, output_tokens=5, request_id=kwargs["request_id"],
            response_hash="a" * 64, repaired=False, cached=False,
            input_hash="b" * 64, prompt_hash="c" * 64, schema_hash="d" * 64,
        )


def case_and_evidence():
    payload = WebhookPayload.model_validate_json(Path("data/fixtures/hero-payment-failed.json").read_bytes())
    case = _normalize(payload, "agent-test", Settings(), "fixture")
    evidence = [{
        "evidence_id": evidence_id, "kind": "normalized_payment_field",
        "path": f"fixture.field.{index}", "value": "trusted", "source": "fixture",
        "observed_at": case.occurred_at, "available_at": case.decision_at, "trusted": True,
    } for index, evidence_id in enumerate(case.evidence_ids)]
    return case, evidence


def test_fabricated_evidence_id_forces_safe_diagnosis_fallback():
    case, evidence = case_and_evidence()
    provider = FakeModel({
        "status": "SUPPORTED", "hypotheses": [{
            "cause": "AUTHENTICATION_FRICTION", "confidence": .9,
            "evidence_ids": ["ev_fabricated"], "contradicting_evidence_ids": [],
        }], "unknowns": [], "evidence_quality_assessment": .9,
    })
    diagnosis = asyncio.run(run_diagnosis(case, evidence, Settings(), provider))
    assert diagnosis.model_metadata.fallback_used is True
    assert diagnosis.model_metadata.fallback_reason == "EVIDENCE_RESOLUTION_FAILED"
    assert "ev_fabricated" not in diagnosis.hypotheses[0].evidence_ids


def test_unsupported_challenge_fact_is_rejected():
    case, evidence = case_and_evidence()
    futures = deterministic_futures(case.amount_subunits)
    provider = FakeModel({
        "verdict": "OBJECTION", "objection_reason": "OPT_OUT",
        "evidence_ids": [case.evidence_ids[0]], "missing_checks": [],
        "severity": "HIGH", "recommendation": "BLOCK",
    })
    challenge = asyncio.run(run_challenge(
        case, evidence, futures, Action.STANDARD_PAYMENT_LINK, Settings(), provider,
    ))
    assert challenge.model_metadata.fallback_used is True
    assert "OPT_OUT" not in challenge.objections


def test_provider_timeout_yields_complete_labeled_fallback():
    case, evidence = case_and_evidence()
    provider = FakeModel(error=StructuredModelError("OPENROUTER_TIMEOUT", "timeout", retryable=True))
    diagnosis = asyncio.run(run_diagnosis(case, evidence, Settings(), provider))
    assert diagnosis.hypotheses
    assert diagnosis.model_metadata.provider == "deterministic"
    assert diagnosis.model_metadata.fallback_reason == "OPENROUTER_TIMEOUT"
