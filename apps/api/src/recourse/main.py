from __future__ import annotations

import hashlib
import hmac
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from recourse.config import get_settings
from recourse.domain.audit import verify_chain
from recourse.domain.models import PaymentFailureCase
from recourse.domain.state_machine import InvalidTransition
from recourse.persistence.database import Base, engine, get_db
from recourse.persistence.tables import AuditRow, CaseRow, EvidenceRow
from recourse.persistence.tables import DecisionRow
from recourse.product import SurgeryMutations, decision_surgery, load_final_evaluation, reset_and_seed
from recourse.razorpay import create_checkout_order, execute_action, process_fixture_webhook, process_razorpay_webhook
from recourse.razorpay.adapter import RazorpayAdapterError
from recourse.services import analyze_case, ingest_signed_event, list_audit


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
    razorpay_test_ready = bool(
        settings.razorpay_enabled and settings.test_mode and settings.razorpay_key_id
        and settings.razorpay_key_id.startswith("rzp_test_") and settings.razorpay_key_secret
        and settings.razorpay_webhook_secret
    )
    return {
        "status": "ready", "database": "ok", "test_mode": settings.test_mode,
        "fixture_mode": settings.demo_mode,
        "openrouter_configured": bool(settings.openrouter_enabled and settings.openrouter_api_key),
        "razorpay_test_mode_configured": razorpay_test_ready,
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


@app.post("/api/v1/webhooks/razorpay")
async def webhook(request: Request, db: Session = Depends(get_db),
                  x_razorpay_signature: str | None = Header(None),
                  x_razorpay_event_id: str | None = Header(None)):
    body = await request.body()
    try:
        result = process_razorpay_webhook(
            db, body=body, signature=x_razorpay_signature,
            event_id=x_razorpay_event_id, settings=settings,
        )
        return {**result.__dict__, "mode_label": "RAZORPAY TEST MODE — NO REAL MONEY"}
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


@app.get("/api/v1/cases/{case_id}/replay")
def replay(case_id: str, db: Session = Depends(get_db)):
    if not db.get(CaseRow, case_id):
        raise HTTPException(status_code=404, detail="case not found")
    rows = list(db.scalars(select(AuditRow).where(AuditRow.case_id == case_id).order_by(AuditRow.sequence)).all())
    return {"case_id": case_id, "chain_valid": verify_chain(rows), "event_count": len(rows)}
