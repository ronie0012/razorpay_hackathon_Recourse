from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from recourse.domain.models import StrictModel


class DiagnosisCause(StrEnum):
    AUTHENTICATION_FRICTION = "AUTHENTICATION_FRICTION"
    INSUFFICIENT_FUNDS_SIGNAL = "INSUFFICIENT_FUNDS_SIGNAL"
    INSTRUMENT_RESTRICTED = "INSTRUMENT_RESTRICTED"
    INSTRUMENT_EXPIRED_OR_INVALID = "INSTRUMENT_EXPIRED_OR_INVALID"
    NETWORK_OR_GATEWAY_TRANSIENT = "NETWORK_OR_GATEWAY_TRANSIENT"
    METHOD_FRICTION = "METHOD_FRICTION"
    MERCHANT_CONFIGURATION = "MERCHANT_CONFIGURATION"
    CUSTOMER_ABORTED = "CUSTOMER_ABORTED"
    REPEATED_ATTEMPT_EXHAUSTION = "REPEATED_ATTEMPT_EXHAUSTION"
    POSSIBLE_LOW_INTENT = "POSSIBLE_LOW_INTENT"
    UNKNOWN = "UNKNOWN"


class DiagnosisHypothesisOutput(StrictModel):
    cause: DiagnosisCause
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(max_length=8)
    contradicting_evidence_ids: list[str] = Field(max_length=8)


class DiagnosisOutput(StrictModel):
    status: str = Field(pattern=r"^(SUPPORTED|INSUFFICIENT_EVIDENCE)$")
    hypotheses: list[DiagnosisHypothesisOutput] = Field(max_length=3)
    unknowns: list[str] = Field(max_length=10)
    evidence_quality_assessment: float = Field(ge=0, le=1)


class ObjectionReason(StrEnum):
    NONE = "NONE"
    ALREADY_PAID = "ALREADY_PAID"
    ACTIVE_LINK_EXISTS = "ACTIVE_LINK_EXISTS"
    TEST_MODE_REQUIRED = "TEST_MODE_REQUIRED"
    LOW_EVIDENCE_QUALITY = "LOW_EVIDENCE_QUALITY"
    OPT_OUT = "OPT_OUT"
    QUIET_HOURS = "QUIET_HOURS"
    CONTACT_BUDGET = "CONTACT_BUDGET"
    ATTEMPT_BUDGET = "ATTEMPT_BUDGET"
    HIGH_UNCERTAINTY = "HIGH_UNCERTAINTY"
    NON_POSITIVE_VALUE = "NON_POSITIVE_VALUE"
    PROVIDER_UNHEALTHY = "PROVIDER_UNHEALTHY"
    DUPLICATE_ACTION = "DUPLICATE_ACTION"


class MissingCheck(StrEnum):
    ORDER_ALREADY_PAID = "order_already_paid"
    ACTIVE_LINK_EXISTS = "active_link_exists"
    TEST_MODE = "test_mode"
    PROVIDER_HEALTH = "provider_health"
    COMMAND_IDEMPOTENCY = "command_idempotency"


class ChallengeOutput(StrictModel):
    verdict: str = Field(pattern=r"^(NO_BLOCKING_OBJECTION|OBJECTION)$")
    objection_reason: ObjectionReason
    evidence_ids: list[str] = Field(max_length=8)
    missing_checks: list[MissingCheck] = Field(max_length=8)
    severity: str = Field(pattern=r"^(LOW|MEDIUM|HIGH)$")
    recommendation: str = Field(pattern=r"^(ALLOW_REVIEW|BLOCK|REQUEST_HUMAN_REVIEW)$")

