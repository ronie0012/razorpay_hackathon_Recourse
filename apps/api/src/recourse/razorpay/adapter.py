from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from recourse.config import Settings
from recourse.domain.audit import append_audit, canonical_json
from recourse.domain.models import Action, CaseState, PaymentFailureCase
from recourse.services import _transition, build_command, get_analysis
from recourse.persistence.tables import CaseRow, ExecutionRow


class RazorpayAdapterError(RuntimeError):
    def __init__(self, code: str, message: str, *, ambiguous: bool = False):
        super().__init__(message)
        self.code = code
        self.ambiguous = ambiguous


def _safe_provider_error(response: httpx.Response) -> str:
    """Return only Razorpay's bounded validation description, never request data."""
    try:
        error = response.json().get("error", {})
        description = str(error.get("description") or "Razorpay request failed")
        field = error.get("field")
    except (ValueError, AttributeError, TypeError):
        description, field = "Razorpay request failed", None
    description = " ".join(description.split())[:240]
    return f"{description} (field: {field})" if field else description


class RazorpayClient(Protocol):
    async def create_payment_link(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def find_payment_link(self, reference_id: str) -> dict[str, Any] | None: ...


class HttpRazorpayClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client
        self._validate()

    def _validate(self) -> None:
        if not self.settings.razorpay_enabled:
            raise RazorpayAdapterError("RAZORPAY_DISABLED", "Razorpay adapter is disabled")
        if not self.settings.razorpay_key_id or not self.settings.razorpay_key_secret:
            raise RazorpayAdapterError("RAZORPAY_NOT_CONFIGURED", "Razorpay credentials are missing")
        if not self.settings.razorpay_key_id.startswith("rzp_test_"):
            raise RazorpayAdapterError("LIVE_KEY_REFUSED", "only rzp_test_ keys are accepted")

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        own = self.client is None
        client = self.client or httpx.AsyncClient()
        try:
            try:
                async with asyncio.timeout(self.settings.razorpay_timeout_seconds):
                    response = await client.request(
                        method, self.settings.razorpay_base_url.rstrip("/") + path,
                        auth=(self.settings.razorpay_key_id, self.settings.razorpay_key_secret),
                        timeout=httpx.Timeout(self.settings.razorpay_timeout_seconds), **kwargs,
                    )
            except (TimeoutError, httpx.TimeoutException) as exc:
                raise RazorpayAdapterError("RAZORPAY_TIMEOUT", "Razorpay request timed out", ambiguous=method == "POST") from exc
            except httpx.TransportError as exc:
                raise RazorpayAdapterError("RAZORPAY_TRANSPORT", "Razorpay transport failed", ambiguous=method == "POST") from exc
            if response.status_code >= 400:
                raise RazorpayAdapterError(
                    f"RAZORPAY_HTTP_{response.status_code}", _safe_provider_error(response)
                )
            return response
        finally:
            if own:
                await client.aclose()

    async def create_payment_link(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._request("POST", "/payment_links", json=payload)
        try:
            result = response.json()
            if not result.get("id") or result.get("reference_id") != payload["reference_id"]:
                raise ValueError
            return result
        except (ValueError, AttributeError) as exc:
            raise RazorpayAdapterError("RAZORPAY_RESPONSE_SHAPE", "invalid payment-link response") from exc

    async def create_order(self, *, amount_subunits: int, currency: str, receipt: str) -> dict[str, Any]:
        response = await self._request("POST", "/orders", json={
            "amount": amount_subunits, "currency": currency, "receipt": receipt,
            "notes": {"purpose": "recourse_test_failure_demo"},
        })
        try:
            result = response.json()
            if not result.get("id") or result.get("amount") != amount_subunits:
                raise ValueError
            return result
        except (ValueError, AttributeError) as exc:
            raise RazorpayAdapterError("RAZORPAY_RESPONSE_SHAPE", "invalid order response") from exc

    async def find_payment_link(self, reference_id: str) -> dict[str, Any] | None:
        response = await self._request("GET", "/payment_links", params={"reference_id": reference_id})
        try:
            data = response.json()
            items = data.get("items", [])
            return next((item for item in items if item.get("reference_id") == reference_id), None)
        except (ValueError, AttributeError, TypeError) as exc:
            raise RazorpayAdapterError("RAZORPAY_RESPONSE_SHAPE", "invalid reconciliation response") from exc


def _provider_payload(case: PaymentFailureCase, command) -> dict[str, Any]:
    return {
        "amount": command.amount_subunits, "currency": command.currency,
        "accept_partial": False, "expire_by": int(command.expires_at.timestamp()),
        "reference_id": command.reference_id,
        "description": f"Recovery for failed payment {case.payment_id}",
        "notify": {"sms": False, "email": False}, "reminder_enable": False,
        "notes": {"recourse_case_id": case.case_id, "decision_id": command.decision_id},
    }


async def execute_action(session: Session, case_id: str, settings: Settings,
                         client: RazorpayClient | None = None) -> dict:
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

    # Non-link commands and offline fixture runs keep the bounded, visibly simulated path.
    if command.action != Action.STANDARD_PAYMENT_LINK or not settings.razorpay_enabled:
        from recourse.services import execute_noop
        session.rollback()
        return execute_noop(session, case_id, settings)

    if not settings.test_mode:
        return {"executed": False, "reason": "TEST_MODE_REQUIRED", "command": None}
    provider = client or HttpRazorpayClient(settings)
    payload = _provider_payload(case, command)
    now = datetime.now(timezone.utc)
    _transition(session, case_row, CaseState.EXECUTING)
    execution = ExecutionRow(
        id=f"exe_{uuid.uuid4().hex}", case_id=case_id, decision_id=command.decision_id,
        command_id=command.command_id, action=command.action,
        idempotency_key=command.idempotency_key, provider_status="PENDING_PROVIDER",
        request_redacted_json=command.model_dump_json(),
        response_redacted_json=canonical_json({"request_sha256": hashlib.sha256(canonical_json(payload).encode()).hexdigest()}),
        started_at=now,
    )
    session.add(execution)
    append_audit(session, case_id=case_id, event_type="PAYMENT_LINK_REQUESTED", payload={
        "command_id": command.command_id, "reference_id": command.reference_id,
        "mode": "RAZORPAY TEST MODE", "notify": payload["notify"], "reminder_enable": False,
    })
    session.commit()

    try:
        response = await provider.create_payment_link(payload)
    except RazorpayAdapterError as exc:
        execution = session.get(ExecutionRow, execution.id)
        execution.error_code = exc.code
        execution.provider_status = "RECONCILING" if exc.ambiguous else "FAILED"
        append_audit(session, case_id=case_id, event_type="PAYMENT_LINK_PROVIDER_ERROR", payload={
            "code": exc.code, "ambiguous": exc.ambiguous, "reference_id": command.reference_id,
        })
        session.commit()
        if not exc.ambiguous:
            return {
                "executed": False, "reason": exc.code, "error": str(exc),
                "command": command.model_dump(mode="json"),
            }
        try:
            response = await provider.find_payment_link(command.reference_id)
        except RazorpayAdapterError as reconcile_exc:
            return {"executed": False, "reason": "RECONCILING", "error": reconcile_exc.code,
                    "command": command.model_dump(mode="json")}
        if response is None:
            return {"executed": False, "reason": "RECONCILING", "command": command.model_dump(mode="json")}

    execution = session.get(ExecutionRow, execution.id)
    case_row = session.get(CaseRow, case_id)
    session.refresh(case_row)
    if response.get("reference_id") != command.reference_id:
        raise RazorpayAdapterError("REFERENCE_MISMATCH", "provider response reference does not match command")
    execution.provider_resource_id = str(response["id"])
    execution.provider_status = str(response.get("status", "created"))
    execution.response_redacted_json = canonical_json({
        "id": response["id"], "status": response.get("status"),
        "reference_id": response.get("reference_id"), "short_url": response.get("short_url"),
    })
    execution.completed_at = datetime.now(timezone.utc)
    # A paid webhook may have arrived while the provider call was in flight.
    if CaseState(case_row.state) != CaseState.RECOVERED:
        _transition(session, case_row, CaseState.LINK_ISSUED)
    append_audit(session, case_id=case_id, event_type="PAYMENT_LINK_RECONCILED", payload={
        "provider_resource_id": response["id"], "reference_id": command.reference_id,
        "provider_status": execution.provider_status, "mode": "RAZORPAY TEST MODE",
    })
    session.commit()
    return {"executed": True, "reason": "RAZORPAY_TEST_MODE", "command": command.model_dump(mode="json"),
            "provider_resource_id": response["id"], "state": case_row.state,
            "mode_label": "RAZORPAY TEST MODE — NO REAL MONEY"}


async def create_checkout_order(settings: Settings, *, amount_subunits: int, currency: str = "INR") -> dict:
    if amount_subunits <= 0:
        raise ValueError("amount_subunits must be positive")
    if len(currency) != 3 or currency.upper() != currency:
        raise ValueError("currency must be a three-letter uppercase code")
    client = HttpRazorpayClient(settings)
    receipt = "recourse_demo_" + hashlib.sha256(f"{amount_subunits}|{currency}".encode()).hexdigest()[:20]
    order = await client.create_order(amount_subunits=amount_subunits, currency=currency, receipt=receipt)
    return {
        "order_id": order["id"], "amount_subunits": order["amount"],
        "currency": order.get("currency", currency), "key_id": settings.razorpay_key_id,
        "mode_label": "RAZORPAY TEST MODE — NO REAL MONEY",
    }
