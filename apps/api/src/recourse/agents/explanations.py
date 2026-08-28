from __future__ import annotations

from recourse.domain.models import Diagnosis


CAUSE_LABELS = {
    "AUTHENTICATION_FRICTION": "authentication friction",
    "INSUFFICIENT_FUNDS_SIGNAL": "an insufficient-funds signal",
    "INSTRUMENT_RESTRICTED": "an instrument restriction",
    "INSTRUMENT_EXPIRED_OR_INVALID": "an expired or invalid instrument",
    "NETWORK_OR_GATEWAY_TRANSIENT": "a transient network or gateway failure",
    "METHOD_FRICTION": "payment-method friction",
    "MERCHANT_CONFIGURATION": "a merchant configuration issue",
    "CUSTOMER_ABORTED": "a customer-aborted payment",
    "REPEATED_ATTEMPT_EXHAUSTION": "repeated-attempt exhaustion",
    "POSSIBLE_LOW_INTENT": "an explicit low-intent signal",
    "UNKNOWN": "an unknown failure cause",
}


def verified_diagnosis_explanation(diagnosis: Diagnosis) -> dict:
    """Render only fixed prose populated by already-resolved model fields."""
    hypothesis = diagnosis.hypotheses[0]
    label = CAUSE_LABELS.get(hypothesis.cause, CAUSE_LABELS["UNKNOWN"])
    return {
        "text": f"Stored evidence supports {label} at {hypothesis.confidence:.0%} classification confidence.",
        "evidence_ids": hypothesis.evidence_ids,
        "unknowns": diagnosis.unknowns,
        "template_version": "diagnosis-explanation-v1",
    }
