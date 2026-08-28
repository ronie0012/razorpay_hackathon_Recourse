from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path

from recourse.agents import run_diagnosis
from recourse.config import get_settings
from recourse.domain.audit import canonical_json
from recourse.persistence.database import Base, SessionLocal, engine
from recourse.persistence.tables import ExecutionRow
from recourse.product import reset_and_seed
from recourse.razorpay.adapter import HttpRazorpayClient, execute_action
from recourse.razorpay.gateway import process_razorpay_webhook
from recourse.services import EVIDENCE_FIELDS, WebhookPayload, _normalize

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evals" / "results"
EPHEMERAL_WEBHOOK_SECRET = "live-validation-local-reconciliation-secret"


def write_artifact(name: str, content: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / name).write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")


async def openrouter_validation() -> dict:
    settings = get_settings().model_copy(update={"openrouter_timeout_seconds": 30.0, "openrouter_max_tokens": 2000})
    body = (ROOT / "data" / "fixtures" / "hero-payment-failed.json").read_bytes()
    payload = WebhookPayload.model_validate_json(body)
    case = _normalize(payload, "live-openrouter-validation", settings, "fixture")
    evidence = []
    for evidence_id, (_name, (path, getter)) in zip(case.evidence_ids, EVIDENCE_FIELDS.items()):
        evidence.append({
            "evidence_id": evidence_id, "kind": "normalized_payment_field", "path": path,
            "value": getter(case), "source": "signed_fixture", "observed_at": case.occurred_at,
            "available_at": case.decision_at, "trusted": True,
        })
    diagnosis = await run_diagnosis(case, evidence, settings)
    metadata = diagnosis.model_metadata
    result = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(), "purpose": "live_openrouter_schema_and_evidence_gate",
        "passed": bool(metadata and metadata.provider == "openrouter" and not metadata.fallback_used),
        "provider": metadata.provider if metadata else None, "model": metadata.model if metadata else None,
        "fallback_used": metadata.fallback_used if metadata else None,
        "fallback_reason": metadata.fallback_reason if metadata else None,
        "repaired": metadata.repaired if metadata else None, "cached": metadata.cached if metadata else None,
        "latency_ms": metadata.latency_ms if metadata else None,
        "input_tokens": metadata.input_tokens if metadata else None, "output_tokens": metadata.output_tokens if metadata else None,
        "input_hash": metadata.input_hash if metadata else None, "prompt_hash": metadata.prompt_hash if metadata else None,
        "schema_hash": metadata.schema_hash if metadata else None, "response_hash": metadata.response_hash if metadata else None,
        "diagnosis_status": diagnosis.status,
        "resolved_evidence_count": sum(len(item.evidence_ids) for item in diagnosis.hypotheses),
        "secrets_persisted": False, "raw_model_output_persisted": False,
    }
    write_artifact("live-openrouter-validation.json", result)
    if not result["passed"]:
        raise RuntimeError(f"OpenRouter live validation fell back: {result['fallback_reason']}")
    return result


async def razorpay_create() -> dict:
    settings = get_settings()
    live = settings.model_copy(update={"razorpay_enabled": True, "test_mode": True,
                                       "razorpay_webhook_secret": EPHEMERAL_WEBHOOK_SECRET})
    if not live.razorpay_key_id or not live.razorpay_key_id.startswith("rzp_test_"):
        raise RuntimeError("a non-placeholder rzp_test_ key is required")
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        offline = live.model_copy(update={"openrouter_enabled": False, "razorpay_enabled": False})
        case_ids = await reset_and_seed(session, offline)
        case_id = case_ids[0]
        result = await execute_action(session, case_id, live)
        if not result.get("executed"):
            raise RuntimeError(f"Razorpay link was not created: {result.get('reason')}")
        execution = session.query(ExecutionRow).filter_by(case_id=case_id).one()
        response = json.loads(execution.response_redacted_json)
        artifact = {
            "run_timestamp": datetime.now(timezone.utc).isoformat(), "purpose": "live_razorpay_test_mode_link",
            "passed": True, "case_id": case_id, "decision_id": execution.decision_id,
            "provider_resource_id": execution.provider_resource_id, "provider_status": execution.provider_status,
            "reference_id": result["command"]["reference_id"], "amount_subunits": result["command"]["amount_subunits"],
            "currency": result["command"]["currency"], "notify": result["command"]["notify"],
            "reminder_enable": result["command"]["reminder_enable"], "mode": "RAZORPAY TEST MODE",
            "paid_verified": False, "provider_delivered_webhook": False, "secrets_persisted": False,
        }
        write_artifact("live-razorpay-validation.json", artifact)
        return {**artifact, "short_url": response.get("short_url")}


async def razorpay_verify() -> dict:
    settings = get_settings()
    live = settings.model_copy(update={"razorpay_enabled": True, "test_mode": True,
                                       "razorpay_webhook_secret": EPHEMERAL_WEBHOOK_SECRET})
    artifact_path = RESULTS / "live-razorpay-validation.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    client = HttpRazorpayClient(live)
    response = await client._request("GET", f"/payment_links/{artifact['provider_resource_id']}")
    link = response.json()
    if link.get("status") != "paid":
        raise RuntimeError(f"Payment Link is not paid; current status is {link.get('status')}")
    envelope = {
        "event": "payment_link.paid", "created_at": int(datetime.now(timezone.utc).timestamp()),
        "payload": {"payment_link": {"entity": {
            "id": link["id"], "status": link["status"], "reference_id": link["reference_id"],
            "amount": link["amount"], "amount_paid": link.get("amount_paid", link["amount"]),
            "currency": link["currency"],
        }}},
    }
    body = canonical_json(envelope).encode()
    signature = hmac.new(EPHEMERAL_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    with SessionLocal() as session:
        outcome = process_razorpay_webhook(
            session, body=body, signature=signature,
            event_id=f"live-reconciled-{link['id']}", settings=live,
        )
    artifact.update({
        "verified_at": datetime.now(timezone.utc).isoformat(), "paid_verified": True,
        "provider_status": link["status"], "terminal_state": outcome.state,
        "provider_delivered_webhook": False,
        "outcome_proof": "locally signed outcome created only after live provider GET returned paid",
    })
    write_artifact("live-razorpay-validation.json", artifact)
    return artifact


async def main(command: str):
    if command == "openrouter":
        return await openrouter_validation()
    if command == "razorpay-create":
        return await razorpay_create()
    return await razorpay_verify()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sanitized manual live-provider validation")
    parser.add_argument("command", choices=("openrouter", "razorpay-create", "razorpay-verify"))
    args = parser.parse_args()
    print(json.dumps(asyncio.run(main(args.command)), indent=2))
