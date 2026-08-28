from __future__ import annotations

from recourse.domain.models import Action
from recourse.modeling.artifacts import ModelRegistry
from recourse.modeling.features import ACTIONS


def rules_baseline(context: dict) -> dict:
    if context["retry_eligible"] and context["failure_reason"] in {"incorrect_otp", "payment_timed_out"}:
        selected = Action.RETRY_LATER.value
    elif context["link_eligible"] and context["amount_subunits"] >= 25_000:
        selected = Action.STANDARD_PAYMENT_LINK.value
    else:
        selected = Action.NO_ACTION.value
    return {"selected_action": selected, "status": "ACTION_READY" if selected != Action.NO_ACTION.value else "NO_ACTION", "predictions": None}


def single_model_baseline(context: dict, registry: ModelRegistry) -> dict:
    predictions = registry.predict_single_all(context)
    eligible = [Action.NO_ACTION.value]
    if context["retry_eligible"]:
        eligible.append(Action.RETRY_LATER.value)
    if context["link_eligible"]:
        eligible.append(Action.STANDARD_PAYMENT_LINK.value)
    if context["nudge_eligible"] and context["contact_consent"] and not context["opt_out"]:
        eligible.append(Action.ONE_BOUNDED_NUDGE.value)
    selected = max(eligible, key=lambda action: (predictions[action], -ACTIONS.index(action)))
    return {"selected_action": selected, "status": "ACTION_READY" if selected != Action.NO_ACTION.value else "NO_ACTION", "predictions": predictions}
