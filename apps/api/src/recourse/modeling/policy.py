from __future__ import annotations

from recourse.domain.models import Action
from recourse.domain.value import conservative_value, incremental_value
from recourse.modeling.artifacts import ModelRegistry
from recourse.modeling.features import ACTIONS, action_costs

MIN_EVIDENCE_QUALITY = .70
MIN_CONSERVATIVE_INV = 1000
MAX_INTERVAL_WIDTH = .35
TIE_BAND = 500
BURDEN = {action: index for index, action in enumerate(ACTIONS)}


def _eligible(context: dict, action: str) -> bool:
    if action == Action.NO_ACTION.value:
        return True
    if action == Action.RETRY_LATER.value:
        return bool(context["retry_eligible"])
    if action == Action.STANDARD_PAYMENT_LINK.value:
        return bool(context["link_eligible"])
    return bool(context["nudge_eligible"] and context["contact_consent"] and not context["opt_out"] and context["contacts_7d"] < 2)


def estimate_and_select(context: dict, registry: ModelRegistry) -> dict:
    predictions = registry.predict_all(context)
    direct, downstream = action_costs(context)
    baseline_point, baseline_lower, baseline_upper = predictions[Action.NO_ACTION.value]
    estimates = {}
    for action in ACTIONS:
        point, lower, upper = predictions[action]
        if action == Action.NO_ACTION.value:
            expected, conservative, uplift, uplift_lower = 0, 0, 0.0, 0.0
        else:
            uplift = point - baseline_point
            uplift_lower = lower - baseline_upper
            expected = incremental_value(
                amount_subunits=context["amount_subunits"], action_probability=point,
                no_action_probability=baseline_point, direct_cost_subunits=direct[action],
                downstream_cost_subunits=downstream[action],
            )
            conservative = conservative_value(
                amount_subunits=context["amount_subunits"], uplift_lower=uplift_lower,
                direct_cost_subunits=direct[action], downstream_cost_subunits=downstream[action],
            )
        estimates[action] = {
            "success_probability": round(point, 10), "probability_lower": round(lower, 10),
            "probability_upper": round(upper, 10), "no_action_probability": round(baseline_point, 10),
            "uplift": round(uplift, 10), "uplift_lower": round(uplift_lower, 10),
            "direct_cost_subunits": direct[action], "downstream_cost_subunits": downstream[action],
            "expected_inv_subunits": expected, "conservative_inv_subunits": conservative,
        }
    if context["evidence_completeness"] < MIN_EVIDENCE_QUALITY or context["conflicting_signal"]:
        return {"selected_action": Action.NO_ACTION.value, "status": "HUMAN_REVIEW", "estimates": estimates}
    feasible = [action for action in ACTIONS if _eligible(context, action)]
    best_value = max(estimates[action]["conservative_inv_subunits"] for action in feasible)
    tied = [action for action in feasible if best_value - estimates[action]["conservative_inv_subunits"] < TIE_BAND]
    selected = min(tied, key=BURDEN.get)
    if estimates[selected]["conservative_inv_subunits"] <= MIN_CONSERVATIVE_INV:
        return {"selected_action": Action.NO_ACTION.value, "status": "NO_ACTION", "estimates": estimates}
    point, lower, upper = predictions[selected]
    if upper - lower > MAX_INTERVAL_WIDTH:
        return {"selected_action": Action.NO_ACTION.value, "status": "HUMAN_REVIEW", "estimates": estimates}
    return {"selected_action": selected, "status": "ACTION_READY", "estimates": estimates}
