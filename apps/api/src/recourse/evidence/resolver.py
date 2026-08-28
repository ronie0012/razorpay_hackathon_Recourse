from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class EvidenceResolutionError(ValueError):
    pass


def resolve_evidence_ids(ids: list[str], evidence: list[dict[str, Any]], decision_at: datetime) -> list[dict[str, Any]]:
    by_id = {item["evidence_id"]: item for item in evidence}
    resolved = []
    for evidence_id in ids:
        item = by_id.get(evidence_id)
        if item is None:
            raise EvidenceResolutionError(f"unknown evidence ID: {evidence_id}")
        if not item.get("trusted", False):
            raise EvidenceResolutionError(f"untrusted evidence ID: {evidence_id}")
        available_at = datetime.fromisoformat(str(item["available_at"]).replace("Z", "+00:00"))
        comparable_decision = decision_at if decision_at.tzinfo else decision_at.replace(tzinfo=timezone.utc)
        if available_at.tzinfo is None:
            available_at = available_at.replace(tzinfo=timezone.utc)
        if available_at > comparable_decision:
            raise EvidenceResolutionError(f"post-decision evidence ID: {evidence_id}")
        resolved.append(item)
    return resolved


def minimize_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed_kinds = {"normalized_payment_field", "razorpay_payment_field", "policy_state"}
    result = []
    for item in evidence:
        if item.get("kind") not in allowed_kinds or not item.get("trusted", False):
            continue
        value = item.get("value")
        if isinstance(value, str):
            value = value[:500]
        elif not isinstance(value, (str, int, float, bool, type(None))):
            value = str(value)[:500]
        result.append({
            "evidence_id": item["evidence_id"], "kind": item["kind"], "path": item["path"],
            "value": value, "source": item["source"], "observed_at": str(item["observed_at"]),
            "available_at": str(item["available_at"]), "trusted": True,
        })
    return result

