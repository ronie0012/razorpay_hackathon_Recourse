from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from recourse.config import get_settings
from recourse.domain.audit import append_audit, verify_chain
from recourse.domain.models import PaymentFailureCase
from recourse.domain.state_machine import InvalidTransition
from recourse.persistence.database import Base, engine, get_db
from recourse.persistence.tables import AuditRow, CaseRow, EvidenceRow, ExecutionRow
from recourse.persistence.tables import DecisionRow
from recourse.product import SurgeryMutations, decision_surgery, load_final_evaluation, reset_and_seed
from recourse.razorpay import (
    HttpRazorpayClient, create_checkout_order, execute_action, find_failed_order_payment,
    process_api_verified_event, process_fixture_webhook, process_razorpay_webhook,
)
from recourse.razorpay.adapter import RazorpayAdapterError
from recourse.services import analyze_case, ingest_signed_event, list_audit


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="RECOURSE API", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins.split(",")],
    allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"],
)


def error(code: str, message: str, status_code: int, details: dict | None = None):
    return JSONResponse(status_code=status_code, content={"error": {
        "code": code, "message": message, "retryable": False, "trace_id": None, "details": details or {},
    }})


@app.exception_handler(InvalidTransition)
def transition_error(_request, exc):
    return error("INVALID_STATE_TRANSITION", str(exc), 409)


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    razorpay_missing = []
    if not settings.razorpay_enabled:
        razorpay_missing.append("RAZORPAY_ENABLED=true")
    if not settings.test_mode:
        razorpay_missing.append("TEST_MODE=true")
    if not settings.razorpay_key_id or not settings.razorpay_key_id.startswith("rzp_test_"):
        razorpay_missing.append("RAZORPAY_KEY_ID=rzp_test_…")
    if not settings.razorpay_key_secret:
        razorpay_missing.append("RAZORPAY_KEY_SECRET")
    if not settings.razorpay_webhook_secret:
        razorpay_missing.append("RAZORPAY_WEBHOOK_SECRET")
    razorpay_test_ready = bool(
        not razorpay_missing
    )
    return {
        "status": "ready", "database": "ok", "test_mode": settings.test_mode,
        "fixture_mode": settings.demo_mode,
        "openrouter_configured": bool(settings.openrouter_enabled and settings.openrouter_api_key),
        "razorpay_test_mode_configured": razorpay_test_ready,
        "razorpay_test_mode_missing": razorpay_missing,
    }


@app.post("/api/v1/demo/checkout-order")
async def checkout_order(amount_subunits: int = 499900, currency: str = "INR"):
    if not settings.demo_mode:
        raise HTTPException(status_code=404)
    try:
        return await create_checkout_order(settings, amount_subunits=amount_subunits, currency=currency)
    except RazorpayAdapterError as exc:
        return error(exc.code, str(exc), 503)
    except ValueError as exc:
        return error("INVALID_ORDER", str(exc), 422)


@app.post("/api/v1/demo/reconcile-failure/{order_id}")
async def reconcile_failure(order_id: str, db: Session = Depends(get_db)):
    """Confirm a real Test Mode failure when webhook delivery is delayed."""
    if not settings.demo_mode or not settings.test_mode:
        raise HTTPException(status_code=404)
    try:
        payment = await find_failed_order_payment(settings, order_id)
        if payment is None:
            return {"found": False, "order_id": order_id}
        envelope = {
            "event": "payment.failed",
            "created_at": payment.get("created_at"),
            "payload": {"payment": {"entity": payment}},
        }
        body = json.dumps(envelope, separators=(",", ":")).encode()
        signature = hmac.new(settings.command_signing_secret.encode(), body, hashlib.sha256).hexdigest()
        result = process_api_verified_event(
            db, body=body, signature=signature,
            event_id=f"api_verified_failure_{payment['id']}", settings=settings,
        )
        if result.case_id and result.created:
            append_audit(db, case_id=result.case_id, event_type="PAYMENT_FAILURE_API_VERIFIED", payload={
                "payment_id": payment["id"], "order_id": order_id,
                "provider_status": payment.get("status"), "source": "authenticated Razorpay Test API",
            })
            db.commit()
        return {
            "found": True, **result.__dict__,
            "mode_label": "RAZORPAY API VERIFIED — NO REAL MONEY",
        }
    except RazorpayAdapterError as exc:
        return error(exc.code, str(exc), 503)
    except ValueError as exc:
        return error("INVALID_ORDER", str(exc), 422)


@app.post("/api/v1/demo/reconcile-outcome/{case_id}")
async def reconcile_outcome(case_id: str, db: Session = Depends(get_db)):
    """Confirm a terminal Test payment-link state when its webhook is delayed."""
    if not settings.demo_mode or not settings.test_mode:
        raise HTTPException(status_code=404)
    case = db.get(CaseRow, case_id)
    execution = db.scalar(select(ExecutionRow).where(ExecutionRow.case_id == case_id))
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    if execution is None:
        return {"found": False, "case_id": case_id}
    command = json.loads(execution.request_redacted_json)
    try:
        link = await HttpRazorpayClient(settings).find_payment_link(command["reference_id"])
        if link is None or link.get("status") not in {"paid", "expired", "cancelled"}:
            return {"found": False, "case_id": case_id, "status": link.get("status") if link else None}
        event = f"payment_link.{link['status']}"
        envelope = {"event": event, "payload": {"payment_link": {"entity": link}}}
        body = json.dumps(envelope, separators=(",", ":")).encode()
        signature = hmac.new(settings.command_signing_secret.encode(), body, hashlib.sha256).hexdigest()
        result = process_api_verified_event(
            db, body=body, signature=signature,
            event_id=f"api_verified_{link['id']}_{link['status']}", settings=settings,
        )
        return {
            "found": True, **result.__dict__,
            "mode_label": "RAZORPAY API VERIFIED — NO REAL MONEY",
        }
    except RazorpayAdapterError as exc:
        return error(exc.code, str(exc), 503)


async def run_live_agent(case_id: str, session_factory: sessionmaker) -> None:
    """Finish a newly ingested Test Mode failure after the webhook is acknowledged."""
    with session_factory() as session:
        try:
            await analyze_case(session, case_id, settings)
            await execute_action(session, case_id, settings)
        except Exception:
            session.rollback()
            logger.exception("live agent pipeline failed for case %s", case_id)


@app.post("/api/v1/webhooks/razorpay")
async def webhook(request: Request, background_tasks: BackgroundTasks,
                  db: Session = Depends(get_db),
                  x_razorpay_signature: str | None = Header(None),
                  x_razorpay_event_id: str | None = Header(None)):
    body = await request.body()
    try:
        result = process_razorpay_webhook(
            db, body=body, signature=x_razorpay_signature,
            event_id=x_razorpay_event_id, settings=settings,
        )
        agent_run = "not_applicable"
        if result.event == "payment.failed" and result.case_id:
            # Use a fresh session after the HTTP request. Replayed webhooks are safe:
            # analysis and execution both enforce database-level idempotency.
            factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
            background_tasks.add_task(run_live_agent, result.case_id, factory)
            agent_run = "scheduled"
        return {
            **result.__dict__, "agent_run": agent_run,
            "mode_label": "RAZORPAY TEST MODE — NO REAL MONEY",
        }
    except PermissionError as exc:
        return error("INVALID_SIGNATURE", str(exc), 401)
    except (ValueError, json.JSONDecodeError) as exc:
        return error("INVALID_WEBHOOK", str(exc), 422)


@app.post("/api/v1/demo/failures/{fixture_id}")
def inject_fixture(fixture_id: str, db: Session = Depends(get_db)):
    if not settings.demo_mode:
        raise HTTPException(status_code=404)
    path = Path("data/fixtures") / f"{fixture_id}.json"
    if not path.is_file() or path.parent.resolve() != Path("data/fixtures").resolve():
        raise HTTPException(status_code=404, detail="fixture not found")
    body = path.read_bytes()
    signature = hmac.new(settings.fixture_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    case, created = ingest_signed_event(db, body=body, signature=signature,
                                        event_id=f"fixture_{fixture_id}_v1", settings=settings)
    return {"case_id": case.case_id, "created": created}


@app.post("/api/v1/demo/journeys/failure")
def start_guided_failure(db: Session = Depends(get_db)):
    """Create a fresh signed failure for the interactive judge journey."""
    if not settings.demo_mode:
        raise HTTPException(status_code=404)
    template = json.loads(Path("data/fixtures/hero-payment-failed.json").read_text(encoding="utf-8"))
    journey_id = uuid.uuid4().hex
    entity = template["payload"]["payment"]["entity"]
    entity["id"] = f"pay_demo_{journey_id[:16]}"
    entity["order_id"] = f"order_demo_{journey_id[:16]}"
    entity["notes"]["customer_ref"] = f"guided_demo_{journey_id[:16]}"
    body = json.dumps(template, separators=(",", ":")).encode()
    signature = hmac.new(settings.fixture_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    result = process_fixture_webhook(
        db, body=body, signature=signature,
        event_id=f"guided_failure_{journey_id}", settings=settings,
    )
    return {
        **result.__dict__, "order_id": entity["order_id"],
        "mode_label": "SIGNED GUIDED DEMO — NO REAL MONEY",
    }


@app.post("/api/v1/demo/journeys/{case_id}/paid")
def complete_guided_recovery(case_id: str, db: Session = Depends(get_db)):
    """Replay a signed paid outcome tied to this journey's emitted command."""
    if not settings.demo_mode:
        raise HTTPException(status_code=404)
    case = db.get(CaseRow, case_id)
    execution = db.scalar(select(ExecutionRow).where(ExecutionRow.case_id == case_id))
    if case is None or case.source != "fixture":
        raise HTTPException(status_code=404, detail="guided journey not found")
    if execution is None:
        return error("ACTION_NOT_EXECUTED", "the recovery action has not been issued", 409)
    command = json.loads(execution.request_redacted_json)
    outcome = {
        "event": "payment_link.paid",
        "payload": {"payment_link": {"entity": {
            "id": execution.provider_resource_id,
            "status": "paid",
            "reference_id": command["reference_id"],
            "amount": case.amount_subunits,
            "amount_paid": case.amount_subunits,
            "currency": case.currency,
        }}},
    }
    body = json.dumps(outcome, separators=(",", ":")).encode()
    signature = hmac.new(settings.fixture_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    result = process_fixture_webhook(
        db, body=body, signature=signature,
        event_id=f"guided_paid_{case_id}", settings=settings,
    )
    return {**result.__dict__, "mode_label": "SIGNED GUIDED DEMO — NO REAL MONEY"}


@app.post("/api/v1/demo/webhooks/{fixture_id}")
def replay_fixture_webhook(fixture_id: str, db: Session = Depends(get_db)):
    if not settings.demo_mode:
        raise HTTPException(status_code=404)
    root = Path("data/fixtures").resolve()
    path = (root / f"{fixture_id}.json").resolve()
    if not path.is_file() or path.parent != root:
        raise HTTPException(status_code=404, detail="fixture not found")
    body = path.read_bytes()
    signature = hmac.new(settings.fixture_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    try:
        result = process_fixture_webhook(
            db, body=body, signature=signature, event_id=f"fixture_{fixture_id}_v1", settings=settings,
        )
        return {**result.__dict__, "mode_label": "FIXTURE REPLAY — NO REAL MONEY"}
    except ValueError as exc:
        return error("INVALID_FIXTURE", str(exc), 422)


@app.get("/api/v1/cases")
def cases(db: Session = Depends(get_db)):
    rows = db.scalars(select(CaseRow).order_by(CaseRow.created_at.desc())).all()
    result = []
    for row in rows:
        decision = db.scalar(select(DecisionRow).where(DecisionRow.case_id == row.id).order_by(DecisionRow.created_at.desc()))
        decision_payload = json.loads(decision.payload_json) if decision else None
        result.append({
            "case_id": row.id, "amount_subunits": row.amount_subunits, "currency": row.currency,
            "state": row.state, "source": row.source, "payment_id": row.payment_id,
            "order_id": row.order_id,
            "recoverable_value_subunits": decision_payload["conservative_incremental_value_subunits"] if decision_payload else None,
            "selected_action": decision_payload["selected_action"] if decision_payload else None,
            "priority_score": max(0, decision_payload["conservative_incremental_value_subunits"] if decision_payload else 0),
        })
    return sorted(result, key=lambda item: (item["priority_score"], item["amount_subunits"]), reverse=True)


@app.post("/api/v1/demo/reset")
async def demo_reset(db: Session = Depends(get_db)):
    try:
        case_ids = await reset_and_seed(db, settings)
        return {"reset": True, "case_ids": case_ids, "count": len(case_ids),
                "mode_label": "SIGNED SYNTHETIC FIXTURES — NO REAL MONEY"}
    except PermissionError as exc:
        return error("DEMO_DISABLED", str(exc), 403)


@app.post("/api/v1/cases/{case_id}/surgery")
def surgery(case_id: str, mutations: SurgeryMutations, db: Session = Depends(get_db)):
    try:
        return decision_surgery(db, case_id, mutations, settings)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/evaluation")
def evaluation():
    try:
        return load_final_evaluation()
    except (OSError, ValueError) as exc:
        return error("EVALUATION_ARTIFACT_UNAVAILABLE", str(exc), 503)


@app.get("/api/v1/cases/{case_id}")
def case_detail(case_id: str, db: Session = Depends(get_db)):
    row = db.get(CaseRow, case_id)
    if not row:
        raise HTTPException(status_code=404, detail="case not found")
    evidence = db.scalars(select(EvidenceRow).where(EvidenceRow.case_id == case_id)).all()
    return {"case": PaymentFailureCase.model_validate_json(row.normalized_json), "state": row.state,
            "evidence": [{"evidence_id": e.id, "kind": e.kind, "path": e.source_path,
                          "value": json.loads(e.value_json), "sha256": e.sha256, "trusted": e.trusted}
                         for e in evidence]}


@app.post("/api/v1/cases/{case_id}/analyze")
async def analyze(case_id: str, db: Session = Depends(get_db)):
    try:
        return await analyze_case(db, case_id, settings)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/v1/cases/{case_id}/execute")
async def execute(case_id: str, db: Session = Depends(get_db)):
    try:
        return await execute_action(db, case_id, settings)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RazorpayAdapterError as exc:
        return error(exc.code, str(exc), 503)


@app.get("/api/v1/cases/{case_id}/audit")
def audit(case_id: str, db: Session = Depends(get_db)):
    if not db.get(CaseRow, case_id):
        raise HTTPException(status_code=404, detail="case not found")
    return list_audit(db, case_id)


@app.get("/api/v1/cases/{case_id}/execution")
def execution_status(case_id: str, db: Session = Depends(get_db)):
    if not db.get(CaseRow, case_id):
        raise HTTPException(status_code=404, detail="case not found")
    execution = db.scalar(select(ExecutionRow).where(ExecutionRow.case_id == case_id))
    if execution is None:
        return {"issued": False, "case_id": case_id}
    response = json.loads(execution.response_redacted_json) if execution.response_redacted_json else {}
    return {
        "issued": True, "case_id": case_id, "action": execution.action,
        "provider_status": execution.provider_status,
        "provider_resource_id": execution.provider_resource_id,
        "short_url": response.get("short_url"),
        "error_code": execution.error_code,
        "completed_at": execution.completed_at,
    }


@app.get("/api/v1/cases/{case_id}/replay")
def replay(case_id: str, db: Session = Depends(get_db)):
    if not db.get(CaseRow, case_id):
        raise HTTPException(status_code=404, detail="case not found")
    rows = list(db.scalars(select(AuditRow).where(AuditRow.case_id == case_id).order_by(AuditRow.sequence)).all())
    return {"case_id": case_id, "chain_valid": verify_chain(rows), "event_count": len(rows)}
