from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from recourse.persistence.database import Base


class CaseRow(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_event_id: Mapped[str] = mapped_column(String, nullable=False)
    payment_id: Mapped[str] = mapped_column(String, nullable=False)
    order_id: Mapped[str | None] = mapped_column(String)
    merchant_id: Mapped[str] = mapped_column(String, nullable=False)
    customer_ref: Mapped[str] = mapped_column(String, nullable=False)
    amount_subunits: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="INR")
    state: Mapped[str] = mapped_column(String, nullable=False)
    normalized_json: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decision_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("source", "source_event_id", name="uq_case_source_event"),
        CheckConstraint("source IN ('razorpay_test_mode','fixture','benchmark')", name="ck_case_source"),
        CheckConstraint("amount_subunits >= 0", name="ck_case_amount_nonnegative"),
    )


class RawEventRow(Base):
    __tablename__ = "raw_events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    provider_event_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    raw_body: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    headers_redacted_json: Mapped[str] = mapped_column(Text, nullable=False)
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    body_sha256: Mapped[str] = mapped_column(String, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_error: Mapped[str | None] = mapped_column(Text)


class EvidenceRow(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    source_path: Mapped[str] = mapped_column(String, nullable=False)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sha256: Mapped[str] = mapped_column(String, nullable=False)
    sensitivity: Mapped[str] = mapped_column(String, nullable=False)
    trusted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DiagnosisRow(Base):
    __tablename__ = "diagnoses"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EstimateRow(Base):
    __tablename__ = "model_estimates"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    lower: Mapped[float] = mapped_column(Float, nullable=False)
    upper: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_probability: Mapped[float] = mapped_column(Float, nullable=False)
    uplift: Mapped[float] = mapped_column(Float, nullable=False)
    uplift_lower: Mapped[float] = mapped_column(Float, nullable=False)
    direct_cost_subunits: Mapped[int] = mapped_column(Integer, nullable=False)
    downstream_cost_subunits: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_inv_subunits: Mapped[int] = mapped_column(Integer, nullable=False)
    conservative_inv_subunits: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    calibration_version: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("case_id", "action", "model_version", name="uq_estimate_case_action_model"),
        CheckConstraint("probability BETWEEN 0 AND 1", name="ck_estimate_probability"),
        CheckConstraint("lower BETWEEN 0 AND 1", name="ck_estimate_lower"),
        CheckConstraint("upper BETWEEN 0 AND 1", name="ck_estimate_upper"),
        CheckConstraint("lower <= probability AND probability <= upper", name="ck_estimate_bounds"),
        CheckConstraint("direct_cost_subunits >= 0 AND downstream_cost_subunits >= 0", name="ck_estimate_costs"),
    )


class ChallengeRow(Base):
    __tablename__ = "challenges"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DecisionRow(Base):
    __tablename__ = "decisions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    input_hash: Mapped[str] = mapped_column(String, nullable=False)
    selected_action: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("case_id", "input_hash", name="uq_decision_case_input"),)


class ExecutionRow(Base):
    __tablename__ = "action_executions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False, unique=True)
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.id"), nullable=False, unique=True)
    command_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    provider_resource_id: Mapped[str | None] = mapped_column(String)
    provider_status: Mapped[str | None] = mapped_column(String)
    request_redacted_json: Mapped[str] = mapped_column(Text, nullable=False)
    response_redacted_json: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String)


class AuditRow(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    actor_type: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[str] = mapped_column(String, nullable=False)
    input_hash: Mapped[str | None] = mapped_column(String)
    output_hash: Mapped[str | None] = mapped_column(String)
    payload_redacted_json: Mapped[str] = mapped_column(Text, nullable=False)
    previous_event_hash: Mapped[str | None] = mapped_column(String)
    event_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("case_id", "sequence", name="uq_audit_case_sequence"),)
