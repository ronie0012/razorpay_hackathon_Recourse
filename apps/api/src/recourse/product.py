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
