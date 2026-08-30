from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from recourse.config import Settings
from recourse.domain.audit import append_audit, canonical_json
from recourse.domain.models import CaseState
from recourse.domain.state_machine import reduce_terminal
from recourse.persistence.tables import CaseRow, ExecutionRow, RawEventRow
from recourse.services import ingest_signed_event, verify_signature


class LinkEntity(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    status: str
    reference_id: str
    amount: int | None = None
    amount_paid: int | None = None
    currency: str | None = None


class LinkWrapper(BaseModel):
    model_config = ConfigDict(extra="ignore")
    entity: LinkEntity


class OutcomeEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")
    event: str
    payload: dict[str, LinkWrapper]
    created_at: int | None = None


@dataclass(frozen=True)
class WebhookResult:
    case_id: str | None
    created: bool
    state: str | None
    event: str


OUTCOMES = {
    "payment_link.paid": CaseState.RECOVERED,
    "payment_link.expired": CaseState.EXPIRED,
    "payment_link.cancelled": CaseState.CANCELLED,
}


def _execution_by_reference(session: Session, link: LinkEntity) -> ExecutionRow | None:
    rows = session.scalars(select(ExecutionRow)).all()
    for row in rows:
        if row.provider_resource_id == link.id:
            return row
        try:
            request = json.loads(row.request_redacted_json)
        except ValueError:
            continue
        if request.get("reference_id") == link.reference_id:
            return row
    return None


def _process_webhook(session: Session, *, body: bytes, signature: str | None,
                     event_id: str | None, settings: Settings, source: str,
                     secret: str | None, label: str) -> WebhookResult:
    """Verify the untouched body, deduplicate, then reduce one Razorpay Test event."""
    if not secret:
        raise PermissionError("webhook verification is not configured")
    if not verify_signature(body, signature, secret):
        raise PermissionError("invalid webhook signature")
    if not event_id:
        raise ValueError("X-Razorpay-Event-Id is required")
    try:
        envelope = json.loads(body)
        event = str(envelope["event"])
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("invalid webhook envelope") from exc

    raw_id = f"{source}:{event_id}"
    existing_raw = session.scalar(select(RawEventRow).where(RawEventRow.provider_event_id == raw_id))
    if existing_raw:
        duplicate_case = session.scalar(
            select(CaseRow).where(CaseRow.source == source, CaseRow.source_event_id == event_id)
        )
        if duplicate_case:
            return WebhookResult(case_id=duplicate_case.id, created=False, state=duplicate_case.state, event=event)
        try:
            duplicate_link = OutcomeEnvelope.model_validate(envelope).payload["payment_link"].entity
            duplicate_execution = _execution_by_reference(session, duplicate_link)
            duplicate_case = session.get(CaseRow, duplicate_execution.case_id) if duplicate_execution else None
        except (ValidationError, KeyError):
            duplicate_case = None
        return WebhookResult(
            case_id=duplicate_case.id if duplicate_case else None, created=False,
            state=duplicate_case.state if duplicate_case else None, event=event,
        )

    if event == "payment.failed":
        case, created = ingest_signed_event(
            session, body=body, signature=signature, event_id=event_id, settings=settings,
            source=source, secret=secret,
        )
        return WebhookResult(case_id=case.case_id, created=created, state=CaseState.NORMALIZED, event=event)
    if event not in OUTCOMES:
        raise ValueError(f"unsupported Razorpay event: {event}")

    try:
        parsed = OutcomeEnvelope.model_validate(envelope)
        link = parsed.payload["payment_link"].entity
    except (ValidationError, KeyError) as exc:
        raise ValueError("invalid payment-link outcome") from exc
    execution = _execution_by_reference(session, link)
    if execution is None:
        raise ValueError("payment link does not belong to a recovery case")
    case = session.get(CaseRow, execution.case_id)
    if case is None:
        raise ValueError("recovery case not found")
    if link.amount is not None and link.amount != case.amount_subunits:
        raise ValueError("payment-link amount does not match the recovery case")
    if link.currency is not None and link.currency != case.currency:
        raise ValueError("payment-link currency does not match the recovery case")

    now = datetime.now(timezone.utc)
    session.add(RawEventRow(
        id=f"raw_{uuid.uuid4().hex}", provider_event_id=raw_id, event_type=event,
        raw_body=body, headers_redacted_json=canonical_json({"event_id": event_id}),
        signature_valid=True, body_sha256=hashlib.sha256(body).hexdigest(),
        received_at=now, processed_at=now,
    ))
    incoming = OUTCOMES[event]
    current = CaseState(case.state)
    target = reduce_terminal(current, incoming)
    if target != current:
        case.state = target
        case.updated_at = now
        if target == CaseState.RECOVERED:
            execution.provider_status = "paid"
        elif current != CaseState.RECOVERED:
            execution.provider_status = link.status
        append_audit(session, case_id=case.id, event_type="PAYMENT_LINK_OUTCOME", payload={
            "provider_event_id": event_id, "provider_resource_id": link.id,
            "reference_id": link.reference_id, "incoming": incoming, "from": current,
            "to": target, "source": label,
        })
    session.commit()
    return WebhookResult(case_id=case.id, created=True, state=target, event=event)


def process_razorpay_webhook(session: Session, *, body: bytes, signature: str | None,
                             event_id: str | None, settings: Settings) -> WebhookResult:
    return _process_webhook(
        session, body=body, signature=signature, event_id=event_id, settings=settings,
        source="razorpay_test_mode", secret=settings.razorpay_webhook_secret,
        label="RAZORPAY TEST MODE",
    )


def process_fixture_webhook(session: Session, *, body: bytes, signature: str | None,
                            event_id: str | None, settings: Settings) -> WebhookResult:
    return _process_webhook(
        session, body=body, signature=signature, event_id=event_id, settings=settings,
        source="fixture", secret=settings.fixture_webhook_secret, label="FIXTURE REPLAY",
    )


def process_api_verified_event(session: Session, *, body: bytes, signature: str | None,
                               event_id: str | None, settings: Settings) -> WebhookResult:
    """Process an event whose provider state was read through authenticated Test API access."""
    return _process_webhook(
        session, body=body, signature=signature, event_id=event_id, settings=settings,
        source="razorpay_api_verified", secret=settings.command_signing_secret,
        label="RAZORPAY API VERIFIED",
    )
