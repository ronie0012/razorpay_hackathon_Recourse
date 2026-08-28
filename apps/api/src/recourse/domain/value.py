from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN

from recourse.domain.models import Action, FutureEstimate


ROUNDING_METHOD = "ROUND_HALF_EVEN"


def probability(value: float | Decimal) -> Decimal:
    result = Decimal(str(value))
    if result < 0 or result > 1:
        raise ValueError("probability must be between 0 and 1")
    return result


def rounded_subunits(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


def incremental_value(
    *, amount_subunits: int, action_probability: float, no_action_probability: float,
    direct_cost_subunits: int, downstream_cost_subunits: int,
) -> int:
    uplift = max(Decimal("-1"), min(Decimal("1"), probability(action_probability) - probability(no_action_probability)))
    return rounded_subunits(uplift * amount_subunits - direct_cost_subunits - downstream_cost_subunits)


def conservative_value(
    *, amount_subunits: int, uplift_lower: float,
    direct_cost_subunits: int, downstream_cost_subunits: int,
) -> int:
    uplift = max(Decimal("-1"), min(Decimal("1"), Decimal(str(uplift_lower))))
    return rounded_subunits(uplift * amount_subunits - direct_cost_subunits - downstream_cost_subunits)


@dataclass(frozen=True)
class Placeholder:
    point: float
    lower: float
    upper: float
    uplift_lower: float
    direct_cost: int
    downstream_cost: int


PLACEHOLDERS = {
    Action.NO_ACTION: Placeholder(.18, .13, .23, 0, 0, 0),
    Action.RETRY_LATER: Placeholder(.55, .45, .64, .22, 600, 800),
    Action.STANDARD_PAYMENT_LINK: Placeholder(.71, .63, .78, .42, 3800, 0),
    Action.ONE_BOUNDED_NUDGE: Placeholder(.73, .64, .80, .41, 1600, 6000),
}


def deterministic_futures(amount_subunits: int) -> list[FutureEstimate]:
    baseline = PLACEHOLDERS[Action.NO_ACTION].point
    futures: list[FutureEstimate] = []
    for action in Action:
        p = PLACEHOLDERS[action]
        expected = 0 if action is Action.NO_ACTION else incremental_value(
            amount_subunits=amount_subunits,
            action_probability=p.point,
            no_action_probability=baseline,
            direct_cost_subunits=p.direct_cost,
            downstream_cost_subunits=p.downstream_cost,
        )
        conservative = 0 if action is Action.NO_ACTION else conservative_value(
            amount_subunits=amount_subunits,
            uplift_lower=p.uplift_lower,
            direct_cost_subunits=p.direct_cost,
            downstream_cost_subunits=p.downstream_cost,
        )
        futures.append(FutureEstimate(
            action=action,
            success_probability=p.point,
            probability_lower=p.lower,
            probability_upper=p.upper,
            no_action_probability=baseline,
            uplift=0 if action is Action.NO_ACTION else p.point - baseline,
            uplift_lower=p.uplift_lower,
            direct_cost_subunits=p.direct_cost,
            downstream_cost_subunits=p.downstream_cost,
            expected_incremental_value_subunits=expected,
            conservative_incremental_value_subunits=conservative,
            model_version="deterministic-counterfactual-v1",
            calibration_version="deterministic-intervals-v1",
        ))
    return futures
