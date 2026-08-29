from __future__ import annotations

import hashlib
import hmac
import asyncio
from pathlib import Path

import pytest
import httpx

from recourse.config import Settings
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from recourse.persistence.database import Base
from recourse.persistence.tables import ExecutionRow
from recourse.razorpay.adapter import HttpRazorpayClient, RazorpayAdapterError, _safe_provider_error, execute_action
from recourse.services import analyze_case, ingest_signed_event


def test_offline_fixture_failure_link_paid_is_exactly_once_and_monotone(client):
    failure = client.post("/api/v1/demo/webhooks/hero-payment-failed").json()
    case_id = failure["case_id"]
    assert failure["mode_label"] == "FIXTURE REPLAY — NO REAL MONEY"
    assert client.post(f"/api/v1/cases/{case_id}/analyze").status_code == 200
    execution = client.post(f"/api/v1/cases/{case_id}/execute").json()
    assert execution["executed"] is True
    assert execution["command"]["notify"] == {"sms": False, "email": False}
    assert execution["command"]["reminder_enable"] is False

    cancelled = client.post("/api/v1/demo/webhooks/hero-payment-link-cancelled").json()
    assert cancelled["state"] == "CANCELLED"
    paid = client.post("/api/v1/demo/webhooks/hero-payment-link-paid").json()
    assert paid["state"] == "RECOVERED"
    duplicate = client.post("/api/v1/demo/webhooks/hero-payment-link-paid").json()
    assert duplicate["created"] is False
    assert duplicate["state"] == "RECOVERED"
    late_expiry = client.post("/api/v1/demo/webhooks/hero-payment-link-expired").json()
    assert late_expiry["state"] == "RECOVERED"
    assert client.get(f"/api/v1/cases/{case_id}").json()["state"] == "RECOVERED"
    outcomes = [e for e in client.get(f"/api/v1/cases/{case_id}/audit").json()
                if e["event_type"] == "PAYMENT_LINK_OUTCOME" and e["payload_redacted"]["to"] == "RECOVERED"]
    assert len(outcomes) == 1


def test_fixture_signature_is_not_accepted_by_provider_gateway(client):
    body = Path("data/fixtures/hero-payment-failed.json").read_bytes()
    fixture_signature = hmac.new(b"local-fixture-secret", body, hashlib.sha256).hexdigest()
    response = client.post("/api/v1/webhooks/razorpay", content=body, headers={
        "X-Razorpay-Signature": fixture_signature, "X-Razorpay-Event-Id": "secret-separation",
    })
    assert response.status_code == 401


def test_valid_provider_failure_uses_test_mode_source(client):
    body = Path("data/fixtures/hero-payment-failed.json").read_bytes()
    signature = hmac.new(b"local-razorpay-webhook-secret", body, hashlib.sha256).hexdigest()
    response = client.post("/api/v1/webhooks/razorpay", content=body, headers={
        "X-Razorpay-Signature": signature, "X-Razorpay-Event-Id": "rzp-event-payment-failed",
    })
    assert response.status_code == 200
    result = response.json()
    assert result["created"] is True
    assert result["agent_run"] == "scheduled"
    assert result["mode_label"] == "RAZORPAY TEST MODE — NO REAL MONEY"
    detail = client.get(f"/api/v1/cases/{result['case_id']}").json()
    assert detail["case"]["source"] == "razorpay_test_mode"
    assert detail["state"] == "LINK_ISSUED"

    duplicate = client.post("/api/v1/webhooks/razorpay", content=body, headers={
        "X-Razorpay-Signature": signature, "X-Razorpay-Event-Id": "rzp-event-payment-failed",
    }).json()
    assert duplicate["created"] is False
    assert duplicate["agent_run"] == "scheduled"
    audit = client.get(f"/api/v1/cases/{result['case_id']}/audit").json()
    assert len([event for event in audit if event["event_type"] == "ACTION_EXECUTED_NOOP"]) == 1


class AmbiguousThenReconciledClient:
    def __init__(self):
        self.reference_id = None

    async def create_payment_link(self, payload):
        self.reference_id = payload["reference_id"]
        raise RazorpayAdapterError("RAZORPAY_TIMEOUT", "timeout", ambiguous=True)

    async def find_payment_link(self, reference_id):
        assert reference_id == self.reference_id
        return {"id": "plink_test_reconciled", "status": "created", "reference_id": reference_id,
                "short_url": "https://rzp.io/i/test-only"}


def test_ambiguous_create_reconciles_without_a_second_link(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'reconcile.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        openrouter_enabled=False, razorpay_enabled=True, test_mode=True,
        razorpay_key_id="rzp_test_demo", razorpay_key_secret="secret",
    )
    body = Path("data/fixtures/hero-payment-failed.json").read_bytes()
    signature = hmac.new(settings.fixture_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    with factory() as session:
        case, _ = ingest_signed_event(
            session, body=body, signature=signature, event_id="fixture_hero-payment-failed_v1", settings=settings,
        )
        asyncio.run(analyze_case(session, case.case_id, settings))
        result = asyncio.run(execute_action(session, case.case_id, settings, AmbiguousThenReconciledClient()))
        assert result["executed"] is True
        assert result["provider_resource_id"] == "plink_test_reconciled"
        executions = session.scalars(select(ExecutionRow)).all()
        assert len(executions) == 1
        assert executions[0].provider_status == "created"


def test_live_key_can_never_enable_adapter():
    with pytest.raises(RazorpayAdapterError, match="only rzp_test_ keys"):
        HttpRazorpayClient(Settings(
            razorpay_enabled=True, razorpay_key_id="rzp_live_forbidden", razorpay_key_secret="secret",
        ))


def test_provider_validation_error_is_bounded_and_excludes_request_data():
    response = httpx.Response(400, json={"error": {
        "description": "reference_id must be unique", "field": "reference_id",
        "metadata": {"secret": "must-not-leak"},
    }})
    message = _safe_provider_error(response)
    assert message == "reference_id must be unique (field: reference_id)"
    assert "must-not-leak" not in message
