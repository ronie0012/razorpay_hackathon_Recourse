from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from recourse.domain.audit import sha256_json
from recourse.domain.models import (
    Action, Decision, DecisionStatus, FutureEstimate, GuardrailResult,
    PaymentFailureCase, ReasonCode,
)

MIN_EVIDENCE_QUALITY = .70
MIN_CONSERVATIVE_INV = 1000
MAX_INTERVAL_WIDTH = .35
TIE_BAND_SUBUNITS = 500
BURDEN_ORDER = {action: index for index, action in enumerate(Action)}


def decide(case: PaymentFailureCase, futures: list[FutureEstimate], *, test_mode: bool, already_executed: bool = False) -> Decision:
    guardrails: list[GuardrailResult] = []
    blocked: dict[str, list[ReasonCode]] = {}

    def check(rule: str, passed: bool, action: Action | None = None, reason: ReasonCode | None = None):
        guardrails.append(GuardrailResult(rule=rule, passed=passed, action=action, reason_code=None if passed else reason))
        if not passed and action and reason:
            blocked.setdefault(action.value, []).append(reason)

    check("TEST_MODE", test_mode, reason=ReasonCode.TEST_MODE_REQUIRED)
    check("EVIDENCE_QUALITY", case.evidence_quality >= MIN_EVIDENCE_QUALITY, reason=ReasonCode.LOW_EVIDENCE_QUALITY)
    check("INTERVENTION_BUDGET", not already_executed, reason=ReasonCode.INTERVENTION_BUDGET_EXCEEDED)
    check("OPT_OUT", not case.opt_out, Action.ONE_BOUNDED_NUDGE, ReasonCode.OPT_OUT)
    check("CONTACT_CONSENT", case.contact_consent, Action.ONE_BOUNDED_NUDGE, ReasonCode.OPT_OUT)
    check("QUIET_HOURS", not case.quiet_hours, Action.ONE_BOUNDED_NUDGE, ReasonCode.QUIET_HOURS)
    check("CONTACT_BUDGET", case.contacts_7d < 2, Action.ONE_BOUNDED_NUDGE, ReasonCode.CONTACT_BUDGET_EXCEEDED)
    check("RETRY_BUDGET", case.attempt_count < 2 and case.failure.reason not in {"card_declined", "insufficient_funds"}, Action.RETRY_LATER, ReasonCode.RETRY_BUDGET_EXCEEDED)

    by_action = {future.action: future for future in futures}
    if not test_mode:
        status, selected, reasons = DecisionStatus.ABSTAIN, Action.NO_ACTION, [ReasonCode.TEST_MODE_REQUIRED]
    elif case.evidence_quality < MIN_EVIDENCE_QUALITY:
        status, selected, reasons = DecisionStatus.HUMAN_REVIEW, Action.NO_ACTION, [ReasonCode.LOW_EVIDENCE_QUALITY]
    elif already_executed:
        status, selected, reasons = DecisionStatus.NO_ACTION, Action.NO_ACTION, [ReasonCode.INTERVENTION_BUDGET_EXCEEDED]
    else:
        feasible = [f for f in futures if f.action.value not in blocked]
        best_value = max(f.conservative_incremental_value_subunits for f in feasible)
        tie_set = [f for f in feasible if best_value - f.conservative_incremental_value_subunits < TIE_BAND_SUBUNITS]
        best = min(tie_set, key=lambda f: BURDEN_ORDER[f.action])
        if best.conservative_incremental_value_subunits <= MIN_CONSERVATIVE_INV:
            status, selected, reasons = DecisionStatus.NO_ACTION, Action.NO_ACTION, [ReasonCode.NON_POSITIVE_VALUE]
        elif best.probability_upper - best.probability_lower > MAX_INTERVAL_WIDTH:
            status, selected, reasons = DecisionStatus.HUMAN_REVIEW, Action.NO_ACTION, [ReasonCode.HIGH_UNCERTAINTY]
        else:
            status, selected, reasons = DecisionStatus.ACTION_READY, best.action, [ReasonCode.MAX_CONSERVATIVE_INV, ReasonCode.ALL_GUARDRAILS_PASS]
        for future in futures:
            if future.action != selected and future.action.value not in blocked:
                blocked.setdefault(future.action.value, []).append(ReasonCode.LOWER_CONSERVATIVE_INV)

    chosen = by_action[selected]
    evidence_hash = sha256_json(sorted(case.evidence_ids))
    decision_key = hashlib.sha256(
        f"{case.case_id}|{evidence_hash}|policy-v1".encode()
    ).hexdigest()[:24]
    return Decision(
        decision_id=f"dec_{decision_key}", case_id=case.case_id,
        selected_action=selected, status=status, reason_codes=reasons,
        blocked_actions=blocked, guardrail_results=guardrails,
        expected_incremental_value_subunits=chosen.expected_incremental_value_subunits,
        conservative_incremental_value_subunits=chosen.conservative_incremental_value_subunits,
        evidence_snapshot_hash=evidence_hash, policy_version="policy-v1",
        model_versions=sorted({future.model_version for future in futures}),
        created_at=datetime.now(timezone.utc),
    )
