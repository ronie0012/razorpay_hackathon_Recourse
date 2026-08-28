import hashlib
import hmac
import json
from pathlib import Path

from recourse.domain.audit import verify_chain
from recourse.persistence.tables import AuditRow


def test_fixture_to_payment_link_command_and_audit(client):
    injected = client.post("/api/v1/demo/failures/hero-payment-failed")
    assert injected.status_code == 200
    case_id = injected.json()["case_id"]
    duplicate = client.post("/api/v1/demo/failures/hero-payment-failed")
    assert duplicate.json() == {"case_id": case_id, "created": False}
    assert len(client.get("/api/v1/cases").json()) == 1

    analysis = client.post(f"/api/v1/cases/{case_id}/analyze")
    assert analysis.status_code == 200
    body = analysis.json()
    assert len(body["futures"]) == 4
    assert body["decision"]["selected_action"] == "STANDARD_PAYMENT_LINK"
    assert body["state"] == "ACTION_READY"

    execution = client.post(f"/api/v1/cases/{case_id}/execute").json()
    assert execution["executed"] is True
    assert execution["state"] == "LINK_ISSUED"
    assert execution["command"]["notify"] == {"sms": False, "email": False}
    assert execution["command"]["reminder_enable"] is False
    second = client.post(f"/api/v1/cases/{case_id}/execute").json()
    assert second["executed"] is False
    assert second["reason"] == "DUPLICATE_ACTION"

    audit = client.get(f"/api/v1/cases/{case_id}/audit").json()
    assert [event["sequence"] for event in audit] == list(range(1, len(audit) + 1))
    for previous, current in zip(audit, audit[1:]):
        assert current["previous_event_hash"] == previous["event_hash"]
    replay = client.get(f"/api/v1/cases/{case_id}/replay").json()
    assert replay == {"case_id": case_id, "chain_valid": True, "event_count": len(audit)}


def test_invalid_signature_and_schema_create_no_case(client):
    payload = Path("data/fixtures/hero-payment-failed.json").read_bytes()
    invalid = client.post("/api/v1/webhooks/razorpay", content=payload, headers={
        "X-Razorpay-Signature": "bad", "X-Razorpay-Event-Id": "bad-signature",
    })
    assert invalid.status_code == 401
    malformed = b"{not json"
    signature = hmac.new(b"local-razorpay-webhook-secret", malformed, hashlib.sha256).hexdigest()
    invalid_json = client.post("/api/v1/webhooks/razorpay", content=malformed, headers={
        "X-Razorpay-Signature": signature, "X-Razorpay-Event-Id": "bad-json",
    })
    assert invalid_json.status_code == 422
    assert client.get("/api/v1/cases").json() == []
