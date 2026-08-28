from __future__ import annotations

from typing import Any

from recourse.domain.models import Action

ACTIONS = [action.value for action in Action]
FEATURE_COLUMNS = [
    "amount_subunits", "method", "attempt_count", "hour", "day_of_week", "failure_code",
    "failure_source", "failure_step", "failure_reason", "merchant_category", "recovery_bucket",
    "configured_methods", "prior_failures", "prior_recoveries", "contacts_7d", "opt_out",
    "contact_consent", "checkout_duration_bucket", "method_switches", "last_interaction_age_bucket",
    "friction_signal", "network_degradation", "issuer_response_family", "evidence_completeness",
    "conflicting_signal", "alternate_method_available", "retry_eligible", "link_eligible", "nudge_eligible",
]
NUMERIC_FEATURES = [
    "amount_subunits", "attempt_count", "hour", "day_of_week", "prior_failures", "prior_recoveries",
    "contacts_7d", "method_switches", "evidence_completeness",
]
CATEGORICAL_FEATURES = [name for name in FEATURE_COLUMNS if name not in NUMERIC_FEATURES]


def action_costs(context: dict[str, Any]) -> tuple[dict[str, int], dict[str, int]]:
    direct = {
        Action.NO_ACTION.value: 0,
        Action.RETRY_LATER.value: 600,
        Action.STANDARD_PAYMENT_LINK.value: 3800,
        Action.ONE_BOUNDED_NUDGE.value: 1600,
    }
    downstream = {
        Action.NO_ACTION.value: 0,
        Action.RETRY_LATER.value: 700 if context["attempt_count"] else 300,
        Action.STANDARD_PAYMENT_LINK.value: 0,
        Action.ONE_BOUNDED_NUDGE.value: 2500 + context["contacts_7d"] * 2200,
    }
    return direct, downstream

