from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

from pydantic import Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from recourse.config import Settings
from recourse.domain.audit import sha256_json
from recourse.domain.models import PaymentFailureCase, StrictModel
from recourse.domain.policy import decide
from recourse.domain.value import deterministic_futures
from recourse.persistence.tables import (
    AuditRow, CaseRow, ChallengeRow, DecisionRow, DiagnosisRow, EstimateRow,
    EvidenceRow, ExecutionRow, RawEventRow,
)
from recourse.services import analyze_case, get_analysis, ingest_signed_event

ROOT = Path(__file__).resolve().parents[4]
JUDGE_FIXTURES = (
    "hero-payment-failed", "low-value-payment-failed",
    "opt-out-payment-failed", "uncertain-payment-failed",
)


class SurgeryMutations(StrictModel):
    amount_subunits: int | None = Field(default=None, ge=0, le=100_000_000)
    evidence_quality: float | None = Field(default=None, ge=0, le=1)
    opt_out: bool | None = None
    contact_consent: bool | None = None
    quiet_hours: bool | None = None
    contacts_7d: int | None = Field(default=None, ge=0, le=20)
    attempt_count: int | None = Field(default=None, ge=0, le=20)


async def reset_and_seed(session: Session, settings: Settings) -> list[str]:
    if not settings.demo_mode:
        raise PermissionError("demo mode is disabled")
    for table in (AuditRow, ExecutionRow, DecisionRow, ChallengeRow, EstimateRow,
                  DiagnosisRow, EvidenceRow, CaseRow, RawEventRow):
        session.execute(delete(table))
    session.commit()
    case_ids = []
    for fixture_id in JUDGE_FIXTURES:
        body = (ROOT / "data" / "fixtures" / f"{fixture_id}.json").read_bytes()
        signature = hmac.new(settings.fixture_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        case, _ = ingest_signed_event(
            session, body=body, signature=signature,
            event_id=f"fixture_{fixture_id}_v1", settings=settings,
        )
        await analyze_case(session, case.case_id, settings)
        case_ids.append(case.case_id)
    return case_ids


def decision_surgery(session: Session, case_id: str, mutations: SurgeryMutations,
                     settings: Settings) -> dict:
    row = session.get(CaseRow, case_id)
    if not row:
        raise LookupError("case not found")
    before = get_analysis(session, case_id)
    original = PaymentFailureCase.model_validate_json(row.normalized_json)
    changes = {key: value for key, value in mutations.model_dump().items() if value is not None}
    clone = original.model_copy(update=changes)
    futures = deterministic_futures(clone.amount_subunits)
    after = decide(clone, futures, test_mode=settings.test_mode, already_executed=False)
    clone_hash = sha256_json(clone.model_dump(mode="json"))
    comparison = {
        "selected_action": {"before": before.decision.selected_action, "after": after.selected_action},
        "status": {"before": before.decision.status, "after": after.status},
        "conservative_inv_subunits": {
            "before": before.decision.conservative_incremental_value_subunits,
            "after": after.conservative_incremental_value_subunits,
        },
    }
    return {
        "case_id": case_id, "simulation_only": True, "external_adapters_enabled": False,
        "allowed_mutations": list(SurgeryMutations.model_fields), "mutations": changes,
        "original_input_hash": sha256_json(original.model_dump(mode="json")),
        "cloned_input_hash": clone_hash,
        "decision_hash": sha256_json({"clone": clone_hash, "decision": after.model_dump(mode="json")}),
        "before": before.decision, "after": after, "futures": futures, "comparison": comparison,
    }


def load_final_evaluation() -> dict:
    path = ROOT / "evals" / "results" / "final-evaluation.json"
    if not path.is_file():
        path = ROOT / "evals" / "results" / "development-evaluation.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["artifact_file"] = path.name
    return report


def load_evaluation_replay() -> dict:
    """Build a compact, deterministic replay from the frozen per-case ledger."""
    report = load_final_evaluation()
    path = ROOT / "evals" / "results" / "final-per-case.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    by_variant = {
        variant: {row["case_id"]: row for row in rows if row["variant"] == variant}
        for variant in ("rules", "full_recourse")
    }
    cases = []
    for case_id in sorted(by_variant["full_recourse"]):
        full = by_variant["full_recourse"][case_id]
        rules = by_variant["rules"][case_id]
        cases.append({
            "case_id": case_id,
            "rules_action": rules["selected_action"],
            "full_action": full["selected_action"],
            "status": full["status"],
            "natural_recovery_subunits": full["natural_recovery_subunits"],
            "gross_recovered_subunits": full["gross_recovered_subunits"],
            "incremental_recovered_subunits": max(
                0, full["gross_recovered_subunits"] - full["natural_recovery_subunits"]
            ),
            "action_cost_subunits": full["realized_action_cost_subunits"],
            "net_value_subunits": full["realized_value_subunits"],
            "changed_by_ai": rules["selected_action"] != full["selected_action"],
            "oracle_action": full["oracle_action"],
            "latency_ms": full["latency_ms"],
        })
    rules_metrics = report["variants"]["rules"]
    full_metrics = report["variants"]["full_recourse"]
    changed = [item for item in cases if item["changed_by_ai"]]
    safety_overrides = [
        item for item in changed
        if item["rules_action"] != "NO_ACTION" and item["full_action"] == "NO_ACTION"
    ]
    correct_no_action = [
        item for item in cases
        if item["full_action"] == "NO_ACTION" and item["oracle_action"] == "NO_ACTION"
    ]
    return {
        "label": report["label"],
        "case_count": len(cases),
        "run_hash": report["per_case_sha256"],
        "download_file": path.name,
        "cases": cases,
        "ai_uplift": {
            "decisions_changed": len(changed),
            "additional_net_value_subunits": (
                full_metrics["realized_incremental_net_value_subunits"]
                - rules_metrics["realized_incremental_net_value_subunits"]
            ),
            "safety_overrides": len(safety_overrides),
            "correct_no_action": len(correct_no_action),
            "human_reviews": full_metrics["review_count"],
            "rules_net_value_subunits": rules_metrics["realized_incremental_net_value_subunits"],
            "full_net_value_subunits": full_metrics["realized_incremental_net_value_subunits"],
            "latency_p95_ms": full_metrics["latency_ms"]["p95"],
            "external_model_cost_usd": report["openrouter_summary"]["estimated_cost_usd"],
            "confidence_interval_95": full_metrics["incremental_net_value_interval"],
            "attribution_note": (
                "Frozen policy evaluation uses calibrated local models and deterministic policy. "
                "External diagnosis/challenger calls are intentionally excluded from policy selection."
            ),
        },
    }


def load_production_proof() -> dict:
    path = ROOT / "evals" / "results" / "load-test.json"
    load_test = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    return {
        "architecture": [
            {"name": "Webhook ingress", "detail": "HMAC verification before parsing; Test Mode keys only"},
            {"name": "Deduplication", "detail": "Unique provider event plus command idempotency key"},
            {"name": "Case state machine", "detail": "Monotone transitions; recovered is terminal"},
            {"name": "Agent orchestration", "detail": "Bounded schemas, cited evidence, deterministic fallback"},
            {"name": "Policy authorization", "detail": "Offline guardrails own the final action"},
            {"name": "Provider adapter", "detail": "Razorpay Test Mode, timeout reconciliation, no live keys"},
            {"name": "Audit store", "detail": "Append-only hash chain with redacted payloads"},
            {"name": "Background workers", "detail": "Webhook acknowledged before agent execution"},
            {"name": "Merchant isolation", "detail": "Merchant-scoped case and customer references"},
            {"name": "Rate limits & retries", "detail": "Bounded retries; ambiguous writes reconcile before retry"},
        ],
        "load_test": load_test,
        "business_case": {
            "target_segment": "Indian digital merchants processing 25,000+ monthly payments",
            "volume_threshold": "500+ failed payments per month",
            "expected_lift": "3–8% incremental recovery, validated merchant-by-merchant",
            "pricing": "10–15% of verified incremental net recovery; optional platform tier",
            "deployment": "One webhook, read-only payment status, and Test Mode validation in 1–2 days",
            "payback": "Within the first billing cycle when verified recovery exceeds ₹50,000/month",
            "compliance": "No autonomous refunds, live charges, card data, or unconsented outreach",
            "razorpay_fit": "Native distribution can reuse payment events, links, identity, and reconciliation while preserving merchant controls",
        },
    }
